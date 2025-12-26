-- Fix webhook tables - make user_id and client_id nullable, create sales_order_result table

-- Make user_id nullable in sales_order_upload
ALTER TABLE cin7_uploader.sales_order_upload 
  ALTER COLUMN user_id DROP NOT NULL;

-- Make client_id nullable in sales_order_upload
ALTER TABLE cin7_uploader.sales_order_upload 
  ALTER COLUMN client_id DROP NOT NULL;

-- Create sales_order_result table if it doesn't exist
CREATE TABLE IF NOT EXISTS cin7_uploader.sales_order_result (
    id UUID PRIMARY KEY,
    upload_id UUID NOT NULL,
    order_key VARCHAR(255) NOT NULL,
    row_numbers JSONB,
    status VARCHAR(50) NOT NULL,
    sale_id UUID,
    sale_order_id UUID,
    error_message TEXT,
    order_data JSONB,
    created_at TIMESTAMP NOT NULL,
    processed_at TIMESTAMP,
    CONSTRAINT fk_sales_order_result_upload 
        FOREIGN KEY (upload_id) 
        REFERENCES cin7_uploader.sales_order_upload(id) 
        ON DELETE CASCADE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS ix_sales_order_result_upload_id 
    ON cin7_uploader.sales_order_result(upload_id);
    
CREATE INDEX IF NOT EXISTS ix_sales_order_result_created_at 
    ON cin7_uploader.sales_order_result(created_at);

