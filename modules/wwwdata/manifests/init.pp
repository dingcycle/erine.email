# Create www-data user before apache2 package does
class wwwdata
{

  group { 'www-data':
    ensure => present,
    gid    => '33',
  }

  user { 'www-data':
    ensure     => present,
    uid        => '33',
    gid        => 'www-data',
    shell      => '/bin/false',
    home       => '/home/www-data',
    managehome => true,
    password   => '*',
  }

}
