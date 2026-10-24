#!/bin/bash
# STEP 1 (alternative) - Build the 3 images with Google Cloud Build and push them to Artifact Registry.
# Use this if `docker push` from Cloud Shell fails with "connection refused".
# Cloud Build runs inside Google's network, so Cloud Shell's network is not involved.
# Run in Cloud Shell:  bash 1b-build-with-cloud-build.sh
set -e
cd "$(dirname "$0")"
source ./config.sh

echo "==> Project: $PROJECT   Region: $REGION"
echo "==> Enabling APIs (Compute Engine, Artifact Registry, Cloud Build)"
gcloud services enable compute.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

echo "==> Docker repository '$REPO' in Artifact Registry"
gcloud artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$REPO" --repository-format=docker --location="$REGION" \
    --description="ShopEasy microservice images"

echo "==> Giving the build service account permission to push images and write logs"
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format="value(projectNumber)")
for SA in "${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" "${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"; do
  for ROLE in roles/artifactregistry.writer roles/storage.objectViewer roles/logging.logWriter; do
    gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" --role="$ROLE" \
      --condition=None >/dev/null 2>&1 || true
  done
done

for s in $SERVICES; do
  IMAGE="$AR/${s}-service:$TAG"
  echo; echo "==> Cloud Build: building and pushing $IMAGE"
  gcloud builds submit "services/${s}-service" --tag="$IMAGE"
done

echo; echo "==> Images now in the registry:"
gcloud artifacts docker images list "$AR" --format="table(package.basename():label=IMAGE,tags,createTime.date('%Y-%m-%d %H:%M'):label=CREATED)"
echo; echo "Step 1 done. Next: bash 2-create-mig.sh"
