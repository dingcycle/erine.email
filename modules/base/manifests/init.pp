class base
{
  notify { 'Processing base module':
  }
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
