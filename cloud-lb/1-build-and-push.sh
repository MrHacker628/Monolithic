#!/bin/bash
# STEP 1 - Build the 3 microservice images and push them to Artifact Registry.
# Run in Cloud Shell:  bash 1-build-and-push.sh
set -e
cd "$(dirname "$0")"
source ./config.sh

echo "==> Project: $PROJECT   Region: $REGION"
echo "==> Enabling APIs (Compute Engine, Artifact Registry)"
gcloud services enable compute.googleapis.com artifactregistry.googleapis.com

echo "==> Creating Docker repository '$REPO' in Artifact Registry"
gcloud artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$REPO" --repository-format=docker --location="$REGION" \
    --description="ShopEasy microservice images"

echo "==> Letting Docker push to ${REGION}-docker.pkg.dev"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

for s in $SERVICES; do
  IMAGE="$AR/${s}-service:$TAG"
  echo; echo "==> Building $IMAGE"
  docker build -t "$IMAGE" "services/${s}-service"
  echo "==> Pushing $IMAGE"
  docker push "$IMAGE"
done

echo; echo "==> Images now in the registry:"
gcloud artifacts docker images list "$AR" --format="table(package.basename():label=IMAGE,tags,createTime.date('%Y-%m-%d %H:%M'):label=CREATED)"
echo; echo "Step 1 done. Next: bash 2-create-mig.sh"
