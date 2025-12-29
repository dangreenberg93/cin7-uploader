#!/bin/bash
# Script to check application logs for API logging messages

echo "Checking for API logging messages in Cloud Run logs..."
echo ""

# Check for log_api_call invocations
echo "1. Searching for 'log_api_call invoked' messages:"
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=cin7-uploader AND textPayload=~\"log_api_call invoked\"" --limit 20 --format="table(timestamp,textPayload)" --freshness=1d

echo ""
echo "2. Searching for successful API logging ('✓ Logged API call'):"
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=cin7-uploader AND textPayload=~\"✓ Logged API call\"" --limit 20 --format="table(timestamp,textPayload)" --freshness=1d

echo ""
echo "3. Searching for API logging errors ('✗ Error logging API call'):"
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=cin7-uploader AND textPayload=~\"✗ Error logging API call\"" --limit 20 --format="table(timestamp,textPayload)" --freshness=1d

echo ""
echo "4. Searching for API client initialization:"
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=cin7-uploader AND textPayload=~\"API client initialized\"" --limit 20 --format="table(timestamp,textPayload)" --freshness=1d

echo ""
echo "5. Searching for upload processing messages:"
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=cin7-uploader AND textPayload=~\"Initializing API client with logger_callback\"" --limit 20 --format="table(timestamp,textPayload)" --freshness=1d

echo ""
echo "6. All recent application logs (excluding access logs):"
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=cin7-uploader AND NOT httpRequest:*" --limit 30 --format="table(timestamp,severity,textPayload)" --freshness=1d | head -50



