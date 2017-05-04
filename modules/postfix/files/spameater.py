#!/usr/bin/python

# http://mysql-python.sourceforge.net/MySQLdb.html
import MySQLdb

import logging
import os
import re
import subprocess
import sys
import time

# Exit codes from <sysexits.h>
EX_TEMPFAIL = 75    # Postfix places the message in the deferred mail queue and tries again later
EX_UNAVAILABLE = 69 # The mail is bounced by terminating with exit status 69

def execQuery(query):
  try:
    dbCursor.execute(query)
  except Exception as e:
    logging.critical("Exception while executing the following query: " + query)
    logging.critical(str(e))
    sys.exit(EX_TEMPFAIL)

def loopmsg(messageId, subject, finalRecipient):
  logging.info("Message-ID " + messageId + " already processed")
  execQuery("INSERT INTO `message` (messageId, subject, rcptTo, status) VALUES ('" + messageId + "', '" + subject + "', '" + finalRecipient + "', 'looped');")

def sendmsg(messageId, subject, finalRecipient, finalMail):
  logging.info("Sending Message-ID " + messageId)
  execQuery("INSERT INTO `message` (messageId, subject, rcptTo, status) VALUES ('" + messageId + "', '" + subject + "', '" + finalRecipient + "', 'sent');")
  # TODO - Hard-coding the sender is for proof of concept only. It will be removed later.
  p = subprocess.Popen(['/usr/sbin/sendmail', '-G', '-i', '-f', '<dpw2vtlkwq@erine.email>', '--', '<' + finalRecipient + '>'], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
  l = p.communicate(input=finalMail)

def dropmsg(messageId, subject, finalRecipient):
  logging.info("Dropping Message-ID " + messageId)
  execQuery("INSERT INTO `message` (messageId, subject, rcptTo, status) VALUES ('" + messageId + "', '" + subject + "', '" + finalRecipient + "', 'dropped');")

# Retrieve user email and ID
# Username column has a UNIQUE constraint. So using fetchone() is enough.
def fetchUser(username, reserved):
  execQuery("SELECT `Email`, `ID` FROM `Users` WHERE `Username` = '" + username + "' AND `Reserved` = " + str(reserved) + ";")
  return dbCursor.fetchone()

# Be sure /var/log/spameater/spameater.log exists and is accessible to spameater user
# On exception raising, do not use logging to display the error as something's wrong with it
try:
  logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO, filename="/var/log/spameater/spameater.log")
except Exception as e:
  print "CRITICAL " + str(e)
  sys.exit(EX_UNAVAILABLE)

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
if len(sys.argv) != 3:
  logger.critical(str(len(sys.argv)) + " arguments instead of 3")
  sys.exit(EX_UNAVAILABLE)
sender = sys.argv[1].lower()
recipient = sys.argv[2].lower()

# Connect to spameater database and begin a transaction
try:
  f = open('/home/spameater/.mariadb.pwd', 'r')
  password = f.readline().strip()
  f.close()
  connector = MySQLdb.connect(host = "127.0.0.1", connect_timeout = 2, user = "spameater", passwd=password, db="spameater")
  dbCursor = connector.cursor()
  execQuery("BEGIN;")
except Exception as e:
  logging.critical(str(e))
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
      sys.exit(EX_UNAVAILABLE)
  else:
    logging.critical("Incorrect recipient: " + recipient)
    sys.exit(EX_UNAVAILABLE)
userID = finalRecipient[1]
finalRecipient = finalRecipient[0]

# Forge finalMail, messageId and subject
try:
  finalMail = ""
  messageId = ""
  subject = ""
  for line in originalMail:
    r = re.match("From:\s(.+)$", line, re.IGNORECASE)
    if r:
      if not re.match(".*<" + sender + ">$", r.group(1), re.IGNORECASE):
        logging.warning("From (" + r.group(1) + ") is different than sender (" + sender + ")")
      # TODO - Hard-coding the "From" field is for proof of concept only. It will be removed later.
      finalMail += "From: <dpw2vtlkwq@erine.email>\n"
      continue
    r = re.match("Return-Path:\s(.+)$", line, re.IGNORECASE)
    if r:
      if r.group(1).lower() != "<" + sender + ">":
        logging.warning("Return-Path (" + r.group(1) + ") is different than sender (" + sender + ")")
      # TODO - Hard-coding the "Return-Path" field is for proof of concept only. It will be removed later.
      finalMail += "Return-Path: <dpw2vtlkwq@erine.email>\n"
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
    sys.exit(EX_UNAVAILABLE)
  if not subject:
    logging.warning("Subject not found")
except Exception as e:
  logging.critical(str(e))
  sys.exit(EX_UNAVAILABLE)

# Exit if message already processed
execQuery("SELECT `id` FROM `message` WHERE `messageId` = '" + messageId + "';")
if dbCursor.fetchone():
  loopmsg(messageId, subject, finalRecipient)
  dbCursor.close()
  sys.exit(EX_UNAVAILABLE)

# Create or update disposable mail address in DB. Call sendmsg() or dropmsg().
# mailAddress column has a UNIQUE constraint. So using fetchone() is enough.
execQuery("SELECT `enabled` FROM `disposableMailAddress` WHERE mailAddress = '" + recipient + "';")
enabled = dbCursor.fetchone()
if not enabled:

  # The disposable mail address is used for the first time
  execQuery("INSERT INTO `disposableMailAddress` (mailAddress, userID, forwarded) VALUES ('" + recipient + "', " + str(userID) + ", 1);")
  sendmsg(messageId, subject, finalRecipient, finalMail)

else:
  if enabled[0] == 1:

    # The disposable mail address is enabled
    execQuery("UPDATE `disposableMailAddress` SET `forwarded` = `forwarded` + 1 WHERE `mailAddress` = '" + recipient + "';")
    sendmsg(messageId, subject, finalRecipient, finalMail)

  else:

    # The disposable mail address is disabled
    execQuery("UPDATE `disposableMailAddress` SET `dropped` = `dropped` + 1 WHERE `mailAddress` = '" + recipient + "';")
    dropmsg(messageId, subject, finalRecipient)

# Terminate transaction and close connection to spameater database
execQuery("COMMIT;")
dbCursor.close()
