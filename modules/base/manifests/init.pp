# Install basic administration tools
class base
{

  package { [
    'dnsutils',
    'lsof',
    'strace',
    'sysstat',
    'tree',
    'vim',
    'whois',
  ]:
    ensure => present,
  }

  file { '/etc/bash.bashrc':
    ensure  => file,
    mode    => '0644',
    owner   => 'root',
    group   => 'root',
    content => template('base/bash.bashrc.erb'),
  }

}
