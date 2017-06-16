--
-- Current Database: `spameater`
-- WARNING, do NOT replace the below collation by a case sensitive one. It would lead to unexpected behaviors.
--

CREATE DATABASE `spameater` DEFAULT CHARACTER SET = utf8 DEFAULT COLLATE = utf8_general_ci;

USE `spameater`;

--
-- Table structure for table `Users`
--

CREATE TABLE `Users` (
  `ID` int(7) unsigned NOT NULL AUTO_INCREMENT,
  `Username` varchar(15) NOT NULL,
  `Reserved` tinyint(1) NOT NULL DEFAULT '0',
  `first_name` varchar(15) NOT NULL,
  `last_name` varchar(15) NOT NULL,
  `Password` varchar(40) NOT NULL,
  `Email` varchar(100) NOT NULL,
  `Activated` tinyint(1) unsigned NOT NULL DEFAULT '0',
  `Confirmation` char(40) NOT NULL DEFAULT '',
  `RegDate` int(11) unsigned NOT NULL,
  `LastLogin` int(11) unsigned NOT NULL DEFAULT '0',
  PRIMARY KEY (`ID`),
  UNIQUE KEY `Username` (`Username`)
) ENGINE=InnoDB;

--
-- Table structure for table `disposableMailAddress`
-- WARNING, do NOT replace the below InnoDB engine, as the spameater Postfix filter uses transactions on this table.
--

CREATE TABLE `disposableMailAddress` (
  `mailAddress` varchar(254) NOT NULL,
  `userID` int(7) unsigned NOT NULL,
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `remaining` smallint(5) unsigned DEFAULT NULL,
  `sent` int(10) unsigned NOT NULL DEFAULT '0',
  `dropped` int(10) unsigned NOT NULL DEFAULT '0',
  `sentAs` int(10) unsigned NOT NULL DEFAULT '0',
  PRIMARY KEY (`mailAddress`),
  KEY `userID` (`userID`),
  CONSTRAINT `disposableMailAddress_ibfk_1` FOREIGN KEY (`userID`) REFERENCES `Users` (`ID`)
) ENGINE=InnoDB;

--
-- Table structure for table `message`
-- WARNING, do NOT replace the below InnoDB engine, as the spameater Postfix filter uses transactions on this table.
--

CREATE TABLE `message` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `disposableMailAddress` varchar(254) DEFAULT NULL,
  `messageId` varchar(998) NOT NULL,
  `subject` varchar(998) NOT NULL,
  `from` varchar(2048) NOT NULL,
  `rcptTo` varchar(2048) NOT NULL,
  `date` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `status` ENUM('sent', 'dropped', 'sentAs', 'looped'),
  PRIMARY KEY (`id`),
  KEY `disposableMailAddress` (`disposableMailAddress`),
  CONSTRAINT `message_ibfk_1` FOREIGN KEY (`disposableMailAddress`) REFERENCES `disposableMailAddress` (`mailAddress`)
) ENGINE=InnoDB;

--
-- Table structure for table `replyAddress`
-- WARNING, do NOT replace the below InnoDB engine, as the spameater Postfix filter uses transactions on this table.
--

CREATE TABLE `replyAddress` (
  `mailAddress` varchar(254) NOT NULL,
  `disposableMailAddress` varchar(254) NOT NULL,
  `foreignAddress` varchar(254) NOT NULL,
  UNIQUE KEY `mailAddress` (`mailAddress`),
  UNIQUE KEY `disposableMailAddress` (`disposableMailAddress`,`foreignAddress`),
  CONSTRAINT `replyAddress_ibfk_1` FOREIGN KEY (`disposableMailAddress`) REFERENCES `disposableMailAddress` (`mailAddress`)
) ENGINE=InnoDB;

--
-- Grants for user `spameater`
--

GRANT SELECT ON `spameater`.`Users` TO 'spameater'@'%';
GRANT SELECT, UPDATE, INSERT ON `spameater`.`disposableMailAddress` TO 'spameater'@'%';
GRANT SELECT, INSERT ON `spameater`.`message` TO 'spameater'@'%';
GRANT SELECT, INSERT ON `spameater`.`replyAddress` TO 'spameater'@'%';

--
-- Grants for user `www`
--

GRANT SELECT, UPDATE, INSERT ON `spameater`.`Users` TO 'www'@'%';
GRANT SELECT, UPDATE ON `spameater`.`disposableMailAddress` TO 'www'@'%';
GRANT SELECT ON `spameater`.`message` TO 'www'@'%';
