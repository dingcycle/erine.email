#!/usr/bin/python

# http://mysql-python.sourceforge.net/MySQLdb.html
import MySQLdb

import logging
import os
import re
import subprocess
import sys

# Be sure /var/log/spameater/spameater.log exists and is accessible to spameater user
# On exception raising, do not use logging to display the error as something's wrong with it
try:
  logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO, filename="/var/log/spameater/spameater.log")
except Exception as e:
  print "CRITICAL " + str(e)
  sys.exit(1)

# Postfix feeds this script using a pipe, what means the e-mail is sent on stdin
# If the script had been launched manually, do not use logging to display the error
if os.isatty(sys.stdin.fileno()):
  print "CRITICAL Do not run this command by hand"
  sys.exit(1)
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
  sys.exit(1)
sender = sys.argv[1]
recipient = sys.argv[2]

# Connect to spameater database
try:
  f = open('/home/spameater/.mariadb.pwd', 'r')
  password = f.readline().strip()
  f.close()
  connector = MySQLdb.connect(host = "127.0.0.1", connect_timeout = 2, user = "spameater", passwd=password, db="spameater")
  dbCursor = connector.cursor()
except Exception as e:
  logging.critical(str(e))
  sys.exit(1)

# Forge finalRecipient or exit if incorrect
# name column has a UNIQUE constraint. So using fetchone() is enough.
# TODO - Hard-coding the domain name is for proof of concept only. It will be removed later.
r = re.match("([^@]+)\.([^@\.]+)@([^@]+)$", recipient)
if not r:
  logging.critical("Incorrect recipient: " + recipient)
  sys.exit(0)
if r.group(3) != "erine.email":
  logging.critical("Incorrect domain name: " + r.group(3))
  sys.exit(0)
dbCursor.execute("SELECT Email FROM Users WHERE Username = '" + r.group(2) + "';")
finalRecipient = dbCursor.fetchone()
if not finalRecipient:
  logging.critical("Incorrect user name: " + r.group(2))
  sys.exit(0)
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
      if r.group(1) != "<" + sender + ">":
        logging.warning("Return-Path (" + r.group(1) + ") is different than sender (" + sender + ")")
      # TODO - Hard-coding the "Return-Path" field is for proof of concept only. It will be removed later.
      finalMail += "Return-Path: <dpw2vtlkwq@erine.email>\n"
      continue
    r = re.match("(\s+for\s+)(.+);(.+)$", line, re.IGNORECASE)
    if r:
      if r.group(2) != "<" + recipient + ">":
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
  logging.info(finalMail)
  if not messageId:
    logging.critical("Message-ID not found")
    sys.exit(1)
  if not subject:
    logging.warning("Subject not found")
except Exception as e:
  logging.critical(str(e))
  sys.exit(1)

dbCursor.execute("SELECT id FROM message WHERE messageId = '" + messageId + "';")
if not dbCursor.fetchone():
  logging.info("Processing Message-ID " + messageId)
  dbCursor.execute("INSERT INTO message (messageId, subject, rcptTo) values ('" + messageId + "', '" + subject + "', '" + finalRecipient + "'); COMMIT;")
  dbCursor.close()
  # TODO - Hard-coding the sender is for proof of concept only. It will be removed later.
  p = subprocess.Popen(['/usr/sbin/sendmail', '-G', '-i', '-f', '<dpw2vtlkwq@erine.email>', '--', '<' + finalRecipient + '>'], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
  l = p.communicate(input=finalMail)
else:
  logging.info("Message-ID " + messageId + " already processed")
  dbCursor.close()
  sys.exit(0)
