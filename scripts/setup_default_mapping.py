#!/usr/bin/env python3
"""
Script to set up default CSV mapping for a client_erp_credentials

Usage:
    python setup_default_mapping.py <client_erp_credentials_id>
"""

import sys
import os
import uuid

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from database import db, ClientCsvMapping

def setup_default_mapping(client_erp_credentials_id_str):
    """Set up default mapping for MHW WMS export format"""
    
    try:
        client_erp_credentials_id = uuid.UUID(client_erp_credentials_id_str)
    except ValueError:
        print(f"Error: Invalid UUID format: {client_erp_credentials_id_str}")
        return False
    
    app = create_app()
    
    with app.app_context():
        # Check if default mapping already exists
        existing = ClientCsvMapping.query.filter_by(
            client_erp_credentials_id=client_erp_credentials_id,
            is_default=True
        ).first()
        
        if existing:
            print(f"Default mapping already exists. Updating...")
            existing.column_mapping = get_mhw_mapping()
            existing.mapping_name = 'default'
            db.session.commit()
            print(f"✓ Updated default mapping for client_erp_credentials {client_erp_credentials_id_str}")
        else:
            # Unset any existing defaults
            existing_defaults = ClientCsvMapping.query.filter_by(
                client_erp_credentials_id=client_erp_credentials_id,
                is_default=True
            ).all()
            for existing_default in existing_defaults:
                existing_default.is_default = False
            
            # Create new default mapping
            mapping = ClientCsvMapping(
                id=uuid.uuid4(),
                client_erp_credentials_id=client_erp_credentials_id,
                client_id=None,
                mapping_name='default',
                is_default=True,
                column_mapping=get_mhw_mapping()
            )
            
            db.session.add(mapping)
            db.session.commit()
            print(f"✓ Created default mapping for client_erp_credentials {client_erp_credentials_id_str}")
        
        # Print the mapping
        print("\nMapping configuration:")
        print("-" * 50)
        mapping_obj = ClientCsvMapping.query.filter_by(
            client_erp_credentials_id=client_erp_credentials_id,
            is_default=True
        ).first()
        
        if mapping_obj:
            for cin7_field, csv_column in sorted(mapping_obj.column_mapping.items()):
                print(f"  {cin7_field:25} -> {csv_column}")
        
        return True

def get_mhw_mapping():
    """
    Returns the column mapping for MHW WMS export format (Piermont).
    
    Based on the CSV structure:
    Order #, PO #, Date, Status, Customer #, Customer Name, City, State, 
    Salesperson, Item Code, Item Description, Territory, Region, Price, 
    Extended Price, Line #, ADJ CODE
    
    Mapping requirements:
    - Customer Name: Lookup customer record, get shipping and billing IDs
    - Item Code: Lookup product via SKU
    - PO#: Customer reference
    - Price: Use to build line items
    - Date: Order date
    - Order #: Ignored
    - Status: Ignored (uses default from settings)
    """
    return {
        # Customer - REQUIRED: Will lookup customer and get shipping/billing IDs
        'CustomerName': 'Customer Name',
        
        # Order fields
        'CustomerReference': 'PO #',  # REQUIRED: PO number
        'SaleDate': 'Date',  # REQUIRED: Order date
        # 'SaleOrderNumber': 'Order #',  # IGNORED: Not used
        # 'Status': 'Status',  # IGNORED: Uses default from settings
        
        # Line item fields - REQUIRED
        'SKU': 'Item Code',  # REQUIRED: Will lookup product by SKU
        'Price': 'Price',  # REQUIRED: Unit price for line items
        'ProductName': 'Item Description',  # Optional: Will get from product lookup if not provided
        # Quantity will be calculated from Extended Price / Price if not provided
    }

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python setup_default_mapping.py <client_erp_credentials_id>")
        print("\nExample:")
        print("  python setup_default_mapping.py 1e5b5f04-0b4c-400f-929a-320e13cdcee8")
        sys.exit(1)
    
    client_erp_credentials_id = sys.argv[1]
    
    if setup_default_mapping(client_erp_credentials_id):
        print("\n✓ Default mapping setup completed successfully!")
        sys.exit(0)
    else:
        print("\n✗ Failed to setup default mapping")
        sys.exit(1)



