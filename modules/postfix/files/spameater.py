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
import logging
import os
import random
import re
import string
import subprocess
import sys
import time
import traceback

# Exit codes from <sysexits.h>
EX_TEMPFAIL = 75    # Postfix places the message in the deferred mail queue and tries again later
EX_UNAVAILABLE = 69 # The mail is bounced by terminating with exit status 69

# Regular expression that email addresses must match
# You HAVE to prefix this regex by ^ and suffix it by $ to match an email address exactly
emailAddressRegex = '[_a-z0-9-]+(\.[_a-z0-9-]+)*@[a-z0-9-]+(\.[a-z0-9-]+)*(\.[a-z]{2,})'

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
  r = re.match(".*<(" + emailAddressRegex + ")>$", fullAddress)
  if r:
    return r.group(1)
  r = re.match("(" + emailAddressRegex + ")", fullAddress)
  if r:
    return r.group(1)
  raise BounceException('Invalid email address: "{}"'.format(fullAddress))

# Extract email label from a complete address
# Bounce email on invalid fullAddress
def getLabel(fullAddress):
  r = re.match("\"(.+)\"[\s]*<" + emailAddressRegex + ">$", fullAddress)
  if r:
    return r.group(1)
  r = re.match("'(.+)'[\s]*<" + emailAddressRegex + ">$", fullAddress)
  if r:
    return r.group(1)
  r = re.match("(.*\S)[\s]*<" + emailAddressRegex + ">$", fullAddress)
  if r:
    return r.group(1)
  r = re.match("<" + emailAddressRegex + ">$", fullAddress)
  if r:
    return ""
  r = re.match(emailAddressRegex + "$", fullAddress)
  if r:
    return ""
  raise DeferException('Invalid email address: "{}"'.format(fullAddress))


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
def getReplyAddress(fromAddress, toAddress, isAReply):
  if isAReply:
    return ee2f_getReplyAddress(fromAddress, toAddress)
  return f2ee_getReplyAddress(fromAddress, toAddress)

def saveReplyAddress(mailAddress, disposableMailAddress, foreignAddress):
  execQuery("INSERT IGNORE INTO `replyAddress` (`mailAddress`, `disposableMailAddress`, `foreignAddress`) VALUES (%s, %s, %s)", mailAddress, disposableMailAddress, foreignAddress)

def loopmsg(messageId, disposableMailAddress, subject, finalRecipient, originalFromAddress):
  logging.info("Message-ID " + messageId + " already processed")
  execQuery("INSERT INTO `message` (`messageId`, `disposableMailAddress`, `subject`, `from`, `rcptTo`, `status`) VALUES (%s, %s, %s, %s, %s, %s)", messageId, disposableMailAddress, subject, originalFromAddress, finalRecipient, 'looped')

def sendmsg(messageId, disposableMailAddress, subject, finalRecipient, finalMail, finalMailFrom, isAReply, originalFromAddress):
  logging.info("Sending Message-ID " + messageId)
  execQuery("INSERT INTO `message` (`messageId`, `disposableMailAddress`, `subject`, `from`, `rcptTo`, `status`) VALUES (%s, %s, %s, %s, %s, %s)", messageId, disposableMailAddress, subject, originalFromAddress, finalRecipient, "sentAs" if isAReply else "sent")
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

  # Set finalRecipient, userID and isAReply from recipient, or exit if incorrect
  r = re.match("([^@]+)\.([^@\.]+)@([^@]+)$", recipient)
  isAReply = False # Default: a foreign address is writing to an erine.email user
  if r:
    finalRecipient = fetchUser(r.group(2), 0)
    if not finalRecipient:
      if fetchUser(r.group(2), 1):
        logging.critical("Incorrect user usage: " + r.group(2) + " exists, but as a reserved user")
      else:
        logging.critical("Incorrect user name: " + r.group(2))
      logging.critical("Bouncing email")
      sys.exit(EX_UNAVAILABLE)
  else:
    r = re.match("([^@\.]+)@([^@]+)$", recipient)
    if r:
      finalRecipient = fetchUser(r.group(1), 1)
      if not finalRecipient:
        if fetchUser(r.group(1), 0):
          logging.critical("Incorrect user usage: " + r.group(1) + " exists, but as a not reserved user")
        else:
          finalRecipient = getToFromReplyAddresses(recipient)
          isAReply = True # An erine.email user is answering to a foreign address
    else:
      raise BounceException('Incorrect recipient: {}'.format(recipient))
  if not isAReply:
    userID = finalRecipient[1]
    finalRecipient = finalRecipient[0]

  # Forge finalMail, messageId and subject
  finalMail = ""
  messageId = ""
  subject = ""
  originalFromAddress = False
  finalMailFrom = False
  originalReplyToAddress = False
  finalMailReplyTo = False
  for line in originalMail:
    r = re.match("From:\s(.+)$", line, re.IGNORECASE)
    if r:
      if not re.match(".*<" + sender + ">$", r.group(1), re.IGNORECASE) and sender.lower() != r.group(1).lower():
        logging.warning("From (" + r.group(1) + ") is different than sender (" + sender + ")")
      originalFromAddress = getAddress(r.group(1))
      finalMailFrom = getReplyAddress(r.group(1), recipient, isAReply)
      finalMail += "From: " + finalMailFrom + "\n"
      continue
    r = re.match("Reply-to:\s(.+)$", line, re.IGNORECASE)
    if r:
      originalReplyToAddress = getAddress(r.group(1))
      finalMailReplyTo = getReplyAddress(r.group(1), recipient, isAReply)
      finalMail += "Reply-to: " + finalMailReplyTo + "\n"
      continue
    r = re.match("(\s+for\s+)(.+);(.+)$", line, re.IGNORECASE)
    if r:
      if r.group(2).lower() != "<" + recipient + ">":
        logging.warning(line + ": for (" + r.group(2) + ") is different than recipient (" + recipient + ")")
      finalMail += r.group(1) + "<" + finalRecipient + ">" + r.group(3) + "\n"
      continue
    r = re.match("To:\s(.+)$", line, re.IGNORECASE)
    if r and isAReply:
      finalMail += "To: "
      label = ee2f_getLabel(r.group(1))
      if label:
        finalMail += label + " "
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
    logging.warning("Can not retrieve From information. Using sender (" + sender + ")")
    originalFromAddress = sender
  if not finalMailFrom:
    logging.warning("Can not retrieve From information. Using sender (" + sender + ")")
    finalMailFrom = getReplyAddress(sender, recipient, isAReply)
  if not messageId:
    logging.critical("Message-ID not found")
    logging.critical("Bouncing email")
    sys.exit(EX_UNAVAILABLE)
  if not subject:
    logging.warning("Subject not found")

  # Exit if message already processed
  execQuery("SELECT `id` FROM `message` WHERE `messageId` = %s", messageId)
  if dbCursor.fetchone():
    loopmsg(messageId, finalMailFrom, subject, finalRecipient, originalFromAddress)
    dbCursor.close()
    raise BounceException("Bouncing email")

  if isAReply:
    execQuery("UPDATE `disposableMailAddress` SET `sentAs` = `sentAs` + 1 WHERE `mailAddress` = %s", getAddress(finalMailFrom))
    sendmsg(messageId, getAddress(finalMailFrom), subject, finalRecipient, finalMail, getAddress(finalMailFrom), isAReply, originalFromAddress)
  else:

    # Create or update disposable mail address in DB. Call sendmsg() or dropmsg().
    # mailAddress column has a UNIQUE constraint. So using fetchone() is enough.
    execQuery("SELECT `enabled`, `mailAddress` FROM `disposableMailAddress` WHERE `mailAddress` = %s", recipient)
    disposableMailAddress = dbCursor.fetchone()
    if not disposableMailAddress:

      # The disposable mail address is used for the first time
      execQuery("INSERT INTO `disposableMailAddress` (`mailAddress`, `userID`, `sent`) VALUES (%s, %s, %s)", recipient, str(userID), 1);
      saveReplyAddress(getAddress(finalMailFrom), recipient, originalFromAddress)
      if finalMailReplyTo:
        saveReplyAddress(getAddress(finalMailReplyTo), recipient, originalReplyToAddress)
      execQuery("SELECT `mailAddress` FROM `disposableMailAddress` WHERE `mailAddress` = %s", recipient)
      disposableMailAddress = dbCursor.fetchone()
      sendmsg(messageId, disposableMailAddress[0], subject, finalRecipient, finalMail, getAddress(finalMailFrom), isAReply, originalFromAddress)

    else:
      if disposableMailAddress[0] == 1:

        # The disposable mail address is enabled
        execQuery("UPDATE `disposableMailAddress` SET `sent` = `sent` + 1 WHERE `mailAddress` = %s", recipient)
        saveReplyAddress(getAddress(finalMailFrom), recipient, originalFromAddress)
        if finalMailReplyTo:
          saveReplyAddress(getAddress(finalMailReplyTo), recipient, originalReplyToAddress)
        sendmsg(messageId, disposableMailAddress[1], subject, finalRecipient, finalMail, getAddress(finalMailFrom), isAReply, originalFromAddress)

      else:

        # The disposable mail address is disabled
        execQuery("UPDATE `disposableMailAddress` SET `dropped` = `dropped` + 1 WHERE `mailAddress` = %s", recipient)
        dropmsg(messageId, disposableMailAddress[1], subject, finalRecipient, originalFromAddress)

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
