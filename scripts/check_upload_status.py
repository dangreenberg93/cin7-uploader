#!/usr/bin/env python3
"""
Script to check the status of a recent upload and diagnose why orders weren't processed.
"""
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from database import db, SalesOrderUpload, SalesOrderResult, ClientCsvMapping
from sqlalchemy import text

def check_recent_upload(filename="Sales Orders 2.csv"):
    """Check the most recent upload by filename"""
    app = create_app('production' if os.environ.get('FLASK_ENV') == 'production' else 'development')
    
    with app.app_context():
        # Get most recent upload by filename
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        upload = SalesOrderUpload.query.filter(
            SalesOrderUpload.filename.like(f'%{filename}%')
        ).filter(
            SalesOrderUpload.created_at >= one_hour_ago
        ).order_by(SalesOrderUpload.created_at.desc()).first()
        
        if not upload:
            print(f"No upload found for '{filename}' in the last hour")
            # Try without time restriction
            upload = SalesOrderUpload.query.filter(
                SalesOrderUpload.filename.like(f'%{filename}%')
            ).order_by(SalesOrderUpload.created_at.desc()).first()
            if upload:
                print(f"Found older upload (created: {upload.created_at})")
            else:
                print("No upload found with that filename")
                return
        
        cred_id = upload.client_erp_credentials_id
        print(f"Found upload with credentials ID: {cred_id}")
        
        # Check for default mapping
        default_mapping = ClientCsvMapping.query.filter_by(
            client_erp_credentials_id=cred_id,
            is_default=True
        ).first()
        
        if default_mapping:
            print(f"\nDefault mapping found: {default_mapping.mapping_name}")
            print(f"Column mapping: {default_mapping.column_mapping}")
        else:
            print("\n⚠️  NO DEFAULT MAPPING FOUND - This is likely the issue!")
            print("The system needs a default CSV column mapping configured.")
        
        if not upload:
            print("\nNo uploads found in the last hour")
            return
        
        print(f"\n{'='*60}")
        print(f"Most Recent Upload:")
        print(f"{'='*60}")
        print(f"Upload ID: {upload.id}")
        print(f"Filename: {upload.filename}")
        print(f"Status: {upload.status}")
        print(f"Total Rows: {upload.total_rows}")
        print(f"Successful Orders: {upload.successful_orders}")
        print(f"Failed Orders: {upload.failed_orders}")
        print(f"Created At: {upload.created_at}")
        print(f"Completed At: {upload.completed_at}")
        
        if upload.error_log:
            print(f"\nError Log:")
            for error in upload.error_log:
                if isinstance(error, dict):
                    print(f"  - {error.get('message', error)}")
                else:
                    print(f"  - {error}")
        
        # Check order results
        results = SalesOrderResult.query.filter_by(upload_id=upload.id).all()
        print(f"\nOrder Results: {len(results)}")
        for i, result in enumerate(results[:5], 1):  # Show first 5
            print(f"\n  Result {i}:")
            print(f"    Order Key: {result.order_key}")
            print(f"    Status: {result.status}")
            if result.error_message:
                print(f"    Error: {result.error_message}")
            if result.error_type:
                print(f"    Error Type: {result.error_type}")

if __name__ == '__main__':
    filename = sys.argv[1] if len(sys.argv) > 1 else "Sales Orders 2.csv"
    check_recent_upload(filename)

