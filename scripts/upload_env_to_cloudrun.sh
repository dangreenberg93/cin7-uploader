#!/bin/bash
# Upload .env file to Cloud Run service environment variables

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
ENV_FILE=${1:-.env}
SERVICE_NAME=${CLOUD_RUN_SERVICE:-cin7-uploader}
REGION=${CLOUD_RUN_REGION:-us-central1}

if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}Error: .env file not found: ${ENV_FILE}${NC}"
    echo "Usage: $0 [path/to/.env]"
    exit 1
fi

echo -e "${GREEN}Reading environment variables from ${ENV_FILE}...${NC}"

# Parse .env file and build update command
ENV_VARS=""
while IFS='=' read -r key value || [ -n "$key" ]; do
    # Skip empty lines and comments
    [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
    
    # Remove leading/trailing whitespace
    key=$(echo "$key" | xargs)
    value=$(echo "$value" | xargs)
    
    # Remove quotes if present
    value=$(echo "$value" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
    
    # Skip if key or value is empty
    [[ -z "$key" || -z "$value" ]] && continue
    
    # Add to env vars string
    if [ -z "$ENV_VARS" ]; then
        ENV_VARS="${key}=${value}"
    else
        ENV_VARS="${ENV_VARS},${key}=${value}"
    fi
done < "$ENV_FILE"

if [ -z "$ENV_VARS" ]; then
    echo -e "${YELLOW}Warning: No environment variables found in ${ENV_FILE}${NC}"
    exit 1
fi

echo -e "${GREEN}Updating Cloud Run service: ${SERVICE_NAME}${NC}"
echo -e "${YELLOW}Region: ${REGION}${NC}"
echo ""

# Update Cloud Run service with environment variables
gcloud run services update ${SERVICE_NAME} \
    --region ${REGION} \
    --update-env-vars ${ENV_VARS}

echo ""
echo -e "${GREEN}✓ Environment variables updated successfully!${NC}"
echo ""
echo -e "${YELLOW}Note: Some variables may need to be set as secrets in Cloud Run:${NC}"
echo "  - SECRET_KEY"
echo "  - JWT_SECRET_KEY"
echo "  - DATABASE_URL"
echo "  - GOOGLE_CLIENT_SECRET"
echo ""
echo "To set secrets instead:"
echo "  gcloud secrets create secret-name --data-file=-"
echo "  gcloud run services update ${SERVICE_NAME} --region ${REGION} --update-secrets SECRET_KEY=secret-name:latest"



