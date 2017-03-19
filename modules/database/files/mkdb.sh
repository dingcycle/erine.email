#!/bin/bash

if [ -f /home/spameater/.mariadb.pwd -o -f /home/www-data/.mariadb.pwd ]
then
  echo "This script should be called once, by Puppet only"
  exit 1
fi

set -e

# Create the spameater user
PASSWORD=`/bin/mktemp -u XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`
echo ${PASSWORD} > /home/spameater/.mariadb.pwd
/usr/bin/mysql -p`/bin/cat /root/.mariadb.pwd` -e "CREATE USER spameater IDENTIFIED BY \"${PASSWORD}\";"

# Create the www user
PASSWORD=`/bin/mktemp -u XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`
echo ${PASSWORD} > /home/www-data/.mariadb.pwd
/usr/bin/mysql -p`/bin/cat /root/.mariadb.pwd` -e "CREATE USER www IDENTIFIED BY \"${PASSWORD}\";"

# Create the database, the tables, and grant users
/usr/bin/mysql -p`/bin/cat /root/.mariadb.pwd` < /root/mkdb.sql
