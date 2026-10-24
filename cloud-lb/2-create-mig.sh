#!/bin/bash
# STEP 2 - Instance template + regional Managed Instance Group + autoscaling.
# Every VM in the group runs all 3 microservice containers (pulled from Artifact Registry).
# Run in Cloud Shell:  bash 2-create-mig.sh
set -e
cd "$(dirname "$0")"
source ./config.sh

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format="value(projectNumber)")
VM_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "==> Allowing the VMs' service account to pull images from the registry"
gcloud artifacts repositories add-iam-policy-binding "$REPO" --location="$REGION" \
  --member="serviceAccount:$VM_SA" --role="roles/artifactregistry.reader" >/dev/null

echo "==> Writing the VM startup script"
cat > startup.sh <<EOF
#!/bin/bash
# Runs on every VM in the group at boot (Container-Optimized OS has Docker built in).
export DOCKER_CONFIG=/tmp/docker-config
TOKEN=\$(curl -s -H "Metadata-Flavor: Google" \
  http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token \
  | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
echo "\$TOKEN" | docker login -u oauth2accesstoken --password-stdin https://${REGION}-docker.pkg.dev
for s in product cart order; do
  case \$s in product) p=5001;; cart) p=5002;; order) p=5003;; esac
  docker rm -f \$s-service 2>/dev/null
  docker run -d --name \$s-service --restart=always --network=host -e PORT=\$p ${AR}/\$s-service:${TAG}
done
EOF

echo "==> Creating instance template '$TEMPLATE' (${MACHINE_TYPE}, Container-Optimized OS)"
gcloud compute instance-templates describe "$TEMPLATE" >/dev/null 2>&1 || \
  gcloud compute instance-templates create "$TEMPLATE" \
    --machine-type="$MACHINE_TYPE" \
    --image-family=cos-stable --image-project=cos-cloud \
    --boot-disk-size=10GB \
    --tags="$NET_TAG" \
    --scopes=cloud-platform \
    --metadata-from-file=startup-script=startup.sh

echo "==> Firewall: allow Google load balancer + health checks to reach ports 5001-5003"
gcloud compute firewall-rules describe ms-allow-lb >/dev/null 2>&1 || \
  gcloud compute firewall-rules create ms-allow-lb --network=default --direction=INGRESS \
    --allow=tcp:5001-5003 --source-ranges=130.211.0.0/22,35.191.0.0/16 --target-tags="$NET_TAG"

echo "==> Health checks"
gcloud compute health-checks describe "$HC" >/dev/null 2>&1 || \
  gcloud compute health-checks create http "$HC" --use-serving-port --request-path=/health \
    --check-interval=10s --timeout=5s --healthy-threshold=2 --unhealthy-threshold=3
gcloud compute health-checks describe "$HC_AUTOHEAL" >/dev/null 2>&1 || \
  gcloud compute health-checks create http "$HC_AUTOHEAL" --port=5001 --request-path=/health \
    --check-interval=15s --timeout=5s --healthy-threshold=2 --unhealthy-threshold=4

echo "==> Creating regional Managed Instance Group '$MIG' in $REGION (spread over zones = high availability)"
gcloud compute instance-groups managed describe "$MIG" --region="$REGION" >/dev/null 2>&1 || \
  gcloud compute instance-groups managed create "$MIG" --region="$REGION" \
    --template="$TEMPLATE" --size="$MIN_REPLICAS" \
    --health-check="$HC_AUTOHEAL" --initial-delay=180

echo "==> Named ports: product=5001, cart=5002, order=5003"
gcloud compute instance-groups managed set-named-ports "$MIG" --region="$REGION" \
  --named-ports=product:5001,cart:5002,order:5003

echo "==> Autoscaling: min $MIN_REPLICAS, max $MAX_REPLICAS, target CPU $TARGET_CPU"
gcloud compute instance-groups managed set-autoscaling "$MIG" --region="$REGION" \
  --min-num-replicas="$MIN_REPLICAS" --max-num-replicas="$MAX_REPLICAS" \
  --target-cpu-utilization="$TARGET_CPU" --cool-down-period=90

echo; gcloud compute instance-groups managed list-instances "$MIG" --region="$REGION"
echo; echo "Step 2 done. Wait ~2 minutes for the VM(s) to boot, then: bash 3-create-load-balancer.sh"
