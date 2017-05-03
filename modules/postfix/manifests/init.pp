# Install Postfix, and our specific spameater filter
class postfix
{

  package { 'postfix':
    ensure => present,
  }

  group { 'spameater':
    ensure => present,
    gid    => '142',
  }

  user { 'spameater':
    ensure     => present,
    uid        => '142',
    gid        => 'spameater',
    shell      => '/usr/sbin/nologin',
    home       => '/home/spameater',
    managehome => true,
    password   => '*',
    # We need the postfix group, the /var/spool/postfix/ directory and the spameater group
    require    => [
      Package['postfix'],
      Group['spameater'],
    ],
  }

  file { '/usr/lib/postfix/spameater':
    ensure  => present,
    mode    => '0755',
    owner   => 'root',
    group   => 'root',
    source  => 'puppet:///modules/postfix/spameater.py',
    # We need the /usr/lib/postfix/ directory and the Python MySQL library
    require => [
      Package['postfix'],
      Package['python-mysqldb'],
    ],
  }

  file { '/var/log/spameater':
    ensure  => directory,
    mode    => '0755',
    owner   => 'spameater',
    group   => 'spameater',
    # We need the spameater user and group
    require => [
      User['spameater'],
      Group['spameater'],
    ],
  }

  file { '/etc/logrotate.d/spameater':
    ensure  => present,
    mode    => '0644',
    owner   => 'root',
    group   => 'root',
    source  => 'puppet:///modules/postfix/spameater.logrotate',
    # We need the /etc/logrotate.d/ directory
    require => Package['logrotate'],
  }

  exec { 'reloadPostfix':
    command     => '/usr/sbin/postfix reload',
    refreshonly => true,
  }

  exec { 'postmapRelaydomains':
    command     => '/usr/sbin/postmap /etc/postfix/relaydomains',
    refreshonly => true,
    notify      => Exec['reloadPostfix'],
  }

  file { '/etc/postfix/main.cf':
    ensure  => file,
    mode    => '0644',
    owner   => 'root',
    group   => 'root',
    content => template('postfix/main.cf.erb'),
    notify  => Exec['reloadPostfix'],
    # We need the /etc/postfix/ directory and not erasing our main.cf with the postfix package one
    require => Package['postfix'],
  }

  file { '/etc/postfix/relaydomains':
    ensure  => file,
    mode    => '0644',
    owner   => 'root',
    group   => 'root',
    content => template('postfix/relaydomains.erb'),
    notify  => Exec['postmapRelaydomains'],
    # We need the /etc/postfix/ directory
    require => Package['postfix'],
  }

  file { '/etc/postfix/master.cf':
    ensure  => present,
    mode    => '0644',
    owner   => 'root',
    group   => 'root',
    source  => 'puppet:///modules/postfix/master.cf',
    notify  => Exec['reloadPostfix'],
    # We need the /etc/postfix/ directory and not erasing our master.cf with the postfix package one
    require => Package['postfix'],
  }

}
