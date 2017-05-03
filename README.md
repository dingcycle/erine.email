# erine.email

erine.email is a strong shield for your emails against spam. Based on unlimited disposable email addresses, erine.email is completely free, open-source, and simple. Really. [Check it out!](https://erine.email)

## Host deployment from scratch on Debian Jessie

Follow those few steps to install a full working erine.email system.

First, get a freshly installed server with Debian Jessie as operating system.

Then, as root, update your system, install prerequisites, and get the Puppet environment:

```
apt-get update && apt-get upgrade
apt-get install git puppetmaster puppet
cd /etc/puppet/
test -d environments || mkdir environments
cd environments
git clone https://github.com/mdavranche/erine.email.git production
```

On /etc/puppet/puppet.conf, `[main]` section, tell Puppet agent who is your Puppet Master:

```
server=xxx
```

xxx should be your hostname FQDN.

On the `[master]` section, tell Puppet Master where your environments are:

```
environmentpath = /etc/puppet/environments
```

As root, you can setup Puppet agent to run manually:

```
kill -TERM `cat /var/run/puppet/agent.pid`
puppet agent --enable
systemctl disable puppet
```

Setup the iptables rule to prevent anybody connecting to your Puppet Master. As root:

```
iptables -A INPUT -p tcp --source 127.0.0.1 --dport 8140 -j ACCEPT
iptables -A INPUT -p tcp --dport 8140 -j REJECT
apt-get install iptables-persistent
```

Tell Puppet what is(are) your domain name(s) using Hiera. Create `/etc/puppet/hiera.yaml` with the following content:

```
:backends:
  - yaml
:logger: puppet
:hierarchy:
  - "%{hostname}"
  - common
:yaml:
  :datadir: "/etc/puppetlabs/code/hieradata"
```

Create the ``/etc/puppetlabs/code/hieradata/`facter hostname`.yaml`` file with your domain names. For example, my domain name is `erine.email`:

```
domainnames:
  - erine.email
```

And reboot.

As root, launch Puppet agent:

```
puppet agent --test --environment=production
```

That's it!

## OK, and now, how to use it?

So that your server forwards something.user@domain to your real email address, you'll have to fill the `Users` table of the `spameater` database. At least the `Username` and `Email` columns. You can do it manually with a mysql client, but the nice way should be developping a web site to do it, and to read the interesting statistics of the `disposableMailAddress` and `message` tables.

Of course, you'll have to set the `MX` DNS record of your domain name to your server. Do not forget the `spf` record either.

### Reserved users

Note that this part is optional, you do not HAVE to worry about.

A "reserved users" is a user whose disposable email addresses operate differently from the something.user@domain pattern. For this user, your server will forward user@domain to the user's real email address. Be careful, for this kind of users, everything sent to something.user@domain will be dropped!

 | Normal users | Reserved users
-|--------------|---------------
something.user@domain | Forward | Drop
user@domain | Drop | Forward

A user will be "reserved" if the `Reserved` column of the `Users` table is set to 1. The default value is 0 (normal user).

OK, I got it, but what is that for?

The [RFC 2142](https://www.ietf.org/rfc/rfc2142.txt) tells that you should reserve mailbox names for common services, roles and functions. For instance, the postmaster@domain email address should route emails to a person responsible for the site's mail system or to a person with responsibility for general site operation. You also have email addresses like webmaster@domain, abuse@domain...
