# Testing in Development

This guide explains how to test the webhook and queue features locally.

## Prerequisites

1. **Python 3.9+** installed
2. **Node.js 16+** installed
3. **PostgreSQL database** running (or Supabase connection)
4. **Environment variables** configured in `.env` file

## Step 1: Run Database Migrations

First, apply the new migration for `csv_content` column:

```bash
cd migrations
python run_migration.py
```

Or manually in your database:
```sql
ALTER TABLE cin7_uploader.sales_order_upload 
ADD COLUMN csv_content TEXT;
```

## Step 2: Start Backend (Flask)

In one terminal:

```bash
# Install dependencies if needed
pip install -r requirements.txt

# Set environment (optional, defaults to development)
export FLASK_ENV=development

# Start Flask server
python app.py
```

Backend will run on: `http://localhost:5001`

## Step 3: Start Frontend (React)

In another terminal:

```bash
cd frontend

# Install dependencies if needed
npm install

# Start development server
npm start
```

Frontend will run on: `http://localhost:3000`

The React dev server automatically proxies API requests to `http://localhost:5001`.

## Step 4: Test Webhook Endpoint

### Option A: Using curl (Quick Test)

Create a test webhook payload file `test_webhook.json`:

```json
{
  "subject": "Scheduled Report -> Chida Chida Daily Sales Orders",
  "latest_message": {
    "subject": "Scheduled Report -> Chida Chida Daily Sales Orders",
    "attachments": [
      {
        "filename": "Report_15_2025-12-26_14-00.csv",
        "extension": "csv",
        "url": "https://example.com/test.csv"
      }
    ]
  }
}
```

Then send it:
```bash
curl -X POST http://localhost:5001/api/webhooks/email \
  -H "Content-Type: application/json" \
  -d @test_webhook.json
```

### Option B: Using Python Script

Create `test_webhook.py`:

```python
import requests
import json

# Test webhook payload
payload = {
    "subject": "Scheduled Report -> Chida Chida Daily Sales Orders",
    "latest_message": {
        "subject": "Scheduled Report -> Chida Chida Daily Sales Orders",
        "attachments": [
            {
                "filename": "Report_15_2025-12-26_14-00.csv",
                "extension": "csv",
                "url": "https://example.com/test.csv"  # Replace with actual CSV URL
            }
        ]
    }
}

response = requests.post(
    "http://localhost:5001/api/webhooks/email",
    json=payload
)

print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
```

Run it:
```bash
python test_webhook.py
```

### Option C: Using Postman/Insomnia

1. Create a new POST request
2. URL: `http://localhost:5001/api/webhooks/email`
3. Headers: `Content-Type: application/json`
4. Body (JSON):
```json
{
  "subject": "Scheduled Report -> Chida Chida Daily Sales Orders",
  "latest_message": {
    "subject": "Scheduled Report -> Chida Chida Daily Sales Orders",
    "attachments": [
      {
        "filename": "Report_15_2025-12-26_14-00.csv",
        "extension": "csv",
        "url": "https://your-csv-url.com/file.csv"
      }
    ]
  }
}
```

## Step 5: Test with Real CSV File

To test with an actual CSV file, you need to:

1. **Host the CSV file** somewhere accessible (or use a local file server)
2. **Update the webhook payload** with the actual CSV URL

### Quick Local File Server

```bash
# Python 3
python -m http.server 8000

# Or use a service like ngrok to expose localhost
ngrok http 8000
```

Then use: `http://localhost:8000/Report_15_2025-12-26_14-00.csv` as the URL

## Step 6: View Results in Queue

1. Open browser: `http://localhost:3000`
2. Log in (if required)
3. Navigate to **Queue** page (sidebar → Queue)
4. You should see:
   - Your upload with status "Processing" or "Completed"
   - Expandable order results
   - All mapped columns
   - Matching details (if failed)
   - Retry button (for failed orders)
   - CSV preview button (eye icon)

## Step 7: Test Individual Features

### Test Retry Functionality

1. Find a failed order in the queue
2. Click the **Retry** button
3. The order should re-process
4. Check if it succeeds or fails again

### Test CSV Preview

1. Find an upload with a CSV file
2. Click the **eye icon** next to the filename
3. CSV should download/open in a new tab

### Test Matching Details

1. Expand a failed order
2. Click **"View matching details"**
3. You should see:
   - Customer lookup results
   - Product/SKU lookup results
   - Missing required fields

## Step 8: Test Row Grouping

To verify that only 1 row is picked up (not continuation rows):

1. Use a CSV with continuation rows (like your test file)
2. Send webhook
3. Check queue - should show only 1 order (not multiple)
4. Expand order - should show all rows merged together

## Debugging Tips

### Check Backend Logs

The Flask server will show logs in the terminal:
- Webhook received messages
- Processing status
- Errors

### Check Frontend Console

Open browser DevTools (F12) → Console tab:
- API request/response logs
- Errors

### Check Database

Query the database to see uploads:
```sql
SELECT * FROM cin7_uploader.sales_order_upload 
ORDER BY created_at DESC 
LIMIT 10;

SELECT * FROM cin7_uploader.sales_order_result 
WHERE upload_id = 'your-upload-id';
```

### Test Webhook Endpoint Directly

```bash
# Test endpoint is accessible
curl http://localhost:5001/api/webhooks/email

# Should return 405 Method Not Allowed (expected - needs POST)
```

## Common Issues

### Issue: "No column mapping found"
**Solution**: Set up column mappings in the Mappings page first

### Issue: "Client not found"
**Solution**: Ensure client name in email subject matches a client in the database

### Issue: CORS errors
**Solution**: Check `CORS_ORIGINS` in `.env` includes `http://localhost:3000`

### Issue: Database connection errors
**Solution**: Verify `DATABASE_URL` in `.env` is correct

### Issue: CSV download fails
**Solution**: Ensure the CSV URL in webhook payload is accessible (not behind auth)

## Testing Checklist

- [ ] Backend starts without errors
- [ ] Frontend starts without errors
- [ ] Can send webhook POST request
- [ ] Webhook returns 200 immediately
- [ ] Upload appears in queue
- [ ] Order processing completes
- [ ] All mapped columns visible
- [ ] Matching details show correctly
- [ ] Retry button works
- [ ] CSV preview works
- [ ] Only 1 order per CSV (no duplicate rows)

## Next Steps

Once testing passes locally:
1. Commit changes
2. Deploy to Cloud Run
3. Update Missive webhook URL to production endpoint
4. Test with real email


