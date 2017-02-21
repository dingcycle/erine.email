# Install basic administration tools
class base
{

  package { [
    'dnsutils',
    'lsof',
    'strace',
    'sysstat',
    'tree',
    'whois',
  ]:
    ensure => present,
  }

}
