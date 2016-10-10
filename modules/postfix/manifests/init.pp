class postfix
{
  notify { 'Processing postfix module':
  }
  package { 'postfix':
    ensure => present,
  }
}
