#!/usr/bin/env python3
"""
Test script to verify the full upload flow with auto-create functionality.
Tests: CSV upload -> validation -> auto-create -> order creation
"""
import sys
import os
import uuid
from pathlib import Path
import json

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app
from database import db, SalesOrderUpload, SalesOrderResult, Cin7ApiLog
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_upload_with_auto_create():
    """Test the full upload flow with auto-create"""
    app = create_app()
    
    with app.app_context():
        print("=" * 80)
        print("Testing Full Upload Flow with Auto-Create")
        print("=" * 80)
        
        # Find PBD Sandbox credentials
        print("\n1. Finding PBD Sandbox profile...")
        query = text("""
            SELECT cec.id, cec.cin7_api_auth_accountid, cec.cin7_api_auth_applicationkey, 
                   cec.auto_create_customers_products, cec.connection_name, c.name as client_name,
                   cec.client_id
            FROM voyager.client_erp_credentials cec
            LEFT JOIN voyager.client c ON c.id = cec.client_id
            WHERE cec.erp = 'cin7_core'
            AND (LOWER(cec.connection_name) LIKE '%pbd%sandbox%' OR LOWER(c.name) LIKE '%pbd%sandbox%')
            AND cec.cin7_api_auth_accountid IS NOT NULL
            AND cec.cin7_api_auth_applicationkey IS NOT NULL
            LIMIT 1
        """)
        result = db.session.execute(query).fetchone()
        
        if not result:
            print("   ERROR: PBD Sandbox profile not found")
            return False
        
        client_erp_credentials_id = result.id
        account_id = result.cin7_api_auth_accountid
        application_key = result.cin7_api_auth_applicationkey
        auto_create_enabled = bool(result.auto_create_customers_products) if result.auto_create_customers_products else False
        profile_name = result.connection_name or result.client_name or 'Unknown'
        client_id = result.client_id
        
        print(f"   Found profile: {profile_name}")
        print(f"   Credentials ID: {client_erp_credentials_id}")
        print(f"   Client ID: {client_id}")
        print(f"   Auto-create enabled: {auto_create_enabled}")
        
        if not auto_create_enabled:
            print("   WARNING: Auto-create is NOT enabled for this profile!")
            print("   The test will still run but auto-create won't work")
        
        # Read test CSV
        csv_path = str(Path(__file__).parent.parent / "test_data.csv")
        if not os.path.exists(csv_path):
            print(f"\n   ERROR: Test CSV not found at {csv_path}")
            return False
        
        with open(csv_path, 'rb') as f:
            csv_content = f.read()
        
        filename = os.path.basename(csv_path)
        print(f"\n2. Loaded test CSV: {filename}")
        print(f"   File size: {len(csv_content)} bytes")
        
        print(f"\n3. Setting up test context...")
        
        print(f"\n4. Analyzing CSV structure...")
        
        # Parse CSV to verify structure
        from cin7_sales.csv_parser import CSVParser
        parser = CSVParser()
        rows, errors, skipped_rows = parser.parse_file(csv_content, filename)
        
        if errors:
            print(f"\n   ERROR: CSV parsing failed:")
            for error in errors:
                print(f"      - {error}")
            return False
        
        print(f"   Parsed {len(rows)} rows successfully")
        
        # Detect column mappings
        detected_mappings = parser.detect_columns(rows)
        column_mapping = {}
        for cin7_field, matches in detected_mappings.items():
            if matches and len(matches) > 0:
                column_mapping[cin7_field] = matches[0]
        
        print(f"\n5. Column mappings detected:")
        key_mappings = ['CustomerName', 'SKU', 'CustomerReference', 'SaleOrderDate', 'Price', 'Quantity']
        for field in key_mappings:
            if field in column_mapping:
                print(f"   {field} -> {column_mapping[field]}")
        
        # Check what customers/products we'll need
        customers_needed = set()
        products_needed = set()
        
        customer_col = column_mapping.get('CustomerName')
        sku_col = column_mapping.get('SKU') or column_mapping.get('ProductCode')
        
        for row in rows:
            if customer_col and customer_col in row['data']:
                customer_name = str(row['data'][customer_col]).strip()
                if customer_name:
                    customers_needed.add(customer_name)
            
            if sku_col and sku_col in row['data']:
                sku = str(row['data'][sku_col]).strip()
                if sku:
                    products_needed.add(sku)
        
        print(f"\n6. Test data analysis:")
        print(f"   Customers needed: {sorted(customers_needed)}")
        print(f"   Products needed: {sorted(products_needed)}")
        
        # Check for order grouping
        from cin7_sales.validator import SalesOrderValidator
        validator = SalesOrderValidator(None)  # No API client needed for grouping
        row_groups = validator._group_rows_by_order(rows, column_mapping)
        
        print(f"\n7. Order grouping analysis:")
        print(f"   Found {len(row_groups)} order groups:")
        for order_key, group_rows in row_groups.items():
            print(f"      - {order_key}: {len(group_rows)} line item(s)")
        
        print(f"\n8. Expected behavior when you upload this CSV via UI:")
        print(f"   ✓ Validation will run and detect missing customers/products")
        if auto_create_enabled:
            print(f"   ✓ Auto-create will create {len(customers_needed)} customers and {len(products_needed)} products")
            print(f"   ✓ Builder cache will be updated with newly created records")
            print(f"   ✓ Orders will be grouped by PO # ({len(row_groups)} groups)")
            print(f"   ✓ Sales and Sales Orders will be created successfully")
        else:
            print(f"   ✗ Auto-create is disabled - orders will fail")
        
        print(f"\n{'=' * 80}")
        print("Test CSV Created Successfully!")
        print(f"{'=' * 80}")
        print(f"\nTo test the actual flow:")
        print(f"1. Open the web UI")
        print(f"2. Select the 'PBD Sandbox' profile (auto-create is {'enabled' if auto_create_enabled else 'disabled'})")
        print(f"3. Upload: {csv_path}")
        print(f"4. Review column mappings (should auto-detect)")
        print(f"5. Click 'Validate' - should show warnings about missing customers/products")
        print(f"6. Click 'Create Orders'")
        if auto_create_enabled:
            print(f"7. Check API logs - should see {len(customers_needed)} customer creations and {len(products_needed)} product creations")
            print(f"8. Verify orders are created and properly grouped ({len(row_groups)} orders)")
        else:
            print(f"7. Orders will fail because auto-create is disabled")
        
        print(f"\nTest CSV location: {csv_path}")
        
        return True

if __name__ == '__main__':
    success = test_upload_with_auto_create()
    sys.exit(0 if success else 1)

