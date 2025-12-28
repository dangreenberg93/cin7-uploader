#!/usr/bin/env python3
"""
Diagnostic script to check API logging status
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from database import db, SalesOrderUpload, Cin7ApiLog, SalesOrderResult
from sqlalchemy import text, desc
from datetime import datetime, timedelta

app = create_app()

def diagnose_api_logging():
    """Diagnose API logging issues"""
    with app.app_context():
        print("=" * 80)
        print("API LOGGING DIAGNOSTIC REPORT")
        print("=" * 80)
        print()
        
        # 1. Check recent uploads
        print("1. RECENT UPLOADS (last 10):")
        print("-" * 80)
        recent_uploads = SalesOrderUpload.query.order_by(desc(SalesOrderUpload.created_at)).limit(10).all()
        
        if not recent_uploads:
            print("   No uploads found in database")
        else:
            for upload in recent_uploads:
                print(f"   Upload ID: {upload.id}")
                print(f"   Filename: {upload.filename}")
                print(f"   Status: {upload.status}")
                print(f"   Created: {upload.created_at}")
                print(f"   Client ERP Credentials ID: {upload.client_erp_credentials_id}")
                print(f"   Total Rows: {upload.total_rows}")
                print()
        
        # 2. Check API logs for recent uploads
        print("2. API LOGS FOR RECENT UPLOADS:")
        print("-" * 80)
        for upload in recent_uploads[:5]:  # Check first 5
            logs = Cin7ApiLog.query.filter_by(upload_id=upload.id).all()
            print(f"   Upload {upload.id} ({upload.filename}):")
            print(f"      Status: {upload.status}")
            print(f"      API Logs: {len(logs)}")
            
            if logs:
                print(f"      Log Details:")
                for log in logs[:5]:  # Show first 5 logs
                    print(f"        - {log.method} {log.endpoint} | Status: {log.response_status} | Trigger: {log.trigger} | Created: {log.created_at}")
            else:
                print(f"      ⚠️  NO API LOGS FOUND!")
            print()
        
        # 3. Check all recent API logs (regardless of upload_id)
        print("3. ALL RECENT API LOGS (last 20, regardless of upload_id):")
        print("-" * 80)
        all_logs = Cin7ApiLog.query.order_by(desc(Cin7ApiLog.created_at)).limit(20).all()
        
        if not all_logs:
            print("   ⚠️  No API logs found in database at all!")
        else:
            print(f"   Found {len(all_logs)} recent API logs")
            for log in all_logs:
                upload_info = f"Upload: {log.upload_id}" if log.upload_id else "Upload: None"
                print(f"   - {log.method} {log.endpoint} | Status: {log.response_status} | {upload_info} | Trigger: {log.trigger} | Created: {log.created_at}")
        print()
        
        # 4. Check for logs with upload_id = None
        print("4. API LOGS WITH upload_id = NULL:")
        print("-" * 80)
        null_upload_logs = Cin7ApiLog.query.filter(Cin7ApiLog.upload_id.is_(None)).order_by(desc(Cin7ApiLog.created_at)).limit(10).all()
        print(f"   Found {len(null_upload_logs)} logs with upload_id = NULL")
        for log in null_upload_logs:
            print(f"   - {log.method} {log.endpoint} | Status: {log.response_status} | Trigger: {log.trigger} | Created: {log.created_at}")
        print()
        
        # 5. Check specific upload if provided
        upload_id_to_check = "7944f791-4722-4069-97b4-0ef9e64a2824"
        print(f"5. CHECKING SPECIFIC UPLOAD: {upload_id_to_check}")
        print("-" * 80)
        try:
            upload_uuid = upload_id_to_check
            # Try to find as upload_id
            upload = SalesOrderUpload.query.get(upload_uuid)
            if upload:
                print(f"   ✓ Found as SalesOrderUpload")
                print(f"   Filename: {upload.filename}")
                print(f"   Status: {upload.status}")
                print(f"   Created: {upload.created_at}")
                
                logs = Cin7ApiLog.query.filter_by(upload_id=upload.id).all()
                print(f"   API Logs: {len(logs)}")
                for log in logs:
                    print(f"     - {log.method} {log.endpoint} | Status: {log.response_status} | Trigger: {log.trigger}")
            else:
                # Try to find as SalesOrderResult
                result = SalesOrderResult.query.get(upload_uuid)
                if result:
                    print(f"   ✓ Found as SalesOrderResult")
                    print(f"   Order Key: {result.order_key}")
                    print(f"   Status: {result.status}")
                    print(f"   Upload ID: {result.upload_id}")
                    
                    upload = SalesOrderUpload.query.get(result.upload_id)
                    if upload:
                        print(f"   Upload Filename: {upload.filename}")
                        logs = Cin7ApiLog.query.filter_by(upload_id=upload.id).all()
                        print(f"   API Logs for this upload: {len(logs)}")
                        for log in logs:
                            print(f"     - {log.method} {log.endpoint} | Status: {log.response_status} | Trigger: {log.trigger}")
                else:
                    print(f"   ✗ Not found as Upload or Order Result")
        except Exception as e:
            print(f"   ✗ Error checking: {str(e)}")
        print()
        
        # 6. Summary
        print("6. SUMMARY:")
        print("-" * 80)
        total_uploads = SalesOrderUpload.query.count()
        total_logs = Cin7ApiLog.query.count()
        logs_with_upload = Cin7ApiLog.query.filter(Cin7ApiLog.upload_id.isnot(None)).count()
        logs_without_upload = Cin7ApiLog.query.filter(Cin7ApiLog.upload_id.is_(None)).count()
        
        print(f"   Total Uploads: {total_uploads}")
        print(f"   Total API Logs: {total_logs}")
        print(f"   Logs with upload_id: {logs_with_upload}")
        print(f"   Logs without upload_id: {logs_without_upload}")
        
        if total_uploads > 0 and logs_with_upload == 0:
            print(f"   ⚠️  WARNING: Uploads exist but no logs have upload_id set!")
        print()

if __name__ == '__main__':
    diagnose_api_logging()

