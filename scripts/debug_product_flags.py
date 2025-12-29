#!/usr/bin/env python3
"""
Debug script to test product flag setting during auto-creation
"""
import sys
import os
import json
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from database import db, SalesOrderUpload, SalesOrderResult, CachedProduct
from routes.webhooks import process_webhook_csv

# Debug logging setup
DEBUG_LOG_PATH = '/Users/dan/Documents/random-projects/cin7-uploader/cin7-uploader/.cursor/debug.log'

def debug_log(location, message, data, hypothesis_id=None):
    """Write debug log entry"""
    log_entry = {
        "sessionId": "debug-product-flags",
        "runId": "run1",
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(datetime.now().timestamp() * 1000)
    }
    with open(DEBUG_LOG_PATH, 'a') as f:
        f.write(json.dumps(log_entry) + '\n')

def test_product_flags():
    """Test product flag setting with instrumentation"""
    
    # Configuration
    client_erp_credentials_id = uuid.UUID('97ff98b6-dd64-48f0-b139-31ee18798e10')
    csv_file_path = 'test_upload_simple.csv'
    
    print("=" * 80)
    print("DEBUGGING PRODUCT FLAG SETTING")
    print("=" * 80)
    print()
    
    app = create_app()
    
    with app.app_context():
        # Step 1: Read CSV file
        print("Step 1: Reading CSV file...")
        try:
            with open(csv_file_path, 'rb') as f:
                csv_content = f.read()
            print(f"   ✓ CSV file read: {len(csv_content)} bytes")
            debug_log("debug_product_flags.py:40", "CSV file read", {"size": len(csv_content)}, "H1")
        except FileNotFoundError:
            print(f"   ✗ CSV file not found: {csv_file_path}")
            return
        except Exception as e:
            print(f"   ✗ Error reading CSV: {str(e)}")
            return
        
        # Step 2: Check existing products in cache before processing
        print("\nStep 2: Checking existing products in cache...")
        from cin7_sales.csv_parser import CSVParser
        parser = CSVParser()
        rows, errors, skipped = parser.parse_file(csv_content, csv_file_path)
        
        # Extract unique SKUs from CSV
        all_skus = set()
        for row in rows:
            row_data = row.get('data', {})
            # Try common SKU column names
            for col in ['Item Code', 'SKU', 'ProductCode', 'ItemCode']:
                if col in row_data and row_data[col]:
                    all_skus.add(str(row_data[col]).strip())
                    break
        
        print(f"   Found {len(all_skus)} unique SKUs in CSV: {sorted(all_skus)}")
        debug_log("debug_product_flags.py:65", "SKUs extracted from CSV", {"skus": list(all_skus), "count": len(all_skus)}, "H2")
        
        # Check which products already exist in cache
        existing_products = {}
        for sku in all_skus:
            cached = CachedProduct.query.filter_by(
                client_erp_credentials_id=client_erp_credentials_id,
                sku=sku
            ).first()
            if cached:
                existing_products[sku] = {
                    'id': str(cached.id),
                    'cin7_product_id': str(cached.cin7_product_id),
                    'is_new': cached.is_new,
                    'created_via_auto_create': cached.created_via_auto_create,
                    'cached_at': cached.cached_at.isoformat() if cached.cached_at else None
                }
        
        print(f"   Found {len(existing_products)} products already in cache:")
        for sku, info in existing_products.items():
            print(f"     - {sku}: is_new={info['is_new']}, created_via_auto_create={info['created_via_auto_create']}")
        
        debug_log("debug_product_flags.py:85", "Existing products in cache", {"existing": existing_products}, "H2")
        
        # Step 3: Create upload record
        print("\nStep 3: Creating upload record...")
        upload_id = uuid.uuid4()
        upload = SalesOrderUpload(
            id=upload_id,
            client_erp_credentials_id=client_erp_credentials_id,
            filename=csv_file_path,
            total_rows=0,
            status='processing',
            created_at=datetime.utcnow()
        )
        db.session.add(upload)
        db.session.commit()
        print(f"   ✓ Upload record created: {upload_id}")
        debug_log("debug_product_flags.py:100", "Upload record created", {"upload_id": str(upload_id)}, "H1")
        
        # Step 4: Process the upload
        print("\nStep 4: Processing upload...")
        print("   This will auto-create products and set flags...")
        
        try:
            result = process_webhook_csv(
                upload_id=upload_id,
                client_erp_credentials_id=client_erp_credentials_id,
                csv_content=csv_content,
                filename=csv_file_path,
                trigger='test',
                user_id=None
            )
            
            print(f"\n   Processing result:")
            print(f"     Successful: {result.get('successful', 0)}")
            print(f"     Failed: {result.get('failed', 0)}")
            debug_log("debug_product_flags.py:120", "Processing completed", result, "H1")
            
        except Exception as e:
            print(f"   ✗ Error processing upload: {str(e)}")
            import traceback
            traceback.print_exc()
            debug_log("debug_product_flags.py:125", "Processing error", {"error": str(e)}, "H4")
            return
        
        # Step 5: Check product flags after processing
        print("\nStep 5: Checking product flags after processing...")
        db.session.expire_all()  # Force refresh from database
        
        final_product_flags = {}
        for sku in all_skus:
            cached = CachedProduct.query.filter_by(
                client_erp_credentials_id=client_erp_credentials_id,
                sku=sku
            ).first()
            
            if cached:
                final_product_flags[sku] = {
                    'id': str(cached.id),
                    'cin7_product_id': str(cached.cin7_product_id),
                    'is_new': cached.is_new,
                    'created_via_auto_create': cached.created_via_auto_create,
                    'cached_at': cached.cached_at.isoformat() if cached.cached_at else None,
                    'updated_at': cached.updated_at.isoformat() if cached.updated_at else None
                }
                status = "✓ FLAGGED" if (cached.is_new and cached.created_via_auto_create) else "✗ NOT FLAGGED"
                print(f"     {status}: {sku} - is_new={cached.is_new}, created_via_auto_create={cached.created_via_auto_create}")
            else:
                final_product_flags[sku] = None
                print(f"     ✗ NOT FOUND: {sku}")
        
        debug_log("debug_product_flags.py:150", "Final product flags", {"flags": final_product_flags}, "H1")
        
        # Step 6: Compare before/after
        print("\nStep 6: Before/After Comparison:")
        for sku in all_skus:
            before = existing_products.get(sku)
            after = final_product_flags.get(sku)
            
            if before and after:
                if before['is_new'] != after['is_new'] or before['created_via_auto_create'] != after['created_via_auto_create']:
                    print(f"     {sku}: FLAGS CHANGED")
                    print(f"       Before: is_new={before['is_new']}, created_via_auto_create={before['created_via_auto_create']}")
                    print(f"       After: is_new={after['is_new']}, created_via_auto_create={after['created_via_auto_create']}")
                else:
                    print(f"     {sku}: FLAGS UNCHANGED (is_new={after['is_new']}, created_via_auto_create={after['created_via_auto_create']})")
            elif not before and after:
                print(f"     {sku}: NEW PRODUCT - is_new={after['is_new']}, created_via_auto_create={after['created_via_auto_create']}")
            elif before and not after:
                print(f"     {sku}: PRODUCT REMOVED (was in cache before)")
            else:
                print(f"     {sku}: NOT FOUND (neither before nor after)")
        
        debug_log("debug_product_flags.py:170", "Before/After comparison", {
            "before": existing_products,
            "after": final_product_flags
        }, "H1")
        
        print("\n" + "=" * 80)
        print("DEBUGGING COMPLETE")
        print("=" * 80)

if __name__ == '__main__':
    test_product_flags()

