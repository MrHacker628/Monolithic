#!/bin/bash
# STEP 4 - Start Locust (load-testing tool) in Cloud Shell against the load balancer.
#   bash 4-load-test.sh            -> Locust web UI on port 8080 (open with Cloud Shell "Web preview")
#   bash 4-load-test.sh headless   -> no UI: 150 users for 15 minutes, results saved to loadtest_*.csv
cd "$(dirname "$0")"
source ./config.sh

IP=$(gcloud compute addresses describe "$IP_NAME" --global --format="value(address)")
[ -z "$IP" ] && { echo "Load balancer IP not found. Run step 3 first."; exit 1; }

if [ ! -x "$HOME/locust-venv/bin/locust" ]; then
  echo "==> Installing Locust (one time, ~1 minute)"
  python3 -m venv "$HOME/locust-venv"
  "$HOME/locust-venv/bin/pip" install -q locust
fi

if [ "$1" = "headless" ]; then
  echo "==> Running 150 users for 15 minutes against http://$IP (Ctrl+C to stop early)"
  "$HOME/locust-venv/bin/locust" -f loadtest/locustfile.py --host "http://$IP" \
    --headless -u 150 -r 5 -t 15m --csv=loadtest --only-summary
else
  echo "==> Locust web UI starting on port 8080."
  echo "    In Cloud Shell click 'Web preview' (eye icon) -> 'Preview on port 8080'."
  echo "    Then set: Number of users = 150, Ramp up = 5, Host = http://$IP  and click START."
  "$HOME/locust-venv/bin/locust" -f loadtest/locustfile.py --host "http://$IP" --web-port 8080
fi
