#!/bin/bash
# STEP 3 - One global external HTTP Load Balancer in front of the instance group.
#   frontend : static IP + forwarding rule (port 80) -> target HTTP proxy -> URL map
#   URL map  : /products*  -> backend service ms-product-bs  (named port product = 5001)
#              /cart*      -> backend service ms-cart-bs     (named port cart    = 5002)
#              /orders*    -> backend service ms-order-bs    (named port order   = 5003)
#              everything else (the web page "/") -> ms-product-bs
# Run in Cloud Shell:  bash 3-create-load-balancer.sh
set -e
cd "$(dirname "$0")"
source ./config.sh

echo "==> Reserving a global static IP '$IP_NAME'"
gcloud compute addresses describe "$IP_NAME" --global >/dev/null 2>&1 || \
  gcloud compute addresses create "$IP_NAME" --global --ip-version=IPV4

for s in $SERVICES; do
  BS="ms-${s}-bs"
  echo "==> Backend service $BS -> $MIG (port name '$s' = ${PORT[$s]})"
  gcloud compute backend-services describe "$BS" --global >/dev/null 2>&1 || {
    gcloud compute backend-services create "$BS" --global --protocol=HTTP --port-name="$s" \
      --health-checks="$HC" --timeout=30s --enable-logging --logging-sample-rate=1.0
    gcloud compute backend-services add-backend "$BS" --global \
      --instance-group="$MIG" --instance-group-region="$REGION" \
      --balancing-mode=UTILIZATION --max-utilization=0.8 --capacity-scaler=1.0
  }
done

echo "==> URL map '$URL_MAP' (path-based routing to the 3 microservices)"
gcloud compute url-maps describe "$URL_MAP" >/dev/null 2>&1 || {
  gcloud compute url-maps create "$URL_MAP" --default-service=ms-product-bs
  gcloud compute url-maps add-path-matcher "$URL_MAP" --path-matcher-name=ms-paths \
    --default-service=ms-product-bs --new-hosts="*" \
    --path-rules="/products=ms-product-bs,/products/*=ms-product-bs,/cart=ms-cart-bs,/cart/*=ms-cart-bs,/orders=ms-order-bs,/orders/*=ms-order-bs"
}

echo "==> Target HTTP proxy '$PROXY' and forwarding rule '$FWD_RULE' (port 80)"
gcloud compute target-http-proxies describe "$PROXY" >/dev/null 2>&1 || \
  gcloud compute target-http-proxies create "$PROXY" --url-map="$URL_MAP"
gcloud compute forwarding-rules describe "$FWD_RULE" --global >/dev/null 2>&1 || \
  gcloud compute forwarding-rules create "$FWD_RULE" --global --address="$IP_NAME" \
    --target-http-proxy="$PROXY" --ports=80

IP=$(gcloud compute addresses describe "$IP_NAME" --global --format="value(address)")
echo
echo "================================================================"
echo " Load balancer IP:  http://$IP"
echo " It takes 5-10 minutes before it starts answering (404/502 until then)."
echo " Check backend health with:  bash status.sh"
echo "================================================================"
