#!/usr/bin/env python3
"""
Test script to test customer and product creation with PBD Sandbox
to understand what fields are required for POST requests
"""
import sys
import os
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from cin7_sales.api_client import Cin7SalesAPI
from database import db
from sqlalchemy import text

def test_customer_creation():
    """Test creating a customer with minimal fields"""
    app = create_app()
    
    with app.app_context():
        # Find PBD Sandbox client
        query = text("""
            SELECT 
                cec.id,
                cec.cin7_api_auth_accountid as account_id,
                cec.cin7_api_auth_applicationkey as application_key,
                c.name as client_name,
                cec.connection_name
            FROM voyager.client_erp_credentials cec
            LEFT JOIN voyager.client c ON c.id = cec.client_id
            WHERE cec.erp = 'cin7_core'
            AND (c.name ILIKE '%pbd%sandbox%' OR cec.connection_name ILIKE '%pbd%sandbox%' 
                 OR c.name ILIKE '%sandbox%' OR cec.connection_name ILIKE '%sandbox%')
            LIMIT 1
        """)
        
        result = db.session.execute(query)
        cred_row = result.fetchone()
        
        if not cred_row:
            print("ERROR: Could not find PBD Sandbox credentials")
            print("Trying to find any client with 'pbd' or 'sandbox' in name...")
            # Try broader search
            query2 = text("""
                SELECT 
                    cec.id,
                    cec.cin7_api_auth_accountid as account_id,
                    cec.cin7_api_auth_applicationkey as application_key,
                    c.name as client_name,
                    cec.connection_name
                FROM voyager.client_erp_credentials cec
                LEFT JOIN voyager.client c ON c.id = cec.client_id
                WHERE cec.erp = 'cin7_core'
                LIMIT 5
            """)
            result2 = db.session.execute(query2)
            rows = result2.fetchall()
            if rows:
                print("\nAvailable clients:")
                for row in rows:
                    print(f"  - {row.client_name or row.connection_name} (ID: {row.id})")
            return False
        
        print(f"Found credentials for: {cred_row.client_name or cred_row.connection_name}")
        print(f"Account ID: {cred_row.account_id}\n")
        
        # Initialize API client
        api_client = Cin7SalesAPI(
            account_id=str(cred_row.account_id),
            application_key=str(cred_row.application_key),
            base_url='https://inventory.dearsystems.com/ExternalApi/v2/'
        )
        
        # Test 1: Create customer with minimal fields (Name only)
        print("=" * 80)
        print("TEST 1: Create Customer with minimal fields (Name only)")
        print("=" * 80)
        
        test_customer_name = f"Test Customer {datetime.now().strftime('%Y%m%d%H%M%S')}"
        customer_data_minimal = {
            "Name": test_customer_name
        }
        
        print(f"\nRequest payload:")
        print(json.dumps(customer_data_minimal, indent=2))
        
        success, message, response = api_client.create_customer(customer_data_minimal)
        
        if success:
            print(f"\n✓ Customer created successfully!")
            print(f"Response:")
            print(json.dumps(response, indent=2))
            customer_id = response.get('ID') if isinstance(response, dict) else None
            if customer_id:
                print(f"\nCustomer ID: {customer_id}")
        else:
            print(f"\n✗ Customer creation failed: {message}")
            if response:
                print(f"Response: {json.dumps(response, indent=2)}")
        
        # Test 2: Create customer with all required fields
        print("\n" + "=" * 80)
        print("TEST 2: Create Customer with all required fields")
        print("=" * 80)
        
        # First, let's try to get default values from settings
        # Get customer defaults from credentials
        cred_query = text("""
            SELECT 
                customer_account_receivable,
                customer_revenue_account,
                customer_tax_rule
            FROM voyager.client_erp_credentials
            WHERE id = :cred_id
        """)
        cred_result = db.session.execute(cred_query, {'cred_id': cred_row.id})
        cred_defaults = cred_result.fetchone()
        
        # Get a valid tax rule from Cin7 if customer_tax_rule is not set
        # Note: TaxRule should be the Name, not the ID
        tax_rule_name = None
        if cred_defaults and cred_defaults.customer_tax_rule:
            # If we have a UUID, we need to look up the name
            tax_rule_uuid = str(cred_defaults.customer_tax_rule)
            print(f"Default tax rule UUID found: {tax_rule_uuid}, looking up name...")
            try:
                tax_rules = api_client.get_tax_rules()
                for rule in tax_rules:
                    if str(rule.get('ID')) == tax_rule_uuid:
                        tax_rule_name = rule.get('Name')
                        print(f"Found tax rule name: {tax_rule_name}")
                        break
            except Exception as e:
                print(f"Warning: Could not look up tax rule name: {e}")
        else:
            # Try to get a tax rule from Cin7
            print("No default tax rule found, fetching tax rules from Cin7...")
            try:
                tax_rules = api_client.get_tax_rules()
                if tax_rules and len(tax_rules) > 0:
                    tax_rule_name = tax_rules[0].get('Name')
                    print(f"Using tax rule: {tax_rule_name} (ID: {tax_rules[0].get('ID')})")
            except Exception as e:
                print(f"Warning: Could not fetch tax rules: {e}")
        
        test_customer_name2 = f"Test Customer Full {datetime.now().strftime('%Y%m%d%H%M%S')}"
        customer_data_full = {
            "Name": test_customer_name2,
            "Status": "Active",
            "Currency": "USD",
            "PaymentTerm": "30 days",
            "AccountReceivable": cred_defaults.customer_account_receivable if cred_defaults and cred_defaults.customer_account_receivable else "1200",
            "RevenueAccount": cred_defaults.customer_revenue_account if cred_defaults and cred_defaults.customer_revenue_account else "4000"
        }
        
        # Only add TaxRule if we have a valid name
        if tax_rule_name:
            customer_data_full["TaxRule"] = tax_rule_name
        else:
            print("WARNING: No tax rule available, customer creation may fail")
        
        print(f"\nRequest payload:")
        print(json.dumps(customer_data_full, indent=2))
        
        success2, message2, response2 = api_client.create_customer(customer_data_full)
        
        if success2:
            print(f"\n✓ Customer created successfully!")
            print(f"Response:")
            print(json.dumps(response2, indent=2))
        else:
            print(f"\n✗ Customer creation failed: {message2}")
            if response2:
                print(f"Response: {json.dumps(response2, indent=2)}")
        
        return success or success2

def test_product_creation():
    """Test creating a product with minimal fields"""
    app = create_app()
    
    with app.app_context():
        # Find PBD Sandbox client
        query = text("""
            SELECT 
                cec.id,
                cec.cin7_api_auth_accountid as account_id,
                cec.cin7_api_auth_applicationkey as application_key,
                c.name as client_name,
                cec.connection_name
            FROM voyager.client_erp_credentials cec
            LEFT JOIN voyager.client c ON c.id = cec.client_id
            WHERE cec.erp = 'cin7_core'
            AND (c.name ILIKE '%pbd%sandbox%' OR cec.connection_name ILIKE '%pbd%sandbox%' 
                 OR c.name ILIKE '%sandbox%' OR cec.connection_name ILIKE '%sandbox%')
            LIMIT 1
        """)
        
        result = db.session.execute(query)
        cred_row = result.fetchone()
        
        if not cred_row:
            print("ERROR: Could not find PBD Sandbox credentials")
            return False
        
        print(f"Found credentials for: {cred_row.client_name or cred_row.connection_name}")
        print(f"Account ID: {cred_row.account_id}\n")
        
        # Initialize API client
        api_client = Cin7SalesAPI(
            account_id=str(cred_row.account_id),
            application_key=str(cred_row.application_key),
            base_url='https://inventory.dearsystems.com/ExternalApi/v2/'
        )
        
        # Add create_product method if it doesn't exist (temporary for testing)
        if not hasattr(api_client, 'create_product'):
            import time
            import requests
            import types
            
            def create_product(self, product_data):
                """Create a new product in Cin7"""
                self._rate_limit()
                url = f"{self.base_url}/product"
                endpoint = "/product"
                method = "POST"
                start_time = time.time()
                
                try:
                    response = self.session.post(url, json=product_data, timeout=30)
                    return self._handle_response(response, endpoint, method, url,
                                               dict(self.session.headers), product_data, start_time)
                except requests.exceptions.Timeout:
                    duration_ms = int((time.time() - start_time) * 1000)
                    if self.logger_callback:
                        self.logger_callback(
                            endpoint=endpoint,
                            method=method,
                            request_url=url,
                            request_headers=dict(self.session.headers),
                            request_body=product_data,
                            response_status=None,
                            response_body=None,
                            error_message="Request timeout",
                            duration_ms=duration_ms
                        )
                    return (False, "Request timeout", None)
                except Exception as e:
                    duration_ms = int((time.time() - start_time) * 1000)
                    error_msg = str(e)[:200]
                    if self.logger_callback:
                        self.logger_callback(
                            endpoint=endpoint,
                            method=method,
                            request_url=url,
                            request_headers=dict(self.session.headers),
                            request_body=product_data,
                            response_status=None,
                            response_body=None,
                            error_message=error_msg,
                            duration_ms=duration_ms
                        )
                    return (False, error_msg, None)
            
            api_client.create_product = types.MethodType(create_product, api_client)
        
        # Test 1: Create product with minimal fields (Name and SKU)
        print("=" * 80)
        print("TEST 1: Create Product with minimal fields (Name and SKU)")
        print("=" * 80)
        
        test_sku = f"TEST-SKU-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        product_data_minimal = {
            "Name": f"Test Product {datetime.now().strftime('%Y%m%d%H%M%S')}",
            "SKU": test_sku
        }
        
        print(f"\nRequest payload:")
        print(json.dumps(product_data_minimal, indent=2))
        
        success, message, response = api_client.create_product(product_data_minimal)
        
        if success:
            print(f"\n✓ Product created successfully!")
            print(f"Response:")
            print(json.dumps(response, indent=2))
            product_id = response.get('ID') if isinstance(response, dict) else None
            if product_id:
                print(f"\nProduct ID: {product_id}")
        else:
            print(f"\n✗ Product creation failed: {message}")
            if response:
                print(f"Response: {json.dumps(response, indent=2)}")
        
        # Test 2: Create product with all required fields
        print("\n" + "=" * 80)
        print("TEST 2: Create Product with all required fields")
        print("=" * 80)
        
        # Try to get an existing product to see PriceTiers structure
        print("Checking existing product structure for PriceTiers format...")
        price_tiers_structure = None
        try:
            existing_products = api_client.get_all_products(limit=5)
            if existing_products and len(existing_products) > 0:
                for product in existing_products:
                    price_tiers = product.get('PriceTiers')
                    if price_tiers:
                        price_tiers_structure = price_tiers
                        print(f"Found sample PriceTiers structure: {json.dumps(price_tiers[:1] if isinstance(price_tiers, list) and len(price_tiers) > 0 else price_tiers, indent=2)}")
                        break
                if not price_tiers_structure:
                    print("No PriceTiers found in existing products, will try different formats")
        except Exception as e:
            print(f"Could not fetch sample product: {e}")
        
        test_sku2 = f"TEST-SKU-FULL-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # PriceTiers is a dictionary/object with tier names as keys and prices as values
        # Use the structure we found from existing products
        product_data_full = {
            "Name": f"Test Product Full {datetime.now().strftime('%Y%m%d%H%M%S')}",
            "SKU": test_sku2,
            "Status": "Active",
            "Type": "Stock",
            "CostingMethod": "FIFO",  # Common values: FIFO, LIFO, Average, Standard
            "PriceTiers": {
                "Tier 1": 0.0  # At least one tier is required
            }
        }
        
        print(f"\nRequest payload:")
        print(json.dumps(product_data_full, indent=2))
        
        success2, message2, response2 = api_client.create_product(product_data_full)
        
        if success2:
            print(f"\n✓ Product created successfully!")
            print(f"Response:")
            print(json.dumps(response2, indent=2))
        else:
            print(f"\n✗ Product creation failed: {message2}")
            if response2:
                print(f"Response: {json.dumps(response2, indent=2)}")
        
        return success or success2

if __name__ == '__main__':
    print("Testing Customer and Product Creation with PBD Sandbox")
    print("=" * 80)
    
    print("\n[1/2] Testing Customer Creation")
    print("-" * 80)
    customer_success = test_customer_creation()
    
    print("\n\n[2/2] Testing Product Creation")
    print("-" * 80)
    product_success = test_product_creation()
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Customer creation: {'✓ PASSED' if customer_success else '✗ FAILED'}")
    print(f"Product creation: {'✓ PASSED' if product_success else '✗ FAILED'}")
    
    sys.exit(0 if (customer_success and product_success) else 1)

