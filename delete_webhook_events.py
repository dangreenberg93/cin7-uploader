#!/usr/bin/env python3
"""Delete webhook-related events (uploads, order results, API logs)"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from database import db, SalesOrderUpload, SalesOrderResult, Cin7ApiLog
from sqlalchemy import text
import uuid
from datetime import datetime, timedelta

app = create_app('development' if os.environ.get('FLASK_ENV') != 'production' else 'production')

def delete_webhook_uploads(upload_ids=None, filename_pattern=None, days_old=None, all_webhooks=False):
    """
    Delete webhook uploads and related records.
    
    Args:
        upload_ids: List of upload IDs to delete (UUIDs as strings)
        filename_pattern: Delete uploads matching filename pattern (e.g., "Report_15_")
        days_old: Delete uploads older than N days
        all_webhooks: Delete all webhook uploads (user_id is NULL)
    """
    with app.app_context():
        try:
            # Build query for webhook uploads (user_id is NULL)
            query = SalesOrderUpload.query.filter(SalesOrderUpload.user_id.is_(None))
            
            if upload_ids:
                # Convert string IDs to UUIDs
                uuid_ids = []
                for id_str in upload_ids:
                    try:
                        uuid_ids.append(uuid.UUID(id_str))
                    except ValueError:
                        print(f"Invalid UUID format: {id_str}")
                        return
                query = query.filter(SalesOrderUpload.id.in_(uuid_ids))
            elif filename_pattern:
                query = query.filter(SalesOrderUpload.filename.like(f'%{filename_pattern}%'))
            elif days_old:
                cutoff_date = datetime.utcnow() - timedelta(days=days_old)
                query = query.filter(SalesOrderUpload.created_at < cutoff_date)
            elif not all_webhooks:
                print("Please specify one of: upload_ids, filename_pattern, days_old, or all_webhooks=True")
                return
            
            uploads = query.all()
            
            if not uploads:
                print("No webhook uploads found matching criteria.")
                return
            
            print(f"Found {len(uploads)} webhook upload(s) to delete:")
            for upload in uploads:
                print(f"  - {upload.id} | {upload.filename} | {upload.created_at} | Status: {upload.status}")
            
            # Confirm deletion
            response = input(f"\nDelete {len(uploads)} webhook upload(s) and all related records? (yes/no): ")
            if response.lower() != 'yes':
                print("Cancelled.")
                return
            
            deleted_uploads = 0
            deleted_order_results = 0
            deleted_api_logs = 0
            
            for upload in uploads:
                upload_id = upload.id
                
                # Count related records
                order_results_count = SalesOrderResult.query.filter_by(upload_id=upload_id).count()
                api_logs_count = Cin7ApiLog.query.filter_by(upload_id=upload_id).count()
                
                # Delete API logs first (foreign key constraint)
                deleted_logs = Cin7ApiLog.query.filter_by(upload_id=upload_id).delete()
                deleted_api_logs += deleted_logs
                
                # Delete order results (should cascade, but being explicit)
                deleted_results = SalesOrderResult.query.filter_by(upload_id=upload_id).delete()
                deleted_order_results += deleted_results
                
                # Delete upload
                db.session.delete(upload)
                deleted_uploads += 1
                
                print(f"Deleted upload {upload_id}: {deleted_logs} API logs, {deleted_results} order results")
            
            db.session.commit()
            
            print(f"\n✓ Successfully deleted:")
            print(f"  - {deleted_uploads} upload(s)")
            print(f"  - {deleted_order_results} order result(s)")
            print(f"  - {deleted_api_logs} API log(s)")
            
        except Exception as e:
            db.session.rollback()
            print(f"✗ Error deleting webhook events: {str(e)}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Delete webhook-related events')
    parser.add_argument('--ids', nargs='+', help='Upload IDs to delete (UUIDs)')
    parser.add_argument('--filename', help='Filename pattern to match (e.g., "Report_15_")')
    parser.add_argument('--days', type=int, help='Delete uploads older than N days')
    parser.add_argument('--all', action='store_true', help='Delete all webhook uploads')
    
    args = parser.parse_args()
    
    delete_webhook_uploads(
        upload_ids=args.ids,
        filename_pattern=args.filename,
        days_old=args.days,
        all_webhooks=args.all
    )

