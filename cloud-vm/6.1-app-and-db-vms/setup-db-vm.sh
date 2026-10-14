#!/bin/bash
# Task 6.1 - run on VM2 (the DATABASE VM)
# Usage:  sudo bash setup-db-vm.sh <db_password>
# Installs MySQL, lets it accept connections from the internal network only
# (users from 10.x.x.x addresses), and creates the 'shopeasy' database.
set -e
DB_PASSWORD="${1:?Usage: sudo bash setup-db-vm.sh <db_password>}"

echo "==> Installing MySQL server"
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y mysql-server

echo "==> Making MySQL listen on the VM's network interface (not just localhost)"
sed -i 's/^bind-address.*/bind-address = 0.0.0.0/' /etc/mysql/mysql.conf.d/mysqld.cnf
systemctl restart mysql

echo "==> Creating database and a user that may only connect from internal IPs (10.%)"
mysql <<SQL
CREATE DATABASE IF NOT EXISTS shopeasy CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'shopeasy'@'10.%' IDENTIFIED WITH mysql_native_password BY '${DB_PASSWORD}';
ALTER USER 'shopeasy'@'10.%' IDENTIFIED WITH mysql_native_password BY '${DB_PASSWORD}';
GRANT ALL PRIVILEGES ON shopeasy.* TO 'shopeasy'@'10.%';
FLUSH PRIVILEGES;
SQL

echo
echo "Done. MySQL is running on this VM."
echo "Internal IP of this VM (use it as DB_HOST on the app VM): $(hostname -I | awk '{print $1}')"
