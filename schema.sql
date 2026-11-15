-- Petroleum SRS sections 4.2-4.3; MySQL 8.0.16+ (enforced CHECK constraints).
-- This file creates tables in the selected database; it does not migrate existing tables.
-- Resolve document inconsistencies using section 4.2 for Supply_Monthly.area
-- (VARCHAR(100), not a foreign key), and section 4.3.3 for Unit.unit_id.
-- BR-01 (each Field has a production link to a Block) requires a post-import audit.
-- BR-08 intentionally excludes currency: one price currency per grain.
-- Nullable dates follow section 4.2; UNIQUE permits repeated grains containing NULL.

CREATE TABLE `Product` (
  `product_id` VARCHAR(50) PRIMARY KEY,
  `name` VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE `Field` (
  `field_id` VARCHAR(50) PRIMARY KEY,
  `name` VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE `Block` (
  `block_id` VARCHAR(50) PRIMARY KEY,
  `label` VARCHAR(50) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE `Unit` (
  `unit_id` VARCHAR(50) PRIMARY KEY,
  `symbol` VARCHAR(20) NOT NULL,
  `description` VARCHAR(100) NULL
) ENGINE=InnoDB;

CREATE TABLE `Emission_Factor` (
  `factor_id` VARCHAR(50) PRIMARY KEY,
  `product_id` VARCHAR(50) NOT NULL,
  `unit_id` VARCHAR(50) NOT NULL,
  `factor_value` DECIMAL(10,6) NULL,
  `activity_type` VARCHAR(100) NULL,
  `basis` VARCHAR(100) NULL,
  FOREIGN KEY (`product_id`) REFERENCES `Product` (`product_id`),
  FOREIGN KEY (`unit_id`) REFERENCES `Unit` (`unit_id`),
  CHECK (factor_value >= 0)
) ENGINE=InnoDB;

CREATE TABLE `Supply_Monthly` (
  `supply_id` VARCHAR(50) PRIMARY KEY,
  `product_id` VARCHAR(50) NOT NULL,
  `unit_id` VARCHAR(50) NOT NULL,
  `area` VARCHAR(100) NULL,
  `daily_rate` DECIMAL(15,6) NULL,
  `month` INT NULL,
  `year` INT NULL,
  FOREIGN KEY (`product_id`) REFERENCES `Product` (`product_id`),
  FOREIGN KEY (`unit_id`) REFERENCES `Unit` (`unit_id`),
  CHECK (daily_rate >= 0)
) ENGINE=InnoDB;

CREATE TABLE `Reserve_Annual` (
  `reserve_id` VARCHAR(50) PRIMARY KEY,
  `product_id` VARCHAR(50) NOT NULL,
  `block_id` VARCHAR(50) NOT NULL,
  `unit_id` VARCHAR(50) NOT NULL,
  `proven_reserves` DECIMAL(18,6) NULL,
  `year` INT NULL,
  FOREIGN KEY (`product_id`) REFERENCES `Product` (`product_id`),
  FOREIGN KEY (`block_id`) REFERENCES `Block` (`block_id`),
  FOREIGN KEY (`unit_id`) REFERENCES `Unit` (`unit_id`),
  CHECK (proven_reserves >= 0)
) ENGINE=InnoDB;

CREATE TABLE `Price_Monthly` (
  `price_id` VARCHAR(50) PRIMARY KEY,
  `product_id` VARCHAR(50) NOT NULL,
  `field_id` VARCHAR(50) NOT NULL,
  `unit_id` VARCHAR(50) NOT NULL,
  `unit_price` DECIMAL(12,6) NULL,
  `currency` VARCHAR(10) NULL,
  `month` INT NULL,
  `year` INT NULL,
  FOREIGN KEY (`product_id`) REFERENCES `Product` (`product_id`),
  FOREIGN KEY (`field_id`) REFERENCES `Field` (`field_id`),
  FOREIGN KEY (`unit_id`) REFERENCES `Unit` (`unit_id`),
  CHECK (unit_price >= 0),
  UNIQUE (field_id, product_id, unit_id, month, year)
) ENGINE=InnoDB;

CREATE TABLE `Sale` (
  `sale_id` VARCHAR(50) PRIMARY KEY,
  `product_id` VARCHAR(50) NOT NULL,
  `field_id` VARCHAR(50) NOT NULL,
  `volume_bbl` DECIMAL(15,6) NULL,
  `volume_mmscf` DECIMAL(15,6) NULL,
  `energy_mmbtu` DECIMAL(15,6) NULL,
  `sale_value` DECIMAL(18,6) NULL,
  `royalty` DECIMAL(15,6) NULL,
  `currency` VARCHAR(10) NULL,
  `month` INT NULL,
  `year` INT NULL,
  FOREIGN KEY (`product_id`) REFERENCES `Product` (`product_id`),
  FOREIGN KEY (`field_id`) REFERENCES `Field` (`field_id`),
  CHECK (royalty >= 0),
  CHECK (sale_value >= 0),
  CHECK (volume_bbl >= 0),
  CHECK (volume_mmscf >= 0)
) ENGINE=InnoDB;

CREATE TABLE `Production_Monthly` (
  `production_id` VARCHAR(50) PRIMARY KEY,
  `product_id` VARCHAR(50) NOT NULL,
  `field_id` VARCHAR(50) NULL,
  `block_id` VARCHAR(50) NULL,
  `unit_id` VARCHAR(50) NOT NULL,
  `quantity` DECIMAL(15,6) NULL,
  `oil_equivalent` DECIMAL(15,6) NULL,
  `production_days` INT NULL,
  `month` INT NULL,
  `year` INT NULL,
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
