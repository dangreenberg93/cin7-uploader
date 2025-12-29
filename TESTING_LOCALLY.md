# Testing API Logging Locally

## Quick Start

### 1. Set Environment Variables

Make sure you have a `.env` file with:
```bash
DATABASE_URL=postgresql://user:password@localhost:5432/database
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret-key
FLASK_ENV=development
CORS_ORIGINS=http://localhost:3000
```

### 2. Start Backend

```bash
# From project root
python app.py
```

The backend will run on `http://localhost:5001` and logs will appear in the terminal.

### 3. Start Frontend (in another terminal)

```bash
cd frontend
npm start
```

The frontend will run on `http://localhost:3000`

## Testing the Upload Flow

### Step 1: Upload a CSV

1. Open `http://localhost:3000` in your browser
2. Select a client
3. Upload a CSV file
4. Watch the **backend terminal** for log messages

### Step 2: Watch for Log Messages

In the backend terminal, you should see:

**Good signs (working):**
```
INFO:routes.sales:log_api_call invoked: POST /sale, upload_id: xxx-xxx-xxx
INFO:routes.sales:✓ Logged API call: POST /sale - Status: 200, upload_id: xxx-xxx-xxx
INFO:routes.sales:API client initialized - logger_callback set: True
```

**Bad signs (not working):**
```
ERROR:routes.sales:✗ Error logging API call: ...
ERROR:routes.webhooks:✗ Error logging API call: ...
```

### Step 3: Validate Data

1. After uploading, click "Validate" in the UI
2. Watch terminal for:
   - `"log_api_call invoked: GET /customer"`
   - `"log_api_call invoked: GET /product"`
   - `"✓ Logged API call"` messages

### Step 4: Create Sales Orders

1. Click "Create Sales Orders"
2. Watch terminal for:
   - `"log_api_call invoked: POST /sale"`
   - `"log_api_call invoked: POST /sale/order"`
   - `"✓ Logged API call"` messages

## Verify API Logs in Database

After testing, run the diagnostic script:

```bash
python3 scripts/diagnose_api_logging.py
```

This will show:
- Recent uploads
- API logs for each upload
- Whether logs have `upload_id` set

## What to Look For

### In Terminal Logs:

1. **Upload creation:**
   ```
   Upload record created successfully - upload_id: xxx-xxx-xxx
   ```

2. **API client initialization:**
   ```
   Initializing API client with logger_callback for upload_id: xxx-xxx-xxx
   API client initialized - logger_callback set: True
   ```

3. **API calls being logged:**
   ```
   log_api_call invoked: POST /sale, upload_id: xxx-xxx-xxx, response_status: 200
   ✓ Logged API call: POST /sale - Status: 200, upload_id: xxx-xxx-xxx
   ```

### In Database (via diagnostic script):

- Uploads should have API logs
- Logs should have `upload_id` set (not NULL)
- Logs should have `trigger` set ('validation' or 'upload')

## Troubleshooting

### No logs appearing?

1. **Check terminal output** - Are there any errors?
2. **Check database connection** - Is `DATABASE_URL` correct?
3. **Check if callback is set:**
   - Look for: `"API client initialized - logger_callback set: True"`
   - If it says `False`, the callback isn't being set

### Errors in logs?

1. **Database errors:**
   - Check `DATABASE_URL` is correct
   - Check database is running
   - Check migrations are up to date

2. **Missing upload_id:**
   - Check: `"WARNING: upload_id not found in session!"`
   - This means the upload wasn't created early enough

## Quick Test Script

After uploading, run:

```bash
# Check recent uploads and their logs
python3 scripts/diagnose_api_logging.py

# Or check specific upload
python3 scripts/test_full_upload_flow.py
```

## Expected Behavior

After the fix:
1. ✅ Upload creates record immediately
2. ✅ `upload_id` stored in session
3. ✅ Validation API calls logged with `upload_id`
4. ✅ Create API calls logged with `upload_id`
5. ✅ All logs appear in database with correct `upload_id`



