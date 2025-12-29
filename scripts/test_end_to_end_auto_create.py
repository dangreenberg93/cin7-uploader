#!/usr/bin/env python3
"""
Full end-to-end test of the auto-create workflow.
This simulates the complete flow from CSV parsing to order creation.
"""
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cin7_sales.csv_parser import CSVParser
from cin7_sales.sales_order_builder import SalesOrderBuilder
from cin7_sales.validator import SalesOrderValidator


def test_full_workflow():
    """Test the complete workflow end-to-end"""
    print("=" * 80)
    print("END-TO-END AUTO-CREATE WORKFLOW TEST")
    print("=" * 80)
    
    # Mock API client to avoid actual API calls
    class MockAPIClient:
        def __init__(self):
            self.created_customers = {}
            self.created_products = {}
            self.customer_counter = 1
            self.product_counter = 1
        
        def create_customer(self, payload):
            """Simulate customer creation"""
            customer_id = f"cust-{self.customer_counter}"
            self.customer_counter += 1
            response = {
                'ID': customer_id,
                'Name': payload.get('Name'),
                'Status': payload.get('Status', 'Active'),
                'Currency': payload.get('Currency', 'USD')
            }
            self.created_customers[payload.get('Name')] = response
            print(f"      [MOCK API] Created customer '{payload.get('Name')}' with ID {customer_id}")
            return (True, "Success", response)
        
        def create_product(self, payload):
            """Simulate product creation"""
            product_id = f"prod-{self.product_counter}"
            self.product_counter += 1
            response = {
                'ID': product_id,
                'SKU': payload.get('SKU'),
                'Name': payload.get('Name'),
                'Status': payload.get('Status', 'Active')
            }
            self.created_products[payload.get('SKU')] = response
            print(f"      [MOCK API] Created product '{payload.get('SKU')}' with ID {product_id}")
            return (True, "Success", response)
        
        def search_customer(self, name=None):
            """Simulate customer search"""
            if name in self.created_customers:
                return [self.created_customers[name]]
            return []
        
        def search_product(self, sku=None):
            """Simulate product search"""
            if sku in self.created_products:
                return [self.created_products[sku]]
            return []
        
        def get_product(self, sku):
            """Simulate get product by SKU"""
            # Check in created products
            for created_sku, product in self.created_products.items():
                if created_sku == sku or created_sku.upper() == sku.upper():
                    return product
            return None
        
        def get_customer(self, customer_id):
            """Simulate get customer by ID"""
            for customer_name, customer in self.created_customers.items():
                if customer.get('ID') == customer_id:
                    return customer
            return None
    
    print("\n1. Parse CSV file")
    csv_path = Path(__file__).parent.parent / "test_auto_create.csv"
    if not csv_path.exists():
        print(f"   ERROR: Test CSV not found at {csv_path}")
        return False
    
    with open(csv_path, 'rb') as f:
        csv_content = f.read()
    
    parser = CSVParser()
    rows, errors, skipped = parser.parse_file(csv_content, csv_path.name)
    
    if errors:
        print(f"   ✗ CSV parsing failed: {errors}")
        return False
    
    print(f"   ✓ Parsed {len(rows)} rows successfully")
    
    print("\n2. Detect column mappings")
    detected_mappings = parser.detect_columns(rows)
    column_mapping = {}
    for cin7_field, matches in detected_mappings.items():
        if matches and len(matches) > 0:
            column_mapping[cin7_field] = matches[0]
    
    # Ensure SKU is mapped (may need manual mapping)
    if 'SKU' not in column_mapping:
        # Try to find Item Code column
        for row in rows[:1]:
            for col_name in row['data'].keys():
                if 'item' in col_name.lower() and 'code' in col_name.lower():
                    column_mapping['SKU'] = col_name
                    break
    
    print(f"   ✓ Column mappings: {len(column_mapping)} fields mapped")
    print(f"     Key mappings: CustomerName -> {column_mapping.get('CustomerName', 'NOT FOUND')}")
    print(f"                   SKU -> {column_mapping.get('SKU', 'NOT FOUND')}")
    
    if 'SKU' not in column_mapping or 'CustomerName' not in column_mapping:
        print("   ⚠ WARNING: Critical mappings missing - test may not work correctly")
    
    print("\n3. Initialize validator and builder")
    mock_api = MockAPIClient()
    validator = SalesOrderValidator(mock_api)
    
    settings = {
        'default_currency': 'USD',
        'default_status': 'DRAFT',
        'auto_create_customers_products': True,
        'product_costing_method': 'FIFO',
        'product_default_price_tier': 'Tier 1',
        'product_default_price': 0.0,
        'product_currency': 'USD'
    }
    
    builder = SalesOrderBuilder(
        settings,
        mock_api,
        preloaded_customers={},
        preloaded_products={}
    )
    
    print("   ✓ Validator and builder initialized")
    
    print("\n4. Validate rows (simulating validation step)")
    valid_rows, invalid_rows = validator.validate_batch(
        rows,
        column_mapping,
        settings,
        builder=builder
    )
    
    print(f"   Valid rows: {len(valid_rows)}")
    print(f"   Invalid rows: {len(invalid_rows)}")
    
    # Check what customers/products are needed
    customers_needed = set()
    products_needed = set()
    
    customer_col = column_mapping.get('CustomerName')
    sku_col = column_mapping.get('SKU')
    
    for row_result in valid_rows:
        if customer_col and customer_col in row_result['data']:
            customer_name = str(row_result['data'][customer_col]).strip()
            if customer_name:
                customers_needed.add(customer_name)
        
        # Check all rows in group if grouped
        rows_to_check = [row_result['data']]
        if 'group_rows' in row_result:
            rows_to_check = row_result['group_rows']
        
        if sku_col:
            for row_data in rows_to_check:
                sku = row_data.get(sku_col, '')
                if sku:
                    sku = str(sku).strip()
                    if sku:
                        products_needed.add(sku)
    
    print(f"\n5. Analysis - Customers/Products needed:")
    print(f"   Customers: {sorted(customers_needed)}")
    print(f"   Products: {sorted(products_needed)}")
    
    print("\n6. Simulate auto-create workflow (what happens in routes/sales.py)")
    print("   Processing each valid row and auto-creating missing customers/products...")
    
    auto_created_customers = []
    auto_created_products = []
    
    for i, row_result in enumerate(valid_rows, 1):
        print(f"\n   Processing row group {i}/{len(valid_rows)}")
        
        # Extract customer name
        if customer_col and customer_col in row_result['data']:
            customer_name = str(row_result['data'][customer_col]).strip() if row_result['data'][customer_col] else None
            
            if customer_name:
                print(f"      Checking customer: '{customer_name}'")
                
                # Check if customer exists (simulating lookup)
                customer_data = builder._lookup_customer_by_name(customer_name, None)
                
                if not customer_data:
                    print(f"      Customer not found - auto-creating...")
                    
                    # Simulate customer creation (what routes/sales.py does)
                    customer_payload = {
                        'Name': customer_name,
                        'Status': 'Active',
                        'Currency': 'USD',
                        'PaymentTerm': '30 days'
                    }
                    
                    create_success, create_message, create_response = mock_api.create_customer(customer_payload)
                    
                    if create_success and create_response:
                        customer_id = create_response.get('ID')
                        print(f"      Customer created with ID: {customer_id}")
                        
                        # Update builder's preloaded_customers (EXACT code from routes/sales.py)
                        customer_name_clean = customer_name.strip()
                        additional_attribute1 = None
                        
                        builder.preloaded_customers[customer_name_clean] = create_response
                        builder.preloaded_customers[customer_name_clean.upper()] = create_response
                        builder.preloaded_customers[customer_name_clean.lower()] = create_response
                        
                        # Clear ALL cache entries for this customer name
                        cache_keys_to_remove = [key for key in builder._customer_cache.keys() if key.startswith(f"{customer_name_clean}|")]
                        for key in cache_keys_to_remove:
                            del builder._customer_cache[key]
                            print(f"         Cleared cache key: '{key}'")
                        
                        # Update cache
                        cache_key_with_attr = f"{customer_name_clean}|{additional_attribute1}"
                        cache_key_no_attr = f"{customer_name_clean}|None"
                        builder._customer_cache[cache_key_with_attr] = create_response
                        builder._customer_cache[cache_key_no_attr] = create_response
                        
                        auto_created_customers.append(customer_name)
                        print(f"      ✓ Customer cache updated")
                    else:
                        print(f"      ✗ Customer creation failed: {create_message}")
                else:
                    print(f"      Customer already exists (ID: {customer_data.get('ID')})")
        
        # Extract and auto-create products
        rows_to_check = [row_result['data']]
        if 'group_rows' in row_result:
            rows_to_check = row_result['group_rows']
        
        if sku_col:
            for row_data in rows_to_check:
                sku = row_data.get(sku_col, '')
                if sku:
                    sku = str(sku).strip()
                    if sku:
                        print(f"      Checking product: '{sku}'")
                        
                        # Check if product exists
                        product = builder._lookup_product_by_sku(sku)
                        
                        if not product:
                            print(f"      Product not found - auto-creating...")
                            
                            # Get product name
                            product_name_col = column_mapping.get('ProductName') or column_mapping.get('Name')
                            product_name = None
                            if product_name_col and product_name_col in row_data:
                                product_name = str(row_data[product_name_col]).strip() if row_data[product_name_col] else None
                            
                            if not product_name:
                                product_name = sku
                            
                            # Simulate product creation
                            product_payload = {
                                'Name': product_name,
                                'SKU': sku,
                                'Status': 'Active',
                                'Type': 'Stock',
                                'CostingMethod': 'FIFO',
                                'PriceTiers': {'Tier 1': 0.0}
                            }
                            
                            create_success, create_message, create_response = mock_api.create_product(product_payload)
                            
                            if create_success and create_response:
                                product_id = create_response.get('ID')
                                print(f"      Product created with ID: {product_id}")
                                
                                # Update builder's preloaded_products (EXACT code from routes/sales.py)
                                sku_clean = sku.strip()
                                builder.preloaded_products[sku_clean] = create_response
                                builder.preloaded_products[sku_clean.upper()] = create_response
                                builder.preloaded_products[sku_clean.lower()] = create_response
                                
                                # Clear cache
                                if sku_clean in builder._product_cache:
                                    del builder._product_cache[sku_clean]
                                if sku in builder._product_cache:
                                    del builder._product_cache[sku]
                                builder._product_cache[sku_clean] = create_response
                                
                                auto_created_products.append(sku)
                                print(f"      ✓ Product cache updated")
                            else:
                                print(f"      ✗ Product creation failed: {create_message}")
                        else:
                            print(f"      Product already exists (ID: {product.get('ID')})")
    
    print(f"\n7. Auto-create summary:")
    print(f"   Customers auto-created: {len(auto_created_customers)}")
    print(f"   Products auto-created: {len(auto_created_products)}")
    
    print("\n8. Verify customers/products can be found after auto-create")
    print("   Testing lookups...")
    
    all_found = True
    for customer_name in customers_needed:
        result = builder._lookup_customer_by_name(customer_name, None)
        if result and result.get('ID'):
            print(f"   ✓ Customer '{customer_name}' found (ID: {result.get('ID')})")
        else:
            print(f"   ✗ Customer '{customer_name}' NOT FOUND after auto-create!")
            print(f"     Cache keys: {[k for k in builder._customer_cache.keys() if customer_name in k]}")
            print(f"     Preloaded keys: {[k for k in builder.preloaded_customers.keys() if customer_name.lower() in k.lower()]}")
            all_found = False
    
    for sku in products_needed:
        result = builder._lookup_product_by_sku(sku)
        if result and result.get('ID'):
            print(f"   ✓ Product '{sku}' found (ID: {result.get('ID')})")
        else:
            print(f"   ✗ Product '{sku}' NOT FOUND after auto-create!")
            print(f"     Cache: {sku in builder._product_cache}")
            print(f"     Preloaded: {sku in builder.preloaded_products}")
            all_found = False
    
    if not all_found:
        print("\n   ✗ SOME LOOKUPS FAILED - this is the issue!")
        return False
    
    print("\n9. Simulate build_sale() for each row")
    build_failures = []
    
    for i, row_result in enumerate(valid_rows, 1):
        print(f"\n   Building sale for row group {i}/{len(valid_rows)}")
        
        try:
            sale_data = builder.build_sale(row_result['data'], column_mapping)
            
            # Check if CustomerID is set (critical for API call)
            if 'CustomerID' in sale_data and sale_data['CustomerID']:
                customer_name_in_row = row_result['data'].get(customer_col, 'Unknown') if customer_col else 'Unknown'
                print(f"      ✓ Sale payload built successfully")
                print(f"         CustomerID: {sale_data.get('CustomerID')}")
                print(f"         Customer: {sale_data.get('Customer', 'N/A')}")
            else:
                customer_name_in_row = row_result['data'].get(customer_col, 'Unknown') if customer_col else 'Unknown'
                print(f"      ✗ Sale payload missing CustomerID!")
                print(f"         Customer field: {sale_data.get('Customer', 'N/A')}")
                build_failures.append({
                    'row': i,
                    'customer': customer_name_in_row,
                    'issue': 'Missing CustomerID'
                })
        except Exception as e:
            customer_name_in_row = row_result['data'].get(customer_col, 'Unknown') if customer_col else 'Unknown'
            print(f"      ✗ build_sale() failed: {str(e)}")
            build_failures.append({
                'row': i,
                'customer': customer_name_in_row,
                'issue': str(e)
            })
    
    if build_failures:
        print(f"\n   ✗ {len(build_failures)} build failures detected:")
        for failure in build_failures:
            print(f"      Row {failure['row']} ({failure['customer']}): {failure['issue']}")
        return False
    
    print("\n" + "=" * 80)
    print("END-TO-END TEST PASSED ✓")
    print("=" * 80)
    print(f"\nSummary:")
    print(f"  - Parsed {len(rows)} CSV rows")
    print(f"  - Validated {len(valid_rows)} row groups")
    print(f"  - Auto-created {len(auto_created_customers)} customers")
    print(f"  - Auto-created {len(auto_created_products)} products")
    print(f"  - All lookups successful")
    print(f"  - All build_sale() calls successful")
    print(f"\nThe workflow logic is correct!")
    return True


if __name__ == '__main__':
    success = test_full_workflow()
    sys.exit(0 if success else 1)

