# Settings shared by all the scripts. Change them here if needed.
PROJECT=$(gcloud config get-value project 2>/dev/null)
REGION=asia-south1                       # Mumbai
REPO=shopeasy-repo                       # Artifact Registry (container registry) repository
AR="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}"
TAG=v1

MACHINE_TYPE=e2-small
MIN_REPLICAS=1                           # scaling rule: minimum instances
MAX_REPLICAS=3                           # scaling rule: maximum instances
TARGET_CPU=0.60                          # scale out when average CPU > 60%

# Resource names
TEMPLATE=ms-template-v2                   # v2 = opens ports 5001-5003 in the COS host firewall
MIG=ms-mig
HC=ms-hc                                 # load balancer health check (checks each service's port)
HC_AUTOHEAL=ms-hc-autoheal               # MIG auto-healing health check
IP_NAME=ms-ip
URL_MAP=ms-urlmap
PROXY=ms-proxy
FWD_RULE=ms-forwarding-rule
NET_TAG=ms-backend
SERVICES="product cart order"            # 3 microservices
declare -A PORT=([product]=5001 [cart]=5002 [order]=5003)

if [ -z "$PROJECT" ]; then
  echo "No project set. Run:  gcloud config set project <PROJECT_ID>"; exit 1
fi
