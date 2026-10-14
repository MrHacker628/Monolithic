#!/bin/bash
# Task 6.1 - run on VM1 (the APPLICATION VM)
# Usage:  sudo bash setup-app-vm.sh <db_vm_internal_ip> <db_password>
# Installs the ShopEasy app and runs it on port 80 as a service.
# The app connects to MySQL on VM2 using VM2's INTERNAL IP.
set -e
DB_IP="${1:?Usage: sudo bash setup-app-vm.sh <db_vm_internal_ip> <db_password>}"
DB_PASSWORD="${2:?Usage: sudo bash setup-app-vm.sh <db_vm_internal_ip> <db_password>}"
APP_DIR="$(cd "$(dirname "$0")/app" && pwd)"

echo "==> Installing Python"
apt-get update -y
apt-get install -y python3-venv python3-pip mysql-client

echo "==> Checking the database VM is reachable at $DB_IP (internal IP)"
if mysql -h "$DB_IP" -u shopeasy -p"$DB_PASSWORD" -e "SELECT 'DB reachable' AS status;" shopeasy; then
  echo "    OK"
else
  echo "    Could not connect to MySQL at $DB_IP. Check the IP, password and that setup-db-vm.sh ran on VM2."
  exit 1
fi

echo "==> Installing app dependencies"
python3 -m venv /opt/shopeasy-venv
/opt/shopeasy-venv/bin/pip install -q -r "$APP_DIR/requirements.txt"

echo "==> Creating the shopeasy service"
cat > /etc/systemd/system/shopeasy.service <<UNIT
[Unit]
Description=ShopEasy app (Task 6.1) - database on $DB_IP
After=network-online.target

[Service]
WorkingDirectory=$APP_DIR
Environment=DB_TYPE=mysql
Environment=DB_HOST=$DB_IP
Environment=DB_USER=shopeasy
Environment=DB_PASSWORD=$DB_PASSWORD
Environment=DB_NAME=shopeasy
Environment=PORT=80
ExecStart=/opt/shopeasy-venv/bin/python app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable shopeasy
systemctl restart shopeasy
sleep 3
systemctl --no-pager status shopeasy | head -5

echo
echo "Done. Open http://<this VM's EXTERNAL IP> in your browser."
echo "Proof page: http://<this VM's EXTERNAL IP>/dbinfo"
