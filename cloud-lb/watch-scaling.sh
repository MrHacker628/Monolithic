#!/bin/bash
# Prints the instance count every 15 seconds and saves it to scaling-log.txt.
# Run it in a SECOND Cloud Shell tab while the load test runs. Stop with Ctrl+C.
# The saved log is your text "proof of scaling" (instances going 1 -> 2 -> 3 and back).
cd "$(dirname "$0")"
source ./config.sh

echo "time      target_size  running  recommended  instances" | tee scaling-log.txt
while true; do
  TARGET=$(gcloud compute instance-groups managed describe "$MIG" --region="$REGION" --format="value(targetSize)")
  INST=$(gcloud compute instance-groups managed list-instances "$MIG" --region="$REGION" \
           --format="value(instance.basename(),instanceStatus)")
  RUNNING=$(echo "$INST" | grep -c RUNNING)
  NAMES=$(echo "$INST" | awk '{printf "%s(%s) ", $1, $2}')
  REC=$(gcloud compute instance-groups managed describe "$MIG" --region="$REGION" --format="value(autoscaler.recommendedSize)" 2>/dev/null)
  printf "%s  %-11s  %-7s  %-11s  %s\n" "$(date +%H:%M:%S)" "$TARGET" "$RUNNING" "${REC:--}" "$NAMES" | tee -a scaling-log.txt
  sleep 15
done
