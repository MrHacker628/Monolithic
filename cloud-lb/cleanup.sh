#!/bin/bash
# Deletes EVERYTHING this assignment created, in the right order, so it stops using credits.
# Run in Cloud Shell:  bash cleanup.sh
cd "$(dirname "$0")"
source ./config.sh

echo "This deletes the load balancer, instance group, template, health checks, firewall rule,"
echo "static IP and the image repository in project '$PROJECT'."
read -r -p "Type yes to continue: " OK
[ "$OK" = "yes" ] || { echo "Cancelled."; exit 0; }

q() { "$@" --quiet 2>&1 | grep -v "^$" || true; }
q gcloud compute forwarding-rules delete "$FWD_RULE" --global
q gcloud compute target-http-proxies delete "$PROXY"
q gcloud compute url-maps delete "$URL_MAP"
for s in $SERVICES; do q gcloud compute backend-services delete "ms-${s}-bs" --global; done
q gcloud compute instance-groups managed delete "$MIG" --region="$REGION"
q gcloud compute instance-templates delete "$TEMPLATE" ms-template
q gcloud compute health-checks delete "$HC" "$HC_AUTOHEAL"
q gcloud compute firewall-rules delete ms-allow-lb
q gcloud compute addresses delete "$IP_NAME" --global
q gcloud artifacts repositories delete "$REPO" --location="$REGION"

echo; echo "Left over (should all be empty):"
gcloud compute instances list; gcloud compute forwarding-rules list; gcloud compute addresses list
