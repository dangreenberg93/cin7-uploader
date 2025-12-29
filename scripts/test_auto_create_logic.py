#!/usr/bin/env python3
"""
Test script to verify the auto-create logic flow works correctly.
This simulates the key parts without making actual API calls.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_builder_cache_update():
    """Test that builder cache updates work correctly after auto-create"""
    print("=" * 80)
    print("Testing Builder Cache Update Logic")
    print("=" * 80)
    
    # Simulate the SalesOrderBuilder's lookup logic
    class MockBuilder:
        def __init__(self):
            self._customer_cache = {}
            self.preloaded_customers = {}
            self._product_cache = {}
            self.preloaded_products = {}
        
        def _lookup_customer_by_name(self, customer_name, additional_attribute1=None):
            """Simulate the actual lookup logic"""
            cache_key = f"{customer_name}|{additional_attribute1}"
            
            # Check cache first (this is the critical part)
            if cache_key in self._customer_cache:
                cached_result = self._customer_cache[cache_key]
                print(f"  Cache hit for key '{cache_key}': {cached_result is not None}")
                return cached_result
            
            # Check preloaded data
            if self.preloaded_customers:
                customer_name_clean = customer_name.strip() if customer_name else None
                if customer_name_clean:
                    customer = (self.preloaded_customers.get(customer_name_clean) or 
                               self.preloaded_customers.get(customer_name_clean.upper()) or
                               self.preloaded_customers.get(customer_name_clean.lower()))
                    if customer:
                        self._customer_cache[cache_key] = customer
                        print(f"  Found in preloaded_customers, caching with key '{cache_key}'")
                        return customer
            
            # Not found - cache None
            self._customer_cache[cache_key] = None
            print(f"  Not found, caching None with key '{cache_key}'")
            return None
        
        def _lookup_product_by_sku(self, sku):
            """Simulate product lookup logic"""
            if sku in self._product_cache:
                return self._product_cache[sku]
            
            if self.preloaded_products:
                sku_clean = sku.strip()
                product = (self.preloaded_products.get(sku_clean) or 
                          self.preloaded_products.get(sku_clean.upper()) or
                          self.preloaded_products.get(sku_clean.lower()))
                if product:
                    self._product_cache[sku] = product
                    return product
            
            self._product_cache[sku] = None
            return None
    
    print("\n1. Testing initial lookup (customer doesn't exist yet)")
    builder = MockBuilder()
    customer_name = "Test Customer Alpha"
    result = builder._lookup_customer_by_name(customer_name)
    assert result is None, "Customer should not be found initially"
    print(f"   ✓ Customer not found (as expected)")
    
    print(f"\n2. Simulating auto-create (customer created with ID '12345')")
    create_response = {'ID': '12345', 'Name': customer_name, 'Status': 'Active'}
    
    # Simulate the cache update logic from routes/sales.py
    customer_name_clean = customer_name.strip()
    additional_attribute1 = None  # Simulate no additional attribute
    
    # Update preloaded_customers
    builder.preloaded_customers[customer_name_clean] = create_response
    builder.preloaded_customers[customer_name_clean.upper()] = create_response
    builder.preloaded_customers[customer_name_clean.lower()] = create_response
    
    # Clear ALL cache entries for this customer name
    cache_keys_to_remove = [key for key in builder._customer_cache.keys() if key.startswith(f"{customer_name_clean}|")]
    for key in cache_keys_to_remove:
        del builder._customer_cache[key]
        print(f"   Removed cache key: '{key}'")
    
    # Update cache with the new customer
    cache_key_with_attr = f"{customer_name_clean}|{additional_attribute1}"
    cache_key_no_attr = f"{customer_name_clean}|None"
    builder._customer_cache[cache_key_with_attr] = create_response
    builder._customer_cache[cache_key_no_attr] = create_response
    print(f"   Updated cache with keys: '{cache_key_with_attr}', '{cache_key_no_attr}'")
    
    print(f"\n3. Testing lookup after auto-create")
    result = builder._lookup_customer_by_name(customer_name)
    if result and result.get('ID') == '12345':
        print(f"   ✓ Customer found correctly (ID: {result.get('ID')})")
    else:
        print(f"   ✗ FAILED: Customer not found after auto-create!")
        print(f"     Cache keys: {list(builder._customer_cache.keys())}")
        print(f"     Preloaded keys: {list(builder.preloaded_customers.keys())}")
        return False
    
    print(f"\n4. Testing edge case: None was cached before auto-create")
    builder2 = MockBuilder()
    # First lookup caches None
    builder2._lookup_customer_by_name(customer_name)
    print(f"   Initial lookup cached None")
    
    # Now simulate auto-create
    builder2.preloaded_customers[customer_name_clean] = create_response
    builder2.preloaded_customers[customer_name_clean.upper()] = create_response
    builder2.preloaded_customers[customer_name_clean.lower()] = create_response
    
    # Clear ALL cache entries (this is the fix)
    cache_keys_to_remove = [key for key in builder2._customer_cache.keys() if key.startswith(f"{customer_name_clean}|")]
    print(f"   Clearing {len(cache_keys_to_remove)} cache entries")
    for key in cache_keys_to_remove:
        del builder2._customer_cache[key]
    
    # Update cache
    cache_key_with_attr = f"{customer_name_clean}|{additional_attribute1}"
    cache_key_no_attr = f"{customer_name_clean}|None"
    builder2._customer_cache[cache_key_with_attr] = create_response
    builder2._customer_cache[cache_key_no_attr] = create_response
    
    # Now lookup should work
    result = builder2._lookup_customer_by_name(customer_name)
    if result and result.get('ID') == '12345':
        print(f"   ✓ Customer found correctly even after None was cached (ID: {result.get('ID')})")
    else:
        print(f"   ✗ FAILED: Customer not found after clearing None cache!")
        print(f"     Cache contents: {builder2._customer_cache}")
        return False
    
    print(f"\n5. Testing product lookup logic")
    builder3 = MockBuilder()
    sku = "TEST-SKU-001"
    
    # Initial lookup
    result = builder3._lookup_product_by_sku(sku)
    assert result is None, "Product should not be found initially"
    print(f"   ✓ Product not found initially (as expected)")
    
    # Simulate auto-create
    create_response = {'ID': 'prod-123', 'SKU': sku, 'Name': 'Test Product'}
    sku_clean = sku.strip()
    builder3.preloaded_products[sku_clean] = create_response
    builder3.preloaded_products[sku_clean.upper()] = create_response
    builder3.preloaded_products[sku_clean.lower()] = create_response
    
    # Clear cache
    if sku_clean in builder3._product_cache:
        del builder3._product_cache[sku_clean]
    if sku in builder3._product_cache:
        del builder3._product_cache[sku]
    
    # Update cache
    builder3._product_cache[sku_clean] = create_response
    
    # Lookup should work
    result = builder3._lookup_product_by_sku(sku)
    if result and result.get('ID') == 'prod-123':
        print(f"   ✓ Product found correctly (ID: {result.get('ID')})")
    else:
        print(f"   ✗ FAILED: Product not found after auto-create!")
        return False
    
    print(f"\n{'=' * 80}")
    print("All tests passed! ✓")
    print(f"{'=' * 80}")
    return True


def test_cache_key_variations():
    """Test that cache keys are handled correctly with different additional_attribute1 values"""
    print("\n" + "=" * 80)
    print("Testing Cache Key Variations")
    print("=" * 80)
    
    class MockBuilder:
        def __init__(self):
            self._customer_cache = {}
            self.preloaded_customers = {}
        
        def _lookup_customer_by_name(self, customer_name, additional_attribute1=None):
            cache_key = f"{customer_name}|{additional_attribute1}"
            if cache_key in self._customer_cache:
                return self._customer_cache[cache_key]
            
            if self.preloaded_customers:
                customer_name_clean = customer_name.strip()
                customer = (self.preloaded_customers.get(customer_name_clean) or 
                           self.preloaded_customers.get(customer_name_clean.upper()) or
                           self.preloaded_customers.get(customer_name_clean.lower()))
                if customer:
                    self._customer_cache[cache_key] = customer
                    return customer
            
            self._customer_cache[cache_key] = None
            return None
    
    builder = MockBuilder()
    customer_name = "Test Customer"
    
    # Scenario 1: Lookup with None additional_attribute1
    print(f"\n1. Lookup with additional_attribute1=None")
    builder._lookup_customer_by_name(customer_name, None)
    cache_key1 = f"{customer_name}|None"
    print(f"   Cache key used: '{cache_key1}'")
    assert cache_key1 in builder._customer_cache, "Cache key should exist"
    
    # Scenario 2: Auto-create and update cache
    print(f"\n2. Auto-create customer and update cache")
    create_response = {'ID': '123', 'Name': customer_name}
    customer_name_clean = customer_name.strip()
    builder.preloaded_customers[customer_name_clean] = create_response
    
    # Clear ALL cache entries for this customer
    cache_keys_to_remove = [key for key in builder._customer_cache.keys() if key.startswith(f"{customer_name_clean}|")]
    print(f"   Found {len(cache_keys_to_remove)} cache entries to remove: {cache_keys_to_remove}")
    for key in cache_keys_to_remove:
        del builder._customer_cache[key]
    
    # Update cache with both keys
    additional_attribute1 = None
    cache_key_with_attr = f"{customer_name_clean}|{additional_attribute1}"
    cache_key_no_attr = f"{customer_name_clean}|None"
    builder._customer_cache[cache_key_with_attr] = create_response
    builder._customer_cache[cache_key_no_attr] = create_response
    print(f"   Updated cache with keys: '{cache_key_with_attr}', '{cache_key_no_attr}'")
    
    # Scenario 3: Lookup should now work
    print(f"\n3. Lookup after cache update")
    result = builder._lookup_customer_by_name(customer_name, None)
    if result:
        print(f"   ✓ Customer found (ID: {result.get('ID')})")
    else:
        print(f"   ✗ FAILED: Customer not found!")
        print(f"     Current cache: {builder._customer_cache}")
        return False
    
    print(f"\n{'=' * 80}")
    print("Cache key variation tests passed! ✓")
    print(f"{'=' * 80}")
    return True


if __name__ == '__main__':
    print("\n" + "=" * 80)
    print("AUTO-CREATE LOGIC TEST SUITE")
    print("=" * 80)
    
    test1_passed = test_builder_cache_update()
    test2_passed = test_cache_key_variations()
    
    if test1_passed and test2_passed:
        print("\n" + "=" * 80)
        print("ALL TESTS PASSED ✓")
        print("=" * 80)
        print("\nThe cache update logic should work correctly.")
        print("If it's still failing, the issue might be:")
        print("1. The builder instance is different between auto-create and build_sale")
        print("2. The cache keys don't match exactly (case sensitivity, spacing)")
        print("3. There's a timing issue with database commits")
        sys.exit(0)
    else:
        print("\n" + "=" * 80)
        print("TESTS FAILED ✗")
        print("=" * 80)
        sys.exit(1)



