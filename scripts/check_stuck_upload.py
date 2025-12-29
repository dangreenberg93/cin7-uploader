#!/usr/bin/env python3
"""
Script to check a specific stuck upload and potentially fix it.
"""
import sys
import os
import uuid
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from database import db, SalesOrderUpload, SalesOrderResult

def check_upload(upload_id_str):
    """Check a specific upload by ID"""
    app = create_app('production' if os.environ.get('FLASK_ENV') == 'production' else 'development')
    
    with app.app_context():
        try:
            upload_id = uuid.UUID(upload_id_str)
        except ValueError:
            print(f"Invalid upload ID format: {upload_id_str}")
            return
        
        upload = SalesOrderUpload.query.get(upload_id)
        
        if not upload:
            print(f"Upload {upload_id_str} not found")
            return
        
        print(f"\n=== Upload Status ===")
        print(f"ID: {upload.id}")
        print(f"Filename: {upload.filename}")
        print(f"Status: {upload.status}")
        print(f"Created at: {upload.created_at}")
        print(f"Completed at: {upload.completed_at}")
        print(f"Total rows: {upload.total_rows}")
        print(f"Successful orders: {upload.successful_orders}")
        print(f"Failed orders: {upload.failed_orders}")
        print(f"Error log: {upload.error_log}")
        
        # Check order results
        results = SalesOrderResult.query.filter_by(upload_id=upload_id).all()
        print(f"\n=== Order Results ===")
        print(f"Total results: {len(results)}")
        
        status_counts = {}
        for result in results:
            status = result.status
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"Status breakdown: {status_counts}")
        
        # Check if stuck (processing for more than 30 minutes)
        if upload.status == 'processing':
            time_diff = datetime.utcnow() - upload.created_at
            minutes = time_diff.total_seconds() / 60
            print(f"\n⚠️  Upload has been processing for {minutes:.1f} minutes")
            
            if minutes > 30:
                print(f"\n❌ Upload appears to be stuck (processing for >30 minutes)")
                print(f"\nOptions:")
                print(f"1. Mark as failed manually")
                print(f"2. Check logs for errors")
                
                response = input("\nMark as failed? (y/n): ")
                if response.lower() == 'y':
                    upload.status = 'failed'
                    upload.error_log = upload.error_log or []
                    upload.error_log.append(f'Manually marked as failed - was stuck in processing for {minutes:.1f} minutes')
                    upload.completed_at = datetime.utcnow()
                    db.session.commit()
                    print(f"✅ Upload marked as failed")
                else:
                    print("Upload status unchanged")
        else:
            print(f"\n✅ Upload status: {upload.status}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python check_stuck_upload.py <upload_id>")
        sys.exit(1)
    
    check_upload(sys.argv[1])

