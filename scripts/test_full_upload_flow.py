#!/usr/bin/env python3
"""
Test the full upload flow to verify API logging works end-to-end
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from database import db, SalesOrderUpload, Cin7ApiLog
import uuid
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = create_app()

def test_upload_flow():
    """Test that upload_id is properly set and used"""
    with app.app_context():
        print("=" * 80)
        print("TESTING UPLOAD FLOW")
        print("=" * 80)
        print()
        
        # Check recent uploads and their API logs
        recent_uploads = SalesOrderUpload.query.order_by(SalesOrderUpload.created_at.desc()).limit(5).all()
        
        print("Recent Uploads and their API Logs:")
        print("-" * 80)
        for upload in recent_uploads:
            logs = Cin7ApiLog.query.filter_by(upload_id=upload.id).all()
            print(f"Upload: {upload.id}")
            print(f"  Filename: {upload.filename}")
            print(f"  Status: {upload.status}")
            print(f"  Created: {upload.created_at}")
            print(f"  API Logs: {len(logs)}")
            
            if logs:
                print(f"  Log Details:")
                for log in logs[:3]:
                    print(f"    - {log.method} {log.endpoint} | Status: {log.response_status} | Trigger: {log.trigger}")
            else:
                print(f"  ⚠️  NO API LOGS!")
            print()
        
        # Check if there are any API logs at all in the last hour
        from datetime import datetime, timedelta
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent_logs = Cin7ApiLog.query.filter(Cin7ApiLog.created_at >= one_hour_ago).all()
        
        print(f"API Logs in last hour: {len(recent_logs)}")
        print("-" * 80)
        for log in recent_logs[:10]:
            upload_info = f"Upload: {log.upload_id}" if log.upload_id else "Upload: None"
            print(f"  - {log.method} {log.endpoint} | {upload_info} | Trigger: {log.trigger} | Created: {log.created_at}")
        print()

if __name__ == '__main__':
    test_upload_flow()

