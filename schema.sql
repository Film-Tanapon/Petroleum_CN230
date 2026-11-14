-- Reference schema for the SRS tests. Replace with the team's DDL to test it.

CREATE TABLE `Product` (
  `product_id` INT PRIMARY KEY,
  `name` VARCHAR(120) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE `Field` (
  `field_id` INT PRIMARY KEY,
  `name` VARCHAR(120) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE `Block` (
  `block_id` INT PRIMARY KEY,
  `label` VARCHAR(120) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE `Unit` (
  `unit_id` INT PRIMARY KEY,
  `symbol` VARCHAR(120) NOT NULL,
  `description` VARCHAR(120) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE `Emission_Factor` (
  `factor_id` INT PRIMARY KEY,
  `product_id` INT NOT NULL,
  `unit_id` INT NOT NULL,
  `factor_value` DECIMAL(22,8) NULL,
  `activity_type` VARCHAR(120) NOT NULL,
  `basis` VARCHAR(120) NOT NULL,
  FOREIGN KEY (`product_id`) REFERENCES `Product` (`product_id`),
  FOREIGN KEY (`unit_id`) REFERENCES `Unit` (`unit_id`),
  CHECK (factor_value >= 0)
) ENGINE=InnoDB;

CREATE TABLE `Supply_Monthly` (
  `supply_id` INT PRIMARY KEY,
  `product_id` INT NOT NULL,
  `unit_id` INT NOT NULL,
  `area` VARCHAR(120) NOT NULL,
  `daily_rate` DECIMAL(22,8) NULL,
  `month` INT NOT NULL,
  `year` INT NOT NULL,
  FOREIGN KEY (`product_id`) REFERENCES `Product` (`product_id`),
  FOREIGN KEY (`unit_id`) REFERENCES `Unit` (`unit_id`),
  CHECK (daily_rate >= 0)
) ENGINE=InnoDB;

CREATE TABLE `Reserve_Annual` (
  `reserve_id` INT PRIMARY KEY,
  `product_id` INT NOT NULL,
  `block_id` INT NOT NULL,
  `unit_id` INT NOT NULL,
  `proven_reserves` DECIMAL(22,8) NULL,
  `year` INT NOT NULL,
  FOREIGN KEY (`product_id`) REFERENCES `Product` (`product_id`),
  FOREIGN KEY (`block_id`) REFERENCES `Block` (`block_id`),
  FOREIGN KEY (`unit_id`) REFERENCES `Unit` (`unit_id`),
  CHECK (proven_reserves >= 0)
) ENGINE=InnoDB;

CREATE TABLE `Price_Monthly` (
  `price_id` INT PRIMARY KEY,
  `product_id` INT NOT NULL,
  `field_id` INT NOT NULL,
  `unit_id` INT NOT NULL,
  `unit_price` DECIMAL(22,8) NULL,
  `currency` VARCHAR(120) NOT NULL,
  `month` INT NOT NULL,
  `year` INT NOT NULL,
  FOREIGN KEY (`product_id`) REFERENCES `Product` (`product_id`),
  FOREIGN KEY (`field_id`) REFERENCES `Field` (`field_id`),
  FOREIGN KEY (`unit_id`) REFERENCES `Unit` (`unit_id`),
  CHECK (unit_price >= 0),
  UNIQUE (field_id, product_id, unit_id, month, year)
) ENGINE=InnoDB;

CREATE TABLE `Sale` (
  `sale_id` INT PRIMARY KEY,
  `product_id` INT NOT NULL,
  `field_id` INT NOT NULL,
  `volume_bbl` DECIMAL(22,8) NULL,
  `volume_mmscf` DECIMAL(22,8) NULL,
  `energy_mmbtu` DECIMAL(22,8) NULL,
  `sale_value` DECIMAL(22,8) NULL,
  `royalty` DECIMAL(22,8) NULL,
  `currency` VARCHAR(120) NOT NULL,
  `month` INT NOT NULL,
  `year` INT NOT NULL,
  FOREIGN KEY (`product_id`) REFERENCES `Product` (`product_id`),
  FOREIGN KEY (`field_id`) REFERENCES `Field` (`field_id`),
  CHECK (royalty >= 0),
  CHECK (sale_value >= 0),
  CHECK (volume_bbl >= 0),
  CHECK (volume_mmscf >= 0)
) ENGINE=InnoDB;

CREATE TABLE `Production_Monthly` (
  `production_id` INT PRIMARY KEY,
  `product_id` INT NOT NULL,
  `field_id` INT NULL,
  `block_id` INT NULL,
  `unit_id` INT NOT NULL,
  `quantity` DECIMAL(22,8) NULL,
  `oil_equivalent` DECIMAL(22,8) NULL,
  `production_days` INT NOT NULL,
  `year` INT NOT NULL,
  `month` INT NOT NULL,
  FOREIGN KEY (`product_id`) REFERENCES `Product` (`product_id`),
  FOREIGN KEY (`field_id`) REFERENCES `Field` (`field_id`),
  FOREIGN KEY (`block_id`) REFERENCES `Block` (`block_id`),
  FOREIGN KEY (`unit_id`) REFERENCES `Unit` (`unit_id`),
  CHECK (quantity >= 0),
  CHECK (month BETWEEN 1 AND 12),
  CHECK (production_days BETWEEN 0 AND CASE
      WHEN month IN (4,6,9,11) THEN 30
      WHEN month=2 THEN 28 + (MOD(year,400)=0 OR (MOD(year,4)=0 AND MOD(year,100)<>0))
      ELSE 31 END)
) ENGINE=InnoDB;
