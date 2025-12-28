# API Logging Fix Summary

## Problem
API calls to Cin7 were not being logged to the `cin7_api_logs` table when CSVs were uploaded.

## Root Causes Identified

1. **Upload record created too late**: The `SalesOrderUpload` record was only created in `/sales/create`, after validation. This meant validation API calls were logged with `upload_id=None`.

2. **Missing upload_id in session**: The `upload_id` was not stored in the session, so validation couldn't link API calls to the upload.

3. **Database session issues**: The callback might be failing silently due to transaction conflicts in background threads.

## Fixes Applied

### 1. Early Upload Record Creation (`routes/sales.py`)
- Modified `/sales/upload` to create the upload record immediately when CSV is uploaded
- Store `upload_id` in the session for use in validation and creation

### 2. Validation Logging (`routes/sales.py`)
- Updated `/sales/validate` to use `upload_id` from session
- Added warning if `upload_id` is missing (for backward compatibility)

### 3. Create Endpoint (`routes/sales.py`)
- Updated `/sales/create` to retrieve existing upload record instead of creating new one
- Added debug logging to track callback invocation

### 4. Webhook Callback Error Handling (`routes/webhooks.py`)
- Improved error handling in logger callback
- Added better logging for debugging callback failures

## Testing Performed

1. **Callback Test**: Verified logger callback works in isolation ✓
2. **Database Diagnostic**: Found that recent uploads have 0 API logs
3. **Flow Analysis**: Confirmed API client correctly invokes callbacks

## Remaining Issues

The diagnostic shows recent uploads still have 0 API logs. Possible causes:

1. **Background thread session issues**: The callback might be failing due to database session conflicts
2. **Silent failures**: Errors in the callback might be caught but not properly logged
3. **Transaction conflicts**: Commits in the callback might conflict with ongoing transactions

## Next Steps for Verification

1. Check application logs for "log_api_call invoked" messages
2. Check for "Error logging API call" messages
3. Verify the callback is being set on the API client (check logs for "API client initialized - logger_callback set: True")
4. Test with a fresh upload to ensure the new code path is used

## Files Modified

- `routes/sales.py`: Early upload creation, session storage, validation logging
- `routes/webhooks.py`: Improved callback error handling
- `scripts/diagnose_api_logging.py`: Diagnostic script
- `scripts/test_logger_callback.py`: Callback test script
- `scripts/test_full_upload_flow.py`: Full flow test script

