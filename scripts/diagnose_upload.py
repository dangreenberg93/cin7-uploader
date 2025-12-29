#!/usr/bin/env python3
"""
Diagnose a specific upload to understand cache refresh issues
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from database import SalesOrderUpload, SalesOrderResult, CachedCustomer, CachedProduct, Cin7ApiLog
import uuid
import json
from datetime import datetime

app = create_app()

def diagnose_upload(upload_id_str):
    """Diagnose a specific upload"""
    with app.app_context():
        try:
            upload_id = uuid.UUID(upload_id_str)
        except ValueError:
            print(f"Invalid upload ID format: {upload_id_str}")
            return
        
        print(f"{'='*80}")
        print(f"DIAGNOSING UPLOAD: {upload_id_str}")
        print(f"{'='*80}\n")
        
        # 1. Get upload details
        upload = SalesOrderUpload.query.get(upload_id)
        if not upload:
            print(f"❌ Upload not found: {upload_id_str}")
            return
        
        print(f"1. UPLOAD DETAILS")
        print(f"   Filename: {upload.filename}")
        print(f"   Status: {upload.status}")
        print(f"   Total Rows: {upload.total_rows}")
        print(f"   Successful Orders: {upload.successful_orders}")
        print(f"   Failed Orders: {upload.failed_orders}")
        print(f"   Created At: {upload.created_at}")
        print(f"   Completed At: {upload.completed_at}")
        print(f"   Client ERP Credentials ID: {upload.client_erp_credentials_id}")
        
        if upload.error_log:
            print(f"\n   Error Log:")
            for error in upload.error_log[:10]:  # First 10 errors
                if isinstance(error, dict):
                    print(f"     - Row {error.get('row', '?')}: {error.get('error', error)}")
                else:
                    print(f"     - {error}")
        
        # 2. Get order results
        print(f"\n2. ORDER RESULTS")
        results = SalesOrderResult.query.filter_by(upload_id=upload_id).all()
        print(f"   Total Results: {len(results)}")
        
        failed_results = [r for r in results if r.status != 'success']
        print(f"   Failed Results: {len(failed_results)}")
        
        for i, result in enumerate(failed_results[:5], 1):  # First 5 failed
            print(f"\n   Failed Result {i}:")
            print(f"     Order Key: {result.order_key}")
            print(f"     Status: {result.status}")
            print(f"     Error Type: {result.error_type}")
            print(f"     Error Message: {result.error_message}")
            print(f"     Sale ID: {result.sale_id}")
            print(f"     Sale Order ID: {result.sale_order_id}")
            print(f"     Row Numbers: {result.row_numbers}")
            
            # Check order data
            if result.order_data:
                order_data = result.order_data
                print(f"     Order Data Keys: {list(order_data.keys())}")
                if 'Lines' in order_data:
                    lines = order_data['Lines']
                    print(f"     Number of Lines: {len(lines) if isinstance(lines, list) else 'N/A'}")
                    if isinstance(lines, list) and len(lines) > 0:
                        print(f"     First Line: {json.dumps(lines[0], indent=8)}")
        
        # 3. Check API logs for this upload
        print(f"\n3. API LOGS")
        logs = Cin7ApiLog.query.filter_by(upload_id=upload_id).order_by(Cin7ApiLog.created_at).all()
        print(f"   Total API Calls: {len(logs)}")
        
        # Group by endpoint
        endpoint_counts = {}
        for log in logs:
            endpoint = f"{log.method} {log.endpoint}"
            endpoint_counts[endpoint] = endpoint_counts.get(endpoint, 0) + 1
        
        print(f"\n   API Calls by Endpoint:")
        for endpoint, count in sorted(endpoint_counts.items()):
            print(f"     {endpoint}: {count}")
        
        # Check for customer/product creation
        create_customer_logs = [l for l in logs if 'customer' in l.endpoint.lower() and l.method == 'POST']
        create_product_logs = [l for l in logs if 'product' in l.endpoint.lower() and l.method == 'POST']
        
        print(f"\n   Customer Creation Calls: {len(create_customer_logs)}")
        for log in create_customer_logs[:5]:
            print(f"     - {log.created_at}: Status {log.response_status}")
            if log.response_status == 200 or log.response_status == 201:
                print(f"       ✓ Success")
            else:
                print(f"       ✗ Failed: {log.error_message}")
        
        print(f"\n   Product Creation Calls: {len(create_product_logs)}")
        for log in create_product_logs[:5]:
            print(f"     - {log.created_at}: Status {log.response_status}")
            if log.response_status == 200 or log.response_status == 201:
                print(f"       ✓ Success")
            else:
                print(f"       ✗ Failed: {log.error_message}")
        
        # 4. Check cached customers/products created around upload time
        if upload.client_erp_credentials_id:
            print(f"\n4. CACHED CUSTOMERS/PRODUCTS")
            print(f"   Client ERP Credentials ID: {upload.client_erp_credentials_id}")
            
            # Check customers created around upload time
            time_window_start = upload.created_at
            time_window_end = upload.completed_at if upload.completed_at else datetime.utcnow()
            
            cached_customers = CachedCustomer.query.filter_by(
                client_erp_credentials_id=upload.client_erp_credentials_id,
                created_via_auto_create=True
            ).filter(
                CachedCustomer.updated_at >= time_window_start,
                CachedCustomer.updated_at <= time_window_end
            ).all()
            
            print(f"\n   Auto-Created Customers (during upload window): {len(cached_customers)}")
            for customer in cached_customers[:5]:
                customer_data = json.loads(customer.customer_data) if isinstance(customer.customer_data, str) else customer.customer_data
                customer_name = customer_data.get('Name', 'Unknown')
                print(f"     - {customer_name} (ID: {customer.cin7_customer_id}, Updated: {customer.updated_at})")
            
            cached_products = CachedProduct.query.filter_by(
                client_erp_credentials_id=upload.client_erp_credentials_id,
                created_via_auto_create=True
            ).filter(
                CachedProduct.updated_at >= time_window_start,
                CachedProduct.updated_at <= time_window_end
            ).all()
            
            print(f"\n   Auto-Created Products (during upload window): {len(cached_products)}")
            for product in cached_products[:5]:
                print(f"     - SKU: {product.sku} (ID: {product.cin7_product_id}, Updated: {product.updated_at})")
        
        # 5. Analyze the issue
        print(f"\n5. ANALYSIS")
        print(f"   {'='*80}")
        
        if len(failed_results) > 0:
            # Check if failed results have sale_id but no sale_order_id
            sale_created_no_order = [r for r in failed_results if r.sale_id and not r.sale_order_id]
            if sale_created_no_order:
                print(f"\n   ⚠️  ISSUE DETECTED: {len(sale_created_no_order)} orders have Sale created but no Sale Order")
                print(f"      This suggests the order creation step failed after the sale was created.")
                print(f"      This is consistent with cache refresh issues after auto-creation.")
                
                # Check if these orders have lines
                for result in sale_created_no_order[:3]:
                    if result.order_data and 'Lines' in result.order_data:
                        lines = result.order_data['Lines']
                        if isinstance(lines, list):
                            print(f"\n      Order Key: {result.order_key}")
                            print(f"      Lines in order_data: {len(lines)}")
                            # Check if lines have ProductID
                            lines_with_product = [l for l in lines if l.get('ProductID')]
                            lines_without_product = [l for l in lines if not l.get('ProductID')]
                            print(f"      Lines with ProductID: {len(lines_with_product)}")
                            print(f"      Lines without ProductID: {len(lines_without_product)}")
                            
                            if lines_without_product:
                                print(f"      ⚠️  Some lines are missing ProductID - this is the issue!")
                                for line in lines_without_product[:3]:
                                    print(f"         Line: SKU={line.get('SKU', 'N/A')}, ProductID={line.get('ProductID', 'MISSING')}")
            
            # Check error messages
            cache_errors = [r for r in failed_results if r.error_message and ('not found' in r.error_message.lower() or 'cache' in r.error_message.lower())]
            if cache_errors:
                print(f"\n   ⚠️  {len(cache_errors)} errors mention 'not found' or 'cache'")
                for error in cache_errors[:3]:
                    print(f"      - {error.order_key}: {error.error_message}")
        
        print(f"\n{'='*80}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python diagnose_upload.py <upload_id>")
        sys.exit(1)
    
    upload_id = sys.argv[1]
    diagnose_upload(upload_id)



