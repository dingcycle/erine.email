# Logrotate and its hourly crontab
class logrotate
{

  package { 'logrotate':
    ensure => present,
  }

  file { '/etc/cron.hourly/logrotate':
    ensure => present,
    mode   => '0755',
    owner  => 'root',
    group  => 'root',
    source => 'puppet:///modules/logrotate/logrotate.sh',
  }

}
