#!/bin/bash
# Quick deployment script for Google Cloud Run

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ID=${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null)}
REGION=${CLOUD_RUN_REGION:-us-central1}
SERVICE_NAME=${CLOUD_RUN_SERVICE:-cin7-uploader}
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}Error: PROJECT_ID not set. Set GOOGLE_CLOUD_PROJECT or run 'gcloud config set project YOUR_PROJECT_ID'${NC}"
    exit 1
fi

echo -e "${GREEN}Deploying ${SERVICE_NAME} to Cloud Run...${NC}"
echo -e "Project: ${YELLOW}${PROJECT_ID}${NC}"
echo -e "Region: ${YELLOW}${REGION}${NC}"
echo -e "Image: ${YELLOW}${IMAGE_NAME}${NC}"
echo ""

# Build the Docker image
echo -e "${GREEN}Building Docker image...${NC}"
docker build -t ${IMAGE_NAME}:latest .

# Push to Container Registry
echo -e "${GREEN}Pushing image to Container Registry...${NC}"
docker push ${IMAGE_NAME}:latest

# Deploy to Cloud Run
echo -e "${GREEN}Deploying to Cloud Run...${NC}"
gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME}:latest \
    --platform managed \
    --region ${REGION} \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 300 \
    --max-instances 10 \
    --min-instances 0 \
    --set-env-vars FLASK_ENV=production

# Get the service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format 'value(status.url)')

echo ""
echo -e "${GREEN}✓ Deployment complete!${NC}"
echo -e "Service URL: ${YELLOW}${SERVICE_URL}${NC}"
echo -e "Webhook URL: ${YELLOW}${SERVICE_URL}/api/webhooks/email${NC}"
echo ""
echo -e "${YELLOW}Don't forget to set environment variables:${NC}"
echo "  gcloud run services update ${SERVICE_NAME} --region ${REGION} --update-env-vars KEY=VALUE"


