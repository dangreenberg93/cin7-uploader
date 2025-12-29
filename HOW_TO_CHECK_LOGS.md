# How to Check Application Logs

## Production (Google Cloud Run)

Your application is deployed on **Google Cloud Run**, so logs are automatically captured in **Google Cloud Logging**.

### Option 1: Google Cloud Console (Web UI)

1. **Go to Google Cloud Console**:
   - Navigate to: https://console.cloud.google.com
   - Select your project

2. **Open Cloud Logging**:
   - Go to **Logging** → **Logs Explorer**
   - Or direct link: https://console.cloud.google.com/logs/query

3. **Filter for your service**:
   ```
   resource.type="cloud_run_revision"
   resource.labels.service_name="cin7-uploader"
   ```

4. **Search for specific log messages**:
   - To find API logging callbacks: `"log_api_call invoked"`
   - To find successful logs: `"✓ Logged API call"`
   - To find errors: `"✗ Error logging API call"`
   - To find API client initialization: `"API client initialized"`
   - To find upload processing: `"Initializing API client with logger_callback"`

5. **Example query for API logging**:
   ```
   resource.type="cloud_run_revision"
   resource.labels.service_name="cin7-uploader"
   ("log_api_call invoked" OR "✓ Logged API call" OR "✗ Error logging API call" OR "API client initialized")
   ```

### Option 2: Google Cloud CLI (gcloud)

```bash
# Install gcloud CLI if not already installed
# https://cloud.google.com/sdk/docs/install

# Authenticate
gcloud auth login

# Set your project
gcloud config set project YOUR_PROJECT_ID

# View recent logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=cin7-uploader" --limit 50 --format json

# Filter for API logging messages
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=cin7-uploader AND (\"log_api_call invoked\" OR \"✓ Logged API call\" OR \"✗ Error logging API call\")" --limit 100

# Follow logs in real-time
gcloud logging tail "resource.type=cloud_run_revision AND resource.labels.service_name=cin7-uploader"
```

### Option 3: Filter by Upload ID

If you have a specific upload ID, you can search for it:

```
resource.type="cloud_run_revision"
resource.labels.service_name="cin7-uploader"
"YOUR_UPLOAD_ID_HERE"
```

## Local Development

If you're running the app locally:

1. **Terminal/Console Output**: Logs appear directly in the terminal where you run the app
   ```bash
   python app.py
   # or
   gunicorn wsgi:app
   ```

2. **Look for these messages**:
   - `"log_api_call invoked: POST /sale, upload_id: ..."`
   - `"✓ Logged API call: POST /sale - Status: 200"`
   - `"✗ Error logging API call: ..."`
   - `"API client initialized - logger_callback set: True"`

## Key Log Messages to Look For

### Successful API Logging:
- `"log_api_call invoked: {method} {endpoint}, upload_id: {upload_id}"`
- `"✓ Logged API call: {method} {endpoint} - Status: {status}, upload_id: {upload_id}"`
- `"API client initialized - logger_callback set: True"`

### Errors to Watch For:
- `"✗ Error logging API call: {error}"`
- `"Error in logger callback (first attempt): {error}"`
- `"log_api_call called outside of Flask app context!"`
- `"WARNING: upload_id not found in session!"`

### Upload Processing:
- `"Initializing API client with logger_callback for upload_id: {upload_id}"`
- `"Processing CSV from webhook: parse, validate, group orders"`
- `"Creating Sale via API for order {order_key}..."`

## Tips

1. **Time Range**: Set the time range in Cloud Logging to the last hour/day when you made the upload
2. **Severity**: Filter by severity level (INFO, WARNING, ERROR) to focus on important messages
3. **Export**: You can export logs to BigQuery or download as JSON for analysis
4. **Alerts**: Set up log-based alerts for errors if needed

## Quick Test

After uploading a CSV, search for:
```
"log_api_call invoked" AND "upload_id"
```

This should show you all API calls that were logged with an upload_id.



