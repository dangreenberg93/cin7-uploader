#!/usr/bin/env python3
"""
Test the upload workflow with randomized CSV file
Expected flow:
1. Initial validation fails (products/customers not found)
2. Auto-create new products and customers
3. Orders are created successfully
4. Workflow completes successfully
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from database import db, SalesOrderUpload, SalesOrderResult, ClientSettings, ClientCsvMapping
from cin7_sales.api_client import Cin7SalesAPI
from cin7_sales.csv_parser import CSVParser
from cin7_sales.validator import SalesOrderValidator
from routes.webhooks import process_webhook_csv
import uuid
import json
from datetime import datetime

app = create_app()

def test_randomized_upload():
    """Test the full workflow with randomized CSV"""
    
    # Configuration - adjust these to match your test environment
    client_erp_credentials_id = uuid.UUID('97ff98b6-dd64-48f0-b139-31ee18798e10')
    csv_file_path = 'test_upload_randomized6.csv'
    
    print("=" * 80)
    print("TESTING RANDOMIZED UPLOAD WORKFLOW")
    print("=" * 80)
    print()
    
    with app.app_context():
        # Step 1: Read CSV file
        print("Step 1: Reading CSV file...")
        try:
            with open(csv_file_path, 'rb') as f:
                csv_content = f.read()
            print(f"   ✓ CSV file read: {len(csv_content)} bytes")
        except FileNotFoundError:
            print(f"   ✗ CSV file not found: {csv_file_path}")
            return
        except Exception as e:
            print(f"   ✗ Error reading CSV: {str(e)}")
            return
        
        # Step 2: Create upload record
        print("\nStep 2: Creating upload record...")
        upload_id = uuid.uuid4()
        upload = SalesOrderUpload(
            id=upload_id,
            client_erp_credentials_id=client_erp_credentials_id,
            filename=csv_file_path,
            total_rows=0,  # Will be updated
            status='processing',
            created_at=datetime.utcnow()
        )
        db.session.add(upload)
        db.session.commit()
        print(f"   ✓ Upload record created: {upload_id}")
        
        # Step 3: Parse CSV
        print("\nStep 3: Parsing CSV...")
        parser = CSVParser()
        rows, errors, skipped_rows = parser.parse_file(csv_content, csv_file_path)
        if errors:
            print(f"   ⚠️  Parsing errors: {errors}")
        if skipped_rows:
            print(f"   ⚠️  Skipped rows: {skipped_rows}")
        print(f"   ✓ Parsed {len(rows)} rows")
        
        # Update upload with row count
        upload.total_rows = len(rows)
        db.session.commit()
        
        # Step 4: Get settings and mapping (from voyager.client_erp_credentials)
        print("\nStep 4: Loading settings and column mapping...")
        from sqlalchemy import text
        
        # Get credentials and settings from voyager.client_erp_credentials
        # Note: base_url is typically 'https://api.cin7.com/api/v1' for Cin7
        creds_query = text("""
            SELECT 
                cec.cin7_api_auth_accountid as api_key,
                cec.cin7_api_auth_applicationkey as api_secret,
                COALESCE(cec.auto_create_customers_products, false) as auto_create_customers_products,
                cec.default_location,
                cec.customer_account_receivable,
                cec.customer_revenue_account,
                cec.customer_tax_rule,
                cec.customer_attribute_set,
                cec.product_costing_method,
                cec.product_default_price_tier,
                cec.product_default_price,
                cec.product_currency
            FROM voyager.client_erp_credentials cec
            WHERE cec.id = :cred_id
            AND cec.erp = 'cin7_core'
        """)
        creds_result = db.session.execute(creds_query, {'cred_id': client_erp_credentials_id}).fetchone()
        
        if not creds_result:
            print("   ✗ No credentials found - cannot proceed")
            return
        
        # Build settings dict
        settings_dict = {
            'api_key': creds_result.api_key,
            'api_secret': creds_result.api_secret,
            'base_url': 'https://api.cin7.com/api/v1',  # Standard Cin7 API URL
            'auto_create_customers_products': bool(creds_result.auto_create_customers_products),
            'default_location': str(creds_result.default_location) if creds_result.default_location else None,
            'customer_account_receivable': creds_result.customer_account_receivable,
            'customer_revenue_account': creds_result.customer_revenue_account,
            'customer_tax_rule': str(creds_result.customer_tax_rule) if creds_result.customer_tax_rule else None,
            'customer_attribute_set': creds_result.customer_attribute_set,
            'product_costing_method': creds_result.product_costing_method or 'FIFO',
            'product_default_price_tier': creds_result.product_default_price_tier or 'Tier 1',
            'product_default_price': float(creds_result.product_default_price) if creds_result.product_default_price else 0.0,
            'product_currency': creds_result.product_currency or 'USD',
            'default_currency': 'USD',
            'tax_rule': None  # Will be set from customer if available
        }
        
        # Get default mapping
        mapping = ClientCsvMapping.query.filter_by(
            client_erp_credentials_id=client_erp_credentials_id,
            is_default=True
        ).first()
        
        if not mapping:
            print("   ✗ No default mapping found - cannot proceed")
            return
        
        column_mapping = mapping.column_mapping
        print(f"   ✓ Settings loaded")
        print(f"   ✓ Column mapping loaded: {len(column_mapping)} columns")
        
        # Check if auto-create is enabled
        auto_create_enabled = settings_dict.get('auto_create_customers_products', False)
        print(f"   ✓ Auto-create enabled: {auto_create_enabled}")
        
        if not auto_create_enabled:
            print("   ⚠️  WARNING: Auto-create is not enabled! This test expects it to be enabled.")
        
        # Step 5: Initial validation (should fail for new customers/products)
        print("\nStep 5: Initial validation (expecting failures for new customers/products)...")
        api_client = Cin7SalesAPI(
            account_id=settings_dict['api_key'],
            application_key=settings_dict['api_secret'],
            base_url=settings_dict['base_url']
        )
        
        validator = SalesOrderValidator(api_client)
        
        # Preload existing customers/products
        customer_count, product_count = validator.preload_customers_and_products(
            db_session=db.session,
            client_erp_credentials_id=client_erp_credentials_id
        )
        print(f"   ✓ Preloaded {customer_count} customers and {product_count} products from cache")
        
        # Validate first few rows to see what's missing
        validation_errors = []
        missing_customers = set()
        missing_products = set()
        
        for i, row_data in enumerate(rows[:5]):  # Check first 5 rows
            # Rows from parse_file are dicts with 'data' key
            row = row_data.get('data', row_data) if isinstance(row_data, dict) and 'data' in row_data else row_data
            errors = validator.validate_row(row, column_mapping)
            if errors:
                validation_errors.extend(errors)
                for error in errors:
                    if 'customer' in error.lower() and 'not found' in error.lower():
                        # Extract customer name
                        customer_col = column_mapping.get('CustomerName', '')
                        if customer_col in row:
                            missing_customers.add(row[customer_col])
                    if 'sku' in error.lower() or 'product' in error.lower():
                        # Extract SKU
                        sku_col = column_mapping.get('SKU', '') or column_mapping.get('ProductCode', '')
                        if sku_col in row:
                            missing_products.add(row[sku_col])
        
        print(f"   ✓ Found {len(validation_errors)} validation errors (expected)")
        print(f"   ✓ Missing customers: {len(missing_customers)} - {list(missing_customers)[:3]}")
        print(f"   ✓ Missing products: {len(missing_products)} - {list(missing_products)[:3]}")
        
        # Step 6: Process the upload (this should auto-create and then create orders)
        print("\nStep 6: Processing upload (auto-create + order creation)...")
        print("   This may take a while...")
        
        try:
            result = process_webhook_csv(
                upload_id=upload_id,
                client_erp_credentials_id=client_erp_credentials_id,
                csv_content=csv_content,
                filename=csv_file_path,
                trigger='test'
            )
            
            print(f"\n   Processing Results:")
            print(f"   - Total orders: {result.get('total_orders', 0)}")
            print(f"   - Successful: {result.get('successful', 0)}")
            print(f"   - Failed: {result.get('failed', 0)}")
            
            if 'error' in result:
                print(f"   ✗ Error: {result.get('error')}")
            
        except Exception as e:
            print(f"   ✗ Error during processing: {str(e)}")
            import traceback
            traceback.print_exc()
            return
        
        # Step 7: Check upload status
        print("\nStep 7: Checking upload status...")
        upload = SalesOrderUpload.query.get(upload_id)
        if upload:
            print(f"   Status: {upload.status}")
            print(f"   Successful orders: {upload.successful_orders}")
            print(f"   Failed orders: {upload.failed_orders}")
            print(f"   Completed at: {upload.completed_at}")
            
            if upload.error_log:
                print(f"   Errors: {len(upload.error_log)}")
                for error in upload.error_log[:3]:
                    print(f"     - {error}")
        else:
            print("   ✗ Upload not found")
        
        # Step 8: Check order results
        print("\nStep 8: Checking order results...")
        results = SalesOrderResult.query.filter_by(upload_id=upload_id).all()
        print(f"   Total order results: {len(results)}")
        
        successful_results = [r for r in results if r.status == 'success']
        failed_results = [r for r in results if r.status != 'success']
        
        print(f"   Successful: {len(successful_results)}")
        print(f"   Failed: {len(failed_results)}")
        
        if successful_results:
            print(f"\n   ✓ Sample successful orders:")
            for result in successful_results[:3]:
                print(f"     - Order {result.order_key}: Sale ID {result.sale_id}, Sale Order ID {result.sale_order_id}")
        
        if failed_results:
            print(f"\n   ✗ Sample failed orders:")
            for result in failed_results[:3]:
                print(f"     - Order {result.order_key}: {result.error_type} - {result.error_message}")
        
        # Step 9: Verify auto-created items
        print("\nStep 9: Verifying auto-created customers/products...")
        from database import CachedCustomer, CachedProduct
        
        # Check for newly created items around upload time
        time_window_start = upload.created_at
        time_window_end = upload.completed_at if upload.completed_at else datetime.utcnow()
        
        auto_created_customers = CachedCustomer.query.filter_by(
            client_erp_credentials_id=client_erp_credentials_id,
            created_via_auto_create=True
        ).filter(
            CachedCustomer.updated_at >= time_window_start,
            CachedCustomer.updated_at <= time_window_end
        ).all()
        
        auto_created_products = CachedProduct.query.filter_by(
            client_erp_credentials_id=client_erp_credentials_id,
            created_via_auto_create=True
        ).filter(
            CachedProduct.updated_at >= time_window_start,
            CachedProduct.updated_at <= time_window_end
        ).all()
        
        print(f"   Auto-created customers: {len(auto_created_customers)}")
        for customer in auto_created_customers[:3]:
            customer_data = json.loads(customer.customer_data) if isinstance(customer.customer_data, str) else customer.customer_data
            print(f"     - {customer_data.get('Name', 'Unknown')} (ID: {customer.cin7_customer_id})")
        
        print(f"   Auto-created products: {len(auto_created_products)}")
        for product in auto_created_products[:3]:
            print(f"     - SKU: {product.sku} (ID: {product.cin7_product_id})")
        
        # Final summary
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        
        if upload.status == 'completed' and len(successful_results) > 0:
            print("✓ WORKFLOW COMPLETED SUCCESSFULLY")
            print(f"  - {len(successful_results)} orders created successfully")
            print(f"  - {len(auto_created_customers)} customers auto-created")
            print(f"  - {len(auto_created_products)} products auto-created")
        elif upload.status == 'failed' or len(failed_results) > 0:
            print("⚠️  WORKFLOW COMPLETED WITH ERRORS")
            print(f"  - {len(successful_results)} orders succeeded")
            print(f"  - {len(failed_results)} orders failed")
            print(f"  - {len(auto_created_customers)} customers auto-created")
            print(f"  - {len(auto_created_products)} products auto-created")
        else:
            print("✗ WORKFLOW FAILED")
            print(f"  - Upload status: {upload.status}")
            print(f"  - No successful orders")
        
        print("=" * 80)

if __name__ == '__main__':
    test_randomized_upload()

