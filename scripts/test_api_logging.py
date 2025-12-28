#!/usr/bin/env python3
"""
Test script to verify API logging is working correctly
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
app = create_app()
from database import db, SalesOrderUpload, Cin7ApiLog
from sqlalchemy import text
import uuid

def test_api_logging():
    """Test that API logs are being created for uploads"""
    with app.app_context():
        # Find a recent upload
        upload = SalesOrderUpload.query.order_by(SalesOrderUpload.created_at.desc()).first()
        
        if not upload:
            print("No uploads found in database")
            return
        
        print(f"Found upload: {upload.id}")
        print(f"  Status: {upload.status}")
        print(f"  Filename: {upload.filename}")
        print(f"  Created at: {upload.created_at}")
        print(f"  Client ERP Credentials ID: {upload.client_erp_credentials_id}")
        
        # Check for API logs
        logs = Cin7ApiLog.query.filter_by(upload_id=upload.id).all()
        print(f"\nFound {len(logs)} API logs for this upload")
        
        if logs:
            print("\nAPI Logs:")
            for i, log in enumerate(logs[:10], 1):  # Show first 10
                print(f"  {i}. {log.method} {log.endpoint} - Status: {log.response_status}")
                print(f"     Trigger: {log.trigger}, Created: {log.created_at}")
        else:
            print("\nNo API logs found!")
            print("\nChecking all recent API logs...")
            all_logs = Cin7ApiLog.query.order_by(Cin7ApiLog.created_at.desc()).limit(10).all()
            print(f"Found {len(all_logs)} recent API logs in total")
            for log in all_logs:
                print(f"  - {log.method} {log.endpoint} - Upload ID: {log.upload_id}, Trigger: {log.trigger}")
        
        # Check for order results
        from database import SalesOrderResult
        results = SalesOrderResult.query.filter_by(upload_id=upload.id).all()
        print(f"\nFound {len(results)} order results for this upload")
        for result in results:
            print(f"  - Order {result.order_key}: {result.status} (ID: {result.id})")

if __name__ == '__main__':
    test_api_logging()

