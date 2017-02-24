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

  exec { 'mkSpameaterPwdFile':
    command => '/bin/mktemp -u XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX > /home/spameater/.mariadb.pwd',
    creates => '/home/spameater/.mariadb.pwd',
    require => User['spameater'],
    notify  => Exec['mkSpameaterDb'],
  }

  exec { 'mkSpameaterDb':
    command     => '/usr/bin/mysql -p`/bin/cat /root/.mariadb.pwd` -e "CREATE USER spameater IDENTIFIED BY \"`/bin/cat /home/spameater/.mariadb.pwd`\";"',
    refreshonly => true,
    require     => [
      Package['mariadb-server'],
      Package['mariadb-client'],
    ],
    notify      => Exec['mkDb'],
  }

  exec { 'mkDb':
    command     => '/usr/bin/mysql -p`/bin/cat /root/.mariadb.pwd` < /root/dump.sql',
    refreshonly => true,
    require     => [
      File['/root/dump.sql'],
      Package['mariadb-server'],
      Package['mariadb-client'],
    ],
  }

  file { '/root/dump.sql':
    ensure => present,
    mode   => '0640',
    owner  => 'root',
    group  => 'root',
    source => 'puppet:///modules/database/dump.sql',
  }

}
