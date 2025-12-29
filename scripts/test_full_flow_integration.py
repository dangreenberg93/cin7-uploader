#!/usr/bin/env python3
"""
Integration test that simulates the full flow more accurately
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_real_workflow_simulation():
    """Simulate the actual workflow with the exact code logic"""
    print("=" * 80)
    print("FULL WORKFLOW SIMULATION TEST")
    print("=" * 80)
    
    # Import the actual builder class
    from cin7_sales.sales_order_builder import SalesOrderBuilder
    
    print("\n1. Initialize builder (simulating validation step)")
    settings = {'default_currency': 'USD'}
    builder = SalesOrderBuilder(settings)
    
    # Simulate that validation ran and customer wasn't found (cached None)
    print("\n2. Simulate validation step - customer lookup fails")
    customer_name = "Auto Test Customer One"
    result = builder._lookup_customer_by_name(customer_name, None)
    print(f"   Lookup result: {result is None} (should be None - not found)")
    print(f"   Cache now has: {list(builder._customer_cache.keys())}")
    
    print("\n3. Simulate auto-create step (what happens in routes/sales.py)")
    # Simulate the exact code from routes/sales.py
    create_response = {
        'ID': 'test-customer-id-12345',
        'Name': customer_name,
        'Status': 'Active',
        'Currency': 'USD'
    }
    
    additional_attribute1 = None  # From CSV extraction in routes/sales.py
    customer_name_clean = customer_name.strip()
    
    # Update preloaded_customers (exact code from routes/sales.py)
    builder.preloaded_customers[customer_name_clean] = create_response
    builder.preloaded_customers[customer_name_clean.upper()] = create_response
    builder.preloaded_customers[customer_name_clean.lower()] = create_response
    
    # Clear ALL cache entries (exact code from routes/sales.py)
    cache_keys_to_remove = [key for key in builder._customer_cache.keys() if key.startswith(f"{customer_name_clean}|")]
    print(f"   Clearing {len(cache_keys_to_remove)} cache entries: {cache_keys_to_remove}")
    for key in cache_keys_to_remove:
        del builder._customer_cache[key]
    
    # Update cache (exact code from routes/sales.py)
    cache_key_with_attr = f"{customer_name_clean}|{additional_attribute1}"
    cache_key_no_attr = f"{customer_name_clean}|None"
    builder._customer_cache[cache_key_with_attr] = create_response
    builder._customer_cache[cache_key_no_attr] = create_response
    print(f"   Updated cache with keys: '{cache_key_with_attr}', '{cache_key_no_attr}'")
    print(f"   Cache now has: {list(builder._customer_cache.keys())}")
    
    print("\n4. Simulate build_sale() step - customer lookup")
    # This is what build_sale() does - extracts additional_attribute1 from mapped data
    # In this case, it would be None if not in CSV
    additional_attribute1_from_build = None
    result = builder._lookup_customer_by_name(customer_name, additional_attribute1_from_build)
    
    if result and result.get('ID') == 'test-customer-id-12345':
        print(f"   ✓ SUCCESS: Customer found correctly (ID: {result.get('ID')})")
        print(f"   Cache key used: '{customer_name}|{additional_attribute1_from_build}'")
        return True
    else:
        print(f"   ✗ FAILED: Customer not found!")
        print(f"   Result: {result}")
        print(f"   Cache contents: {builder._customer_cache}")
        print(f"   Preloaded customers keys: {list(builder.preloaded_customers.keys())}")
        return False


def test_product_workflow():
    """Test product workflow similarly"""
    print("\n" + "=" * 80)
    print("PRODUCT WORKFLOW SIMULATION")
    print("=" * 80)
    
    from cin7_sales.sales_order_builder import SalesOrderBuilder
    
    builder = SalesOrderBuilder({})
    sku = "AUTO-SKU-100"
    
    print(f"\n1. Initial lookup (not found)")
    result = builder._lookup_product_by_sku(sku)
    print(f"   Result: {result is None} (should be None)")
    
    print(f"\n2. Auto-create product")
    create_response = {'ID': 'prod-123', 'SKU': sku, 'Name': 'Test Product'}
    sku_clean = sku.strip()
    
    # Update preloaded_products (exact code from routes/sales.py)
    builder.preloaded_products[sku_clean] = create_response
    builder.preloaded_products[sku_clean.upper()] = create_response
    builder.preloaded_products[sku_clean.lower()] = create_response
    
    # Clear cache (exact code from routes/sales.py)
    if sku_clean in builder._product_cache:
        del builder._product_cache[sku_clean]
    if sku in builder._product_cache:
        del builder._product_cache[sku]
    
    # Update cache
    builder._product_cache[sku_clean] = create_response
    
    print(f"\n3. Lookup after auto-create")
    result = builder._lookup_product_by_sku(sku)
    if result and result.get('ID') == 'prod-123':
        print(f"   ✓ SUCCESS: Product found correctly (ID: {result.get('ID')})")
        return True
    else:
        print(f"   ✗ FAILED: Product not found!")
        return False


if __name__ == '__main__':
    test1 = test_real_workflow_simulation()
    test2 = test_product_workflow()
    
    print("\n" + "=" * 80)
    if test1 and test2:
        print("ALL INTEGRATION TESTS PASSED ✓")
        print("=" * 80)
        print("\nThe logic is correct. If it's still failing in production,")
        print("check server logs to see what's happening during actual execution.")
        sys.exit(0)
    else:
        print("INTEGRATION TESTS FAILED ✗")
        print("=" * 80)
        sys.exit(1)



