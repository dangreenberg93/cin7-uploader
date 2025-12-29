#!/usr/bin/env python3
"""
Test script to search for sales by CustomerReference (PO number)
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from cin7_sales.api_client import Cin7SalesAPI
from database import db
from sqlalchemy import text

def test_po_search():
    """Test searching for a sale by CustomerReference"""
    app = create_app()
    
    with app.app_context():
        # Get credentials for Chida Chida
        # First, let's find the client_erp_credentials_id for Chida Chida
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
            AND (c.name ILIKE '%chida%' OR cec.connection_name ILIKE '%chida%')
            LIMIT 1
        """)
        
        result = db.session.execute(query)
        cred_row = result.fetchone()
        
        if not cred_row:
            print("ERROR: Could not find Chida Chida credentials")
            return False
        
        print(f"Found credentials for: {cred_row.client_name or cred_row.connection_name}")
        print(f"Account ID: {cred_row.account_id}")
        
        # Initialize API client
        api_client = Cin7SalesAPI(
            account_id=str(cred_row.account_id),
            application_key=str(cred_row.application_key),
            base_url='https://inventory.dearsystems.com/ExternalApi/v2/'
        )
        
        # Test search for PO #278324
        po_number = "#278324"
        print(f"\nSearching for sale with CustomerReference: {po_number}")
        
        # Use saleList endpoint with Search parameter
        success, message, results = api_client.search_sales_by_po(po_number)
        
        if success:
            print(f"✓ Search successful!")
            print(f"Found {len(results)} matching sale(s)")
            
            for sale in results:
                print(f"\nSale ID: {sale.get('ID')}")
                print(f"Order Number: {sale.get('OrderNumber')}")
                print(f"Customer Reference: {sale.get('CustomerReference')}")
                print(f"Customer: {sale.get('Customer')}")
                print(f"Status: {sale.get('Status')}")
                print(f"Invoice Number: {sale.get('InvoiceNumber')}")
        else:
            print(f"✗ Search failed: {message}")
            if results:
                print(f"Response: {results}")
        
        return success

if __name__ == '__main__':
    success = test_po_search()
    sys.exit(0 if success else 1)




