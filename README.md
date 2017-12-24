# erine.email

*erine.email* is a strong shield for your emails against spam. Based on
unlimited disposable email addresses, *erine.email* is completely free,
open-source, and simple. Really. [Check it out!](https://erine.email)

This repo is the piece of software that you need to host
*erine.email* on your own server.

## Example

Let's say you own the email address **joe@example.org**,
and you created the user **joe** on your *erine.email* instance.

You're about to buy a new vacuum cleaner from **brand42** online shop
and you have to give them your email address.
Communicate them your *erine.email* address instead!

Indeed, emails sent to **brand42.joe@erine.email** will be redirected
automatically to **joe@example.org**. Your personal address is kept private,
and you can disable **brand42.joe** in the future in case **brand42** suddenly
decides to spam you.

## Requirements

A freshly installed server with [Debian Stretch](https://www.debian.org/releases/stretch/) as operating system.

The `MX` DNS record of your domain name set to this server. Make sure you have a result when you dig your domain:

```bash
dig +noall +answer  MX myspameater.example.com.
		59      IN  	MX       	1      smtp.example.com
```

To prevent most of your emails to be tagged as spam, also set the `SPF` DNS record.


## Installation

Follow the following steps to install a full working *erine.email* system.

Install prerequisites using the erine.email installation script:

```bash
wget https://raw.githubusercontent.com/mdavranche/erine.email/master/install.sh --quiet
sudo bash install.sh && rm install.sh
```

Setup the `iptables` rule to prevent anybody connecting to your Puppet Master.
As root:

```bash
iptables -A INPUT -p tcp --source 127.0.0.1 --dport 8140 -j ACCEPT
iptables -A INPUT -p tcp --dport 8140 -j REJECT
apt-get install iptables-persistent
```

And reboot.

As root, launch Puppet agent:

```bash
puppet agent --test --environment=production
```

That's it!

## Add your first user

So that your server forwards `something.user@domain` to your real email address,
you'll have to fill the `user` table of the `spameater` database.
At least the `username` and `mailAddress` columns. You can do it manually
with a MySQL client, but the nice way should be to have a website for it
and to read the interesting statistics of the `disposableMailAddress` and
`message` tables (coming soon).

For now, simply run something like the following (replace the VALUES with
what fits you best):

```bash
mysql -u root -p$( cat /root/.mariadb.pwd ) spameater -e "INSERT INTO user (username, mailAddress) VALUES ('john', 'mysecretemail@example.com');"
```

## Test that it works!

You created user **John**. Supposing your *erine.email* service is hosted at `myspameater.example.com`,
send a test email to `hotelchainidonttrust.john@myspameater.example.com`,
and it should arrive in your `mysecretemail@example.com` mailbox.

Voilà.

## Additional configuration

### Reserved users

Note that this part is optional, you do not HAVE to worry about it.

A *reserved user* is a user whose disposable email addresses operates
differently from the `something.user@domain` pattern.
For this user, your server will forward `user@domain` emails to the user's real
email address.
Be careful, for this kind of users, everything
sent to `something.user@domain` will be dropped!

| Email pattern         |  Normal users policy |  Reserved users policy |
| --------------------- | -------------------- | ---------------------- |
| something.user@domain | Forward              | Drop                   |
| user@domain           | Drop                 | Forward                |

A user will be "reserved" if the `reserved` column of the `user` table
is set to 1. The default value is 0 (normal user).

OK, I got it, but what is that for?

The [RFC 2142](https://www.ietf.org/rfc/rfc2142.txt) tells that you should
reserve mailbox names for common services, roles and functions. For instance,
the postmaster@domain email address should route emails to a person responsible
for the site's mail system or to a person with responsibility for general site
operation. You also have email addresses like webmaster@domain, abuse@domain...
