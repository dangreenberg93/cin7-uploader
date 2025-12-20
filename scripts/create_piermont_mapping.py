#!/usr/bin/env python3
"""
Script to create the Piermont mapping template via API call
This can be run from the command line or used as a reference
"""

import requests
import json
import sys

# Configuration
API_BASE_URL = "http://localhost:5001/api"  # Adjust if needed
CLIENT_ERP_CREDENTIALS_ID = "1e5b5f04-0b4c-400f-929a-320e13cdcee8"

# MHW WMS export format mapping
MHW_MAPPING = {
    'SaleOrderNumber': 'Order #',
    'CustomerReference': 'PO #',
    'SaleDate': 'Date',
    'Status': 'Status',
    'CustomerCode': 'Customer #',
    'CustomerName': 'Customer Name',
    'SKU': 'Item Code',
    'ProductName': 'Item Description',
    'Price': 'Price',
}

def create_mapping_via_api(token):
    """Create mapping via API"""
    url = f"{API_BASE_URL}/mappings"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "client_erp_credentials_id": CLIENT_ERP_CREDENTIALS_ID,
        "mapping_name": "default",
        "column_mapping": MHW_MAPPING,
        "is_default": True
    }
    
    response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code == 201:
        print("✓ Mapping created successfully!")
        print(json.dumps(response.json(), indent=2))
        return True
    else:
        print(f"✗ Failed to create mapping: {response.status_code}")
        print(response.text)
        return False

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python create_piermont_mapping.py <jwt_token>")
        print("\nTo get a token, log in to the app and check localStorage.getItem('token')")
        print("Or use the Python script with database access instead.")
        sys.exit(1)
    
    token = sys.argv[1]
    create_mapping_via_api(token)



