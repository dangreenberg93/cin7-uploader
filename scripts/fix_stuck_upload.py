#!/usr/bin/env python3
"""
Script to manually fix a stuck upload by marking it as failed.
"""
import sys
import os
import uuid
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from database import db, SalesOrderUpload

def fix_stuck_upload(upload_id_str, mark_as='failed'):
    """Fix a stuck upload by updating its status"""
    app = create_app('production' if os.environ.get('FLASK_ENV') == 'production' else 'development')
    
    with app.app_context():
        try:
            upload_id = uuid.UUID(upload_id_str)
        except ValueError:
            print(f"Invalid upload ID format: {upload_id_str}")
            return False
        
        upload = SalesOrderUpload.query.get(upload_id)
        
        if not upload:
            print(f"Upload {upload_id_str} not found")
            return False
        
        if upload.status != 'processing':
            print(f"Upload is not stuck (status: {upload.status})")
            return False
        
        # Calculate how long it's been processing
        time_diff = datetime.utcnow() - upload.created_at
        minutes = time_diff.total_seconds() / 60
        
        print(f"Upload {upload_id_str}:")
        print(f"  Status: {upload.status}")
        print(f"  Created: {upload.created_at}")
        print(f"  Processing for: {minutes:.1f} minutes")
        print(f"  Total rows: {upload.total_rows}")
        
        # Update status
        upload.status = mark_as
        upload.error_log = upload.error_log or []
        upload.error_log.append(f'Manually marked as {mark_as} - was stuck in processing for {minutes:.1f} minutes (total_rows={upload.total_rows})')
        upload.completed_at = datetime.utcnow()
        db.session.commit()
        
        print(f"\n✅ Upload marked as {mark_as}")
        return True

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python fix_stuck_upload.py <upload_id> [status]")
        print("  status: 'failed' (default) or 'completed'")
        sys.exit(1)
    
    upload_id = sys.argv[1]
    status = sys.argv[2] if len(sys.argv) > 2 else 'failed'
    
    if status not in ['failed', 'completed']:
        print(f"Invalid status: {status}. Must be 'failed' or 'completed'")
        sys.exit(1)
    
    fix_stuck_upload(upload_id, status)

