#!/bin/bash
# Shows everything at a glance: LB IP, instances, autoscaling rule, backend health.
cd "$(dirname "$0")"
source ./config.sh

IP=$(gcloud compute addresses describe "$IP_NAME" --global --format="value(address)" 2>/dev/null)
echo "Load balancer:  http://$IP"
echo
echo "=== Managed Instance Group '$MIG' ==="
gcloud compute instance-groups managed list-instances "$MIG" --region="$REGION" \
  --format="table(instance.basename():label=INSTANCE,instance.segment(-3):label=ZONE,instanceStatus:label=STATUS,currentAction:label=ACTION)"
echo
echo "=== Autoscaling rule ==="
gcloud compute instance-groups managed describe "$MIG" --region="$REGION" \
  --format="table(targetSize:label=CURRENT_SIZE,autoscaler.autoscalingPolicy.minNumReplicas:label=MIN,autoscaler.autoscalingPolicy.maxNumReplicas:label=MAX,autoscaler.autoscalingPolicy.cpuUtilization.utilizationTarget:label=TARGET_CPU,autoscaler.recommendedSize:label=RECOMMENDED,autoscaler.status:label=AUTOSCALER)"
echo
for s in $SERVICES; do
  echo "=== Backend health: ms-${s}-bs (port ${PORT[$s]}) ==="
  gcloud compute backend-services get-health "ms-${s}-bs" --global \
    --format="table(status.healthStatus[].instance.basename():label=INSTANCE,status.healthStatus[].healthState:label=HEALTH)" 2>/dev/null
done
