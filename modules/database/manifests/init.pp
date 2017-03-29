# Install MariaDB server, client, and Python library
class database
{

  exec { 'mkRootPwdFile':
    command => '/bin/mktemp -u XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX > /root/.mariadb.pwd',
    creates => '/root/.mariadb.pwd',
    notify  => Exec['mkRootPwdDeb'],
  }

  exec { 'mkRootPwdDeb':
    command     => '/bin/echo "mariadb-server mysql-server/root_password password `/bin/cat /root/.mariadb.pwd`" | debconf-set-selections',
    refreshonly => true,
    notify      => Exec['mkRootPwdDebAgain'],
  }

  exec { 'mkRootPwdDebAgain':
    command     => '/bin/echo "mariadb-server mysql-server/root_password_again password `/bin/cat /root/.mariadb.pwd`" | debconf-set-selections',
    refreshonly => true,
  }

  package { 'mariadb-server':
    ensure  => present,
    require => Exec['mkRootPwdFile'],
    notify  => Exec['rmRootPwdDeb'],
  }

  exec { 'rmRootPwdDeb':
    command     => '/bin/echo "mariadb-server mysql-server/root_password password" | debconf-set-selections',
    refreshonly => true,
    notify      => Exec['rmRootPwdDebAgain'],
  }

  exec { 'rmRootPwdDebAgain':
    command     => '/bin/echo "mariadb-server mysql-server/root_password_again password" | debconf-set-selections',
    refreshonly => true,
  }

  package { [
    'mariadb-client',
    'python-mysqldb',
  ]:
    ensure => present,
  }

  file { '/root/mkdb.sh':
    ensure => present,
    mode   => '0740',
    owner  => 'root',
    group  => 'root',
    source => 'puppet:///modules/database/mkdb.sh',
  }

  file { '/root/mkdb.sql':
    ensure => present,
    mode   => '0640',
    owner  => 'root',
    group  => 'root',
    source => 'puppet:///modules/database/mkdb.sql',
  }

  exec { 'mkDb':
    command => '/root/mkdb.sh',
    creates => [
      '/home/spameater/.mariadb.pwd',
      '/home/www-data/.mariadb.pwd',
    ],
    require => [
      User['spameater'],
      File['/home/www-data'],
      File['/root/mkdb.sh'],
      File['/root/mkdb.sql'],
      Package['mariadb-server'],
      Package['mariadb-client'],
    ]
  }

}
