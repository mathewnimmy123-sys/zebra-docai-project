#!/bin/bash
# deploy.sh
# =========
# Run from inside the zebra demo folder:
#   chmod +x deploy.sh
#   ./deploy.sh
#
# Redeploys the Cloud Run service and updates the GCP Workflow.

set -e

PROJECT_ID="gci-techss-gcp-pjnp-01nl165115"
REGION="us-central1"
SERVICE_NAME="docai-processor"
WORKFLOW_NAME="document-orchestrator"

echo "==> Deploying Cloud Run service: $SERVICE_NAME"
gcloud run deploy $SERVICE_NAME \
  --source . \
  --region $REGION \
  --project $PROJECT_ID \
  --platform managed \
  --allow-unauthenticated=false \
  --set-env-vars \
    PROJECT_ID=$PROJECT_ID,\
LOCATION=us,\
PROCESSOR_ID_CLASSIFIER=42c3854b109dd5e7,\
PROCESSOR_ID_SPLITTER=4eab05ada7d5eaef,\
ARCHIVE_BUCKET=invoice-processed-archive,\
ERROR_BUCKET=invoice-processing-errors,\
CONFIDENCE_THRESHOLD=0.70 \
  --timeout=120 \
  --memory=512Mi

echo ""
echo "==> Fetching Cloud Run URL..."
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
  --region $REGION \
  --project $PROJECT_ID \
  --format "value(status.url)")
echo "    Service URL: $SERVICE_URL"

echo ""
echo "==> IMPORTANT: Update workflow.yaml line:"
echo "    - service_url: \"$SERVICE_URL\""
echo ""
echo "==> Deploying GCP Workflow: $WORKFLOW_NAME"
gcloud workflows deploy $WORKFLOW_NAME \
  --source=workflow.yaml \
  --location=$REGION \
  --project=$PROJECT_ID

echo ""
echo "==> Done. Test with:"
echo "    curl -X POST $SERVICE_URL/classify \\"
echo "      -H 'Content-Type: application/json' \\"
echo "      -d '{\"bucket\":\"invoice-landing-zone\",\"file\":\"test_invoice.pdf\"}'"
