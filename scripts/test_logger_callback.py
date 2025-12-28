#!/usr/bin/env python3
"""
Test script to verify logger callback is working
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from database import db, SalesOrderUpload, Cin7ApiLog
from cin7_sales.api_client import Cin7SalesAPI
import uuid
import logging

app = create_app()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_logger_callback():
    """Test that logger callback works"""
    with app.app_context():
        # Create a test upload record
        test_upload = SalesOrderUpload(
            id=uuid.uuid4(),
            user_id=None,
            client_id=None,
            client_erp_credentials_id=uuid.uuid4(),  # Dummy credential ID
            filename='test.csv',
            total_rows=1,
            successful_orders=0,
            failed_orders=0,
            status='pending'
        )
        db.session.add(test_upload)
        db.session.commit()
        
        print(f"Created test upload: {test_upload.id}")
        
        # Create logger callback
        callback_invoked = []
        
        def log_api_call(endpoint, method, request_url, request_headers, request_body,
                         response_status, response_body, error_message, duration_ms):
            """Test callback"""
            callback_invoked.append({
                'endpoint': endpoint,
                'method': method,
                'response_status': response_status
            })
            
            logger.info(f"Callback invoked: {method} {endpoint}, status: {response_status}")
            
            try:
                log_entry = Cin7ApiLog(
                    id=uuid.uuid4(),
                    client_id=test_upload.client_erp_credentials_id,
                    user_id=None,
                    upload_id=test_upload.id,
                    trigger='test',
                    endpoint=endpoint,
                    method=method,
                    request_url=request_url,
                    request_headers=request_headers,
                    request_body=request_body,
                    response_status=response_status,
                    response_body=response_body,
                    error_message=error_message,
                    duration_ms=duration_ms
                )
                db.session.add(log_entry)
                db.session.commit()
                logger.info(f"✓ Successfully logged API call to database")
            except Exception as e:
                logger.error(f"✗ Error logging API call: {str(e)}", exc_info=True)
                db.session.rollback()
        
        # Create API client with callback
        # Use dummy credentials - this will fail but should still log
        api_client = Cin7SalesAPI(
            account_id=str(uuid.uuid4()),
            application_key='dummy-key',
            base_url='https://inventory.dearsystems.com/ExternalApi/v2/',
            logger_callback=log_api_call
        )
        
        print(f"API client created, logger_callback set: {api_client.logger_callback is not None}")
        
        # Make a test API call (this will fail but should trigger the callback)
        print("Making test API call to /me endpoint...")
        result = api_client.get_company()
        
        print(f"API call completed. Result: {result}")
        print(f"Callback invoked {len(callback_invoked)} times")
        
        # Check if log was created
        logs = Cin7ApiLog.query.filter_by(upload_id=test_upload.id).all()
        print(f"API logs in database for test upload: {len(logs)}")
        
        for log in logs:
            print(f"  - {log.method} {log.endpoint} | Status: {log.response_status} | Trigger: {log.trigger}")
        
        # Clean up
        db.session.delete(test_upload)
        for log in logs:
            db.session.delete(log)
        db.session.commit()
        
        print("\nTest completed!")

if __name__ == '__main__':
    test_logger_callback()

