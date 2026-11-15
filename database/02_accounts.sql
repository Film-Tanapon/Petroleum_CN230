CREATE USER IF NOT EXISTS 'reader'@'%' IDENTIFIED BY 'read_test';
GRANT SELECT ON cn230_test.* TO 'reader'@'%';
