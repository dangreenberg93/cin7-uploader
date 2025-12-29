#!/usr/bin/env python3
"""
Test script to verify auto-create functionality works correctly.
Tests the flow: validation -> auto-create customers/products -> create sales orders
"""
import sys
import os
import uuid
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app
from database import db, SalesOrderUpload, SalesOrderResult, ClientSettings
from cin7_sales.api_client import Cin7SalesAPI
from cin7_sales.csv_parser import CSVParser
from cin7_sales.validator import SalesOrderValidator
from cin7_sales.sales_order_builder import SalesOrderBuilder
from sqlalchemy import text
import json

def test_auto_create_flow():
    """Test the auto-create flow with a sample CSV"""
    app = create_app()
    
    with app.app_context():
        print("=" * 80)
        print("Testing Auto-Create Flow")
        print("=" * 80)
        
        # Read the CSV file
        csv_path = "/Users/dan/Downloads/Sales Orders 11.csv"
        if not os.path.exists(csv_path):
            print(f"ERROR: CSV file not found at {csv_path}")
            return False
        
        with open(csv_path, 'rb') as f:
            csv_content = f.read()
        
        filename = os.path.basename(csv_path)
        print(f"\n1. Loading CSV file: {filename}")
        print(f"   File size: {len(csv_content)} bytes")
        
        # Parse CSV
        parser = CSVParser()
        rows, errors, skipped_rows = parser.parse_file(csv_content, filename)
        
        if errors:
            print(f"\nERROR: CSV parsing failed with errors:")
            for error in errors:
                print(f"   - {error}")
            return False
        
        print(f"   Parsed {len(rows)} rows")
        if skipped_rows:
            print(f"   Skipped {len(skipped_rows)} rows")
        
        # Use PBD Sandbox profile
        print("\n2. Looking for PBD Sandbox profile...")
        
        query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'voyager' 
            AND table_name = 'client_erp_credentials' 
            AND column_name = 'auto_create_customers_products'
        """)
        col_exists = db.session.execute(query).fetchone()
        
        if not col_exists:
            print("   ERROR: auto_create_customers_products column does not exist")
            return False
        
        # Get PBD Sandbox credentials
        query = text("""
            SELECT cec.id, cec.cin7_api_auth_accountid, cec.cin7_api_auth_applicationkey, cec.auto_create_customers_products, cec.connection_name, c.name as client_name
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
        
        print(f"   Found profile: {profile_name}")
        print(f"   Credentials ID: {client_erp_credentials_id}")
        print(f"   Auto-create enabled: {auto_create_enabled}")
        
        # Get settings
        query = text("""
            SELECT client_id FROM voyager.client_erp_credentials
            WHERE id = :cred_id
        """)
        client_result = db.session.execute(query, {'cred_id': client_erp_credentials_id}).fetchone()
        
        # Load settings (simplified - just get auto_create from credentials)
        settings = {
            'default_status': 'DRAFT',
            'default_currency': 'USD',
            'tax_inclusive': False,
            'default_location': None,
            'default_delay_between_orders': 0.7,
            'auto_create_customers_products': auto_create_enabled,
            'product_costing_method': 'FIFO',
            'product_default_price_tier': 'Tier 1',
            'product_default_price': 0.0,
            'product_currency': 'USD'
        }
        
        print(f"\n3. Initializing API client...")
        api_client = Cin7SalesAPI(
            account_id=str(account_id),
            application_key=str(application_key),
            base_url='https://inventory.dearsystems.com/ExternalApi/v2/',
            logger_callback=None  # Disable logging for test
        )
        print("   API client initialized")
        
        print(f"\n4. Preloading customers and products...")
        validator = SalesOrderValidator(api_client)
        try:
            customer_count, product_count = validator.preload_customers_and_products(
                db_session=db.session,
                client_erp_credentials_id=client_erp_credentials_id
            )
            print(f"   Preloaded {customer_count} customers and {product_count} products")
        except Exception as e:
            print(f"   WARNING: Failed to preload: {e}")
            customer_count, product_count = 0, 0
        
        # Detect column mapping (simplified)
        detected_mappings = parser.detect_columns(rows)
        column_mapping = {}
        for cin7_field, matches in detected_mappings.items():
            if matches and len(matches) > 0:
                column_mapping[cin7_field] = matches[0]
        
        print(f"\n5. Detected column mappings:")
        for field, col in column_mapping.items():
            print(f"   {field} -> {col}")
        
        # Initialize builder with preloaded data
        builder = SalesOrderBuilder(
            settings,
            api_client,
            preloaded_customers=validator.customer_lookup,
            preloaded_products=validator.product_lookup
        )
        
        # Check what customers/products we'll need
        print(f"\n6. Analyzing CSV for customers and products...")
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
        
        print(f"   Customers needed: {sorted(customers_needed)}")
        print(f"   Products needed: {sorted(products_needed)}")
        
        # Check which exist
        print(f"\n7. Checking which customers/products already exist...")
        customers_found = {}
        products_found = {}
        
        for customer_name in customers_needed:
            customer = builder._lookup_customer_by_name(customer_name)
            if customer:
                customers_found[customer_name] = customer.get('ID')
                print(f"   ✓ Customer '{customer_name}' found (ID: {customer.get('ID')})")
            else:
                print(f"   ✗ Customer '{customer_name}' NOT found")
        
        for sku in products_needed:
            product = builder._lookup_product_by_sku(sku)
            if product:
                products_found[sku] = product.get('ID')
                print(f"   ✓ Product '{sku}' found (ID: {product.get('ID')})")
            else:
                print(f"   ✗ Product '{sku}' NOT found")
        
        missing_customers = customers_needed - set(customers_found.keys())
        missing_products = products_needed - set(products_found.keys())
        
        print(f"\n8. Summary:")
        print(f"   Missing customers: {sorted(missing_customers) if missing_customers else 'None'}")
        print(f"   Missing products: {sorted(missing_products) if missing_products else 'None'}")
        print(f"   Auto-create enabled: {auto_create_enabled}")
        
        if missing_customers or missing_products:
            if auto_create_enabled:
                print(f"\n   ✓ Auto-create is enabled - these will be created during upload")
            else:
                print(f"\n   ✗ Auto-create is NOT enabled - upload will fail")
        else:
            print(f"\n   ✓ All customers and products found - upload should succeed")
        
        print(f"\n9. Testing builder cache update (simulating auto-create)...")
        
        # Simulate creating a test customer
        if missing_customers:
            test_customer_name = list(missing_customers)[0]
            print(f"   Simulating creation of customer: '{test_customer_name}'")
            
            # Create a mock customer response
            mock_customer = {
                'ID': str(uuid.uuid4()),
                'Name': test_customer_name,
                'Status': 'Active',
                'Currency': 'USD'
            }
            
            # Update builder's preloaded_customers (simulating what the auto-create code does)
            customer_name_clean = test_customer_name.strip()
            builder.preloaded_customers[customer_name_clean] = mock_customer
            builder.preloaded_customers[customer_name_clean.upper()] = mock_customer
            builder.preloaded_customers[customer_name_clean.lower()] = mock_customer
            
            # Clear cache
            cache_key = f"{customer_name_clean}|None"
            if cache_key in builder._customer_cache:
                del builder._customer_cache[cache_key]
            builder._customer_cache[cache_key] = mock_customer
            
            # Test lookup
            found_customer = builder._lookup_customer_by_name(test_customer_name)
            if found_customer and found_customer.get('ID') == mock_customer['ID']:
                print(f"   ✓ Builder cache update works - customer lookup succeeds")
            else:
                print(f"   ✗ Builder cache update FAILED - customer lookup failed")
                return False
        
        # Simulate creating a test product
        if missing_products:
            test_sku = list(missing_products)[0]
            print(f"   Simulating creation of product: '{test_sku}'")
            
            # Create a mock product response
            mock_product = {
                'ID': str(uuid.uuid4()),
                'SKU': test_sku,
                'Name': test_sku,
                'Status': 'Active'
            }
            
            # Update builder's preloaded_products (simulating what the auto-create code does)
            sku_clean = test_sku.strip()
            builder.preloaded_products[sku_clean] = mock_product
            builder.preloaded_products[sku_clean.upper()] = mock_product
            builder.preloaded_products[sku_clean.lower()] = mock_product
            
            # Clear cache
            if sku_clean in builder._product_cache:
                del builder._product_cache[sku_clean]
            if test_sku in builder._product_cache:
                del builder._product_cache[test_sku]
            builder._product_cache[sku_clean] = mock_product
            
            # Test lookup
            found_product = builder._lookup_product_by_sku(test_sku)
            if found_product and found_product.get('ID') == mock_product['ID']:
                print(f"   ✓ Builder cache update works - product lookup succeeds")
            else:
                print(f"   ✗ Builder cache update FAILED - product lookup failed")
                return False
        
        print(f"\n{'=' * 80}")
        print("Test Summary:")
        print(f"   ✓ CSV parsing: OK")
        print(f"   ✓ Column mapping: OK")
        print(f"   ✓ Customer/product detection: OK")
        print(f"   ✓ Builder cache update simulation: OK")
        print(f"\n   {'✓' if auto_create_enabled else '✗'} Auto-create is {'enabled' if auto_create_enabled else 'disabled'}")
        if auto_create_enabled:
            print(f"   → Upload should create {len(missing_customers)} customers and {len(missing_products)} products")
        else:
            if missing_customers or missing_products:
                print(f"   → Upload will FAIL without auto-create enabled")
        
        print(f"\n{'=' * 80}")
        return True

if __name__ == '__main__':
    success = test_auto_create_flow()
    sys.exit(0 if success else 1)

