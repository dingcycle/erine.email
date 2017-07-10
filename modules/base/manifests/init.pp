# Install basic administration tools
class base
{

  package { [
    'bash-completion',
    'dnsutils',
    'less',
    'lsof',
    'strace',
    'sysstat',
    'tree',
    'vim',
    'whois',
  ]:
    ensure => present,
  }

  $domainnames = hiera('domainnames')

  file { '/etc/bash.bashrc':
    ensure  => file,
    mode    => '0644',
    owner   => 'root',
    group   => 'root',
    content => template('base/bash.bashrc.erb'),
  }

}
