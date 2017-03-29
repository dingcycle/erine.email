# Change the www-data user home dir
class wwwdata
{

  group { 'www-data':
    ensure => present,
    gid    => '33',
  }

  user { 'www-data':
    ensure   => present,
    uid      => '33',
    gid      => 'www-data',
    home     => '/home/www-data',
    password => '*',
  }

  # As www-data user exists by default, home dir won't be created with
  # managehome. So we do it there.
  file { '/home/www-data':
    ensure  => directory,
    mode    => '0755',
    owner   => 'www-data',
    group   => 'www-data',
    # We need the www-data user and group
    require => [
      User['www-data'],
      Group['www-data'],
    ],
  }

}
