#!/usr/bin/env python3
"""
Check if migration is applied and create Piermont mapping if needed
"""

import sys
import os
import uuid

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from database import db, ClientCsvMapping
from sqlalchemy import inspect

def check_migration():
    """Check if the client_erp_credentials_id column exists"""
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('client_csv_mapping', schema='cin7_uploader')]
        return 'client_erp_credentials_id' in columns

def create_piermont_mapping():
    """Create the Piermont mapping"""
    client_erp_credentials_id = uuid.UUID("1e5b5f04-0b4c-400f-929a-320e13cdcee8")
    
    app = create_app()
    with app.app_context():
        # Check if migration is applied
        if not check_migration():
            print("❌ Migration not applied! The client_erp_credentials_id column doesn't exist.")
            print("Please run: flask db upgrade")
            return False
        
        # Check if mapping already exists
        existing = ClientCsvMapping.query.filter_by(
            client_erp_credentials_id=client_erp_credentials_id,
            is_default=True
        ).first()
        
        if existing:
            print(f"✓ Mapping already exists (ID: {existing.id})")
            print(f"  Name: {existing.mapping_name}")
            print(f"  Fields mapped: {len(existing.column_mapping)}")
            return True
        
        # Unset any existing defaults for this client
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
            column_mapping={
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
        )
        
        db.session.add(mapping)
        db.session.commit()
        
        print(f"✓ Created default mapping for Piermont (client_erp_credentials_id: {client_erp_credentials_id})")
        print(f"  Mapping ID: {mapping.id}")
        print(f"  Fields mapped: {len(mapping.column_mapping)}")
        print("\nMapping details:")
        for cin7_field, csv_column in sorted(mapping.column_mapping.items()):
            print(f"  {cin7_field:25} -> {csv_column}")
        
        return True

if __name__ == '__main__':
    try:
        if create_piermont_mapping():
            print("\n✓ Success!")
            sys.exit(0)
        else:
            print("\n✗ Failed")
            sys.exit(1)
    except Exception as e:
        import traceback
        print(f"\n✗ Error: {str(e)}")
        traceback.print_exc()
        sys.exit(1)



