#!/usr/bin/python

# Copyright (C) 2017 Mikael Davranche

# This file is part of erine.email project. https://erine.email

# erine.email is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with erine.mail.  If not, see <http://www.gnu.org/licenses/>.

import MySQLdb

import configparser
import email.utils
import logging
import os
import random
import re
import string
import subprocess
import sys
import traceback

# Exit codes from <sysexits.h>
EX_TEMPFAIL = 75    # Postfix places the message in the deferred mail queue and tries again later
EX_UNAVAILABLE = 69 # The mail is bounced by terminating with exit status 69

# What kind of email is being parsed
# Refers to scenario explained below
CLASSIC = "CLASSIC"
RESERVED = "RESERVED"
REPLY = "REPLY"
FIRST_SHOT = "FIRST_SHOT"

# Regular expression that email addresses must match
# You HAVE to prefix this regex by ^ and suffix it by $ to match an email address exactly
emailAddressRegex = '[_a-z0-9-\+]+(\.[_a-z0-9-\+]+)*@[a-z0-9-]+(\.[a-z0-9-]+)*(\.[a-z]{2,})'

"""
                 +----------------+
                 |                |
                 |    SpamEater   |
      +--------> |    engine      +-------+
      |          |                |       |
      |          +----------------+       |
      |                                   |
      |                                   |
      |                                   |
      +                                   v
original mail                     rewritten mail, by spameater
  (incoming)                         (outgoing)


List of possible scenari for the spameater script:
+-------------------+------------------------------------------------------+-----------------------------------------+
| Name              | Scenario 1: "classic"                                | Scenario 2: "reserved"                  |
+-------------------+------------------------------------------------------+-----------------------------------------+
| Description       | a foreign address writes to                          | a foreign address writes to a           |
|                   | a spameater _classic_ user (e.g. joe)                | a spameater _reserved_ user (e.g. john) |
| original "From:"  | <billing@company-brand-55.com>                       | <billing@company-brand-55.com>          |
| original "To:"    | Joe <brand55.joe@erine.email>                        | John <john@erine.email>                 |
| spameater "From:" | a-4r4nd0m-57r1n6@erine.email                         | a-4r4nd0m-57r1n6@erine.email            |
| spameater "To:"   | joe@example.org                                      | john@example.org                        |
+-------------------+------------------------------------------------------+-----------------------------------------+

+-------------------+------------------------------------------------------+---------------------------------------------------------+
| Name              | Scenario 3: "reply"                                  | Scenario 4: "first_shot"                                |
+-------------------+------------------------------------------------------+---------------------------------------------------------+
| Description       | a spameater user (e.g. jack)                         | a spameater user (judy) wants to initiate a contact     |
|                   | answers an email originally sent from a foreign user | to a foreign address (billing@company-brand-55.com)     |
| original "From:"  | <jack@example.org>                                   | <judy@example.org>                                      |
| original "To:"    | Billing - billing@company-brand-55.com               | <brand55.judy.billing_company-brand-55.com@erine.email> |
|                   | <4n07h3r-r4nd0m-57r1n6@erine.email>                  |                                                         |
| spameater "From:" | brand55.jack@erine.email                             | brand55.judy@erine.email                                |
| spameater "To:"   | joe@example.org                                      | billing@company-brand-55.com                            |
+-------------------+------------------------------------------------------+---------------------------------------------------------+

For scenario 4, note that the '@' from the original recipient is substituted by an underscore (_).
"""

class BounceException(Exception):
     pass

class DeferException(Exception):
     pass

# Execute a SQL query
# Defer email on problem executing the query
def execQuery(query, *params):
  try:
    dbCursor.execute(query, params)
  except Exception as e:
    raise DeferException("While executing the following query: {}\nWith the following parameters: {}\nThe following exception raised: {}".format(query, ', '.join(params), str(e)))

# Extract email address from a complete address
# Bounce email on invalid fullAddress
def getAddress(fullAddress):
  emailAddress = email.utils.parseaddr(fullAddress)
  if not emailAddress[1]:
    raise BounceException('Invalid email address: "{}"'.format(fullAddress))
  return emailAddress[1]

# Extract email label from a complete address
# Bounce email on invalid fullAddress
def getLabel(fullAddress):
  emailAddress = email.utils.parseaddr(fullAddress)
  if not emailAddress[1]:
    raise BounceException('Invalid email address: "{}"'.format(fullAddress))
  return emailAddress[0]


# erine.email user is answering to a foreign address (ee2f as Erine.Email To Foreign)
# Extract xxx email label from a complete address like
# "xxx - x@x.x <random@erine.email>" or "x@x.x <random@erine.email>"
# Bounce email on invalid fullAddress
def ee2f_getLabel(fullAddress):
  name = getLabel(fullAddress)
  r = re.match("(.+) - " + emailAddressRegex + "$", name)
  if r:
    return r.group(1)
  r = re.match(emailAddressRegex + "$", name)
  if r:
    return ""
  return name

# erine.email user is answering a foreign address (ee2f as Erine.Email To Foreign)
# Retrieve reply email address from replyAddress table
# Bounce email if fromAddress is not allowed to send an email as the associated
# disposable mail address
def ee2f_getReplyAddress(fromAddress, toAddress):
  execQuery("SELECT `disposableMailAddress` FROM `replyAddress` WHERE `mailAddress` = %s", getAddress(toAddress))
  replyAddress = dbCursor.fetchone()
  if replyAddress:
    execQuery("SELECT `user`.`mailAddress` FROM `user` JOIN `disposableMailAddress` ON `user`.`ID` = `disposableMailAddress`.`userID` WHERE `disposableMailAddress`.`mailAddress` = %s", replyAddress[0])
    allowedEmail = dbCursor.fetchone()
    if not allowedEmail:
      logging.critical("Can not check if " + getAddress(fromAddress) + " is allowed to send an email as " + replyAddress[0] + ". Assuming yes.")
    else:
      if allowedEmail[0] != getAddress(fromAddress):
        raise BounceException('"{}" is not allowed to send an email as "{}"').format(
          getAddress(fromAddress), replyAddress[0]
        )
    label = getLabel(fromAddress)
    if label:
      return label + " <" + replyAddress[0] + ">"
    else:
      return replyAddress[0]
  else:
    raise BounceException('Invalid email address: "{}"'.format(toAddress))

# A foreign address is writing to an erine.email user (f2ee as Foreign To Erine.Email)
# Forge or retrieve reply email address
# Bounce email on invalid toAddress
def f2ee_getReplyAddress(fromAddress, toAddress):
  execQuery("SELECT `mailAddress` FROM `replyAddress` WHERE `disposableMailAddress` = %s AND `foreignAddress` = %s", getAddress(toAddress), getAddress(fromAddress))
  replyAddress = dbCursor.fetchone()
  if replyAddress:

    # fromAddress already sent an email to toAddress
    replyAddress = replyAddress[0]

  else:

    # The local is a random string
    replyAddress = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(15))

    # Add the destination address domain
    r = re.match(".+(@[^@]+)$", toAddress)
    if not r:
      raise BounceException('Invalid email address: "{}"'.format(toAddress))
    replyAddress += r.group(1)

  # Add the label and return the result
  replyAddress = getAddress(fromAddress) + " <" + replyAddress + ">"
  label = getLabel(fromAddress)
  if label:
    replyAddress = label + " - " + replyAddress
  return replyAddress

# Forge or retrieve reply email address
def getReplyAddress(fromAddress, toAddress, mailType):
  logging.debug("I will get a reply address from {} to {} (mailType = {})".format(fromAddress, toAddress, mailType))
  if mailType == REPLY:
    return ee2f_getReplyAddress(fromAddress, toAddress)
  else:
    return f2ee_getReplyAddress(fromAddress, toAddress)

def saveReplyAddress(mailAddress, disposableMailAddress, foreignAddress):
  execQuery("INSERT IGNORE INTO `replyAddress` (`mailAddress`, `disposableMailAddress`, `foreignAddress`) VALUES (%s, %s, %s)", mailAddress, disposableMailAddress, foreignAddress)

def loopmsg(messageId, disposableMailAddress, subject, finalRecipient, originalFromAddress):
  logging.info("Message-ID " + messageId + " already processed")
  execQuery("INSERT INTO `message` (`messageId`, `disposableMailAddress`, `subject`, `from`, `rcptTo`, `status`) VALUES (%s, %s, %s, %s, %s, %s)", messageId, disposableMailAddress, subject, originalFromAddress, finalRecipient, 'looped')

def sendmsg(messageId, disposableMailAddress, subject, finalRecipient, finalMail, finalMailFrom, mailType, originalFromAddress):
  logging.info("[{}] Sending Message-ID {}".format(mailType,  messageId))

  if mailType in [REPLY, FIRST_SHOT]:
    sendingType = 'sentAs'
  else:
    sendingType = 'sent'

  execQuery(
      "INSERT INTO `message` (`messageId`, `disposableMailAddress`, `subject`, `from`, `rcptTo`, `status`) VALUES (%s, %s, %s, %s, %s, %s)",
      messageId, disposableMailAddress, subject, originalFromAddress, finalRecipient, sendingType
  )

  try:
    p = subprocess.Popen(['/usr/sbin/sendmail', '-G', '-i', '-f', finalMailFrom, '--', '<' + finalRecipient + '>'], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    l = p.communicate(input=finalMail)
  except Exception as e:
    raise DeferException("Exception while launching sendmail: " + str(e))
  if p.returncode != 0:
    raise DeferException("Sendmail returned the following return code: " + str(p.returncode))

def dropmsg(messageId, disposableMailAddress, subject, finalRecipient, originalFromAddress):
  logging.info("Dropping Message-ID " + messageId)
  execQuery("INSERT INTO `message` (`messageId`, `disposableMailAddress`, `subject`, `from`, `rcptTo`, `status`) VALUES (%s, %s, %s, %s, %s, %s)", messageId, disposableMailAddress, subject, originalFromAddress, finalRecipient, 'dropped')

# Retrieve user email and ID
# username column has a UNIQUE constraint, so using fetchone() is enough
def fetchUser(username, reserved):
  execQuery("SELECT `mailAddress`, `ID` FROM `user` WHERE `username` = %s AND `reserved` = %s", username, str(reserved))
  return dbCursor.fetchone()

# Retrieve destination complete address from reply addresses
# foreignAddress column has a UNIQUE constraint, so using fetchone() is enough
def getToFromReplyAddresses(email):
  execQuery("SELECT `foreignAddress` FROM `replyAddress` WHERE `mailAddress` = %s", getAddress(email))
  toAddress = dbCursor.fetchone()
  if toAddress:
    label = getLabel(email)
    if label:
      return label + " <" + toAddress[0] + ">"
    else:
      return toAddress[0]
  else:
    raise BounceException('Not a reply address or reserved user address: "{}"'.format(email))

def main():

  # Be sure /var/log/spameater/spameater.log exists and is accessible to spameater user
  # On exception raising, do not use logging to display the error as something's wrong with it
  logging.basicConfig(format='%(asctime)s %(levelname)8s[%(lineno)4d] %(message)s', level=logging.INFO, filename="/var/log/spameater/spameater.log")

  # Postfix feeds this script using a pipe, what means the e-mail is sent on stdin
  # If the script had been launched manually, do not use logging to display the error
  if os.isatty(sys.stdin.fileno()):
    print "CRITICAL Do not run this command by hand"
    sys.exit(EX_UNAVAILABLE)
  originalMail = sys.stdin.readlines()

  # spameater is called by Postfix using arguments:
  #
  #filter    unix  -       n       n       -       10      pipe
  #    flags=Rq user=spameater null_sender=
  #    argv=/usr/lib/postfix/spameater ${sender} ${recipient}
  #
  # Those arguments are used to rewrite the e-mail and to call sendmail
  #
  # ${sender} and ${recipient} are just the email addresses. They do NOT include
  # the email label nor the <> characters (the format is NOT
  # "Plops <xxx@yyy.zzz>" nor "<xxx@yyy.zzz>" but "xxx@yyy.zzz").
  if len(sys.argv) != 3:
    logging.critical(str(len(sys.argv)) + " arguments instead of 3")
    logging.critical("Bouncing email")
    sys.exit(EX_UNAVAILABLE)
  sender = sys.argv[1].lower()
  recipient = sys.argv[2].lower()

  # Retrieve DBMS configuration
  try:
    config = configparser.RawConfigParser()
    config.read_file(open('/etc/erine-email.conf'))
    host = config.get('dbms', 'host', fallback='localhost')
    port = int(config.get('dbms', 'port', fallback=3306))
    database = config.get('dbms', 'database', fallback='spameater')
  except Exception as e:
    logging.warning('Problem retrieving DBMS configuration. Falling back to spameater database on localhost:3306.')
    host = 'localhost'
    port = 3306
    database = 'spameater'

  # Connect to the database and begin a transaction
  try:

    f = open('/home/spameater/.mariadb.pwd', 'r')
    password = f.readline().strip()
    f.close()
    connector = MySQLdb.connect(host=host, port=port, connect_timeout=2, user="spameater", passwd=password, db=database)
    global dbCursor
    dbCursor = connector.cursor()
    execQuery("BEGIN;")
  except Exception as e:
    raise DeferException("Exception while connecting to DB: " + str(e))

  # Set finalRecipient, userID and mailType from recipient, or exit if incorrect
  mailType = CLASSIC # Default: a foreign address is writing to an erine.email user
  userID = None
  finalRecipient = None
  finalSender = None
  classicMatch = re.match("([^@\.]+)\.([^@\.]+)@([^@]+)$", recipient)
  reservedMatch = re.match("([^@\.]+)@([^@]+)$", recipient)
  firstShotMatch = re.match("(?P<disposableTarget>[^@\.]+)\.(?P<user>[^@\.]+)\.(?P<targetLocal>[^@]+)_(?P<targetDomain>[^@]+)@(?P<ee_domain>[^@]+)$", recipient)

  if classicMatch:
    # recipient looks like a classic spameater address: <something.user@domain>

    logging.debug("Recipient looks like a classic spameater address: {}".format(recipient))
    mailType = CLASSIC

    finalRecipient = fetchUser(classicMatch.group(2), 0)
    if not finalRecipient:
      if fetchUser(classicMatch.group(2), 1):
        errorMsg = "Incorrect user usage: " + classicMatch.group(2) + " exists, but as a reserved user"
      else:
        errorMsg = "Incorrect user name: " + classicMatch.group(2)
      raise BounceException(errorMsg)

  elif reservedMatch:
    # recipient looks like a reserved user address <user@domain> or a reply address

    logging.debug("Recipient looks like a reserved user or reply address: {}".format(recipient))
    mailType = RESERVED

    r = re.match("([^@\.]+)@([^@]+)$", recipient)
    if r:
      finalRecipient = fetchUser(r.group(1), 1)
      if not finalRecipient:
        if fetchUser(r.group(1), 0):
          logging.critical("Incorrect user usage: " + r.group(1) + " exists, but as a not reserved user")
        else:
          ## a reserved user email has the same format than a reply address
          finalRecipient = getToFromReplyAddresses(recipient)
          mailType = REPLY # An erine.email user is answering to a foreign address
    else:
      raise BounceException('Incorrect recipient: {}'.format(recipient))

  elif firstShotMatch:
    # recipient looks like a first shot relay address: <something.user.somecompany_somedomain.com@domain>

    logging.debug("Recipient looks like a first shot relay address: {}".format(recipient))
    mailType = FIRST_SHOT

    firstShotDict = firstShotMatch.groupdict()
    user = firstShotDict['user']
    userInfo = fetchUser(user, 0)

    if not userInfo:
      if fetchUser(user, 1):
        raise BounceException("Incorrect user usage: " + user + " exists, but as a reserved user")
      else:
        raise BounceException("Unknown user name: " + user)
    else:
      userMail,userID = userInfo[0],userInfo[1]
      if (sender != userMail):
        raise BounceException("Incorrect sender email: " + user + "'s emails cannot be forged by " + sender)

    finalRecipient = "{m[targetLocal]}@{m[targetDomain]}".format(m=firstShotDict)
    finalSender = '{m[disposableTarget]}.{m[user]}@{m[ee_domain]}'.format(m=firstShotDict)
    logging.debug("I'll send mail as {}".format(finalSender))

  else:
    raise BounceException('Incorrect recipient: {}'.format(recipient))

  if not userID and mailType != REPLY:
    userID = finalRecipient[1]
    finalRecipient = finalRecipient[0]

  # Forge finalMail, messageId and subject
  messageId = ""
  subject = ""

  # Parse email headers
  # That's also where the rewriting happens

  finalMail = ""
  originalFromAddress = False
  finalMailFrom = False
  originalReplyToAddress = False
  finalMailReplyTo = False

  for line in originalMail:
    # FIXME should we really parse the whole body as well?
    r = re.match("From:\s(.+)$", line, re.IGNORECASE)
    if r:
      if not re.match(".*<" + sender + ">$", r.group(1), re.IGNORECASE) and sender.lower() != r.group(1).lower():
        logging.warning("From (" + r.group(1) + ") is different than sender (" + sender + ")")

      originalFromAddress = getAddress(r.group(1))
      if finalSender:
        finalMailFrom = finalSender
      else:
        finalMailFrom = getReplyAddress(r.group(1), recipient, mailType)
      finalMail += "From: " + finalMailFrom + "\n"
      continue
    r = re.match("Reply-to:\s(.+)$", line, re.IGNORECASE)
    if r:
      originalReplyToAddress = getAddress(r.group(1))
      finalMailReplyTo = getReplyAddress(r.group(1), recipient, mailType)
      finalMail += "Reply-to: " + finalMailReplyTo + "\n"
      continue
    r = re.match("(\s+for\s+)(.+);(.+)$", line, re.IGNORECASE)
    if r:
      if r.group(2).lower() != "<" + recipient + ">":
        logging.warning(line + ": for (" + r.group(2) + ") is different than recipient (" + recipient + ")")
      finalMail += r.group(1) + "<" + finalRecipient + ">" + r.group(3) + "\n"
      continue
    r = re.match("To:\s(.+)$", line, re.IGNORECASE)
    if r:
      if mailType == REPLY:
        finalMail += "To: "
        label = ee2f_getLabel(r.group(1))
        if label:
          finalMail += label + " "
        finalMail += "<" + finalRecipient + ">\n"
        continue
      elif mailType == FIRST_SHOT:
        ## rewrite the recipient
        finalMail += "To: "
        finalMail += "<" + finalRecipient + ">\n"
        continue
    r = re.match("Message-ID:\s(.+)$", line, re.IGNORECASE)
    if r:
      messageId = r.group(1)
    r = re.match("Subject:\s(.+)$", line, re.IGNORECASE)
    if r:
      subject = r.group(1)
    finalMail += line
  if not originalFromAddress:
    logging.warning("Cannot retrieve From information. Using sender (" + sender + ")")
    originalFromAddress = sender
  if not finalMailFrom:
    logging.warning("Cannot retrieve From information. Using sender (" + sender + ")")
    finalMailFrom = getReplyAddress(sender, recipient, mailType)
  if not messageId:
    raise BounceException("Message-ID not found")
  if not subject:
    logging.warning("Subject not found")

  # Exit if message already processed
  execQuery("SELECT `id` FROM `message` WHERE `messageId` = %s", messageId)
  if dbCursor.fetchone():
    loopmsg(messageId, finalMailFrom, subject, finalRecipient, originalFromAddress)
    dbCursor.close()
    raise BounceException("Bouncing email")

  if mailType == REPLY:
    execQuery("UPDATE `disposableMailAddress` SET `sentAs` = `sentAs` + 1 WHERE `mailAddress` = %s", getAddress(finalMailFrom))
    sendmsg(messageId, getAddress(finalMailFrom), subject, finalRecipient, finalMail, getAddress(finalMailFrom), mailType, originalFromAddress)
  elif mailType in [CLASSIC, RESERVED]:
    # Create or update disposable mail address in DB. Call sendmsg() or dropmsg().
    # mailAddress column has a UNIQUE constraint. So using fetchone() is enough.
    execQuery("SELECT `enabled` FROM `disposableMailAddress` WHERE `mailAddress` = %s", recipient)
    disposableMailAddress = dbCursor.fetchone()
    if not disposableMailAddress:
      logging.debug('The disposable address is used for the first time')

      # The disposable mail address is used for the first time
      execQuery("INSERT INTO `disposableMailAddress` (`mailAddress`, `userID`, `sent`) VALUES (%s, %s, %s)", recipient, str(userID), 1);
      saveReplyAddress(getAddress(finalMailFrom), recipient, originalFromAddress)
      if finalMailReplyTo:
        saveReplyAddress(getAddress(finalMailReplyTo), recipient, originalReplyToAddress)
      execQuery("SELECT `mailAddress` FROM `disposableMailAddress` WHERE `mailAddress` = %s", recipient)
      disposableMailAddress = dbCursor.fetchone()
      sendmsg(messageId, disposableMailAddress[0], subject, finalRecipient, finalMail, getAddress(finalMailFrom), mailType, originalFromAddress)

    else:
      # The disposable address has already been created
      if disposableMailAddress[0] == 1:
        # The disposable mail address is enabled
        execQuery("UPDATE `disposableMailAddress` SET `sent` = `sent` + 1 WHERE `mailAddress` = %s", recipient)
        saveReplyAddress(getAddress(finalMailFrom), recipient, originalFromAddress)
        if finalMailReplyTo:
          saveReplyAddress(getAddress(finalMailReplyTo), recipient, originalReplyToAddress)
        sendmsg(messageId, recipient, subject, finalRecipient, finalMail, getAddress(finalMailFrom), mailType, originalFromAddress)

      else:
        # The disposable mail address is disabled
        execQuery("UPDATE `disposableMailAddress` SET `dropped` = `dropped` + 1 WHERE `mailAddress` = %s", recipient)
        dropmsg(messageId, recipient, subject, finalRecipient, originalFromAddress)
  elif mailType == FIRST_SHOT:
    execQuery("SELECT `mailAddress` FROM `disposableMailAddress` WHERE `mailAddress` = %s", finalSender)
    disposableMailAddress = dbCursor.fetchone()
    if not disposableMailAddress:
      logging.debug('The disposable address is used for the first time')

      # The disposable mail address is used for the first time
      execQuery("INSERT INTO `disposableMailAddress` (`mailAddress`, `userID`, `sentAs`) VALUES (%s, %s, %s)", finalSender, str(userID), 1);
      sendmsg(messageId, finalSender, subject, finalRecipient, finalMail, getAddress(finalMailFrom), mailType, originalFromAddress)

    else:
      # The disposable address has already been created
      execQuery("UPDATE `disposableMailAddress` SET `sentAs` = `sentAs` + 1 WHERE `mailAddress` = %s", finalSender)
      sendmsg(messageId, finalSender, subject, finalRecipient, finalMail, getAddress(finalMailFrom), mailType, originalFromAddress)

  # Terminate transaction and close connection to the database
  execQuery("COMMIT;")
  dbCursor.close()

if __name__ == '__main__':
  try:
    main()
  except BounceException as e:
    info = sys.exc_info()
    extract = traceback.extract_tb(info[2])[-1][1:3]
    (lineno, function) = extract
    logging.critical("Bouncing email (reason = '{}', from {}, line {})".format(str(e.message), function, lineno))
    sys.exit(EX_UNAVAILABLE)
  except DeferException as e:
    info = sys.exc_info()
    extract = traceback.extract_tb(info[2])[-1][1:3]
    (lineno, function) = extract
    logging.critical("Deferring email (reason = '{}', from {}, line {})".format(str(e.message), function, lineno))
    sys.exit(EX_TEMPFAIL)
  except Exception as e:
    logging.exception(e)
    logging.critical("Deferring email")
    sys.exit(EX_TEMPFAIL)
