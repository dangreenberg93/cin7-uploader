# How to Filter Application Logs (Not Access Logs)

The logs you're seeing are **HTTP access logs** (gunicorn/nginx), not the **application logs** we need.

## In Google Cloud Console

### Step 1: Go to Logs Explorer
https://console.cloud.google.com/logs/query

### Step 2: Use This Query to Filter for Application Logs

**Exclude HTTP access logs and show only Python application logs:**

```
resource.type="cloud_run_revision"
resource.labels.service_name="cin7-uploader"
NOT httpRequest:*
```

### Step 3: Search for Specific API Logging Messages

**Find callback invocations:**
```
resource.type="cloud_run_revision"
resource.labels.service_name="cin7-uploader"
NOT httpRequest:*
"log_api_call invoked"
```

**Find successful logging:**
```
resource.type="cloud_run_revision"
resource.labels.service_name="cin7-uploader"
NOT httpRequest:*
"✓ Logged API call"
```

**Find errors:**
```
resource.type="cloud_run_revision"
resource.labels.service_name="cin7-uploader"
NOT httpRequest:*
"✗ Error logging API call"
```

**Find API client initialization:**
```
resource.type="cloud_run_revision"
resource.labels.service_name="cin7-uploader"
NOT httpRequest:*
"API client initialized"
```

**Find upload processing:**
```
resource.type="cloud_run_revision"
resource.labels.service_name="cin7-uploader"
NOT httpRequest:*
"Initializing API client with logger_callback"
```

## Using gcloud CLI

Run the script I created:
```bash
./scripts/check_application_logs.sh
```

Or manually:
```bash
# Find callback invocations
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=cin7-uploader AND NOT httpRequest:* AND textPayload=~\"log_api_call invoked\"" --limit 50 --format="table(timestamp,textPayload)" --freshness=1d

# Find all application logs (excluding access logs)
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=cin7-uploader AND NOT httpRequest:*" --limit 100 --format="table(timestamp,severity,textPayload)" --freshness=1d
```

## What to Look For

### Good Signs (Callback is Working):
- `"log_api_call invoked: POST /sale, upload_id: ..."`
- `"✓ Logged API call: POST /sale - Status: 200, upload_id: ..."`
- `"API client initialized - logger_callback set: True"`

### Bad Signs (Issues):
- `"✗ Error logging API call: ..."`
- `"Error in logger callback (first attempt): ..."`
- `"log_api_call called outside of Flask app context!"`
- No logs at all when uploading CSV

## Time Range

Make sure to set the time range to:
- **Last hour** if you just uploaded a CSV
- **Last day** to see recent activity
- **Custom range** around when you made the upload

## Severity Levels

Filter by severity to focus on important messages:
- **INFO**: Normal operation messages
- **WARNING**: Potential issues
- **ERROR**: Actual errors

Add to query: `severity>=WARNING`



