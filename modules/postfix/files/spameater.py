#!/usr/bin/python

# http://mysql-python.sourceforge.net/MySQLdb.html
import MySQLdb

import logging
import os
import random
import re
import string
import subprocess
import sys
import time

# Exit codes from <sysexits.h>
EX_TEMPFAIL = 75    # Postfix places the message in the deferred mail queue and tries again later
EX_UNAVAILABLE = 69 # The mail is bounced by terminating with exit status 69

# Regular expression that email addresses must match
# You HAVE to prefix this regex by ^ and suffix it by $ to match an email address exactly
emailAddressRegex = '[_a-z0-9-]+(\.[_a-z0-9-]+)*@[a-z0-9-]+(\.[a-z0-9-]+)*(\.[a-z]{2,})'

def execQuery(query):
  try:
    dbCursor.execute(query)
  except Exception as e:
    logging.critical("Exception while executing the following query: " + query)
    logging.critical(str(e))
    logging.critical("Deferring email")
    sys.exit(EX_TEMPFAIL)

# Extract email address from a complete address
def getAddress(fullAddress):
  r = re.match(".*<(" + emailAddressRegex + ")>$", fullAddress)
  if r:
    return r.group(1)
  r = re.match("(" + emailAddressRegex + ")", fullAddress)
  if r:
    return r.group(1)
  logger.critical("Invalid email address: \"" + fullAddress + "\"")
  logging.critical("Bouncing email")
  sys.exit(EX_UNAVAILABLE)

# Use source and destination email addresses to forge reply email address.
# Fill database with those informations so recipients can reply.
def getReplyAddress(fromAddress, toAddress):
  # TODO - Do the fromAddress / toAddress set exists in DB? If so, return its mailAddress field

  # The local is a random string
  replyAddress = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(15))

  # Add the destination address domain
  r = re.match(".+(@[^@]+)$", toAddress)
  if not r:
    logger.critical("Invalid email address: \"" + toAddress + "\"")
    logging.critical("Bouncing email")
    sys.exit(EX_UNAVAILABLE)
  replyAddress += r.group(1)

  # TODO - Insert replyAddress in database

  replyAddress = getAddress(fromAddress) + " <" + replyAddress + ">"
  r = re.match("(.+)\s*<" + emailAddressRegex + ">$", fromAddress)
  if r:
    return r.group(1) + " - " + replyAddress
  return replyAddress

def loopmsg(messageId, disposableMailAddress, subject, finalRecipient):
  logging.info("Message-ID " + messageId + " already processed")
  execQuery("INSERT INTO `message` (messageId, disposableMailAddress, subject, rcptTo, status) VALUES ('" + messageId + "', '" + disposableMailAddress + "', '" + subject + "', '" + finalRecipient + "', 'looped');")

def sendmsg(messageId, disposableMailAddress, subject, finalRecipient, finalMail, finalMailFrom):
  logging.info("Sending Message-ID " + messageId)
  execQuery("INSERT INTO `message` (messageId, disposableMailAddress, subject, rcptTo, status) VALUES ('" + messageId + "', '" + disposableMailAddress + "', '" + subject + "', '" + finalRecipient + "', 'sent');")
  try:
    p = subprocess.Popen(['/usr/sbin/sendmail', '-G', '-i', '-f', finalMailFrom, '--', '<' + finalRecipient + '>'], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    l = p.communicate(input=finalMail)
    print "aaa"
  except Exception as e:
    logging.critical("Exception while launching sendmail: " + str(e))
    logging.critical("Deferring email")
    sys.exit(EX_TEMPFAIL)

def dropmsg(messageId, disposableMailAddress, subject, finalRecipient):
  logging.info("Dropping Message-ID " + messageId)
  execQuery("INSERT INTO `message` (messageId, disposableMailAddress, subject, rcptTo, status) VALUES ('" + messageId + "', '" + disposableMailAddress + "', '" + subject + "', '" + finalRecipient + "', 'dropped');")

# Retrieve user email and ID
# Username column has a UNIQUE constraint. So using fetchone() is enough.
def fetchUser(username, reserved):
  execQuery("SELECT `Email`, `ID` FROM `Users` WHERE `Username` = '" + username + "' AND `Reserved` = " + str(reserved) + ";")
  return dbCursor.fetchone()

def main():

  # Be sure /var/log/spameater/spameater.log exists and is accessible to spameater user
  # On exception raising, do not use logging to display the error as something's wrong with it
  logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO, filename="/var/log/spameater/spameater.log")

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
    logger.critical(str(len(sys.argv)) + " arguments instead of 3")
    logging.critical("Bouncing email")
    sys.exit(EX_UNAVAILABLE)
  sender = sys.argv[1].lower()
  recipient = sys.argv[2].lower()

  # Connect to spameater database and begin a transaction
  try:
    f = open('/home/spameater/.mariadb.pwd', 'r')
    password = f.readline().strip()
    f.close()
    connector = MySQLdb.connect(host = "127.0.0.1", connect_timeout = 2, user = "spameater", passwd=password, db="spameater")
    global dbCursor
    dbCursor = connector.cursor()
    execQuery("BEGIN;")
  except Exception as e:
    logging.critical(str(e))
    logging.critical("Deferring email")
    sys.exit(EX_TEMPFAIL)

  # Forge finalRecipient or exit if incorrect
  r = re.match("([^@]+)\.([^@\.]+)@([^@]+)$", recipient)
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
          logging.critical("Incorrect user name: " + r.group(1))
        logging.critical("Bouncing email")
        sys.exit(EX_UNAVAILABLE)
    else:
      logging.critical("Incorrect recipient: " + recipient)
      logging.critical("Bouncing email")
      sys.exit(EX_UNAVAILABLE)
  userID = finalRecipient[1]
  finalRecipient = finalRecipient[0]

  # Forge finalMail, messageId and subject
  finalMail = ""
  messageId = ""
  subject = ""
  for line in originalMail:
    r = re.match("From:\s(.+)$", line, re.IGNORECASE)
    if r:
      if not re.match(".*<" + sender + ">$", r.group(1), re.IGNORECASE) and sender.lower() != r.group(1).lower():
        logging.warning("From (" + r.group(1) + ") is different than sender (" + sender + ")")
      finalMailFrom = getReplyAddress(r.group(1), recipient)
      finalMail += "From: " + finalMailFrom + "\n"
      continue
    r = re.match("Reply-to:\s(.+)$", line, re.IGNORECASE)
    if r:
      finalMail += "Reply-to: " + getReplyAddress(r.group(1), recipient) + "\n"
      continue
    r = re.match("(\s+for\s+)(.+);(.+)$", line, re.IGNORECASE)
    if r:
      if r.group(2).lower() != "<" + recipient + ">":
        logging.warning("for (" + r.group(2) + ") is different than recipient (" + recipient + ")")
      finalMail += r.group(1) + "<" + finalRecipient + ">" + r.group(3) + "\n"
      continue
    r = re.match("Message-ID:\s(.+)$", line, re.IGNORECASE)
    if r:
      messageId = r.group(1)
    r = re.match("Subject:\s(.+)$", line, re.IGNORECASE)
    if r:
      subject = r.group(1)
    finalMail += line
  if not messageId:
    logging.critical("Message-ID not found")
    logging.critical("Bouncing email")
    sys.exit(EX_UNAVAILABLE)
  if not subject:
    logging.warning("Subject not found")

  # Exit if message already processed
  execQuery("SELECT `id` FROM `message` WHERE `messageId` = '" + messageId + "';")
  if dbCursor.fetchone():
    loopmsg(messageId, subject, finalRecipient)
    dbCursor.close()
    logging.critical("Bouncing email")
    sys.exit(EX_UNAVAILABLE)

  # Create or update disposable mail address in DB. Call sendmsg() or dropmsg().
  # mailAddress column has a UNIQUE constraint. So using fetchone() is enough.
  execQuery("SELECT `enabled`, `mailAddress` FROM `disposableMailAddress` WHERE mailAddress = '" + recipient + "';")
  disposableMailAddress = dbCursor.fetchone()
  if not disposableMailAddress:

    # The disposable mail address is used for the first time
    execQuery("INSERT INTO `disposableMailAddress` (mailAddress, userID, forwarded) VALUES ('" + recipient + "', " + str(userID) + ", 1);")
    execQuery("SELECT `mailAddress` FROM `disposableMailAddress` WHERE mailAddress = '" + recipient + "';")
    disposableMailAddress = dbCursor.fetchone()
    sendmsg(messageId, disposableMailAddress[0], subject, finalRecipient, finalMail, getAddress(finalMailFrom))

  else:
    if disposableMailAddress[0] == 1:

      # The disposable mail address is enabled
      execQuery("UPDATE `disposableMailAddress` SET `forwarded` = `forwarded` + 1 WHERE `mailAddress` = '" + recipient + "';")
      sendmsg(messageId, disposableMailAddress[1], subject, finalRecipient, finalMail, getAddress(finalMailFrom))

    else:

      # The disposable mail address is disabled
      execQuery("UPDATE `disposableMailAddress` SET `dropped` = `dropped` + 1 WHERE `mailAddress` = '" + recipient + "';")
      dropmsg(messageId, disposableMailAddress[1], subject, finalRecipient)

  # Terminate transaction and close connection to spameater database
  execQuery("COMMIT;")
  dbCursor.close()

if __name__ == '__main__':
  try:
    main()
  except Exception as e:
    logging.critical(str(e))
    logging.critical("Deferring email")
    sys.exit(EX_TEMPFAIL)
