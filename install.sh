#!/bin/bash

#
# Part 1 - Check requirements
#
echo "Checking requirements..."

# Check mandatory requirement: root user
if [ ${UID} -ne 0 -o -z "${UID}" ]
then
  echo -e "[ \e[31mERROR\e[0m ] You must run this install script as root"
  exit 1
fi
echo -e "- root user: \e[32mOK\e[0m"

# Print an error message about distribution retrieval and exit 1
f_failedGetDistribution()
{
  echo -e "[ \e[31mERROR\e[0m ] Failed retrieving distribution name"
  echo "Make sure you're running this script on a Debian system"
  exit 1
}

# Check mandatory requirement: Debian system
if [ -f '/usr/bin/lsb_release' ]
then
  DISTRIBUTION=$(/usr/bin/lsb_release --id --short)
  if [ $? -ne 0 -o -z "${DISTRIBUTION}" ]
  then
    f_failedGetDistribution
  fi
else
  f_failedGetDistribution
fi
if [ "${DISTRIBUTION}" != "Debian" ]
then
  echo -e "[ \e[31mERROR\e[0m ] erine.email can't be installed in a ${DISTRIBUTION} with this install script"
  echo "Make sure you're running this script on a Debian system"
  exit 1
fi
echo -e "- Debian system: \e[32mOK\e[0m"

# Print an error message about distribution version retrieval
f_failedGetVersion()
{
  echo -e "[ \e[31mWARNING\e[0m ] Failed retrieving distribution version"
  echo "Make sure you're running this script on a Debian 9 system"
  echo -n "Press [Enter] to continue or [Ctrl]+C to cancel."
  read
}

# Check advised requirement: Debian 9 system
if [ -f '/usr/bin/lsb_release' ]
then
  VERSION=$(/usr/bin/lsb_release --release --short)
  if [ $? -ne 0 -o -z "${VERSION}" ]
  then
    f_failedGetVersion
  fi
else
  f_failedGetVersion
fi
if [ $(echo "${VERSION}" | cut -d '.' -f 1) != "9" ]
then
  echo -e "[ \e[33mWARNING\e[0m ] erine.email is probably not supported in a Debian ${VERSION}. This installation script might fail later."
  echo "Make sure you're running this script on a Debian 9 system"
  echo -n "Press [Enter] to continue or [Ctrl]+C to cancel."
  read
else
  echo -e "- Debian version: \e[32mOK\e[0m"
fi

# Check advised requirement: up-to-date packages information
if [ $(find /var/lib/apt/lists -mtime -1 2>/dev/null | wc -l) -eq 0 ]
then
  apt-get update || exit 1
fi
echo -e "- Packages information: \e[32mOK\e[0m"

#
# Part 2 - Upgrade system
#
echo

# Upgrade system
echo "erine.email should be installed on an up-to-date system."
while : ; do
  echo -n "Upgrade system? (y/n) "
 read ANSWER
 case "$ANSWER" in
   [Yy]) apt-get upgrade --yes || exit 1
         echo -e "- System upgrade: \e[32mOK\e[0m"
         break ;;
   [Nn]) echo -e "- System upgrade: \e[33mSkipped\e[0m"
         break ;;
 esac
done

#
# Part 3 - Install packages
#
echo
echo "Installing required packages..."

# Install ${1} package if needed
f_installPkg()
{
  local STATUS=$(/usr/bin/dpkg-query --show --showformat='${Status}\n' ${1} 2>/dev/null)
  if [ ${?} -ne 0 ]
  then
    echo -e "[ \e[31mERROR\e[0m ] Failed retrieving ${1} package information"
    exit 1
  fi
  if [ "${STATUS}" != "install ok installed" ]
  then
    apt install ${1} --yes || exit 1
  fi
}

for PKG in git puppetmaster puppet
do
  f_installPkg ${PKG}
  echo -e "- ${PKG}: \e[32mOK\e[0m"
done

#
# Part 4 - Retrieve or update Puppet's production environment
#
echo

# Print an error message about Puppet's production environment update and exit 1
f_failedUpdatePuppetEnv()
{
  echo -e "[ \e[31mERROR\e[0m ] Can not update Puppet's production environment"
  exit 1
}

# Update Puppet's production environment
f_updatePuppetEnv()
{
  echo "Updating Puppet's production environment..."
  git fetch --prune origin
  if [ ${?} -ne 0 ]
  then
    f_failedUpdatePuppetEnv
  fi
  TMP=$(git checkout master 2>/dev/null)
  if [ ${?} -ne 0 ]
  then
    f_failedUpdatePuppetEnv
  fi
  # Your branch is behind 'origin/master' by x commits, and can be fast-forwarded. (use "git pull" to update your local branch)
  echo ${TMP} | grep -q "Your branch is behind"
  if [ ${?} -eq 0 ]
  then
    git pull
    if [ ${?} -ne 0 ]
    then
      f_failedUpdatePuppetEnv
    fi
  else
    # Your branch is up-to-date with 'origin/master'.
    echo ${TMP} | grep -q "Your branch is up-to-date"
    if [ ${?} -ne 0 ]
    then
      f_failedUpdatePuppetEnv
    fi
  fi
}

cd /etc/puppet/ || exit 1
test -d environments || mkdir environments
cd environments || exit 1
if [ ! -d production ]
then
  echo "Retrieving Puppet's production environment..."
  git clone https://github.com/mdavranche/erine.email.git production || exit 1
  echo -e "- Puppet's production environment: \e[32mOK\e[0m"
else
  cd production || exit 1
  git remote -v | grep -q 'https://github.com/mdavranche/erine.email.git'
  if [ ${?} -ne 0 ]
  then
    echo -e "[ \e[31mERROR\e[0m ] Your Puppet's production environment looks wrong"
    exit 1
  fi
  echo "erine.email should run under an up-to-date Puppet's production environment."
  while : ; do
    echo -n "Update Puppet's production environment? (y/n) "
   read ANSWER
   case "$ANSWER" in
     [Yy]) f_updatePuppetEnv
           echo -e "- Puppet's production environment update: \e[32mOK\e[0m"
           break ;;
     [Nn]) echo -e "- Puppet's production environment update: \e[33mSkipped\e[0m"
           break ;;
   esac
  done
fi

#
# Part 5 - Set Puppet configuration
#
echo
echo "Setting Puppet configuration..."
CONFVALUE=$(puppet config print server --section main)
if [ ${?} -ne 0 ]
then
  echo -e "[ \e[31mERROR\e[0m ] Can not retrieve Puppet configuration"
  exit 1
fi
if [ "${CONFVALUE}" != "$(hostname -f)" ]
then
  echo "Setting Puppet \"server\" parameter from ${CONFVALUE} to $(hostname -f)..."
  puppet config set server $(hostname -f) --section main || exit 1
  echo "Done"
fi
CONFVALUE=$(puppet config print environmentpath --section master)
if [ ${?} -ne 0 ]
then
  echo -e "[ \e[31mERROR\e[0m ] Can not retrieve Puppet configuration"
  exit 1
fi
if [ "${CONFVALUE}" != "/etc/puppet/environments" ]
then
  echo "Setting Puppet \"environmentpath\" parameter from ${CONFVALUE} to /etc/puppet/environments..."
  puppet config set environmentpath /etc/puppet/environments --section master || exit 1
  echo "Done"
fi
echo -e "- Puppet configuration: \e[32mOK\e[0m"

#
# Part 6 - Set up Puppet to run manually
#

echo
echo "Setting up Puppet to run manually..."
puppet agent --enable
if [ ${?} -ne 0 ]
then
  echo -e "[ \e[31mERROR\e[0m ] Can not run puppet agent --enable"
  exit 1
fi
systemctl disable puppet
if [ ${?} -ne 0 ]
then
  echo -e "[ \e[31mERROR\e[0m ] Can not run systemctl disable puppet"
  exit 1
fi
echo -e "- Puppet service: \e[32mOK\e[0m"

#
# Part 7 - Generate yaml files
#
echo
echo "Generating yaml files..."
if [ ! -f /etc/puppet/hiera.yaml ]
then
  touch /etc/puppet/hiera.yaml
fi
if [ "$(md5sum /etc/puppet/hiera.yaml | awk '{print $1}')" != "d64f6a71c88a15996f915a737bbc1ac8" ]
then
cat <<EOF > /etc/puppet/hiera.yaml
:backends:
  - yaml
:logger: puppet
:hierarchy:
  - "%{hostname}"
  - common
:yaml:
  :datadir: "/etc/puppetlabs/code/hieradata"
EOF
fi
echo -e "- /etc/puppet/hiera.yaml: \e[32mOK\e[0m"

f_readDomainFile()
{
  local FILE=${1}
  while read LINE
  do
    echo "  - ${LINE}"
  done < ${FILE}
}

f_readDomain()
{
  local NUM=${1}
  local FILE=${2}
  echo -n "What is your domain name #${NUM}? "
  read DOMAIN
  echo "${DOMAIN}" >> ${FILE}
  while : ; do
   echo -n "Do you have another domain? (y/n) "
   read ANSWER
   case "$ANSWER" in
     [Yy]) f_readDomain $((${NUM}+1)) ${FILE}
           break ;;
     [Nn]) break ;;
   esac
  done
}

test -d /etc/puppetlabs/code/hieradata/ || mkdir -p /etc/puppetlabs/code/hieradata/
YAML="$(facter hostname)"
if [ ${?} -ne 0 ]
then
  echo -e "[ \e[31mERROR\e[0m ] Can not retrieve hostname using facter"
  exit 1
fi
YAML="/etc/puppetlabs/code/hieradata/${YAML}.yaml"
while [ -z "${ALLGOOD}" ]
do
  TMP=$(mktemp)
  f_readDomain 1 ${TMP}
  echo "Your domains are:"
  echo
  f_readDomainFile ${TMP}
  echo
  while : ; do
    echo -n "Is it correct? (y/n) "
    read ANSWER
    case "$ANSWER" in
      [Yy]) ALLGOOD=yes
            break ;;
      [Nn]) rm ${TMP}
            break ;;
    esac
  done
done
echo "domainnames:" > "${YAML}"
f_readDomainFile ${TMP} >> "${YAML}"
rm ${TMP}
echo -e "- ${YAML}: \e[32mOK\e[0m"

#
# Install completed!
#
echo
echo "All good! You can now complete the installation reading the \"Installation\" section on:"
echo "https://github.com/mdavranche/erine.email/blob/master/README.md"
echo
