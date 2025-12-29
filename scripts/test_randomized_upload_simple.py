#!/usr/bin/env python3
"""
Simple test of the upload workflow with randomized CSV file
Tests the actual process_webhook_csv function
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from database import db, SalesOrderUpload, SalesOrderResult, CachedCustomer, CachedProduct
from routes.webhooks import process_webhook_csv
import uuid
import json
from datetime import datetime

app = create_app()

def test_randomized_upload():
    """Test the full workflow with randomized CSV"""
    
    # Configuration
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
        
        # Step 3: Process the upload (this does everything: parse, validate, auto-create, create orders)
        print("\nStep 3: Processing upload (parse + validate + auto-create + create orders)...")
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
        
        # Step 4: Check upload status
        print("\nStep 4: Checking upload status...")
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
        
        # Step 5: Check order results
        print("\nStep 5: Checking order results...")
        results = SalesOrderResult.query.filter_by(upload_id=upload_id).all()
        print(f"   Total order results: {len(results)}")
        
        successful_results = [r for r in results if r.status == 'success']
        failed_results = [r for r in results if r.status != 'success']
        
        print(f"   Successful: {len(successful_results)}")
        print(f"   Failed: {len(failed_results)}")
        
        if successful_results:
            print(f"\n   ✓ Sample successful orders:")
            for result in successful_results[:5]:
                print(f"     - Order {result.order_key}: Sale ID {result.sale_id}, Sale Order ID {result.sale_order_id}")
        
        if failed_results:
            print(f"\n   ✗ Sample failed orders:")
            for result in failed_results[:5]:
                print(f"     - Order {result.order_key}: {result.error_type} - {result.error_message}")
        
        # Step 6: Verify auto-created items
        print("\nStep 6: Verifying auto-created customers/products...")
        
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
        for customer in auto_created_customers[:5]:
            customer_data = json.loads(customer.customer_data) if isinstance(customer.customer_data, str) else customer.customer_data
            print(f"     - {customer_data.get('Name', 'Unknown')} (ID: {customer.cin7_customer_id})")
        
        print(f"   Auto-created products: {len(auto_created_products)}")
        for product in auto_created_products[:5]:
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
        print(f"\nUpload ID: {upload_id}")
        print(f"You can check this upload in the UI or run:")
        print(f"  python3 scripts/diagnose_upload.py {upload_id}")

if __name__ == '__main__':
    test_randomized_upload()



