#!/usr/bin/python

import logging
import os
import re
import subprocess
import sys

# Be sure /var/log/spameater/spameater.log exists and is accessible to spameater user
try:
  logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO, filename="/var/log/spameater/spameater.log")
except Exception as e:
  print "CRITICAL " + str(e)

# Postfix feeds this script using a pipe, what means the e-mail is sent on stdin
if os.isatty(sys.stdin.fileno()):
  print "CRITICAL Do not run this command by hand"
  sys.exit(1)
originalMail = sys.stdin.readlines()
finalMail = ""

# spameater is called by Postfix using arguments:
#
#filter    unix  -       n       n       -       10      pipe
#    flags=Rq user=spameater null_sender=
#    argv=/usr/lib/postfix/spameater -f ${sender} -- ${recipient}
#
# Those arguments are used to call sendmail
sendmailArgs = sys.argv
sendmailArgs.pop(0)

try:

  # This code bloc is for Proof Of Concept only and will be trashed late
  for line in originalMail:
    r = re.match("Subject:\s(.+)$", line)
    if r:
      finalMail += "Subject: (Redirected by erine.email) " + r.group(1) + '\n'
    else:
      finalMail += line

  p = subprocess.Popen(['/usr/sbin/sendmail', '-G', '-i'] + sendmailArgs, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
  l = p.communicate(input=finalMail)
except Exception as e:
  logging.critical(str(e))
