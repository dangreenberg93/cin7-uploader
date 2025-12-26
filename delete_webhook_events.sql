-- Delete webhook events from database
-- Webhook uploads are identified by user_id IS NULL
-- Delete in order: API logs -> Order results -> Uploads

-- Step 1: Delete API logs for webhook uploads
DELETE FROM cin7_uploader.cin7_api_log
WHERE upload_id IN (
    SELECT id FROM cin7_uploader.sales_order_upload
    WHERE user_id IS NULL
);

-- Step 2: Delete order results for webhook uploads
DELETE FROM cin7_uploader.sales_order_result
WHERE upload_id IN (
    SELECT id FROM cin7_uploader.sales_order_upload
    WHERE user_id IS NULL
);

-- Step 3: Delete the webhook uploads themselves
DELETE FROM cin7_uploader.sales_order_upload
WHERE user_id IS NULL;

-- Optional: If you want to delete specific uploads by ID, use this instead:
-- Replace 'YOUR_UPLOAD_ID_HERE' with the actual UUID

/*
-- Step 1: Delete API logs for specific upload
DELETE FROM cin7_uploader.cin7_api_log
WHERE upload_id = 'YOUR_UPLOAD_ID_HERE'::UUID;

-- Step 2: Delete order results for specific upload
DELETE FROM cin7_uploader.sales_order_result
WHERE upload_id = 'YOUR_UPLOAD_ID_HERE'::UUID;

-- Step 3: Delete the specific upload
DELETE FROM cin7_uploader.sales_order_upload
WHERE id = 'YOUR_UPLOAD_ID_HERE'::UUID;
*/

-- Optional: If you want to delete by filename pattern:
/*
-- Step 1: Delete API logs
DELETE FROM cin7_uploader.cin7_api_log
WHERE upload_id IN (
    SELECT id FROM cin7_uploader.sales_order_upload
    WHERE user_id IS NULL AND filename LIKE '%Report_15_%'
);

-- Step 2: Delete order results
DELETE FROM cin7_uploader.sales_order_result
WHERE upload_id IN (
    SELECT id FROM cin7_uploader.sales_order_upload
    WHERE user_id IS NULL AND filename LIKE '%Report_15_%'
);

-- Step 3: Delete uploads
DELETE FROM cin7_uploader.sales_order_upload
WHERE user_id IS NULL AND filename LIKE '%Report_15_%';
*/

