#!/usr/bin/env python3
"""
Test script for webhook endpoint in development.

Usage:
    python test_webhook_local.py

Make sure:
    1. Flask backend is running on http://localhost:5001
    2. CSV file is accessible via URL (or use a local file server)
    3. Client "Chida Chida" exists in database
    4. Column mappings are configured for the client
"""

import requests
import json
import sys
import os

# Configuration
BACKEND_URL = "http://localhost:5001"
WEBHOOK_ENDPOINT = f"{BACKEND_URL}/api/webhooks/email"

# Test payload - CSV file hosted locally
CSV_URL = "http://localhost:8000/Report_15_2025-12-26_14-00_TEST.csv"

def test_webhook():
    """Test the webhook endpoint with a sample payload"""
    
    payload = {
        "subject": "Scheduled Report -> Chida Chida Daily Sales Orders",
        "latest_message": {
            "subject": "Scheduled Report -> Chida Chida Daily Sales Orders",
            "attachments": [
                {
                    "filename": "Report_15_2025-12-26_14-00_TEST.csv",
                    "extension": "csv",
                    "sub_type": "csv",
                    "url": CSV_URL
                }
            ]
        }
    }
    
    print("=" * 60)
    print("Testing Webhook Endpoint")
    print("=" * 60)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Endpoint: {WEBHOOK_ENDPOINT}")
    print(f"CSV URL: {CSV_URL}")
    print()
    
    try:
        print("Sending webhook request...")
        response = requests.post(
            WEBHOOK_ENDPOINT,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        print()
        
        try:
            response_data = response.json()
            print("Response:")
            print(json.dumps(response_data, indent=2))
            
            if response.status_code == 200:
                print()
                print("✓ Webhook accepted!")
                if 'upload_id' in response_data:
                    print(f"  Upload ID: {response_data['upload_id']}")
                    print(f"  Status: {response_data.get('status', 'N/A')}")
                    print()
                    print("Next steps:")
                    print(f"  1. Check queue at: http://localhost:3000/queue")
                    print(f"  2. Look for upload ID: {response_data['upload_id']}")
            else:
                print()
                print("✗ Webhook failed!")
                if 'error' in response_data:
                    print(f"  Error: {response_data['error']}")
                    
        except json.JSONDecodeError:
            print("Response (not JSON):")
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print("✗ Error: Could not connect to backend!")
        print(f"  Make sure Flask is running on {BACKEND_URL}")
        print("  Start it with: python app.py")
        sys.exit(1)
        
    except requests.exceptions.Timeout:
        print("✗ Error: Request timed out!")
        sys.exit(1)
        
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    # Check if CSV is accessible
    try:
        csv_check = requests.get(CSV_URL, timeout=2)
        if csv_check.status_code != 200:
            print(f"⚠ Warning: CSV file not accessible at {CSV_URL}")
            print("  Status code:", csv_check.status_code)
            print("  Make sure CSV file server is running on port 8000")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"⚠ Warning: Could not access CSV file at {CSV_URL}")
        print(f"  Error: {str(e)}")
        print("  Make sure CSV file server is running:")
        print("    cd /Users/dan/Downloads")
        print("    python3 -m http.server 8000")
        sys.exit(1)
    
    test_webhook()

