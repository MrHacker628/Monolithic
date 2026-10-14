#!/bin/bash
# Task 6.2 - set up ONE VM for its role. Run on each VM:
#
#   product VM:  sudo bash setup-vm.sh product <cart_vm_ip> <order_vm_ip>
#   cart VM:     sudo bash setup-vm.sh cart    <product_vm_ip>
#   order VM:    sudo bash setup-vm.sh order   <product_vm_ip> <cart_vm_ip>
#   gateway VM:  sudo bash setup-vm.sh gateway <product_vm_ip> <cart_vm_ip> <order_vm_ip>
#
# All IPs are INTERNAL IPs (10.x.x.x). Service VMs get their own local MySQL
# database, reachable only from that VM (127.0.0.1).
set -e
BASE="$(cd "$(dirname "$0")" && pwd)"
ROLE="$1"; shift || true

usage() { sed -n '3,9p' "$0"; exit 1; }

case "$ROLE" in
  product) [ $# -eq 2 ] || usage
           SVC=product-service; PORT=5001; DBN=productdb
           ENVS=("SYNC_SUBSCRIBERS=http://$1:5002,http://$2:5003") ;;
  cart)    [ $# -eq 1 ] || usage
           SVC=cart-service; PORT=5002; DBN=cartdb
           ENVS=("PRODUCT_SERVICE_URL=http://$1:5001") ;;
  order)   [ $# -eq 2 ] || usage
           SVC=order-service; PORT=5003; DBN=orderdb
           ENVS=("PRODUCT_SERVICE_URL=http://$1:5001" "CART_SERVICE_URL=http://$2:5002") ;;
  gateway) [ $# -eq 3 ] || usage
           SVC=gateway; PORT=80; DBN=""
           ENVS=("PRODUCT_SERVICE_URL=http://$1:5001" "CART_SERVICE_URL=http://$2:5002"
                 "ORDER_SERVICE_URL=http://$3:5003" "SECRET_KEY=$(openssl rand -hex 16)") ;;
  *) usage ;;
esac

echo "==> [$ROLE] Installing Python"
apt-get update -y
apt-get install -y python3-venv python3-pip

if [ -n "$DBN" ]; then
  echo "==> [$ROLE] Installing MySQL and creating database '$DBN' (local to this VM only)"
  DEBIAN_FRONTEND=noninteractive apt-get install -y mysql-server
  systemctl enable --now mysql
  DB_PASSWORD="$(openssl rand -hex 12)"
  mysql <<SQL
CREATE DATABASE IF NOT EXISTS $DBN CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'shopeasy'@'localhost' IDENTIFIED WITH mysql_native_password BY '$DB_PASSWORD';
CREATE USER IF NOT EXISTS 'shopeasy'@'127.0.0.1' IDENTIFIED WITH mysql_native_password BY '$DB_PASSWORD';
ALTER USER 'shopeasy'@'localhost' IDENTIFIED WITH mysql_native_password BY '$DB_PASSWORD';
ALTER USER 'shopeasy'@'127.0.0.1' IDENTIFIED WITH mysql_native_password BY '$DB_PASSWORD';
GRANT ALL PRIVILEGES ON $DBN.* TO 'shopeasy'@'localhost';
GRANT ALL PRIVILEGES ON $DBN.* TO 'shopeasy'@'127.0.0.1';
FLUSH PRIVILEGES;
SQL
  ENVS+=("DB_TYPE=mysql" "DB_HOST=127.0.0.1" "DB_USER=shopeasy" "DB_PASSWORD=$DB_PASSWORD" "DB_NAME=$DBN")
fi

echo "==> [$ROLE] Installing $SVC dependencies"
python3 -m venv /opt/shopeasy-venv
/opt/shopeasy-venv/bin/pip install -q -r "$BASE/$SVC/requirements.txt"

echo "==> [$ROLE] Creating the shopeasy-$ROLE service (port $PORT)"
{
  echo "[Unit]"
  echo "Description=ShopEasy $SVC (Task 6.2)"
  echo "After=network-online.target mysql.service"
  echo
  echo "[Service]"
  echo "WorkingDirectory=$BASE/$SVC"
  echo "Environment=PORT=$PORT"
  for e in "${ENVS[@]}"; do echo "Environment=$e"; done
  echo "ExecStart=/opt/shopeasy-venv/bin/python app.py"
  echo "Restart=always"
  echo "RestartSec=5"
  echo
  echo "[Install]"
  echo "WantedBy=multi-user.target"
} > "/etc/systemd/system/shopeasy-$ROLE.service"

systemctl daemon-reload
systemctl enable "shopeasy-$ROLE"
systemctl restart "shopeasy-$ROLE"
sleep 3

if curl -s "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 || curl -s "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
  echo "==> [$ROLE] Running OK."
else
  echo "==> [$ROLE] Not responding yet. Check logs with:  sudo journalctl -u shopeasy-$ROLE -n 50"
fi
echo "Internal IP of this VM: $(hostname -I | awk '{print $1}')"
