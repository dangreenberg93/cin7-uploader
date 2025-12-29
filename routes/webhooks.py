"""Webhook routes for email automation"""
from flask import Blueprint, request, jsonify, Response, stream_with_context
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
import requests
import uuid
import time
import threading
import queue
import os
import re
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from database import db, SalesOrderUpload, SalesOrderResult, ClientSettings, ClientCsvMapping, Cin7ApiLog, Client, UserClient, CachedCustomer, CachedProduct, CustomerUploadMapping, ProductUploadMapping
from cin7_sales.api_client import Cin7SalesAPI
from cin7_sales.csv_parser import CSVParser
from cin7_sales.validator import SalesOrderValidator
from cin7_sales.sales_order_builder import SalesOrderBuilder
from sqlalchemy import text, func
from routes.auth import User

webhooks_bp = Blueprint('webhooks', __name__)
logger = logging.getLogger(__name__)

# Helper function for debug logging (works in both dev and production)
def debug_log(session_id, run_id, hypothesis_id, location, message, data):
    """
    Debug logging helper that uses proper logging and optionally writes to file.
    In production, logs go to Cloud Run logs. In dev, can also write to file if configured.
    """
    import time
    log_data = {
        "sessionId": session_id,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000)
    }
    
    # Always use proper logging (works in production via Cloud Run logs)
    logger.debug(f"[DEBUG] {json.dumps(log_data)}")
    
    # Optionally write to file if DEBUG_LOG_FILE env var is set (for local dev)
    debug_log_file = os.environ.get('DEBUG_LOG_FILE')
    if debug_log_file:
        try:
            # Ensure directory exists
            log_dir = os.path.dirname(debug_log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            with open(debug_log_file, 'a') as f:
                f.write(json.dumps(log_data) + '\n')
        except Exception:
            pass  # Ignore file write errors

# Global event queue for Server-Sent Events (SSE)
# Thread-safe queue to broadcast upload status updates to connected clients
_event_queue = queue.Queue()

def emit_upload_event(event_type: str, upload_id: str = None, client_id: str = None):
    """
    Emit an event to all connected SSE clients when upload status changes.
    
    Args:
        event_type: Type of event ('upload_status_changed', 'order_processed', etc.)
        upload_id: Optional upload ID
        client_id: Optional client ID
    """
    try:
        event_data = {
            'type': event_type,
            'upload_id': upload_id,
            'client_id': client_id,
            'timestamp': datetime.utcnow().isoformat()
        }
        _event_queue.put(event_data)
    except Exception as e:
        logger.error(f"Error emitting upload event: {e}")


def extract_client_name_from_subject(subject: str) -> Optional[str]:
    """
    Extract client name from email subject line.
    
    Pattern: "Scheduled Report -> {Client Name} Daily Sales Orders"
    Also handles variations: "{Client Name} Daily Sales Orders", "Orders - {Client Name}", etc.
    
    Args:
        subject: Email subject line
        
    Returns:
        Client name string (trimmed) or None if not found
    """
    if not subject:
        return None
    
    subject = subject.strip()
    
    # Primary pattern: "Scheduled Report -> {Client Name} Daily Sales Orders"
    if '->' in subject and 'Daily Sales Orders' in subject:
        parts = subject.split('->', 1)
        if len(parts) == 2:
            client_part = parts[1].split('Daily Sales Orders', 1)[0].strip()
            # Clean up any leading/trailing whitespace or dashes
            client_part = client_part.strip(' -:').strip()
            if client_part:
                logger.info(f"Extracted client name from subject '{subject}': '{client_part}'")
                return client_part
    
    # Fallback pattern: "{Client Name} Daily Sales Orders"
    if 'Daily Sales Orders' in subject:
        parts = subject.split('Daily Sales Orders', 1)
        if len(parts) > 0:
            client_part = parts[0].strip()
            # Remove common prefixes
            for prefix in ['Scheduled Report', 'Report', 'Orders']:
                if client_part.startswith(prefix):
                    client_part = client_part[len(prefix):].strip()
                    if client_part.startswith('-') or client_part.startswith(':'):
                        client_part = client_part[1:].strip()
            if client_part:
                return client_part
    
    # Fallback: "Orders - {Client Name}"
    if 'Orders' in subject and '-' in subject:
        parts = subject.split('-', 1)
        if len(parts) == 2:
            client_part = parts[1].strip()
            if client_part:
                return client_part
    
    return None


def lookup_client_by_name(client_name: str) -> Optional[uuid.UUID]:
    """
    Lookup client by name in voyager.client or voyager.client_erp_credentials.
    
    Args:
        client_name: Client name to search for
        
    Returns:
        client_erp_credentials_id (UUID) or None if not found
    """
    if not client_name:
        return None
    
    client_name = client_name.strip()
    
    # Search in voyager.client.name first
    query = text("""
        SELECT 
            cec.id as credential_id,
            c.name as client_name
        FROM voyager.client c
        INNER JOIN voyager.client_erp_credentials cec ON cec.client_id = c.id
        WHERE cec.erp = 'cin7_core'
        AND LOWER(TRIM(c.name)) = LOWER(TRIM(:client_name))
        AND cec.cin7_api_auth_accountid IS NOT NULL
        AND cec.cin7_api_auth_applicationkey IS NOT NULL
        LIMIT 1
    """)
    
    result = db.session.execute(query, {'client_name': client_name})
    row = result.fetchone()
    
    if row:
        return row.credential_id
    
    # Fallback to voyager.client_erp_credentials.connection_name
    query = text("""
        SELECT 
            cec.id as credential_id,
            cec.connection_name
        FROM voyager.client_erp_credentials cec
        WHERE cec.erp = 'cin7_core'
        AND LOWER(TRIM(cec.connection_name)) = LOWER(TRIM(:client_name))
        AND cec.cin7_api_auth_accountid IS NOT NULL
        AND cec.cin7_api_auth_applicationkey IS NOT NULL
        LIMIT 1
    """)
    
    result = db.session.execute(query, {'client_name': client_name})
    row = result.fetchone()
    
    if row:
        return row.credential_id
    
    return None


def normalize_webhook_payload(payload: Dict, request_obj) -> Optional[Dict]:
    """
    Normalize webhook payload from different email services to common structure.
    
    Currently supports Missive format. Can be extended for other formats.
    
    Args:
        payload: Raw webhook payload (dict or None)
        request_obj: Flask request object
        
    Returns:
        Normalized payload dict: {subject: str, attachments: [{url: str, filename: str}]}
        or None if format not recognized
    """
    if not payload:
        return None
    
    # Missive format - try different possible structures
    # Format 1: payload.subject and payload.latest_message.attachments
    if 'latest_message' in payload:
        latest_message = payload.get('latest_message', {})
        subject = latest_message.get('subject') or payload.get('subject', '')
        attachments = latest_message.get('attachments', [])
        
        # Find CSV attachment
        csv_attachment = None
        for att in attachments:
            # Check various ways CSV might be identified
            ext = att.get('extension', '').lower() or att.get('file_extension', '').lower()
            sub_type = att.get('sub_type', '').lower() or att.get('content_type', '').lower()
            filename = att.get('filename', '').lower() or att.get('name', '').lower()
            
            if ext == 'csv' or sub_type == 'csv' or 'csv' in sub_type or filename.endswith('.csv'):
                csv_attachment = att
                break
        
        if csv_attachment and subject:
            return {
                'subject': subject,
                'attachments': [{
                    'url': csv_attachment.get('url') or csv_attachment.get('download_url') or csv_attachment.get('signed_url'),
                    'filename': csv_attachment.get('filename') or csv_attachment.get('name', 'attachment.csv')
                }]
            }
    
    # Format 2: Direct subject and attachments at root level
    if 'subject' in payload:
        subject = payload.get('subject', '')
        attachments = payload.get('attachments', [])
        
        # Find CSV attachment
        csv_attachment = None
        for att in attachments:
            ext = att.get('extension', '').lower() or att.get('file_extension', '').lower()
            sub_type = att.get('sub_type', '').lower() or att.get('content_type', '').lower()
            filename = att.get('filename', '').lower() or att.get('name', '').lower()
            
            if ext == 'csv' or sub_type == 'csv' or 'csv' in sub_type or filename.endswith('.csv'):
                csv_attachment = att
                break
        
        if csv_attachment:
            return {
                'subject': subject,
                'attachments': [{
                    'url': csv_attachment.get('url') or csv_attachment.get('download_url') or csv_attachment.get('signed_url'),
                    'filename': csv_attachment.get('filename') or csv_attachment.get('name', 'attachment.csv')
                }]
            }
    
    # Future: Add other formats here (Mailgun, SendGrid, etc.)
    
    return None


def download_csv_from_url(url: str) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Download CSV file from signed attachment URL.
    
    Args:
        url: Signed URL to download CSV from
        
    Returns:
        Tuple of (file_content_bytes, error_message) or (None, error_message) on failure
    """
    if not url:
        return None, "No URL provided"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.content, None
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download CSV from URL: {str(e)}")
        return None, f"Failed to download CSV: {str(e)}"


def extract_csv_from_payload(normalized_payload: Dict) -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
    """
    Extract CSV attachment from normalized webhook payload.
    
    Args:
        normalized_payload: Normalized payload dict with attachments
        
    Returns:
        Tuple of (file_content_bytes, filename, error_message)
    """
    if not normalized_payload or 'attachments' not in normalized_payload:
        return None, None, "No attachments in payload"
    
    attachments = normalized_payload.get('attachments', [])
    if not attachments:
        return None, None, "No attachments found"
    
    # Get first CSV attachment
    attachment = attachments[0]
    url = attachment.get('url')
    filename = attachment.get('filename', 'attachment.csv')
    
    if not url:
        return None, None, "No URL in attachment"
    
    # Download CSV
    csv_content, error = download_csv_from_url(url)
    if error:
        return None, None, error
    
    # Validate it's a CSV (basic check)
    if not filename.lower().endswith('.csv'):
        # Check content type or first few bytes
        if csv_content and not csv_content.startswith(b'\xef\xbb\xbf') and b',' not in csv_content[:100]:
            return None, None, "File does not appear to be a CSV"
    
    return csv_content, filename, None


def categorize_error(error_message: str) -> str:
    """
    Categorize error message into error types for filtering.
    
    Args:
        error_message: Error message string
        
    Returns:
        Error type string: "customer_not_found", "missing_fields", "api_error", or "validation_error"
    """
    if not error_message:
        return "validation_error"
    
    error_lower = error_message.lower()
    
    if "customer" in error_lower and ("not found" in error_lower or "notfound" in error_lower):
        return "customer_not_found"
    elif "required" in error_lower or "missing" in error_lower:
        return "missing_fields"
    elif "404" in error_message or "400" in error_message or "api" in error_lower:
        return "api_error"
    else:
        return "validation_error"


def process_single_order(
    upload_id: uuid.UUID,
    order_key: str,
    order_rows: List[Dict],
    row_numbers: List[int],
    column_mapping: Dict,
    settings: Dict,
    api_client: Cin7SalesAPI,
    builder: SalesOrderBuilder,
    credential_id_for_logging: uuid.UUID,
    existing_order_result: Optional[SalesOrderResult] = None
) -> Dict:
    """
    Process a single order (create Sale and Sale Order in Cin7).
    
    Args:
        upload_id: SalesOrderUpload ID
        order_key: Order identifier
        order_rows: List of row data dictionaries for this order
        row_numbers: List of CSV row numbers
        column_mapping: Column mapping dict
        settings: Client settings
        api_client: Cin7SalesAPI instance
        builder: SalesOrderBuilder instance
        credential_id_for_logging: Credential ID for API logging
        existing_order_result: Optional existing SalesOrderResult to update (for retries)
        
    Returns:
        Result dict with status, sale_id, sale_order_id, error_message, order_data
    """
    # Use existing order_result if provided (for retries), otherwise create new one
    if existing_order_result:
        order_result = existing_order_result
        order_result.status = 'processing'
    else:
        # Create order result record with status='processing'
        order_result = SalesOrderResult(
            id=uuid.uuid4(),
            upload_id=upload_id,
            order_key=order_key,
            row_numbers=row_numbers,
            status='processing',
            created_at=datetime.utcnow()
        )
        db.session.add(order_result)
    db.session.commit()
    
    # Capture order_id for logger callback
    order_result_id = order_result.id
    
    # Set the current order_id in the logger callback closure
    # The logger callback uses a mutable list (current_order_id) to store order_id
    if hasattr(api_client, '_current_order_id_ref'):
        api_client._current_order_id_ref[0] = order_result_id
    
    # Extract order data snapshot - include all mapped columns from all rows
    primary_row = order_rows[0] if order_rows else {}
    
    # Build comprehensive order_data with all mapped fields
    order_data = {}
    
    # Add all mapped columns from primary row
    for cin7_field, csv_column in column_mapping.items():
        if csv_column and csv_column in primary_row:
            value = primary_row[csv_column]
            # Use a clean field name (remove spaces, special chars)
            clean_field = cin7_field.lower().replace(' ', '_')
            order_data[clean_field] = value
    
    # Also include row data for all rows in this order
    order_data['all_rows'] = []
    for row in order_rows:
        row_data = {}
        for cin7_field, csv_column in column_mapping.items():
            if csv_column and csv_column in row:
                row_data[csv_column] = row[csv_column]
        order_data['all_rows'].append(row_data)
    
    # Store column mapping so frontend can use it to find columns
    order_data['column_mapping'] = column_mapping
    
    # Keep backward compatibility with old field names
    # Try to get customer name from multiple sources:
    # 1. From order_data (cleaned field name from mapped columns)
    # 2. From primary_row (CSV column names)
    # 3. From order_data with different casing
    order_data['customer_name'] = (
        order_data.get('customer_name', '') or  # From mapped columns (cleaned field name)
        order_data.get('customername', '') or   # Alternative casing
        primary_row.get(column_mapping.get('CustomerName', '')) or  # From CSV using mapped column name
        primary_row.get('CustomerName') or 
        primary_row.get('customer_name', '') or 
        primary_row.get('Customer Name') or  # CSV column might have space
        ''
    )
    order_data['po_number'] = primary_row.get('CustomerReference') or primary_row.get('po_number', '') or order_data.get('customerreference', '')
    order_data['order_date'] = primary_row.get('SaleDate') or primary_row.get('order_date', '') or order_data.get('saledate', '')
    # Capture order number from mapped SaleOrderNumber column (for reference, not sent to Cin7)
    order_data['order_number'] = (
        primary_row.get(column_mapping.get('SaleOrderNumber', '')) or  # From mapped SaleOrderNumber column
        primary_row.get('SaleOrderNumber') or
        primary_row.get('order_number', '') or
        order_data.get('saleordernumber', '') or
        order_data.get('ordernumber', '')
    )
    
    # Initialize sale_id early to avoid UnboundLocalError in exception handler
    sale_id = None
    sale_order_id = None
    
    try:
        # Always use combined approach (single API call with nested Order)
        use_combined_approach = True
        
        # Check customer lookup first (needed for TaxRule in combined call)
        # Get customer name from multiple sources to ensure we capture it
        # First check order_data (has cleaned field names from mapped columns), then primary_row (raw CSV)
        customer_name_col = column_mapping.get('CustomerName', '')
        customer_name = (
            order_data.get('customer_name', '') or  # From mapped columns (cleaned field name)
            order_data.get('customername', '') or   # Alternative casing (all lowercase)
            (primary_row.get(customer_name_col) if customer_name_col else None) or  # From CSV using mapped column name
            primary_row.get('CustomerName') or 
            primary_row.get('customer_name') or 
            primary_row.get('Customer Name') or  # CSV column might have space
            ''
        ).strip()
        customer_data = None
        
        # Collect detailed matching information before API call
        matching_details = {
            'customer': {},
            'products': [],
            'missing_fields': []
        }
        
        # Always ensure customer name is in matching_details, even if empty, so error messages can use it
        # Get customer name from order_data first (most reliable source)
        customer_name_for_matching = customer_name or order_data.get('customer_name', '') or order_data.get('customername', '')
        
        if customer_name_for_matching:
            # Get customer code field from column_mapping (optional - if not set, will match by name only)
            customer_code_field = column_mapping.get('_customer_code_field')
            
            # Extract customer code value from primary row if available
            customer_code_value = None
            if customer_code_field:
                if customer_code_field in column_mapping and column_mapping[customer_code_field]:
                    csv_col = column_mapping[customer_code_field]
                    if csv_col in primary_row:
                        customer_code_value = primary_row[csv_col]
                # Fallback: try direct field name in case it's already mapped
                if not customer_code_value:
                    customer_code_value = primary_row.get(customer_code_field) or primary_row.get(customer_code_field.lower())
                
                if customer_code_value:
                    customer_code_value = str(customer_code_value).strip()
            
            customer_data = builder._lookup_customer_by_name(
                customer_name_for_matching, 
                customer_code_field=customer_code_field,
                customer_code_value=customer_code_value
            )
            
            # Build search query info for debugging (always include, whether found or not)
            search_queries = []
            if customer_code_value:
                search_queries.append({'type': customer_code_field, 'value': customer_code_value, 'api_endpoint': f'/customer?{customer_code_field}={customer_code_value}'})
            search_queries.append({'type': 'name', 'value': customer_name_for_matching, 'api_endpoint': f'/customer?name={customer_name_for_matching}'})
            
            if customer_data:
                # Check if customer was auto-created by looking at cache
                # This captures the state at order creation time and memorializes it in order_data
                # so that even if cache flags change later, the order's historical record still shows
                # whether the customer was newly created for this specific order
                customer_id = customer_data.get('ID')
                was_auto_created = False
                if customer_id:
                    try:
                        customer_id_uuid = uuid.UUID(str(customer_id))
                        cached_customer = CachedCustomer.query.filter_by(
                            client_erp_credentials_id=credential_id_for_logging,
                            cin7_customer_id=customer_id_uuid
                        ).first()
                        if cached_customer:
                            # Capture the auto-created state from cache at order creation time
                            was_auto_created = cached_customer.created_via_auto_create or cached_customer.is_new
                    except (ValueError, AttributeError):
                        pass  # If ID is invalid, just skip the check
                
                matching_details['customer'] = {
                    'name': customer_name_for_matching,
                    'found': True,
                    'cin7_id': customer_data.get('ID'),
                    'cin7_name': customer_data.get('Name'),
                    'tax_rule': customer_data.get('TaxRule'),  # Store TaxRule for later use
                    'search_queries': search_queries,
                    'auto_created': was_auto_created  # Memorialized in order_data - persists even if cache flags change
                }
            else:
                matching_details['customer'] = {
                    'name': customer_name_for_matching,
                    'found': False,
                    'error': f'Customer "{customer_name_for_matching}" not found in Cin7',
                    'search_queries': search_queries
                }
        else:
            # Even if no customer name found in initial extraction, try order_data as fallback
            # This ensures matching_details always has the customer name for error messages
            fallback_customer_name = (order_data.get('customer_name', '') or 
                                    order_data.get('customername', '') or 
                                    '').strip()
            matching_details['customer'] = {
                'name': fallback_customer_name,
                'found': False,
                'error': 'Customer name not provided' if not fallback_customer_name else f'Customer "{fallback_customer_name}" not found in Cin7',
                'search_queries': [{'type': 'name', 'value': fallback_customer_name, 'api_endpoint': f'/customer?name={fallback_customer_name}'}] if fallback_customer_name else []
            }
        
        # Final fallback: ensure matching_details['customer']['name'] is always populated from order_data
        # This handles cases where customer_name extraction might have failed but order_data has it
        if not matching_details['customer'].get('name'):
            final_customer_name = (order_data.get('customer_name', '') or 
                                 order_data.get('customername', '') or 
                                 '').strip()
            if final_customer_name:
                matching_details['customer']['name'] = final_customer_name
                if 'error' not in matching_details['customer'] or not matching_details['customer'].get('error'):
                    matching_details['customer']['error'] = f'Customer "{final_customer_name}" not found in Cin7'
                if 'search_queries' not in matching_details['customer']:
                    matching_details['customer']['search_queries'] = [{'type': 'name', 'value': final_customer_name, 'api_endpoint': f'/customer?name={final_customer_name}'}]
        
        # Build Sale payload (without Order - will create separately)
        sale_data = builder.build_sale(primary_row, column_mapping)
        
        # Get sale type value for "what's needed" payload
        sale_type_setting = settings.get('sale_type', '')
        sale_type_setting = sale_type_setting.strip() if sale_type_setting and isinstance(sale_type_setting, str) else ''
        if sale_type_setting.lower() == 'advanced':
            sale_type_value = 'Advanced Sale'
        elif sale_type_setting.lower() == 'simple':
            sale_type_value = 'Simple Sale'
        else:
            sale_type_value = 'Simple Sale'
        
        # Check product lookups for all rows
        sku_col = column_mapping.get('SKU') or column_mapping.get('ProductCode')
        if sku_col:
            for row in order_rows:
                sku = row.get(sku_col, '')
                if sku:
                    product = builder._lookup_product_by_sku(sku)
                    # Build search query info for debugging (always include, whether found or not)
                    search_queries = [
                        {'type': 'SKU', 'value': sku, 'api_endpoint': f'/product?SKU={sku}'}
                    ]
                    
                    if product:
                        # Check if product was auto-created by looking at cache
                        # This captures the state at order creation time and memorializes it in order_data
                        # so that even if cache flags change later, the order's historical record still shows
                        # whether the product was newly created for this specific order
                        product_id = product.get('ID')
                        was_auto_created = False
                        if product_id:
                            try:
                                product_id_uuid = uuid.UUID(str(product_id))
                                cached_product = CachedProduct.query.filter_by(
                                    client_erp_credentials_id=credential_id_for_logging,
                                    cin7_product_id=product_id_uuid
                                ).first()
                                if cached_product:
                                    # Capture the auto-created state from cache at order creation time
                                    was_auto_created = cached_product.created_via_auto_create or cached_product.is_new
                            except (ValueError, AttributeError):
                                pass  # If ID is invalid, just skip the check
                        
                        matching_details['products'].append({
                            'sku': sku,
                            'found': True,
                            'cin7_id': product.get('ID'),
                            'cin7_name': product.get('Name'),
                            'search_queries': search_queries,
                            'auto_created': was_auto_created  # Memorialized in order_data - persists even if cache flags change
                        })
                    else:
                        matching_details['products'].append({
                            'sku': sku,
                            'found': False,
                            'error': f'Product SKU "{sku}" not found in Cin7',
                            'search_queries': search_queries
                        })
        
        # Check for missing required fields and build "what's needed" payload
        required_fields = ['CustomerID', 'Customer', 'Type']
        missing_required = []
        for field in required_fields:
            if field not in sale_data or not sale_data[field]:
                missing_required.append(field)
                matching_details['missing_fields'].append(field)
        
        # Build "what's needed" payload - show what the complete payload should look like
        what_is_needed = sale_data.copy() if sale_data else {}
        
        # Add missing required fields with placeholders
        if 'CustomerID' in missing_required:
            if matching_details['customer'].get('found'):
                # Customer found but ID not set - use the found ID
                what_is_needed['CustomerID'] = matching_details['customer'].get('cin7_id')
            else:
                what_is_needed['CustomerID'] = '<REQUIRED: Customer ID from Cin7>'
        
        if 'Customer' in missing_required:
            customer_name = primary_row.get('CustomerName') or primary_row.get('customer_name') or ''
            if customer_name:
                what_is_needed['Customer'] = customer_name
            else:
                what_is_needed['Customer'] = '<REQUIRED: Customer Name>'
        
        if 'Type' in missing_required:
            what_is_needed['Type'] = sale_type_value  # Use the determined type
        
        # Build Sale Order payload for "what's needed" (separate from Sale)
        # This shows what the Sale Order payload would look like
        sale_order_for_what_is_needed = None
        try:
            if len(order_rows) > 1:
                sale_order_for_what_is_needed = builder.build_sale_order_from_rows(order_rows, column_mapping, '<SALE_ID_PLACEHOLDER>', customer_data=customer_data)
            else:
                sale_order_for_what_is_needed = builder.build_sale_order(order_rows[0], column_mapping, '<SALE_ID_PLACEHOLDER>', customer_data=customer_data)
        except ValueError as e:
            # If TaxRule error occurs, still try to build a partial order for display
            error_str = str(e)
            if "TaxRule is required" in error_str:
                logger.warning(f"TaxRule error when building order for display: {error_str}. Building order with all products for display.")
                # Build order structure with ALL products (matched and unmatched) for display
                sale_order_for_what_is_needed = {
                    'SaleID': '<SALE_ID_PLACEHOLDER>',
                    'Lines': []
                }
                
                # Add all products from order_rows to Lines
                sku_col = column_mapping.get('SKU') or column_mapping.get('sku')
                if sku_col and order_rows:
                    for row in order_rows:
                        sku = str(row.get(sku_col, '')).strip() if sku_col in row else None
                        if sku:
                            # Find product in matching_details or lookup
                            product_match = None
                            product_data = None
                            
                            # Check matching_details
                            if matching_details.get('products'):
                                product_match = next((p for p in matching_details['products'] if p.get('sku') == sku), None)
                            
                            # If not in matching_details, try to lookup in builder cache
                            if not product_match and builder:
                                product_data = builder._lookup_product_by_sku(sku)
                                if product_data and product_data.get('ID'):
                                    # Add to matching_details
                                    product_match = {
                                        'sku': sku,
                                        'found': True,
                                        'cin7_id': product_data.get('ID')
                                    }
                                    matching_details['products'].append(product_match)
                            
                            # Extract quantity and price from row
                            qty_col = column_mapping.get('Quantity') or column_mapping.get('QuantityOrdered')
                            price_col = column_mapping.get('Price') or column_mapping.get('UnitPrice')
                            
                            quantity = None
                            if qty_col and qty_col in row:
                                try:
                                    qty_val = str(row[qty_col]).replace('$', '').replace(',', '').strip()
                                    quantity = float(qty_val) if qty_val else None
                                except (ValueError, TypeError):
                                    quantity = None
                            
                            price = None
                            if price_col and price_col in row:
                                try:
                                    price_val = str(row[price_col]).replace('$', '').replace(',', '').strip()
                                    price = float(price_val) if price_val else None
                                except (ValueError, TypeError):
                                    price = None
                            
                            # Determine if product was found
                            is_found = product_match and product_match.get('found')
                            product_id = product_match.get('cin7_id') if product_match else (product_data.get('ID') if product_data else None)
                            
                            # Build line item
                            line_item = {
                                'SKU': sku,
                                'ProductID': product_id,
                                'Quantity': quantity if quantity is not None else 0,
                                'Price': price if price is not None else 0,
                                '_not_found': not is_found,
                                '_error': f'Product SKU "{sku}" not found in Cin7' if not is_found else None
                            }
                            sale_order_for_what_is_needed['Lines'].append(line_item)
            else:
                raise  # Re-raise if it's a different error
        
        # Debug: Log if lines are empty
        if sale_order_for_what_is_needed and (not sale_order_for_what_is_needed.get('Lines') or len(sale_order_for_what_is_needed.get('Lines', [])) == 0):
            logger.warning(f"Warning: Sale Order payload has no lines for order {order_key}. Column mapping has SKU: {'SKU' in column_mapping}, Price: {'Price' in column_mapping}, Quantity: {'Quantity' in column_mapping}")
            logger.warning(f"Primary row keys: {list(primary_row.keys())[:10]}...")  # Log first 10 keys
        
        # Add notes about what needs to be fixed
        what_is_needed['_notes'] = []
        if not matching_details['customer'].get('found'):
            what_is_needed['_notes'].append(f"Customer '{matching_details['customer'].get('name', 'N/A')}' needs to be created in Cin7 first, or name corrected")
        if matching_details['products']:
            missing_products = [p for p in matching_details['products'] if not p.get('found')]
            for p in missing_products:
                what_is_needed['_notes'].append(f"Product SKU '{p.get('sku')}' needs to be created in Cin7 first, or SKU corrected")
        
        # Store the payloads (what we'll actually send)
        what_is_needed['_sale_payload'] = sale_data  # Store the sale payload
        what_is_needed['_sale_order_payload'] = sale_order_for_what_is_needed  # Store the sale order payload
        
        # Check for duplicate PO number before creating sale
        customer_reference = sale_data.get('CustomerReference', '').strip() if sale_data.get('CustomerReference') else None
        duplicate_sales = []
        existing_sales = []  # Initialize to ensure it's in scope
        if customer_reference:
            logger.info(f"Checking for duplicate PO number: {customer_reference}")
            search_success, search_message, existing_sales = api_client.search_sales_by_po(customer_reference)
            if search_success and existing_sales:
                # Filter out voided sales (voided sales shouldn't block new orders)
                # Also handle case-insensitive matching and None/empty status
                active_duplicates = [
                    s for s in existing_sales 
                    if s.get('Status') and str(s.get('Status', '')).strip().upper() != 'VOIDED'
                ]
                if active_duplicates:
                    duplicate_sales = active_duplicates
                    logger.warning(f"Found {len(duplicate_sales)} existing non-voided sale(s) with PO number {customer_reference} (filtered out {len(existing_sales) - len(duplicate_sales)} voided sale(s))")
        
        # Note: Auto-create is now handled in Phase 1 (before order processing)
        # This section is kept for backward compatibility but should not be needed
        # if Phase 1 auto-create completed successfully
        auto_create_customers_products = settings.get('auto_create_customers_products', False)
        
        # Auto-create customer if not found and setting is enabled
        # (This is a fallback - Phase 1 should have already created all customers)
        if not matching_details['customer'].get('found') and customer_name and auto_create_customers_products:
            logger.info(f"Auto-creating customer '{customer_name}' (auto_create_customers_products enabled)")
            try:
                # Build customer payload
                customer_payload = {
                    'Name': customer_name,
                    'Status': 'Active',
                    'Currency': settings.get('default_currency', 'USD'),
                    'PaymentTerm': '30 days'
                }
                
                # Add required fields from settings
                if settings.get('customer_account_receivable'):
                    customer_payload['AccountReceivable'] = settings['customer_account_receivable']
                if settings.get('customer_revenue_account'):
                    customer_payload['RevenueAccount'] = settings['customer_revenue_account']
                
                # TaxRule - need to convert UUID to Name
                tax_rule_uuid = settings.get('customer_tax_rule')
                if tax_rule_uuid:
                    try:
                        # Get tax rules to find the name
                        tax_rules = api_client.get_tax_rules()
                        for rule in tax_rules:
                            if str(rule.get('ID')) == str(tax_rule_uuid):
                                customer_payload['TaxRule'] = rule.get('Name')
                                break
                        if 'TaxRule' not in customer_payload:
                            logger.warning(f"Tax rule UUID {tax_rule_uuid} not found, customer creation may fail")
                    except Exception as e:
                        logger.warning(f"Could not fetch tax rules: {e}")
                
                if settings.get('customer_attribute_set'):
                    customer_payload['AttributeSet'] = settings['customer_attribute_set']
                
                # Add customer code field from CSV if mapped (dynamically use the configured field)
                customer_code_field = column_mapping.get('_customer_code_field')
                if customer_code_field and customer_code_field in column_mapping and column_mapping[customer_code_field]:
                    csv_col = column_mapping[customer_code_field]
                    if csv_col in primary_row:
                        attr_value = primary_row[csv_col]
                        if attr_value and str(attr_value).strip():
                            customer_payload[customer_code_field] = str(attr_value).strip()
                
                # Create customer
                create_success, create_message, create_response = api_client.create_customer(customer_payload)
                
                if create_success and create_response:
                    # Extract customer ID from response
                    # Response may be direct customer object or wrapped in CustomerList
                    customer_data = None
                    if isinstance(create_response, dict):
                        if 'ID' in create_response:
                            # Direct customer object
                            customer_data = create_response
                        elif 'CustomerList' in create_response and isinstance(create_response['CustomerList'], list) and len(create_response['CustomerList']) > 0:
                            # Wrapped in CustomerList array
                            customer_data = create_response['CustomerList'][0]
                    
                    if not customer_data:
                        logger.error(f"Customer created but response format unexpected: {create_response}")
                        customer_id = None
                    else:
                        customer_id = customer_data.get('ID')
                    
                    if customer_id:
                        try:
                            customer_id_uuid = uuid.UUID(str(customer_id))
                        except (ValueError, AttributeError):
                            logger.error(f"Invalid customer ID format: {customer_id}")
                            customer_id_uuid = None
                        
                        if customer_id_uuid:
                            # Refresh customer cache and mark as new
                            from routes.sales import refresh_single_customer_cache
                            refresh_single_customer_cache(credential_id_for_logging, customer_id_uuid, customer_data, is_new=True)
                            
                            # Small delay to ensure database cache is updated
                            import time
                            time.sleep(0.1)
                            
                            # Update builder's preloaded_customers so it can be found immediately
                            customer_name_clean = customer_name.strip()
                            builder.preloaded_customers[customer_name_clean] = customer_data
                            builder.preloaded_customers[customer_name_clean.upper()] = customer_data
                            builder.preloaded_customers[customer_name_clean.lower()] = customer_data
                            
                            # Get additional_attribute1 if available
                            additional_attribute1 = None
                            # Get customer code field value for cache key
                            customer_code_field = column_mapping.get('_customer_code_field')
                            customer_code_value = None
                            if customer_code_field and customer_code_field in column_mapping and column_mapping[customer_code_field]:
                                attr_col = column_mapping[customer_code_field]
                                if attr_col in primary_row:
                                    attr_value = primary_row[attr_col]
                                    if attr_value and str(attr_value).strip():
                                        customer_code_value = str(attr_value).strip()
                            
                            # Clear ALL cache entries for this customer name (to handle any additional_attribute1 variations)
                            cache_keys_to_remove = [key for key in builder._customer_cache.keys() if key.startswith(f"{customer_name_clean}|")]
                            for key in cache_keys_to_remove:
                                del builder._customer_cache[key]
                            
                            # Update cache with the new customer (with and without additional_attribute1)
                            cache_key_with_attr = f"{customer_name_clean}|{additional_attribute1}"
                            cache_key_no_attr = f"{customer_name_clean}|None"
                            builder._customer_cache[cache_key_with_attr] = customer_data
                            builder._customer_cache[cache_key_no_attr] = customer_data
                            
                            # Force refresh from database cache to ensure consistency
                            db.session.commit()  # Ensure cache write is committed
                            cached_customer = CachedCustomer.query.filter_by(
                                client_erp_credentials_id=credential_id_for_logging,
                                cin7_customer_id=customer_id_uuid
                            ).first()
                            if cached_customer and cached_customer.customer_data:
                                import json
                                cached_data = json.loads(cached_customer.customer_data) if isinstance(cached_customer.customer_data, str) else cached_customer.customer_data
                                # Ensure we're using the latest data from cache
                                builder.preloaded_customers[customer_name_clean] = cached_data
                                builder.preloaded_customers[customer_name_clean.upper()] = cached_data
                                builder.preloaded_customers[customer_name_clean.lower()] = cached_data
                                builder._customer_cache[cache_key_with_attr] = cached_data
                                builder._customer_cache[cache_key_no_attr] = cached_data
                                logger.info(f"Refreshed customer '{customer_name}' from database cache after auto-create")
                            
                            # Update matching details and customer_data
                            matching_details['customer'] = {
                                'name': customer_name,
                                'found': True,
                                'cin7_id': customer_id,
                                'cin7_name': customer_data.get('Name'),
                                'tax_rule': customer_data.get('TaxRule'),
                                'auto_created': True
                            }
                            
                            # Update sale_data with CustomerID
                            sale_data['CustomerID'] = customer_id
                            sale_data['Customer'] = customer_name
                            
                            logger.info(f"Successfully auto-created customer '{customer_name}' with ID {customer_id}")
                        else:
                            logger.error(f"Could not convert customer ID to UUID: {customer_id}")
                    else:
                        logger.error(f"Customer created but no ID in response: {create_response}")
                        # Try to extract from CustomerList if present
                        if isinstance(create_response, dict) and 'CustomerList' in create_response:
                            customer_list = create_response.get('CustomerList', [])
                            if customer_list and len(customer_list) > 0:
                                customer_data = customer_list[0]
                                customer_id = customer_data.get('ID')
                                if customer_id:
                                    logger.info(f"Extracted customer ID from CustomerList: {customer_id}")
                                    # Retry with extracted customer
                                    try:
                                        customer_id_uuid = uuid.UUID(str(customer_id))
                                        from routes.sales import refresh_single_customer_cache
                                        refresh_single_customer_cache(credential_id_for_logging, customer_id_uuid, customer_data, is_new=True)
                                        # Update builder cache
                                        customer_name_clean = customer_name.strip()
                                        builder.preloaded_customers[customer_name_clean] = customer_data
                                        builder.preloaded_customers[customer_name_clean.upper()] = customer_data
                                        builder.preloaded_customers[customer_name_clean.lower()] = customer_data
                                        # Update matching details
                                        matching_details['customer'] = {
                                            'name': customer_name,
                                            'found': True,
                                            'cin7_id': customer_id,
                                            'cin7_name': customer_data.get('Name'),
                                            'tax_rule': customer_data.get('TaxRule'),
                                            'auto_created': True
                                        }
                                        sale_data['CustomerID'] = customer_id
                                        sale_data['Customer'] = customer_name
                                        logger.info(f"Successfully auto-created customer '{customer_name}' with ID {customer_id} (extracted from CustomerList)")
                                    except (ValueError, AttributeError) as e:
                                        logger.error(f"Error processing extracted customer: {str(e)}")
                else:
                    # Check if customer already exists (409 error)
                    if '409' in str(create_message) or 'already exists' in str(create_message).lower():
                        logger.info(f"Customer '{customer_name}' already exists (409), attempting to look it up")
                        # Try to look up the existing customer using API search
                        try:
                            customers = api_client.search_customer(name=customer_name)
                            if customers and len(customers) > 0:
                                existing_customer = customers[0]
                                customer_id = existing_customer.get('ID')
                                if customer_id:
                                    try:
                                        customer_id_uuid = uuid.UUID(str(customer_id))
                                        # Refresh customer cache with existing customer
                                        from routes.sales import refresh_single_customer_cache
                                        refresh_single_customer_cache(credential_id_for_logging, customer_id_uuid, existing_customer, is_new=False)
                                        logger.info(f"Found existing customer '{customer_name}' with ID {customer_id}")
                                        
                                        # Small delay
                                        import time
                                        time.sleep(0.1)
                                        
                                        # Update builder's preloaded_customers so it can be found immediately
                                        customer_name_clean = customer_name.strip()
                                        builder.preloaded_customers[customer_name_clean] = existing_customer
                                        builder.preloaded_customers[customer_name_clean.upper()] = existing_customer
                                        builder.preloaded_customers[customer_name_clean.lower()] = existing_customer
                                        
                                        # Get additional_attribute1 if available
                                        additional_attribute1 = None
                                        # Get customer code field value for cache key
                                        customer_code_field = column_mapping.get('_customer_code_field')
                                        customer_code_value = None
                                        if customer_code_field and customer_code_field in column_mapping and column_mapping[customer_code_field]:
                                            attr_col = column_mapping[customer_code_field]
                                            if attr_col in primary_row:
                                                attr_value = primary_row[attr_col]
                                                if attr_value and str(attr_value).strip():
                                                    customer_code_value = str(attr_value).strip()
                                        
                                        # Clear ALL cache entries for this customer name
                                        cache_keys_to_remove = [key for key in builder._customer_cache.keys() if key.startswith(f"{customer_name_clean}|")]
                                        for key in cache_keys_to_remove:
                                            del builder._customer_cache[key]
                                        
                                        # Update cache with the existing customer
                                        if customer_code_field:
                                            cache_key_with_code = f"{customer_name_clean}|{customer_code_field}|{customer_code_value}"
                                            cache_key_no_code = f"{customer_name_clean}|{customer_code_field}|None"
                                        else:
                                            cache_key_with_code = f"{customer_name_clean}|None|None"
                                            cache_key_no_code = f"{customer_name_clean}|None|None"
                                        builder._customer_cache[cache_key_with_code] = existing_customer
                                        builder._customer_cache[cache_key_no_code] = existing_customer
                                        
                                        # Force commit
                                        db.session.commit()
                                        
                                        # Update matching details and customer_data
                                        customer_data = existing_customer
                                        matching_details['customer'] = {
                                            'name': customer_name,
                                            'found': True,
                                            'cin7_id': customer_id,
                                            'cin7_name': existing_customer.get('Name'),
                                            'tax_rule': existing_customer.get('TaxRule'),
                                            'auto_created': False  # Not auto-created, already existed
                                        }
                                        
                                        # Update sale_data with CustomerID
                                        sale_data['CustomerID'] = customer_id
                                        sale_data['Customer'] = customer_name
                                    except (ValueError, AttributeError):
                                        logger.error(f"Invalid customer ID format: {customer_id}")
                            else:
                                logger.warning(f"Customer '{customer_name}' reported as existing but not found in search")
                        except Exception as e:
                            logger.error(f"Error looking up existing customer '{customer_name}': {str(e)}", exc_info=True)
                    else:
                        logger.error(f"Failed to auto-create customer '{customer_name}': {create_message}")
                        # Continue without customer - will fail later with proper error
            except Exception as e:
                logger.error(f"Error auto-creating customer '{customer_name}': {str(e)}", exc_info=True)
                # Continue without customer - will fail later with proper error
        
        # Auto-create products if not found and setting is enabled
        # Track auto-created product IDs for bulk cache refresh
        auto_created_product_ids = []
        
        if auto_create_customers_products:
            missing_products = [p for p in matching_details['products'] if not p.get('found')]
            for missing_product in missing_products:
                sku = missing_product.get('sku')
                if not sku:
                    continue
                
                logger.info(f"Auto-creating product with SKU '{sku}' (auto_create_customers_products enabled)")
                try:
                    # Get product name from CSV or use SKU
                    product_name_col = column_mapping.get('ProductName') or column_mapping.get('Name')
                    product_name = None
                    if product_name_col:
                        for row in order_rows:
                            if product_name_col in row and row[product_name_col]:
                                product_name = row[product_name_col]
                                break
                    
                    if not product_name:
                        product_name = sku  # Fallback to SKU
                    
                    # Build product payload
                    product_payload = {
                        'Name': product_name,
                        'SKU': sku,
                        'Status': 'Active',
                        'Type': 'Stock',
                        'CostingMethod': settings.get('product_costing_method', 'FIFO'),
                        'PriceTiers': {
                            settings.get('product_default_price_tier', 'Tier 1'): settings.get('product_default_price', 0.0)
                        }
                    }
                    
                    # Create product
                    create_success, create_message, create_response = api_client.create_product(product_payload)
                    
                    if create_success and create_response:
                        # Extract product ID from response
                        # Response may be direct product object or wrapped in ProductList
                        product_data = None
                        if isinstance(create_response, dict):
                            if 'ID' in create_response:
                                # Direct product object
                                product_data = create_response
                            elif 'ProductList' in create_response and isinstance(create_response['ProductList'], list) and len(create_response['ProductList']) > 0:
                                # Wrapped in ProductList array
                                product_data = create_response['ProductList'][0]
                        
                        if not product_data:
                            logger.error(f"Product created but response format unexpected: {create_response}")
                            product_id = None
                        else:
                            product_id = product_data.get('ID')
                        
                        if product_id:
                            try:
                                product_id_uuid = uuid.UUID(str(product_id))
                            except (ValueError, AttributeError):
                                logger.error(f"Invalid product ID format: {product_id}")
                                product_id_uuid = None
                            
                            if product_id_uuid:
                                # Refresh product cache and mark as new
                                from routes.sales import refresh_single_product_cache
                                refresh_single_product_cache(credential_id_for_logging, product_id_uuid, sku, product_data, is_new=True)
                                
                                # Small delay to ensure database cache is updated
                                import time
                                time.sleep(0.1)
                                
                                # Update builder's preloaded_products so it can be found immediately
                                sku_clean = sku.strip()
                                builder.preloaded_products[sku_clean] = product_data
                                builder.preloaded_products[sku_clean.upper()] = product_data
                                builder.preloaded_products[sku_clean.lower()] = product_data
                                
                                # Clear any cached None entries and update cache with the new product
                                if sku_clean in builder._product_cache:
                                    del builder._product_cache[sku_clean]
                                if sku in builder._product_cache:
                                    del builder._product_cache[sku]
                                builder._product_cache[sku_clean] = product_data
                                
                                # Force commit to ensure cache is persisted
                                db.session.commit()
                                
                                # Track product ID for bulk cache refresh
                                auto_created_product_ids.append(product_id_uuid)
                                
                                logger.info(f"Successfully auto-created product SKU '{sku}' with ID {product_id}")
                                
                                # Update matching details
                                for p in matching_details['products']:
                                    if p.get('sku') == sku:
                                        p['found'] = True
                                        p['cin7_id'] = product_id
                                        p['cin7_name'] = product_data.get('Name')
                                        p['auto_created'] = True
                                        break
                            else:
                                logger.error(f"Could not convert product ID to UUID: {product_id}")
                        else:
                            logger.error(f"Product created but no ID in response: {create_response}")
                            # Try to extract from ProductList if present
                            if isinstance(create_response, dict) and 'ProductList' in create_response:
                                product_list = create_response.get('ProductList', [])
                                if product_list and len(product_list) > 0:
                                    product_data = product_list[0]
                                    product_id = product_data.get('ID')
                                    if product_id:
                                        logger.info(f"Extracted product ID from ProductList: {product_id}")
                                        # Retry with extracted product
                                        try:
                                            product_id_uuid = uuid.UUID(str(product_id))
                                            from routes.sales import refresh_single_product_cache
                                            refresh_single_product_cache(credential_id_for_logging, product_id_uuid, sku, product_data, is_new=True)
                                            # Update builder cache
                                            sku_clean = sku.strip()
                                            builder.preloaded_products[sku_clean] = product_data
                                            builder.preloaded_products[sku_clean.upper()] = product_data
                                            builder.preloaded_products[sku_clean.lower()] = product_data
                                            if sku_clean in builder._product_cache:
                                                del builder._product_cache[sku_clean]
                                            if sku in builder._product_cache:
                                                del builder._product_cache[sku]
                                            builder._product_cache[sku_clean] = product_data
                                            db.session.commit()
                                            auto_created_product_ids.append(product_id_uuid)
                                            # Update matching details
                                            for p in matching_details['products']:
                                                if p.get('sku') == sku:
                                                    p['found'] = True
                                                    p['cin7_id'] = product_id
                                                    p['cin7_name'] = product_data.get('Name')
                                                    p['auto_created'] = True
                                                    break
                                            logger.info(f"Successfully auto-created product SKU '{sku}' with ID {product_id} (extracted from ProductList)")
                                        except (ValueError, AttributeError) as e:
                                            logger.error(f"Error processing extracted product: {str(e)}")
                    else:
                        # Check if product already exists (409 error)
                        if '409' in str(create_message) or 'already exists' in str(create_message).lower():
                            logger.info(f"Product SKU '{sku}' already exists (409), checking cache first...")
                            
                            # Check if product is already in our database cache
                            cached_product = CachedProduct.query.filter_by(
                                client_erp_credentials_id=credential_id_for_logging,
                                sku=sku
                            ).first()
                            
                            if cached_product and cached_product.product_data:
                                # Use cached product data - no need for API call
                                existing_product = cached_product.product_data
                                product_id = existing_product.get('ID')
                                if product_id:
                                    try:
                                        product_id_uuid = uuid.UUID(str(product_id))
                                        
                                        # Update builder's preloaded_products so it can be found immediately
                                        sku_clean = sku.strip()
                                        builder.preloaded_products[sku_clean] = existing_product
                                        builder.preloaded_products[sku_clean.upper()] = existing_product
                                        builder.preloaded_products[sku_clean.lower()] = existing_product
                                        # Clear any cached None entries and update cache with the existing product
                                        if sku_clean in builder._product_cache:
                                            del builder._product_cache[sku_clean]
                                        if sku in builder._product_cache:
                                            del builder._product_cache[sku]
                                        builder._product_cache[sku_clean] = existing_product
                                        
                                        # Track product ID for cache refresh (even if already existed)
                                        auto_created_product_ids.append(product_id_uuid)
                                        
                                        # Update matching details
                                        for p in matching_details['products']:
                                            if p.get('sku') == sku:
                                                p['found'] = True
                                                p['cin7_id'] = product_id
                                                p['cin7_name'] = existing_product.get('Name')
                                                p['auto_created'] = False  # Not auto-created, already existed
                                                break
                                        
                                        logger.info(f"Found existing product SKU '{sku}' in cache (ID: {product_id}) - no API call needed")
                                    except (ValueError, AttributeError):
                                        logger.error(f"Invalid product ID format in cache: {product_id}")
                            else:
                                # Not in cache - need to fetch from API
                                logger.info(f"Product SKU '{sku}' not in cache, fetching from API...")
                                try:
                                    products = api_client.search_product(sku=sku)
                                    if products and len(products) > 0:
                                        existing_product = products[0]
                                        product_id = existing_product.get('ID')
                                        if product_id:
                                            try:
                                                product_id_uuid = uuid.UUID(str(product_id))
                                                # Refresh product cache with existing product
                                                from routes.sales import refresh_single_product_cache
                                                refresh_single_product_cache(credential_id_for_logging, product_id_uuid, sku, existing_product, is_new=False)
                                                logger.info(f"Found existing product SKU '{sku}' with ID {product_id}")
                                                
                                                # Small delay
                                                import time
                                                time.sleep(0.1)
                                                
                                                # Update builder's preloaded_products so it can be found immediately
                                                sku_clean = sku.strip()
                                                builder.preloaded_products[sku_clean] = existing_product
                                                builder.preloaded_products[sku_clean.upper()] = existing_product
                                                builder.preloaded_products[sku_clean.lower()] = existing_product
                                                # Clear any cached None entries and update cache with the existing product
                                                if sku_clean in builder._product_cache:
                                                    del builder._product_cache[sku_clean]
                                                if sku in builder._product_cache:
                                                    del builder._product_cache[sku]
                                                builder._product_cache[sku_clean] = existing_product
                                                
                                                # Force commit
                                                db.session.commit()
                                                
                                                # Track product ID for cache refresh (even if already existed)
                                                auto_created_product_ids.append(product_id_uuid)
                                                
                                                # Update matching details
                                                for p in matching_details['products']:
                                                    if p.get('sku') == sku:
                                                        p['found'] = True
                                                        p['cin7_id'] = product_id
                                                        p['cin7_name'] = existing_product.get('Name')
                                                        p['auto_created'] = False  # Not auto-created, already existed
                                                        break
                                            except (ValueError, AttributeError):
                                                logger.error(f"Invalid product ID format: {product_id}")
                                    else:
                                        logger.warning(f"Product SKU '{sku}' reported as existing but not found in search")
                                except Exception as e:
                                    logger.error(f"Error looking up existing product SKU '{sku}': {str(e)}", exc_info=True)
                        else:
                            logger.error(f"Failed to auto-create product SKU '{sku}': {create_message}")
                            # Continue - product will be missing from order
                except Exception as e:
                    logger.error(f"Error auto-creating product SKU '{sku}': {str(e)}", exc_info=True)
                    # Continue - product will be missing from order
        
        # After all auto-creates, refresh product cache from database using product IDs to ensure all newly created products are available
        if auto_create_customers_products and auto_created_product_ids:
            try:
                db.session.commit()  # Ensure all cache writes are committed
                # Refresh builder's product cache from database using product IDs
                for product_id_uuid in auto_created_product_ids:
                    cached_product = CachedProduct.query.filter_by(
                        client_erp_credentials_id=credential_id_for_logging,
                        cin7_product_id=product_id_uuid
                    ).first()
                    if cached_product and cached_product.product_data:
                        import json
                        product_data = json.loads(cached_product.product_data) if isinstance(cached_product.product_data, str) else cached_product.product_data
                        sku = cached_product.sku
                        if sku:
                            sku_clean = sku.strip()
                            # Update builder's cache
                            builder.preloaded_products[sku_clean] = product_data
                            builder.preloaded_products[sku_clean.upper()] = product_data
                            builder.preloaded_products[sku_clean.lower()] = product_data
                            builder._product_cache[sku_clean] = product_data
                            if sku != sku_clean:
                                builder._product_cache[sku] = product_data
                            logger.debug(f"Refreshed product '{sku}' (ID: {product_id_uuid}) from database cache before building sale order")
            except Exception as e:
                logger.warning(f"Error refreshing product cache from database: {str(e)}", exc_info=True)
                # Continue anyway - builder cache should already be updated
        
        # Check if we should even attempt to send to Cin7
        # CustomerID is required - if we don't have it, don't send
        should_attempt_sale = 'CustomerID' in sale_data and sale_data.get('CustomerID')
        
        # Block if duplicate PO found
        if duplicate_sales:
            # Format error message: "Order SO-0003 exists in Cin7 under PO # XYZ"
            if len(duplicate_sales) == 1:
                order_num = duplicate_sales[0].get('OrderNumber', 'N/A')
                enhanced_error = f'Order {order_num} exists in Cin7 under PO # {customer_reference}'
            else:
                order_nums = ', '.join([s.get('OrderNumber', 'N/A') for s in duplicate_sales[:3]])
                if len(duplicate_sales) > 3:
                    order_nums += f' (and {len(duplicate_sales) - 3} more)'
                enhanced_error = f'Orders {order_nums} exist in Cin7 under PO # {customer_reference}'
            
            logger.error(enhanced_error)
            
            # Get the API response from the search (stored in order_data for dev modal)
            # The API call is already logged via logger_callback, but we'll also store the response here
            duplicate_search_response = {
                'search_query': customer_reference,
                'total_found': len(existing_sales),
                'active_duplicates': len(duplicate_sales),
                'voided_filtered': len(existing_sales) - len(duplicate_sales),
                'duplicate_sales': duplicate_sales,
                'all_sales_found': existing_sales  # Include all sales (including voided) for reference
            }
            
            # Create order result with duplicate error
            order_result = SalesOrderResult(
                id=uuid.uuid4(),
                upload_id=upload_id,
                order_key=order_key,
                row_numbers=row_numbers,
                status='failed',
                error_message=enhanced_error,
                error_type='duplicate_po',
                order_data={
                    'attempted_send': False,
                    'error': enhanced_error,
                    'po_number': customer_reference,
                    'duplicate_search_response': duplicate_search_response,
                    'duplicate_sales': [
                        {
                            'order_number': s.get('OrderNumber'),
                            'status': s.get('Status'),
                            'invoice_number': s.get('InvoiceNumber'),
                            'customer': s.get('Customer'),
                            'sale_id': s.get('ID')  # Store full sale object if available
                        }
                        for s in duplicate_sales[:5]  # Limit to first 5 for storage
                    ],
                    'matching_details': matching_details,
                    'sale_payload': sale_data,
                    'sale_order_payload': sale_order_for_what_is_needed
                }
            )
            db.session.add(order_result)
            db.session.commit()
            return {
                'status': 'failed',
                'error': enhanced_error,
                'error_type': 'duplicate_po',
                'order_result_id': str(order_result.id)
            }
        
        if not should_attempt_sale:
            # Don't send to Cin7 - customer not matched
            error_parts = []
            
            # Customer error
            if not matching_details['customer'].get('found'):
                # Try to get customer name from matching_details first, then from order_data
                customer_name = (matching_details['customer'].get('name', '') or 
                               order_data.get('customer_name', '') or 
                               primary_row.get('CustomerName') or 
                               primary_row.get('customer_name', '')).strip()
                if customer_name and customer_name != 'N/A':
                    error_parts.append(f"Customer '{customer_name}' not found in Cin7")
                else:
                    error_parts.append("Customer not found in Cin7")
            
            # Product errors - summarize missing SKUs
            missing_products = [p for p in matching_details.get('products', []) if not p.get('found')]
            if missing_products:
                missing_skus = [p.get('sku', 'N/A') for p in missing_products if p.get('sku')]
                if missing_skus:
                    if len(missing_skus) == 1:
                        error_parts.append(f"SKU '{missing_skus[0]}' not found in Cin7")
                    elif len(missing_skus) <= 3:
                        sku_list = ', '.join([f"'{s}'" for s in missing_skus])
                        error_parts.append(f"SKUs {sku_list} not found in Cin7")
                    else:
                        sku_list = ', '.join([f"'{s}'" for s in missing_skus[:3]])
                        error_parts.append(f"SKUs {sku_list} and {len(missing_skus) - 3} more not found in Cin7")
            
            enhanced_error = ' | '.join(error_parts) if error_parts else 'Cannot create Sale: CustomerID is required but customer was not found in Cin7'
            
            order_result.status = 'failed'
            order_result.error_message = enhanced_error
            order_result.error_type = 'data_missing'
            order_result.order_data = {
                **order_data,
                'matching_details': matching_details,
                'sale_payload': sale_data,  # Store what we would have sent (sale payload)
                'sale_order_payload': sale_order_for_what_is_needed,  # Store what we would have sent (sale order payload)
                'what_is_needed': what_is_needed,  # Store what's needed
                'attempted_send': False  # Flag to indicate we didn't actually send
            }
            order_result.processed_at = datetime.utcnow()
            db.session.commit()
            return {
                'status': 'failed',
                'error_message': enhanced_error,
                'order_data': order_result.order_data,
                'matching_details': matching_details
            }
        
        # Step 0: Check products BEFORE creating sale
        # If customer is found but NO products are found, don't create the sale/order
        sku_col = column_mapping.get('SKU') or column_mapping.get('sku')
        filtered_order_rows = []
        removed_products = []
        
        if sku_col:
            for row in order_rows:
                sku = str(row.get(sku_col, '')).strip()
                if sku:
                    # Check if product exists in cached/preloaded data
                    product = builder._lookup_product_by_sku(sku)
                    if product and product.get('ID'):
                        # Product found - include in order
                        filtered_order_rows.append(row)
                    else:
                        # Product not found - exclude from order and track it with full details
                        # Extract quantity and price from row for display
                        qty_col = column_mapping.get('Quantity') or column_mapping.get('QuantityOrdered')
                        price_col = column_mapping.get('Price') or column_mapping.get('UnitPrice')
                        
                        quantity = None
                        if qty_col and qty_col in row:
                            try:
                                qty_val = str(row[qty_col]).replace('$', '').replace(',', '').strip()
                                quantity = float(qty_val) if qty_val else None
                            except (ValueError, TypeError):
                                quantity = None
                        
                        price = None
                        if price_col and price_col in row:
                            try:
                                price_val = str(row[price_col]).replace('$', '').replace(',', '').strip()
                                price = float(price_val) if price_val else None
                            except (ValueError, TypeError):
                                price = None
                        
                        removed_products.append({
                            'sku': sku,
                            'quantity': quantity,
                            'price': price,
                            'row_data': row
                        })
                        logger.warning(f"Product SKU '{sku}' not found in Cin7 - excluding from order {order_key}")
                        
                        # Update matching_details to mark this product as not found
                        if 'products' not in matching_details:
                            matching_details['products'] = []
                        
                        # Check if already in matching_details
                        found_in_details = any(p.get('sku') == sku for p in matching_details['products'])
                        if not found_in_details:
                            matching_details['products'].append({
                                'sku': sku,
                                'found': False,
                                'error': f'Product SKU "{sku}" not found in Cin7',
                                'quantity': quantity,
                                'price': price
                            })
                        else:
                            # Update existing entry
                            for product in matching_details['products']:
                                if product.get('sku') == sku:
                                    product['found'] = False
                                    product['error'] = f'Product SKU "{sku}" not found in Cin7'
                                    product['quantity'] = quantity
                                    product['price'] = price
                                    break
                else:
                    # No SKU - include row (will be handled by validation)
                    filtered_order_rows.append(row)
        else:
            # No SKU column mapping - use all rows
            filtered_order_rows = order_rows
        
        # If customer is found but NO products are found, don't create the sale/order
        if matching_details['customer'].get('found') and not filtered_order_rows:
            # Build detailed error message with SKUs
            sku_messages = [f'{removed_product.get("sku", "")} not found in Cin7' for removed_product in removed_products]
            if sku_messages:
                error_msg = ', '.join(sku_messages)
            else:
                error_msg = 'No valid products found - all products were unmatched'
            order_result.status = 'failed'
            order_result.error_message = error_msg
            order_result.error_type = categorize_error(error_msg)
            
            # Build a sale_order_payload with unmatched products for display
            sale_order_payload_for_display = {
                'SaleID': '<SALE_ID_PLACEHOLDER>',
                'Lines': []
            }
            
            # Add unmatched products as lines with "Not found" indicator
            for removed_product in removed_products:
                sku = removed_product.get('sku', '')
                quantity = removed_product.get('quantity')
                price = removed_product.get('price')
                
                line_item = {
                    'SKU': sku,
                    'ProductID': None,  # Not found
                    'Quantity': quantity if quantity is not None else 0,
                    'Price': price if price is not None else 0,
                    '_not_found': True,  # Flag for frontend to show "Not found in Cin7"
                    '_error': f'Product SKU "{sku}" not found in Cin7'
                }
                sale_order_payload_for_display['Lines'].append(line_item)
            
            order_result.order_data = {
                **order_data,
                'matching_details': matching_details,
                'sale_payload': sale_data,
                'sale_order_payload': sale_order_payload_for_display,
                'removed_products': removed_products,
                'all_rows': order_data.get('all_rows', [])
            }
            order_result.processed_at = datetime.utcnow()
            db.session.commit()
            return {
                'status': 'failed',
                'error_message': error_msg,
                'order_data': order_result.order_data,
                'matching_details': matching_details
            }
        
        # Step 1: Create Sale (only if customer is found and at least one product is found)
        logger.info(f"Creating Sale for order {order_key}...")
        sale_success, sale_message, sale_response = api_client.create_sale(sale_data)
        sale_id = None
        sale_data_from_response = None
        sale_api_response = None
        
        # Extract Sale ID, full Sale object, and raw JSON text from response
        if isinstance(sale_response, dict):
            sale_id = sale_response.get('ID')
            sale_data_from_response = sale_response.copy() if sale_response else None  # Copy for TaxRule lookup
            # Extract raw JSON text if available (preserves exact order)
            sale_api_response_raw = sale_response.get('_raw_json_text')
            if sale_api_response_raw:
                # Use raw JSON text to preserve exact order
                sale_api_response = sale_api_response_raw
                # Remove _raw_json_text from the copy used for TaxRule lookup
                if sale_data_from_response and '_raw_json_text' in sale_data_from_response:
                    del sale_data_from_response['_raw_json_text']
            else:
                # No raw text available, use parsed dict
                sale_api_response = sale_response
        elif isinstance(sale_response, list) and len(sale_response) > 0:
            first_item = sale_response[0] if isinstance(sale_response[0], dict) else None
            if first_item:
                sale_id = first_item.get('ID')
                sale_data_from_response = first_item.copy() if first_item else None  # Copy for TaxRule lookup
                # Extract raw JSON text if available
                sale_api_response_raw = first_item.get('_raw_json_text')
                if sale_api_response_raw:
                    sale_api_response = sale_api_response_raw
                    # Remove _raw_json_text from the copy used for TaxRule lookup
                    if sale_data_from_response and '_raw_json_text' in sale_data_from_response:
                        del sale_data_from_response['_raw_json_text']
                else:
                    sale_api_response = first_item
        
        if not sale_success:
            # Enhance error message with matching details
            error_parts = [f'Failed to create Sale: {sale_message}']
            
            if not matching_details['customer'].get('found'):
                # Try to get customer name from matching_details first, then from order_data
                customer_name = (matching_details['customer'].get('name', '') or 
                               order_data.get('customer_name', '') or 
                               primary_row.get('CustomerName') or 
                               primary_row.get('customer_name', '')).strip()
                if customer_name and customer_name != 'N/A':
                    error_parts.append(f"Customer '{customer_name}' not found in Cin7")
                else:
                    error_parts.append("Customer not found in Cin7")
            
            missing_products = [p for p in matching_details['products'] if not p.get('found')]
            if missing_products:
                missing_skus = [p.get('sku', 'N/A') for p in missing_products if p.get('sku')]
                if missing_skus:
                    if len(missing_skus) == 1:
                        error_parts.append(f"SKU '{missing_skus[0]}' not found in Cin7")
                    elif len(missing_skus) <= 3:
                        sku_list = ', '.join([f"'{s}'" for s in missing_skus])
                        error_parts.append(f"SKUs {sku_list} not found in Cin7")
                    else:
                        sku_list = ', '.join([f"'{s}'" for s in missing_skus[:3]])
                        error_parts.append(f"SKUs {sku_list} and {len(missing_skus) - 3} more not found in Cin7")
            
            if matching_details['missing_fields']:
                error_parts.append(f"Missing required fields: {', '.join(matching_details['missing_fields'])}")
            
            enhanced_error = ' | '.join(error_parts)
            
            # Build sale_order_payload with ALL products (matched and unmatched) for display
            # This ensures line items are shown even when sale creation fails (e.g., customer not found)
            sale_order_payload_for_display = {
                'SaleID': '<SALE_ID_PLACEHOLDER>',
                'Lines': []
            }
            
            # Get all products from order_rows
            sku_col = column_mapping.get('SKU') or column_mapping.get('sku')
            if sku_col and order_rows:
                for row in order_rows:
                    sku = str(row.get(sku_col, '')).strip() if sku_col in row else None
                    if sku:
                        # Find product in matching_details or lookup
                        product_match = None
                        product_data = None
                        
                        # Check matching_details
                        if matching_details.get('products'):
                            product_match = next((p for p in matching_details['products'] if p.get('sku') == sku), None)
                        
                        # If not in matching_details, try to lookup in builder cache
                        if not product_match and builder:
                            product_data = builder._lookup_product_by_sku(sku)
                            if product_data and product_data.get('ID'):
                                # Add to matching_details
                                if 'products' not in matching_details:
                                    matching_details['products'] = []
                                product_match = {
                                    'sku': sku,
                                    'found': True,
                                    'cin7_id': product_data.get('ID')
                                }
                                matching_details['products'].append(product_match)
                        
                        # Extract quantity and price from row
                        qty_col = column_mapping.get('Quantity') or column_mapping.get('QuantityOrdered')
                        price_col = column_mapping.get('Price') or column_mapping.get('UnitPrice')
                        
                        quantity = None
                        if qty_col and qty_col in row:
                            try:
                                qty_val = str(row[qty_col]).replace('$', '').replace(',', '').strip()
                                quantity = float(qty_val) if qty_val else None
                            except (ValueError, TypeError):
                                quantity = None
                        
                        price = None
                        if price_col and price_col in row:
                            try:
                                price_val = str(row[price_col]).replace('$', '').replace(',', '').strip()
                                price = float(price_val) if price_val else None
                            except (ValueError, TypeError):
                                price = None
                        
                        # Determine if product was found
                        is_found = product_match and product_match.get('found')
                        product_id = product_match.get('cin7_id') if product_match else (product_data.get('ID') if product_data else None)
                        
                        # Build line item
                        line_item = {
                            'SKU': sku,
                            'ProductID': product_id,
                            'Quantity': quantity if quantity is not None else 0,
                            'Price': price if price is not None else 0,
                            '_not_found': not is_found,
                            '_error': f'Product SKU "{sku}" not found in Cin7' if not is_found else None
                        }
                        sale_order_payload_for_display['Lines'].append(line_item)
            
            order_result.status = 'failed'
            order_result.error_message = enhanced_error
            order_result.error_type = categorize_error(enhanced_error)
            order_result.order_data = {
                **order_data,
                'matching_details': matching_details,
                'sale_payload': sale_data,
                'sale_order_payload': sale_order_payload_for_display,  # Include all products for display
                'sale_api_response': sale_api_response,
                'what_is_needed': what_is_needed,
                'attempted_send': True
            }
            order_result.processed_at = datetime.utcnow()
            db.session.commit()
            return {
                'status': 'failed',
                'error_message': enhanced_error,
                'order_data': order_result.order_data,
                'matching_details': matching_details
            }
        
        if not sale_id:
            order_result.status = 'failed'
            order_result.error_message = 'Sale created but no Sale ID returned'
            order_result.error_type = categorize_error('Sale created but no Sale ID returned')
            order_result.order_data = {
                **order_data,
                'matching_details': matching_details,
                'sale_payload': sale_data,
                'sale_api_response': sale_api_response,
                'what_is_needed': what_is_needed,
                'attempted_send': True
            }
            order_result.processed_at = datetime.utcnow()
            db.session.commit()
            return {
                'status': 'failed',
                'error_message': 'Sale created but no Sale ID returned',
                'order_data': order_result.order_data
            }
        
        # Step 2: Build and create Sale Order with the Sale ID
        logger.info(f"Creating Sale Order for order {order_key} with Sale ID {sale_id}...")
        
        # Use the already-filtered order rows from Step 0
        # filtered_order_rows and removed_products are already set before sale creation
        # If we reach here, it means customer was found and at least one product was found
        
        # Log if any products were filtered
        if removed_products:
            logger.info(f"Filtered out {len(removed_products)} unmatched product(s) from order {order_key}. Proceeding with {len(filtered_order_rows)} matched product(s).")
        
        # Safety check: If somehow we have no filtered rows (shouldn't happen since we checked before sale creation)
        if not filtered_order_rows:
            # Build detailed error message with SKUs
            sku_messages = [f'{removed_product.get("sku", "")} not found in Cin7' for removed_product in removed_products]
            if sku_messages:
                error_msg = ', '.join(sku_messages)
            else:
                error_msg = 'No valid products found - all products were unmatched'
            order_result.status = 'failed'
            order_result.error_message = error_msg
            order_result.error_type = categorize_error(error_msg)
            order_result.sale_id = sale_id
            
            # Build a sale_order_payload with unmatched products for display
            sale_order_payload_for_display = {
                'SaleID': str(sale_id) if sale_id else '<SALE_ID_PLACEHOLDER>',
                'Lines': []
            }
            
            # Add unmatched products as lines with "Not found" indicator
            for removed_product in removed_products:
                sku = removed_product.get('sku', '')
                quantity = removed_product.get('quantity')
                price = removed_product.get('price')
                
                line_item = {
                    'SKU': sku,
                    'ProductID': None,  # Not found
                    'Quantity': quantity if quantity is not None else 0,
                    'Price': price if price is not None else 0,
                    '_not_found': True,  # Flag for frontend to show "Not found in Cin7"
                    '_error': f'Product SKU "{sku}" not found in Cin7'
                }
                sale_order_payload_for_display['Lines'].append(line_item)
            
            order_result.order_data = {
                **order_data,
                'matching_details': matching_details,
                'sale_payload': sale_data,
                'sale_order_payload': sale_order_payload_for_display,
                'removed_products': removed_products,
                'all_rows': order_data.get('all_rows', [])
            }
            order_result.processed_at = datetime.utcnow()
            db.session.commit()
            return {
                'status': 'failed',
                'error_message': error_msg,
                'order_data': order_result.order_data,
                'matching_details': matching_details
            }
        
        # Build sale order payload with filtered rows (only matched products)
        # Use sale_data_from_response (from create_sale response) for TaxRule lookup
        try:
            if len(filtered_order_rows) > 1:
                sale_order_data = builder.build_sale_order_from_rows(filtered_order_rows, column_mapping, str(sale_id), customer_data=customer_data, sale_data=sale_data_from_response)
            else:
                sale_order_data = builder.build_sale_order(filtered_order_rows[0], column_mapping, str(sale_id), customer_data=customer_data, sale_data=sale_data_from_response)
        except ValueError as e:
            # If TaxRule error occurs, check if it's because customer is not found
            error_str = str(e)
            if "TaxRule is required" in error_str:
                auto_create_customers_products = settings.get('auto_create_customers_products', False)
                if not matching_details['customer'].get('found') and not auto_create_customers_products:
                    # Customer not found and auto-create is off - return simple error
                    error_parts = []
                    # Try to get customer name from matching_details first, then from order_data
                    customer_name = (matching_details['customer'].get('name', '') or 
                                   order_data.get('customer_name', '') or 
                                   primary_row.get('CustomerName') or 
                                   primary_row.get('customer_name', '')).strip()
                    if customer_name and customer_name != 'N/A':
                        error_parts.append(f"Customer '{customer_name}' not found in Cin7")
                    else:
                        error_parts.append("Customer not found in Cin7")
                    
                    # Add missing SKUs if any
                    missing_products = [p for p in matching_details.get('products', []) if not p.get('found')]
                    if missing_products:
                        missing_skus = [p.get('sku', 'N/A') for p in missing_products if p.get('sku')]
                        if missing_skus:
                            if len(missing_skus) == 1:
                                error_parts.append(f"SKU '{missing_skus[0]}' not found in Cin7")
                            elif len(missing_skus) <= 3:
                                sku_list = ', '.join([f"'{s}'" for s in missing_skus])
                                error_parts.append(f"SKUs {sku_list} not found in Cin7")
                            else:
                                sku_list = ', '.join([f"'{s}'" for s in missing_skus[:3]])
                                error_parts.append(f"SKUs {sku_list} and {len(missing_skus) - 3} more not found in Cin7")
                    
                    enhanced_error = ' | '.join(error_parts) if error_parts else "Customer not found in Cin7"
                    
                    order_result.status = 'failed'
                    order_result.error_message = enhanced_error
                    order_result.error_type = 'data_missing'
                    order_result.sale_id = sale_id
                    order_result.order_data = {
                        **order_data,
                        'matching_details': matching_details,
                        'sale_payload': sale_data,
                        'sale_order_payload': sale_order_for_what_is_needed,
                        'sale_api_response': sale_api_response,
                        'what_is_needed': what_is_needed,
                        'attempted_send': True
                    }
                    order_result.processed_at = datetime.utcnow()
                    db.session.commit()
                    return {
                        'status': 'failed',
                        'error_message': enhanced_error,
                        'order_data': order_result.order_data,
                        'matching_details': matching_details
                    }
                else:
                    # TaxRule error for other reasons - re-raise
                    raise
            else:
                # Different ValueError - re-raise
                raise
        
        # Create Sale Order via API (should never fail with product not found since we filtered)
        so_success, so_message, so_response = api_client.create_sale_order(sale_order_data)
        sale_order_api_response = None
        
        # Extract raw JSON text if available to preserve exact order
        if isinstance(so_response, dict):
            sale_order_api_response_raw = so_response.get('_raw_json_text')
            if sale_order_api_response_raw:
                sale_order_api_response = sale_order_api_response_raw
            else:
                sale_order_api_response = so_response
        elif isinstance(so_response, list) and len(so_response) > 0:
            first_item = so_response[0] if isinstance(so_response[0], dict) else None
            if first_item:
                sale_order_api_response_raw = first_item.get('_raw_json_text')
                if sale_order_api_response_raw:
                    sale_order_api_response = sale_order_api_response_raw
                else:
                    sale_order_api_response = first_item
        else:
            sale_order_api_response = so_response
        sale_order_id = None
        
        # Extract Sale Order ID from response
        if isinstance(so_response, dict):
            sale_order_id = so_response.get('ID')
        elif isinstance(so_response, list) and len(so_response) > 0:
            first_item = so_response[0] if isinstance(so_response[0], dict) else None
            if first_item:
                sale_order_id = first_item.get('ID')
        
        if not so_success:
            # Sale was created but Sale Order failed (should be rare now since we filter unmatched products)
            order_result.status = 'failed'
            order_result.error_message = f'Sale created (ID: {sale_id}) but Sale Order failed: {so_message}'
            order_result.error_type = categorize_error(f'Sale created but Sale Order failed: {so_message}')
            order_result.sale_id = sale_id  # Store the sale ID even though order failed
            order_result.order_data = {
                **order_data,
                'matching_details': matching_details,
                'sale_payload': sale_data,
                'sale_order_payload': sale_order_data,
                'sale_api_response': sale_api_response,
                'sale_order_api_response': sale_order_api_response,
                'removed_products': removed_products,  # Track which products were removed
                'what_is_needed': what_is_needed,
                'attempted_send': True
            }
            order_result.processed_at = datetime.utcnow()
            db.session.commit()
            return {
                'status': 'failed',
                'error_message': f'Sale created (ID: {sale_id}) but Sale Order failed: {so_message}',
                'order_data': order_result.order_data,
                'matching_details': matching_details
            }
        
        # Success - both Sale and Sale Order were created
        # Create user-friendly message if some products were removed
        if removed_products:
            matched_count = len(sale_order_data.get('Lines', []))
            missing_count = len(removed_products)
            error_message = f'Sale created with {matched_count} line item{"s" if matched_count != 1 else ""}, {missing_count} line item{"s" if missing_count != 1 else ""} missing'
            order_result.status = 'success'  # Still success since sale was created
            order_result.error_message = error_message  # Store as error_message for display
            order_result.error_type = 'partial_success'
        else:
            order_result.status = 'success'
            order_result.error_message = None
        
        # Build complete sale_order_payload with ALL products (matched + unmatched) for display
        sale_order_payload_complete = {
            'SaleID': str(sale_id) if sale_id else '<SALE_ID_PLACEHOLDER>',
            'Lines': []
        }
        
        # Add matched products from sale_order_data
        if sale_order_data and isinstance(sale_order_data, dict):
            matched_lines = sale_order_data.get('Lines', [])
            for line in matched_lines:
                # Ensure matched products don't have _not_found flag
                line_copy = dict(line)
                line_copy['_not_found'] = False
                sale_order_payload_complete['Lines'].append(line_copy)
        
        # Add unmatched products from removed_products
        if removed_products:
            for removed_product in removed_products:
                sku = removed_product.get('sku', '')
                quantity = removed_product.get('quantity')
                price = removed_product.get('price')
                
                line_item = {
                    'SKU': sku,
                    'ProductID': None,  # Not found
                    'Quantity': quantity if quantity is not None else 0,
                    'Price': price if price is not None else 0,
                    '_not_found': True,  # Flag for frontend to show "Not found in Cin7"
                    '_error': f'Product SKU "{sku}" not found in Cin7'
                }
                sale_order_payload_complete['Lines'].append(line_item)
        
        order_result.sale_id = sale_id
        order_result.sale_order_id = sale_order_id if sale_order_id else None
        # Store order_data with matching_details - this memorializes the auto_created flags
        # from the cache at order creation time, so they persist even if cache flags change later
        order_result.order_data = {
            **order_data,
            'matching_details': matching_details,  # Contains auto_created flags captured at order creation time
            'sale_payload': sale_data,
            'sale_order_payload': sale_order_payload_complete,  # Use complete payload with all products
            'sale_api_response': sale_api_response,
            'sale_order_api_response': sale_order_api_response,
            'removed_products': removed_products if removed_products else None,  # Track which products were removed
            'partial_success': True if removed_products else False  # Flag to indicate some products were filtered
        }
        order_result.processed_at = datetime.utcnow()
        
        # Update upload mappings to link this order to the customers/products it uses
        try:
            # Get customer ID from order data
            customer_id = None
            if sale_data and isinstance(sale_data, dict):
                customer_id = sale_data.get('Customer')
            elif order_data and isinstance(order_data, dict):
                customer_id = order_data.get('Customer')
            
            # Get product IDs from line items
            product_ids = []
            if sale_order_data and isinstance(sale_order_data, dict):
                lines = sale_order_data.get('Lines', [])
                for line in lines:
                    if isinstance(line, dict) and 'ProductID' in line:
                        product_ids.append(line['ProductID'])
            
            # Update customer mapping
            if customer_id:
                try:
                    customer_id_uuid = uuid.UUID(str(customer_id))
                    customer_mapping = CustomerUploadMapping.query.filter_by(
                        client_erp_credentials_id=credential_id_for_logging,
                        cin7_customer_id=customer_id_uuid,
                        upload_id=upload_id
                    ).first()
                    
                    if customer_mapping:
                        # Add order_id to the list if not already present
                        order_ids_list = customer_mapping.order_ids or []
                        if str(order_result_id) not in [str(oid) for oid in order_ids_list]:
                            order_ids_list.append(str(order_result_id))
                            customer_mapping.order_ids = order_ids_list
                            logger.debug(f"Updated customer mapping for customer {customer_id} with order {order_result_id}")
                except (ValueError, AttributeError) as e:
                    logger.debug(f"Could not parse customer ID for mapping update: {customer_id} - {str(e)}")
            
            # Update product mappings
            for product_id in product_ids:
                try:
                    product_id_uuid = uuid.UUID(str(product_id))
                    product_mapping = ProductUploadMapping.query.filter_by(
                        client_erp_credentials_id=credential_id_for_logging,
                        cin7_product_id=product_id_uuid,
                        upload_id=upload_id
                    ).first()
                    
                    if product_mapping:
                        # Add order_id to the list if not already present
                        order_ids_list = product_mapping.order_ids or []
                        if str(order_result_id) not in [str(oid) for oid in order_ids_list]:
                            order_ids_list.append(str(order_result_id))
                            product_mapping.order_ids = order_ids_list
                            logger.debug(f"Updated product mapping for product {product_id} with order {order_result_id}")
                except (ValueError, AttributeError) as e:
                    logger.debug(f"Could not parse product ID for mapping update: {product_id} - {str(e)}")
        except Exception as mapping_error:
            logger.warning(f"Failed to update upload mappings for order {order_result_id}: {str(mapping_error)}")
            # Don't fail the order if mapping update fails
        
        db.session.commit()
        
        return {
            'status': 'success',
            'sale_id': str(sale_id),
            'sale_order_id': str(sale_order_id) if sale_order_id else None,
            'order_data': order_result.order_data
        }
    
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error processing order {order_key}: {error_msg}", exc_info=True)
        
        # Improve error message for common issues
        if "'NoneType' object has no attribute 'strip'" in error_msg:
            error_msg = "Missing required data in CSV. Please check that column mappings are configured correctly in the Mappings page. Required fields may be missing or empty."
        elif "No column mapping" in error_msg:
            error_msg = "Column mappings not configured. Please set up CSV column mappings in the Mappings page for this client."
        elif "cannot access local variable 'sale_id'" in error_msg:
            error_msg = f"Processing error: {error_msg}. This may indicate an issue with the order processing logic."
        elif "TaxRule is required" in error_msg:
            # Simplify TaxRule error if customer is not found and auto-create is off
            auto_create_customers_products = settings.get('auto_create_customers_products', False)
            if not matching_details['customer'].get('found') and not auto_create_customers_products:
                error_parts = []
                # Try to get customer name from matching_details first, then from order_data
                customer_name = (matching_details['customer'].get('name', '') or 
                               order_data.get('customer_name', '') or 
                               primary_row.get('CustomerName') or 
                               primary_row.get('customer_name', '')).strip()
                if customer_name and customer_name != 'N/A':
                    error_parts.append(f"Customer '{customer_name}' not found in Cin7")
                else:
                    error_parts.append("Customer not found in Cin7")
                
                # Add missing SKUs if any
                missing_products = [p for p in matching_details.get('products', []) if not p.get('found')]
                if missing_products:
                    missing_skus = [p.get('sku', 'N/A') for p in missing_products if p.get('sku')]
                    if missing_skus:
                        if len(missing_skus) == 1:
                            error_parts.append(f"SKU '{missing_skus[0]}' not found in Cin7")
                        elif len(missing_skus) <= 3:
                            sku_list = ', '.join([f"'{s}'" for s in missing_skus])
                            error_parts.append(f"SKUs {sku_list} not found in Cin7")
                        else:
                            sku_list = ', '.join([f"'{s}'" for s in missing_skus[:3]])
                            error_parts.append(f"SKUs {sku_list} and {len(missing_skus) - 3} more not found in Cin7")
                
                error_msg = ' | '.join(error_parts) if error_parts else "Customer not found in Cin7"
            # Otherwise, keep the original TaxRule error message
        
        # Ensure order_data is populated even on error
        if not order_data:
            # Build order_data from available information
            order_data = {
                'customer_name': primary_row.get('CustomerName') or primary_row.get('customer_name', '') or '',
                'po_number': primary_row.get('CustomerReference') or primary_row.get('po_number', '') or '',
                'order_date': primary_row.get('SaleDate') or primary_row.get('order_date', '') or '',
                'order_number': primary_row.get('SaleOrderNumber') or primary_row.get('order_number', '') or '',
                'all_rows': [r for r in order_rows],
                'column_mapping': column_mapping
            }
        
        # Try to build sale/order payloads for display even if they failed
        sale_payload_for_display = None
        sale_order_payload_for_display = None
        try:
            if 'sale_data' not in locals():
                sale_payload_for_display = builder.build_sale(primary_row, column_mapping) if builder else None
            else:
                sale_payload_for_display = sale_data
        except:
            pass  # Ignore errors when building for display
        
        try:
            if 'sale_order_data' not in locals():
                # First, check if sale_order_for_what_is_needed was already built (e.g., when customer not found)
                # This happens when TaxRule error occurs and we build it with all products
                if 'sale_order_for_what_is_needed' in locals() and sale_order_for_what_is_needed:
                    # Check if it has Lines (it should if we built it properly)
                    if sale_order_for_what_is_needed.get('Lines') and len(sale_order_for_what_is_needed.get('Lines', [])) > 0:
                        # Use the already-built payload with all products
                        sale_order_payload_for_display = sale_order_for_what_is_needed
                    else:
                        # It exists but has no lines - build it with products
                        sale_order_payload_for_display = {
                            'SaleID': '<SALE_ID_PLACEHOLDER>',
                            'Lines': []
                        }
                        # Build lines from order_rows (same logic as below)
                        sku_col = column_mapping.get('SKU') or column_mapping.get('sku')
                        if sku_col and order_rows:
                            for row in order_rows:
                                sku = str(row.get(sku_col, '')).strip() if sku_col in row else None
                                if sku:
                                    # Find product in matching_details or lookup
                                    product_match = None
                                    product_data = None
                                    
                                    if 'matching_details' in locals() and matching_details.get('products'):
                                        product_match = next((p for p in matching_details['products'] if p.get('sku') == sku), None)
                                    
                                    if not product_match and builder:
                                        product_data = builder._lookup_product_by_sku(sku)
                                        if product_data and product_data.get('ID'):
                                            if 'matching_details' not in locals():
                                                matching_details = {'products': []}
                                            elif 'products' not in matching_details:
                                                matching_details['products'] = []
                                            product_match = {
                                                'sku': sku,
                                                'found': True,
                                                'cin7_id': product_data.get('ID')
                                            }
                                            matching_details['products'].append(product_match)
                                    
                                    # Extract quantity and price
                                    qty_col = column_mapping.get('Quantity') or column_mapping.get('QuantityOrdered')
                                    price_col = column_mapping.get('Price') or column_mapping.get('UnitPrice')
                                    
                                    quantity = None
                                    if qty_col and qty_col in row:
                                        try:
                                            qty_val = str(row[qty_col]).replace('$', '').replace(',', '').strip()
                                            quantity = float(qty_val) if qty_val else None
                                        except (ValueError, TypeError):
                                            quantity = None
                                    
                                    price = None
                                    if price_col and price_col in row:
                                        try:
                                            price_val = str(row[price_col]).replace('$', '').replace(',', '').strip()
                                            price = float(price_val) if price_val else None
                                        except (ValueError, TypeError):
                                            price = None
                                    
                                    is_found = product_match and product_match.get('found')
                                    product_id = product_match.get('cin7_id') if product_match else (product_data.get('ID') if product_data else None)
                                    
                                    line_item = {
                                        'SKU': sku,
                                        'ProductID': product_id,
                                        'Quantity': quantity if quantity is not None else 0,
                                        'Price': price if price is not None else 0,
                                        '_not_found': not is_found,
                                        '_error': f'Product SKU \"{sku}\" not found in Cin7' if not is_found else None
                                    }
                                    sale_order_payload_for_display['Lines'].append(line_item)
                else:
                    # Build sale_order_payload with ALL products (matched and unmatched) for display
                    # This ensures products are shown even when customer is not found
                    sale_order_payload_for_display = {
                        'SaleID': '<SALE_ID_PLACEHOLDER>',
                        'Lines': []
                    }
                    
                    # Ensure matching_details has products array
                    if 'matching_details' not in locals():
                        matching_details = {'products': []}
                    elif 'products' not in matching_details:
                        matching_details['products'] = []
                    
                    # Get all products from order_rows and matching_details
                    sku_col = column_mapping.get('SKU') or column_mapping.get('sku')
                    if sku_col and order_rows:
                        for row in order_rows:
                            sku = str(row.get(sku_col, '')).strip() if sku_col in row else None
                            if sku:
                                # Find product in matching_details or lookup
                                product_match = None
                                product_data = None
                                
                                # First check matching_details
                                if matching_details.get('products'):
                                    product_match = next((p for p in matching_details['products'] if p.get('sku') == sku), None)
                                
                                # If not in matching_details, try to lookup in builder cache
                                if not product_match and builder:
                                    product_data = builder._lookup_product_by_sku(sku)
                                    if product_data and product_data.get('ID'):
                                        # Add to matching_details so frontend can show check mark
                                        product_match = {
                                            'sku': sku,
                                            'found': True,
                                            'cin7_id': product_data.get('ID')
                                        }
                                        matching_details['products'].append(product_match)
                                
                                # Extract quantity and price from row
                                qty_col = column_mapping.get('Quantity') or column_mapping.get('QuantityOrdered')
                                price_col = column_mapping.get('Price') or column_mapping.get('UnitPrice')
                                
                                quantity = None
                                if qty_col and qty_col in row:
                                    try:
                                        qty_val = str(row[qty_col]).replace('$', '').replace(',', '').strip()
                                        quantity = float(qty_val) if qty_val else None
                                    except (ValueError, TypeError):
                                        quantity = None
                                
                                price = None
                                if price_col and price_col in row:
                                    try:
                                        price_val = str(row[price_col]).replace('$', '').replace(',', '').strip()
                                        price = float(price_val) if price_val else None
                                    except (ValueError, TypeError):
                                        price = None
                                
                                # Determine if product was found
                                is_found = product_match and product_match.get('found')
                                product_id = product_match.get('cin7_id') if product_match else (product_data.get('ID') if product_data else None)
                                
                                # Build line item
                                line_item = {
                                    'SKU': sku,
                                    'ProductID': product_id,
                                    'Quantity': quantity if quantity is not None else 0,
                                    'Price': price if price is not None else 0,
                                    '_not_found': not is_found,
                                    '_error': f'Product SKU "{sku}" not found in Cin7' if not is_found else None
                                }
                                sale_order_payload_for_display['Lines'].append(line_item)
            else:
                sale_order_payload_for_display = sale_order_data
        except Exception as e:
            logger.warning(f"Error building sale_order_payload_for_display: {str(e)}")
            # Fallback: create empty payload
            sale_order_payload_for_display = {
                'SaleID': '<SALE_ID_PLACEHOLDER>',
                'Lines': []
            }
        
        # Ensure order_data includes all available information
        order_data.update({
            'matching_details': matching_details,
            'sale_payload': sale_payload_for_display,
            'sale_order_payload': sale_order_payload_for_display,
            'what_is_needed': what_is_needed if 'what_is_needed' in locals() else None,
            'attempted_send': False
        })
        
        order_result.status = 'failed'
        order_result.error_message = error_msg
        # Set error_type to 'data_missing' if it's a customer/product not found error
        if "TaxRule is required" in error_msg and 'matching_details' in locals() and not matching_details.get('customer', {}).get('found'):
            order_result.error_type = 'data_missing'
        elif "Customer" in error_msg and "not found" in error_msg:
            order_result.error_type = 'data_missing'
        else:
            order_result.error_type = categorize_error(error_msg)
        order_result.order_data = order_data
        # Only set sale_id if it was successfully created
        if sale_id:
            order_result.sale_id = sale_id
        if sale_order_id:
            order_result.sale_order_id = sale_order_id
        order_result.processed_at = datetime.utcnow()
        db.session.commit()
        
        return {
            'status': 'failed',
            'error_message': error_msg,
            'order_data': order_data,
            'sale_id': str(sale_id) if sale_id else None,
            'sale_order_id': str(sale_order_id) if sale_order_id else None
        }


def process_webhook_csv(
    upload_id: uuid.UUID,
    client_erp_credentials_id: uuid.UUID,
    csv_content: bytes,
    filename: str,
    trigger: str = 'webhook',
    user_id: Optional[uuid.UUID] = None
) -> Dict:
    """
    Process CSV from webhook: parse, validate, group orders, and process each individually.
    
    Args:
        upload_id: SalesOrderUpload ID
        client_erp_credentials_id: Client ERP credentials ID
        csv_content: CSV file content as bytes
        filename: CSV filename
        
    Returns:
        Processing summary dict
    """
    # Parse CSV
    parser = CSVParser()
    rows, errors, skipped_rows = parser.parse_file(csv_content, filename)
    
    if errors:
        return {'error': 'CSV parsing failed', 'errors': errors}
    
    if not rows:
        return {'error': 'CSV file is empty or all rows were incomplete', 'skipped_rows': skipped_rows}
    
    # Detect columns
    detected_mappings = parser.detect_columns(rows)
    
    # Get default mapping if available
    default_mapping = {}
    default_mapping_obj = ClientCsvMapping.query.filter_by(
        client_erp_credentials_id=client_erp_credentials_id,
        is_default=True
    ).first()
    
    if default_mapping_obj:
        default_mapping = default_mapping_obj.column_mapping or {}
    
    # Merge detected mappings with default mapping (default takes precedence)
    # BUT: Always preserve SaleOrderNumber and InvoiceNumber from detection if not in default
    # These are critical for order grouping
    column_mapping = {}
    # First, use detected mappings
    for cin7_field, matches in detected_mappings.items():
        if matches and len(matches) > 0:
            column_mapping[cin7_field] = matches[0]
    # Then, override with default mapping if it exists
    for cin7_field, csv_column in default_mapping.items():
        if csv_column:
            column_mapping[cin7_field] = csv_column
    
    # Critical: Ensure SaleOrderNumber or InvoiceNumber is present for order grouping
    # If default mapping doesn't have it, use detected mapping
    if 'SaleOrderNumber' not in column_mapping and 'InvoiceNumber' not in column_mapping:
        # Try to get from detected mappings
        if 'SaleOrderNumber' in detected_mappings and detected_mappings['SaleOrderNumber']:
            column_mapping['SaleOrderNumber'] = detected_mappings['SaleOrderNumber'][0]
            logger.info(f"Auto-mapped SaleOrderNumber to '{detected_mappings['SaleOrderNumber'][0]}' for order grouping")
        elif 'InvoiceNumber' in detected_mappings and detected_mappings['InvoiceNumber']:
            column_mapping['InvoiceNumber'] = detected_mappings['InvoiceNumber'][0]
            logger.info(f"Auto-mapped InvoiceNumber to '{detected_mappings['InvoiceNumber'][0]}' for order grouping")
    
    # Log final column mapping for debugging
    if 'SaleOrderNumber' in column_mapping or 'InvoiceNumber' in column_mapping:
        grouping_col = column_mapping.get('SaleOrderNumber') or column_mapping.get('InvoiceNumber')
        logger.info(f"Order grouping will use: {grouping_col}")
    else:
        logger.warning(f"WARNING: No SaleOrderNumber or InvoiceNumber mapped - orders may not group correctly! Available columns: {list(rows[0]['data'].keys()) if rows else []}")
    
    if not column_mapping:
        return {
            'error': 'No column mapping found or detected',
            'details': 'Please configure CSV column mappings in the Mappings page for this client. The system could not automatically detect required columns.',
            'detected_columns': list(detected_mappings.keys()) if detected_mappings else [],
            'csv_columns': list(rows[0]['data'].keys()) if rows else []
        }
    
    # Get credentials and settings
    check_customer_cols_query = text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_schema = 'voyager' 
        AND table_name = 'client_erp_credentials' 
            AND column_name IN ('customer_account_receivable', 'customer_revenue_account', 'customer_tax_rule', 'customer_attribute_set', 'product_costing_method', 'product_default_price_tier', 'product_default_price', 'product_currency', 'auto_create_customers_products')
    """)
    existing_customer_cols = {row[0] for row in db.session.execute(check_customer_cols_query).fetchall()}
    existing_product_cols = {
        'product_costing_method', 'product_default_price_tier', 'product_default_price', 'product_currency', 'auto_create_customers_products'
    } & existing_customer_cols  # Intersection to get only product columns that exist
    
    select_fields = [
        'cec.id',
        'cec.cin7_api_auth_accountid as account_id',
        'cec.cin7_api_auth_applicationkey as application_key',
        'cec.sale_type',
        'cec.tax_rule',
        'cec.default_status'
    ]
    
    if 'customer_account_receivable' in existing_customer_cols:
        select_fields.append('cec.customer_account_receivable')
    else:
        select_fields.append('NULL as customer_account_receivable')
    
    if 'customer_revenue_account' in existing_customer_cols:
        select_fields.append('cec.customer_revenue_account')
    else:
        select_fields.append('NULL as customer_revenue_account')
    
    if 'customer_tax_rule' in existing_customer_cols:
        select_fields.append('cec.customer_tax_rule')
    else:
        select_fields.append('NULL as customer_tax_rule')
    
    if 'customer_attribute_set' in existing_customer_cols:
        select_fields.append('cec.customer_attribute_set')
    else:
        select_fields.append('NULL as customer_attribute_set')
    
    if 'product_costing_method' in existing_product_cols:
        select_fields.append('cec.product_costing_method')
    else:
        select_fields.append('NULL as product_costing_method')
    
    if 'product_default_price_tier' in existing_product_cols:
        select_fields.append('cec.product_default_price_tier')
    else:
        select_fields.append('NULL as product_default_price_tier')
    
    if 'product_default_price' in existing_product_cols:
        select_fields.append('cec.product_default_price')
    else:
        select_fields.append('NULL as product_default_price')
    
    if 'product_currency' in existing_product_cols:
        select_fields.append('cec.product_currency')
    else:
        select_fields.append('NULL as product_currency')
    
    if 'auto_create_customers_products' in existing_product_cols:
        select_fields.append('cec.auto_create_customers_products')
    else:
        select_fields.append('false as auto_create_customers_products')
    
    query = text(f"""
        SELECT 
            {', '.join(select_fields)}
        FROM voyager.client_erp_credentials cec
        WHERE cec.erp = 'cin7_core'
        AND cec.id = :cred_id
    """)
    result = db.session.execute(query, {'cred_id': client_erp_credentials_id})
    cred_row = result.fetchone()
    
    if not cred_row or not cred_row.account_id or not cred_row.application_key:
        return {'error': 'Cin7 credentials not configured'}
    
    account_id = cred_row.account_id
    application_key = cred_row.application_key
    sale_type = cred_row.sale_type
    tax_rule = cred_row.tax_rule
    default_status = cred_row.default_status
    
    # Extract customer default fields
    customer_account_receivable = None
    customer_revenue_account = None
    customer_tax_rule = None
    customer_attribute_set = None
    
    if 'customer_account_receivable' in existing_customer_cols and hasattr(cred_row, 'customer_account_receivable'):
        customer_account_receivable = cred_row.customer_account_receivable if cred_row.customer_account_receivable else None
    if 'customer_revenue_account' in existing_customer_cols and hasattr(cred_row, 'customer_revenue_account'):
        customer_revenue_account = cred_row.customer_revenue_account if cred_row.customer_revenue_account else None
    if 'customer_tax_rule' in existing_customer_cols and hasattr(cred_row, 'customer_tax_rule'):
        customer_tax_rule = str(cred_row.customer_tax_rule) if cred_row.customer_tax_rule else None
    if 'customer_attribute_set' in existing_customer_cols and hasattr(cred_row, 'customer_attribute_set'):
        customer_attribute_set = cred_row.customer_attribute_set
    
    # Extract product default fields
    product_costing_method = None
    product_default_price_tier = None
    product_default_price = None
    product_currency = None
    
    if 'product_costing_method' in existing_product_cols and hasattr(cred_row, 'product_costing_method'):
        product_costing_method = cred_row.product_costing_method if cred_row.product_costing_method else None
    if 'product_default_price_tier' in existing_product_cols and hasattr(cred_row, 'product_default_price_tier'):
        product_default_price_tier = cred_row.product_default_price_tier if cred_row.product_default_price_tier else None
    if 'product_default_price' in existing_product_cols and hasattr(cred_row, 'product_default_price'):
        product_default_price = float(cred_row.product_default_price) if cred_row.product_default_price is not None else None
    if 'product_currency' in existing_product_cols and hasattr(cred_row, 'product_currency'):
        product_currency = cred_row.product_currency if cred_row.product_currency else None
    
    # Get auto_create_customers_products from credentials
    auto_create_customers_products = False
    if 'auto_create_customers_products' in existing_product_cols and hasattr(cred_row, 'auto_create_customers_products'):
        auto_create_customers_products = bool(cred_row.auto_create_customers_products) if cred_row.auto_create_customers_products else False
    
    # Get settings
    client_query = text("""
        SELECT client_id FROM voyager.client_erp_credentials
        WHERE id = :cred_id
    """)
    client_result = db.session.execute(client_query, {'cred_id': client_erp_credentials_id})
    client_row = client_result.fetchone()
    
    settings_obj = None
    if client_row and client_row.client_id:
        settings_obj = ClientSettings.query.filter_by(client_id=client_row.client_id).first()
    
    settings = {}
    if settings_obj:
        settings = {
            'default_status': default_status or settings_obj.default_status,
            'default_currency': settings_obj.default_currency,
            'tax_inclusive': settings_obj.tax_inclusive,
            'default_location': settings_obj.default_location,
            'default_delay_between_orders': settings_obj.default_delay_between_orders,
            'sale_type': sale_type,
            'tax_rule': tax_rule,
            'customer_account_receivable': customer_account_receivable,
            'customer_revenue_account': customer_revenue_account,
            'customer_tax_rule': customer_tax_rule,
            'customer_attribute_set': customer_attribute_set,
            'auto_create_customers_products': auto_create_customers_products,
            'product_costing_method': product_costing_method or 'FIFO',
            'product_default_price_tier': product_default_price_tier or 'Tier 1',
            'product_default_price': product_default_price if product_default_price is not None else 0.0,
            'product_currency': product_currency or 'USD'
        }
    else:
        settings = {
            'default_status': default_status or 'DRAFT',
            'default_currency': 'USD',
            'tax_inclusive': False,
            'default_location': None,
            'default_delay_between_orders': 0.7,
            'sale_type': sale_type,
            'tax_rule': tax_rule,
            'customer_account_receivable': customer_account_receivable,
            'customer_revenue_account': customer_revenue_account,
            'customer_tax_rule': customer_tax_rule,
            'customer_attribute_set': customer_attribute_set,
            'auto_create_customers_products': auto_create_customers_products,
            'product_costing_method': product_costing_method or 'FIFO',
            'product_default_price_tier': product_default_price_tier or 'Tier 1',
            'product_default_price': product_default_price if product_default_price is not None else 0.0,
            'product_currency': product_currency or 'USD'
        }
    
    # Create logging callback
    credential_id_for_logging = client_erp_credentials_id
    # Capture trigger and user_id for the closure
    captured_trigger = trigger
    captured_user_id = user_id
    # Use a list to store current order_id (mutable for closure)
    current_order_id = [None]  # Use list to make it mutable in closure
    
    def log_api_call(endpoint, method, request_url, request_headers, request_body,
                     response_status, response_body, error_message, duration_ms):
        """Callback to log API calls to database"""
        logger.info(f"log_api_call invoked: {method} {endpoint}, upload_id: {upload_id}, order_id: {current_order_id[0]}, trigger: {captured_trigger}")
        try:
            # Check if we're in an app context (should be true if called from background thread)
            try:
                from flask import has_app_context
                if not has_app_context():
                    logger.error("log_api_call called outside of Flask app context!")
                    return
            except (ImportError, AttributeError):
                # Flask version might not have has_app_context, try accessing current_app
                try:
                    from flask import current_app
                    _ = current_app.name  # Try to access to trigger RuntimeError if no context
                except RuntimeError:
                    logger.error("log_api_call called outside of Flask app context!")
                    return
            # Parse response_body if it's a string (raw JSON)
            parsed_response_body = response_body
            if isinstance(response_body, str):
                try:
                    import json
                    parsed_response_body = json.loads(response_body)
                except (json.JSONDecodeError, TypeError):
                    # If parsing fails, keep as string
                    parsed_response_body = response_body
            
            try:
                # Use 'validation' trigger for duplicate PO checks (GET /saleList)
                # This is a validation step, not an upload step
                actual_trigger = 'validation' if (endpoint == '/saleList' and method == 'GET') else captured_trigger
                
                log_entry = Cin7ApiLog(
                    id=uuid.uuid4(),
                    client_id=credential_id_for_logging,
                    user_id=captured_user_id,  # Use captured user_id (None for webhooks, actual user_id for manual uploads)
                    upload_id=upload_id,
                    order_id=current_order_id[0],  # Use current order_id from closure
                    trigger=actual_trigger,  # Use 'validation' for duplicate PO checks, otherwise use captured trigger
                    endpoint=endpoint,
                    method=method,
                    request_url=request_url,
                    request_headers=request_headers,
                    request_body=request_body,
                    response_status=response_status,
                    response_body=parsed_response_body,
                    error_message=error_message,
                    duration_ms=duration_ms
                )
                db.session.add(log_entry)
                db.session.commit()
                logger.info(f"✓ Logged API call: {method} {endpoint} - Status: {response_status}, trigger: {actual_trigger}, upload_id: {upload_id}")
            except Exception as trigger_error:
                error_str = str(trigger_error).lower()
                logger.warning(f"Error in logger callback (first attempt): {str(trigger_error)}")
                db.session.rollback()
                if 'trigger' in error_str or 'column' in error_str:
                    try:
                        log_entry = Cin7ApiLog(
                            id=uuid.uuid4(),
                            client_id=credential_id_for_logging,
                            user_id=captured_user_id,  # Use captured user_id (None for webhooks, actual user_id for manual uploads)
                            upload_id=upload_id,
                            endpoint=endpoint,
                            method=method,
                            request_url=request_url,
                            request_headers=request_headers,
                            request_body=request_body,
                            response_status=response_status,
                            response_body=parsed_response_body,
                            error_message=error_message,
                            duration_ms=duration_ms
                        )
                        db.session.add(log_entry)
                        db.session.commit()
                        logger.info(f"✓ Logged API call (fallback): {method} {endpoint} - Status: {response_status}, trigger: {captured_trigger}, upload_id: {upload_id}")
                    except Exception as fallback_error:
                        logger.error(f"✗ Fallback logging also failed: {str(fallback_error)}", exc_info=True)
                        db.session.rollback()
                else:
                    logger.error(f"✗ Non-trigger error in logger callback: {str(trigger_error)}", exc_info=True)
                    # Don't raise - we don't want to break the main flow if logging fails
        except Exception as e:
            logger.error(f"✗ Error logging API call: {str(e)}", exc_info=True)
            logger.error(f"  - Endpoint: {endpoint}, Method: {method}")
            logger.error(f"  - Upload ID: {upload_id}, Trigger: {captured_trigger}, User ID: {captured_user_id}")
            import traceback
            logger.error(f"  - Traceback: {traceback.format_exc()}")
            try:
                db.session.rollback()
            except:
                pass
    
    # Initialize API client
    logger.info(f"Initializing API client with logger_callback - trigger: {captured_trigger}, user_id: {captured_user_id}, upload_id: {upload_id}")
    api_client = Cin7SalesAPI(
        account_id=str(account_id),
        application_key=str(application_key),
        base_url='https://inventory.dearsystems.com/ExternalApi/v2/',
        logger_callback=log_api_call
    )
    # Store reference to current_order_id list so process_single_order can update it
    api_client._current_order_id_ref = current_order_id
    logger.info(f"API client initialized - logger_callback set: {api_client.logger_callback is not None}")
    
    # Group rows into orders
    validator = SalesOrderValidator(api_client)
    row_groups = validator._group_rows_by_order(rows, column_mapping)
    logger.info(f"Grouped {len(rows)} rows into {len(row_groups)} order groups")
    
    # Log order keys for debugging
    if len(row_groups) != len(set(row_groups.keys())):
        logger.warning(f"WARNING: Duplicate order keys detected in grouping!")
    for order_key, group_rows in row_groups.items():
        logger.debug(f"Order key '{order_key}': {len(group_rows)} row(s) - rows {[r['row_number'] for r in group_rows]}")
    
    if not row_groups:
        logger.warning(f"No order groups found - this will result in 0 orders processed")
        upload = SalesOrderUpload.query.get(upload_id)
        if upload:
            upload.status = 'failed'
            upload.error_log = ['No valid order groups found - check column mapping for CustomerReference, InvoiceNumber, or SaleOrderNumber']
            upload.completed_at = datetime.utcnow()
            upload.total_rows = len(rows)
            db.session.commit()
            emit_upload_event('upload_status_changed', str(upload_id), str(upload.client_id) if upload.client_id else None)
        return {
            'successful': 0,
            'failed': 0,
            'total_orders': 0,
            'error': 'No valid order groups found - check column mapping'
        }
    
    # Preload customers and products from database cache for better performance
    try:
        customer_count, product_count = validator.preload_customers_and_products(
            db_session=db.session,
            client_erp_credentials_id=client_erp_credentials_id
        )
        logger.info(f"Preloaded {customer_count} customers and {product_count} products for webhook processing")
    except Exception as e:
        logger.warning(f"Warning: Failed to preload customers/products: {str(e)}")
        # Continue anyway - will use API calls as fallback
    
    # Initialize builder with preloaded data
    builder = SalesOrderBuilder(
        settings, 
        api_client,
        preloaded_customers=getattr(validator, 'customer_lookup', {}),
        preloaded_products=getattr(validator, 'product_lookup', {})
    )
    
    # PHASE 1: Auto-create ALL missing customers and products across ALL orders
    # This ensures everything exists before we start creating orders
    auto_create_customers_products = settings.get('auto_create_customers_products', False)
    
    if auto_create_customers_products:
        logger.info("PHASE 1: Auto-creating all missing customers and products across all orders...")
        
        # Collect all unique customers and products from all orders
        all_customers_needed = set()
        all_products_needed = set()
        customer_name_col = column_mapping.get('CustomerName', '')
        sku_col = column_mapping.get('SKU') or column_mapping.get('ProductCode')
        
        for order_key, group_rows in row_groups.items():
            for row_data in group_rows:
                row = row_data['data']
                
                # Collect customer
                if customer_name_col and customer_name_col in row:
                    customer_name = str(row[customer_name_col]).strip() if row[customer_name_col] else None
                    if customer_name:
                        all_customers_needed.add(customer_name)
                
                # Collect products
                if sku_col and sku_col in row:
                    sku = str(row[sku_col]).strip() if row[sku_col] else None
                    if sku:
                        all_products_needed.add(sku)
        
        logger.info(f"Found {len(all_customers_needed)} unique customers and {len(all_products_needed)} unique products across all orders")
        
        # Auto-create all missing customers
        auto_created_customer_ids = []
        for customer_name in all_customers_needed:
            # Check if customer already exists
            customer = builder._lookup_customer_by_name(customer_name)
            if not customer:
                logger.info(f"Auto-creating customer '{customer_name}'...")
                try:
                    # Build customer payload
                    customer_payload = {
                        'Name': customer_name,
                        'Status': 'Active',
                        'Currency': settings.get('default_currency', 'USD'),
                        'PaymentTerm': '30 days'
                    }
                    
                    # Add required fields from settings
                    if settings.get('customer_account_receivable'):
                        customer_payload['AccountReceivable'] = settings['customer_account_receivable']
                    if settings.get('customer_revenue_account'):
                        customer_payload['RevenueAccount'] = settings['customer_revenue_account']
                    
                    # TaxRule - need to convert UUID to Name
                    tax_rule_uuid = settings.get('customer_tax_rule')
                    if tax_rule_uuid:
                        try:
                            tax_rules = api_client.get_tax_rules()
                            for rule in tax_rules:
                                if str(rule.get('ID')) == str(tax_rule_uuid):
                                    customer_payload['TaxRule'] = rule.get('Name')
                                    break
                        except Exception as e:
                            logger.warning(f"Could not fetch tax rules: {e}")
                    
                    if settings.get('customer_attribute_set'):
                        customer_payload['AttributeSet'] = settings['customer_attribute_set']
                    
                    # Create customer
                    create_success, create_message, create_response = api_client.create_customer(customer_payload)
                    
                    if create_success and create_response:
                        # Extract customer from response (may be wrapped in CustomerList)
                        customer_data = None
                        if isinstance(create_response, dict):
                            if 'ID' in create_response:
                                customer_data = create_response
                            elif 'CustomerList' in create_response and isinstance(create_response['CustomerList'], list) and len(create_response['CustomerList']) > 0:
                                customer_data = create_response['CustomerList'][0]
                        
                        if customer_data:
                            customer_id = customer_data.get('ID')
                            if customer_id:
                                try:
                                    customer_id_uuid = uuid.UUID(str(customer_id))
                                    from routes.sales import refresh_single_customer_cache
                                    refresh_single_customer_cache(credential_id_for_logging, customer_id_uuid, customer_data, is_new=True)
                                    
                                    # Update builder cache
                                    customer_name_clean = customer_name.strip()
                                    builder.preloaded_customers[customer_name_clean] = customer_data
                                    builder.preloaded_customers[customer_name_clean.upper()] = customer_data
                                    builder.preloaded_customers[customer_name_clean.lower()] = customer_data
                                    
                                    # Update customer cache
                                    cache_key = f"{customer_name_clean}|None"
                                    builder._customer_cache[cache_key] = customer_data
                                    
                                    auto_created_customer_ids.append(customer_id_uuid)
                                    
                                    # Create upload mapping for this customer
                                    try:
                                        customer_mapping = CustomerUploadMapping(
                                            id=uuid.uuid4(),
                                            client_erp_credentials_id=credential_id_for_logging,
                                            cin7_customer_id=customer_id_uuid,
                                            upload_id=upload_id,
                                            order_ids=[]  # Will be populated when orders are created
                                        )
                                        db.session.add(customer_mapping)
                                        logger.info(f"Created customer upload mapping for customer '{customer_name}' (ID: {customer_id})")
                                    except Exception as mapping_error:
                                        logger.warning(f"Failed to create customer upload mapping: {str(mapping_error)}")
                                    
                                    db.session.commit()
                                    logger.info(f"✓ Auto-created customer '{customer_name}' with ID {customer_id}")
                                except (ValueError, AttributeError) as e:
                                    logger.error(f"Invalid customer ID format: {customer_id} - {str(e)}")
                        else:
                            logger.error(f"Customer created but response format unexpected: {create_response}")
                    elif '409' in str(create_message) or 'already exists' in str(create_message).lower():
                        # Customer already exists - look it up and cache it
                        logger.info(f"Customer '{customer_name}' already exists, looking it up...")
                        try:
                            customers = api_client.search_customer(name=customer_name)
                            if customers and len(customers) > 0:
                                existing_customer = customers[0]
                                customer_id = existing_customer.get('ID')
                                if customer_id:
                                    try:
                                        customer_id_uuid = uuid.UUID(str(customer_id))
                                        from routes.sales import refresh_single_customer_cache
                                        refresh_single_customer_cache(credential_id_for_logging, customer_id_uuid, existing_customer, is_new=False)
                                        
                                        # Update builder cache
                                        customer_name_clean = customer_name.strip()
                                        builder.preloaded_customers[customer_name_clean] = existing_customer
                                        builder.preloaded_customers[customer_name_clean.upper()] = existing_customer
                                        builder.preloaded_customers[customer_name_clean.lower()] = existing_customer
                                        cache_key = f"{customer_name_clean}|None"
                                        builder._customer_cache[cache_key] = existing_customer
                                        db.session.commit()
                                        logger.info(f"✓ Found and cached existing customer '{customer_name}'")
                                    except (ValueError, AttributeError) as e:
                                        logger.error(f"Invalid customer ID format: {customer_id} - {str(e)}")
                        except Exception as e:
                            logger.error(f"Error looking up existing customer: {str(e)}", exc_info=True)
                except Exception as e:
                    logger.error(f"Error auto-creating customer '{customer_name}': {str(e)}", exc_info=True)
        
        # Auto-create all missing products
        # First, collect product names from CSV rows
        product_names_map = {}  # Map SKU to product name from CSV
        product_name_col = column_mapping.get('ProductName') or column_mapping.get('Name') or column_mapping.get('Item Description')
        
        for order_key, group_rows in row_groups.items():
            for row_data in group_rows:
                row = row_data['data']
                if sku_col and sku_col in row:
                    sku = str(row[sku_col]).strip() if row[sku_col] else None
                    if sku and sku not in product_names_map:
                        # Try to get product name from CSV
                        if product_name_col and product_name_col in row:
                            product_name = str(row[product_name_col]).strip() if row[product_name_col] else None
                            if product_name:
                                product_names_map[sku] = product_name
        
        auto_created_product_ids = []
        for sku in all_products_needed:
            # Check if product already exists in cache first (same pattern as customers)
            product = builder._lookup_product_by_sku(sku)
            if product:
                # Product already exists - update builder cache and skip creation
                logger.info(f"Product SKU '{sku}' already exists in cache, skipping creation")
                sku_clean = sku.strip()
                builder.preloaded_products[sku_clean] = product
                builder.preloaded_products[sku_clean.upper()] = product
                builder.preloaded_products[sku_clean.lower()] = product
                builder._product_cache[sku_clean] = product
                continue
            
            # Product not found - create it
            logger.info(f"Auto-creating product with SKU '{sku}'...")
            
            # #region agent log
            existing_before = CachedProduct.query.filter_by(
                client_erp_credentials_id=credential_id_for_logging,
                sku=sku
            ).first()
            debug_log("debug-product-flags", "run1", "H2", "routes/webhooks.py:process_webhook_csv",
                      "Before product creation attempt", {
                          "sku": sku,
                          "exists_in_cache": existing_before is not None,
                          "existing_is_new": existing_before.is_new if existing_before else None,
                          "existing_created_via_auto_create": existing_before.created_via_auto_create if existing_before else None
                      })
            # #endregion
            
            try:
                # Get product name from map or use SKU
                product_name = product_names_map.get(sku, sku)
                
                # Build product payload
                product_payload = {
                    'Name': product_name,
                    'SKU': sku,
                    'Status': 'Active',
                    'Type': 'Stock',
                    'CostingMethod': settings.get('product_costing_method', 'FIFO'),
                    'PriceTiers': {
                        settings.get('product_default_price_tier', 'Tier 1'): settings.get('product_default_price', 0.0)
                    }
                }
                
                # Create product
                create_success, create_message, create_response = api_client.create_product(product_payload)
                
                # #region agent log
                debug_log("debug-product-flags", "run1", "H5", "routes/webhooks.py:process_webhook_csv",
                          "Product creation API call result", {
                              "sku": sku,
                              "create_success": create_success,
                              "create_message": str(create_message)[:200] if create_message else None,
                              "has_response": create_response is not None
                          })
                # #endregion
                
                if create_success and create_response:
                    # Extract product from response (may be wrapped in ProductList)
                    # Match the customer pattern exactly
                    product_data = None
                    if isinstance(create_response, dict):
                        if 'ID' in create_response:
                            product_data = create_response
                        elif 'ProductList' in create_response and isinstance(create_response['ProductList'], list) and len(create_response['ProductList']) > 0:
                            product_data = create_response['ProductList'][0]
                    
                    # #region agent log
                    debug_log("debug-product-flags", "run2", "H1", "routes/webhooks.py:process_webhook_csv",
                              "After product_data extraction", {
                                  "sku": sku,
                                  "product_data_is_none": product_data is None,
                                  "has_id": product_data.get('ID') if product_data else None
                              })
                    # #endregion
                    
                    if product_data:
                        product_id = product_data.get('ID')
                        if product_id:
                            try:
                                product_id_uuid = uuid.UUID(str(product_id))
                                from routes.sales import refresh_single_product_cache
                                
                                # #region agent log
                                debug_log("debug-product-flags", "run2", "H1", "routes/webhooks.py:process_webhook_csv",
                                          "About to call refresh_single_product_cache with is_new=True",
                                          {"sku": sku, "product_id": str(product_id_uuid)})
                                # #endregion
                                
                                logger.info(f"Calling refresh_single_product_cache for SKU '{sku}' with is_new=True (main path)")
                                refresh_single_product_cache(credential_id_for_logging, product_id_uuid, sku, product_data, is_new=True)
                                
                                # Update builder cache
                                sku_clean = sku.strip()
                                builder.preloaded_products[sku_clean] = product_data
                                builder.preloaded_products[sku_clean.upper()] = product_data
                                builder.preloaded_products[sku_clean.lower()] = product_data
                                builder._product_cache[sku_clean] = product_data
                                
                                auto_created_product_ids.append(product_id_uuid)
                                
                                # Create upload mapping for this product
                                try:
                                    product_mapping = ProductUploadMapping(
                                        id=uuid.uuid4(),
                                        client_erp_credentials_id=credential_id_for_logging,
                                        cin7_product_id=product_id_uuid,
                                        upload_id=upload_id,
                                        order_ids=[]  # Will be populated when orders are created
                                    )
                                    db.session.add(product_mapping)
                                    logger.info(f"Created product upload mapping for SKU '{sku}' (ID: {product_id})")
                                except Exception as mapping_error:
                                    logger.warning(f"Failed to create product upload mapping: {str(mapping_error)}")
                                
                                db.session.commit()
                                logger.info(f"✓ Auto-created product SKU '{sku}' with ID {product_id} and set flags")
                            except (ValueError, AttributeError) as e:
                                logger.error(f"Invalid product ID format: {product_id} - {str(e)}")
                            except Exception as e:
                                logger.error(f"Error refreshing product cache for SKU '{sku}': {str(e)}", exc_info=True)
                    else:
                        logger.error(f"Product created but response format unexpected: {create_response}")
                        # Try to extract product ID from response even if format is unexpected
                        # Sometimes the API returns the product directly without wrapping
                        if create_response and not isinstance(create_response, dict):
                            logger.warning(f"create_response is not a dict: {type(create_response)}")
                        elif create_response and isinstance(create_response, dict):
                            # Log all keys to help debug
                            logger.warning(f"create_response keys: {list(create_response.keys())}")
                            # Try to find product data in any key
                            for key, value in create_response.items():
                                if isinstance(value, dict) and 'ID' in value:
                                    product_data = value
                                    logger.info(f"Found product data in key '{key}'")
                                    break
                                elif isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict) and 'ID' in value[0]:
                                    product_data = value[0]
                                    logger.info(f"Found product data in list at key '{key}'")
                                    break
                        
                        # If we found product_data, process it
                        if product_data:
                            product_id = product_data.get('ID')
                            if product_id:
                                try:
                                    product_id_uuid = uuid.UUID(str(product_id))
                                    from routes.sales import refresh_single_product_cache
                                    logger.info(f"Calling refresh_single_product_cache for SKU '{sku}' with is_new=True (fallback path)")
                                    refresh_single_product_cache(credential_id_for_logging, product_id_uuid, sku, product_data, is_new=True)
                                    
                                    # Update builder cache
                                    sku_clean = sku.strip()
                                    builder.preloaded_products[sku_clean] = product_data
                                    builder.preloaded_products[sku_clean.upper()] = product_data
                                    builder.preloaded_products[sku_clean.lower()] = product_data
                                    builder._product_cache[sku_clean] = product_data
                                    
                                    auto_created_product_ids.append(product_id_uuid)
                                    
                                    # Create upload mapping for this product
                                    try:
                                        product_mapping = ProductUploadMapping(
                                            id=uuid.uuid4(),
                                            client_erp_credentials_id=credential_id_for_logging,
                                            cin7_product_id=product_id_uuid,
                                            upload_id=upload_id,
                                            order_ids=[]  # Will be populated when orders are created
                                        )
                                        db.session.add(product_mapping)
                                        logger.info(f"Created product upload mapping for SKU '{sku}' (ID: {product_id}) - fallback path")
                                    except Exception as mapping_error:
                                        logger.warning(f"Failed to create product upload mapping: {str(mapping_error)}")
                                    
                                    db.session.commit()
                                    logger.info(f"✓ Auto-created product SKU '{sku}' with ID {product_id} and set flags (fallback)")
                                except (ValueError, AttributeError) as e:
                                    logger.error(f"Invalid product ID format: {product_id} - {str(e)}")
                                except Exception as e:
                                    logger.error(f"Error refreshing product cache for SKU '{sku}': {str(e)}", exc_info=True)
                elif '409' in str(create_message) or 'already exists' in str(create_message).lower():
                    # Product already exists - check cache first before making API call
                    logger.info(f"Product SKU '{sku}' already exists in Cin7, checking cache first...")
                    
                    # Check if product is already in our database cache
                    cached_product = CachedProduct.query.filter_by(
                        client_erp_credentials_id=credential_id_for_logging,
                        sku=sku
                    ).first()
                    
                    if cached_product and cached_product.product_data:
                        # Use cached product data - no need for API call
                        existing_product = cached_product.product_data
                        product_id = existing_product.get('ID')
                        if product_id:
                            try:
                                product_id_uuid = uuid.UUID(str(product_id))
                                
                                # Update builder cache
                                sku_clean = sku.strip()
                                builder.preloaded_products[sku_clean] = existing_product
                                builder.preloaded_products[sku_clean.upper()] = existing_product
                                builder.preloaded_products[sku_clean.lower()] = existing_product
                                builder._product_cache[sku_clean] = existing_product
                                
                                logger.info(f"✓ Found existing product SKU '{sku}' in cache (ID: {product_id}) - no API call needed")
                            except (ValueError, AttributeError) as e:
                                logger.error(f"Invalid product ID format in cache: {product_id} - {str(e)}")
                    else:
                        # Not in cache - need to fetch from API
                        logger.info(f"Product SKU '{sku}' not in cache, fetching from API...")
                        try:
                            products = api_client.search_product(sku=sku)
                            if products and len(products) > 0:
                                existing_product = products[0]
                                product_id = existing_product.get('ID')
                                if product_id:
                                    try:
                                        product_id_uuid = uuid.UUID(str(product_id))
                                        from routes.sales import refresh_single_product_cache
                                        refresh_single_product_cache(credential_id_for_logging, product_id_uuid, sku, existing_product, is_new=False)
                                        
                                        # Update builder cache
                                        sku_clean = sku.strip()
                                        builder.preloaded_products[sku_clean] = existing_product
                                        builder.preloaded_products[sku_clean.upper()] = existing_product
                                        builder.preloaded_products[sku_clean.lower()] = existing_product
                                        builder._product_cache[sku_clean] = existing_product
                                        db.session.commit()
                                        logger.info(f"✓ Fetched and cached existing product SKU '{sku}' from API")
                                    except (ValueError, AttributeError) as e:
                                        logger.error(f"Invalid product ID format: {product_id} - {str(e)}")
                        except Exception as e:
                            logger.error(f"Error looking up existing product: {str(e)}", exc_info=True)
            except Exception as e:
                logger.error(f"Error auto-creating product SKU '{sku}': {str(e)}", exc_info=True)
                # Product found in cache - check if it was auto-created in this run
                # If it's in the cache from preload, it might have been created in a previous run
                # We should still try to create it (API will return 409 if it exists), or check if flags need to be set
                logger.info(f"Product SKU '{sku}' found in cache, but checking if it needs to be created or flags need to be set...")
                # Check if product exists in database cache and has flags set
                cached_product = CachedProduct.query.filter_by(
                    client_erp_credentials_id=credential_id_for_logging,
                    sku=sku
                ).first()
                
                if cached_product:
                    # Product exists in database cache
                    if not cached_product.is_new and not cached_product.created_via_auto_create:
                        # Product exists but wasn't auto-created - try to create it anyway
                        # The API will return 409 if it already exists, which we'll handle
                        logger.info(f"Product SKU '{sku}' exists in cache but wasn't auto-created - attempting to create (will get 409 if exists)...")
                        try:
                            product_name = product_names_map.get(sku, sku)
                            product_payload = {
                                'Name': product_name,
                                'SKU': sku,
                                'Status': 'Active',
                                'Type': 'Stock',
                                'CostingMethod': settings.get('product_costing_method', 'FIFO'),
                                'PriceTiers': {
                                    settings.get('product_default_price_tier', 'Tier 1'): settings.get('product_default_price', 0.0)
                                }
                            }
                            
                            create_success, create_message, create_response = api_client.create_product(product_payload)
                            
                            if create_success and create_response:
                                # Product was created (or returned if already exists)
                                product_data = None
                                if isinstance(create_response, dict):
                                    if 'ID' in create_response:
                                        product_data = create_response
                                    elif 'ProductList' in create_response and isinstance(create_response['ProductList'], list) and len(create_response['ProductList']) > 0:
                                        product_data = create_response['ProductList'][0]
                                
                                if product_data:
                                    product_id = product_data.get('ID')
                                    if product_id:
                                        try:
                                            product_id_uuid = uuid.UUID(str(product_id))
                                            from routes.sales import refresh_single_product_cache
                                            # Always set is_new=True for products created in this path (they're being auto-created)
                                            # This matches the customer pattern - if we're creating it, it's new
                                            refresh_single_product_cache(credential_id_for_logging, product_id_uuid, sku, product_data, is_new=True)
                                            
                                            # Update builder cache
                                            sku_clean = sku.strip()
                                            builder.preloaded_products[sku_clean] = product_data
                                            builder.preloaded_products[sku_clean.upper()] = product_data
                                            builder.preloaded_products[sku_clean.lower()] = product_data
                                            builder._product_cache[sku_clean] = product_data
                                            
                                            auto_created_product_ids.append(product_id_uuid)
                                            db.session.commit()
                                            logger.info(f"✓ Auto-created product SKU '{sku}' with ID {product_id} and set flags")
                                        except Exception as e:
                                            logger.error(f"Error processing product SKU '{sku}': {str(e)}", exc_info=True)
                            elif '409' in str(create_message) or 'already exists' in str(create_message).lower():
                                # Product already exists - just refresh cache, don't set flags
                                logger.debug(f"Product SKU '{sku}' already exists in Cin7, cache is up to date")
                        except Exception as e:
                            logger.error(f"Error checking/creating product SKU '{sku}': {str(e)}", exc_info=True)
                    else:
                        logger.debug(f"Product SKU '{sku}' already in cache with flags set (is_new={cached_product.is_new}, created_via_auto_create={cached_product.created_via_auto_create})")
                else:
                    logger.debug(f"Product SKU '{sku}' found in builder cache but not in database cache - this shouldn't happen")
        
        # Final cache refresh from database to ensure everything is available
        logger.info("Refreshing cache from database after auto-creation...")
        db.session.commit()
        
        # Refresh ALL customers from database to ensure everything is in builder's cache
        # This ensures all customers needed for orders are available
        logger.info(f"Refreshing all needed customers from database cache...")
        # Load all cached customers for this client once
        all_cached_customers = CachedCustomer.query.filter_by(
            client_erp_credentials_id=credential_id_for_logging
        ).all()
        
        # Build a lookup map by customer name
        customer_cache_map = {}
        for cached_customer in all_cached_customers:
            if cached_customer.customer_data:
                import json
                cust_data = json.loads(cached_customer.customer_data) if isinstance(cached_customer.customer_data, str) else cached_customer.customer_data
                customer_name_from_data = cust_data.get('Name', '').strip()
                if customer_name_from_data:
                    # Ensure customer_data has 'ID' field set
                    if 'ID' not in cust_data or not cust_data.get('ID'):
                        cust_data['ID'] = str(cached_customer.cin7_customer_id)
                    customer_cache_map[customer_name_from_data] = cust_data
        
        # Refresh each needed customer from the map
        for customer_name in all_customers_needed:
            customer_name_clean = customer_name.strip()
            customer_data = customer_cache_map.get(customer_name_clean)
            
            if customer_data:
                builder.preloaded_customers[customer_name_clean] = customer_data
                builder.preloaded_customers[customer_name_clean.upper()] = customer_data
                builder.preloaded_customers[customer_name_clean.lower()] = customer_data
                cache_key = f"{customer_name_clean}|None"
                builder._customer_cache[cache_key] = customer_data
                logger.debug(f"Refreshed customer '{customer_name}' from database cache (ID: {customer_data.get('ID')})")
        
        # Refresh ALL products from database to ensure everything is in builder's cache
        # This ensures all products needed for orders are available
        # IMPORTANT: This refresh does NOT modify the flags - flags are preserved from auto-creation
        logger.info(f"Refreshing all needed products from database cache...")
        for sku in all_products_needed:
            # Find the product in database cache by SKU
            cached_product = CachedProduct.query.filter_by(
                client_erp_credentials_id=credential_id_for_logging,
                sku=sku
            ).first()
            
            if cached_product and cached_product.product_data:
                import json
                product_data = json.loads(cached_product.product_data) if isinstance(cached_product.product_data, str) else cached_product.product_data
                
                # Ensure product_data has 'ID' field set (use cin7_product_id from cache)
                if 'ID' not in product_data or not product_data.get('ID'):
                    product_data['ID'] = str(cached_product.cin7_product_id)
                
                # Log flag status for debugging
                if cached_product.is_new or cached_product.created_via_auto_create:
                    logger.debug(f"Refreshed product SKU '{sku}' from database cache (ID: {cached_product.cin7_product_id}) - flags: is_new={cached_product.is_new}, created_via_auto_create={cached_product.created_via_auto_create}")
                else:
                    logger.debug(f"Refreshed product SKU '{sku}' from database cache (ID: {cached_product.cin7_product_id}) - not flagged as new")
                
                sku_clean = sku.strip()
                builder.preloaded_products[sku_clean] = product_data
                builder.preloaded_products[sku_clean.upper()] = product_data
                builder.preloaded_products[sku_clean.lower()] = product_data
                builder._product_cache[sku_clean] = product_data
                
                # IMPORTANT: Do NOT modify cached_product here - flags are already set correctly from auto-creation
                # We're just loading product_data into builder's cache, not modifying the database record
        
        logger.info(f"PHASE 1 complete: Auto-created {len(auto_created_customer_ids)} customers and {len(auto_created_product_ids)} products")
        logger.info("PHASE 2: Starting order creation...")
    
    # PHASE 2: Process each order (all customers/products should now exist)
    successful_count = 0
    failed_count = 0
    total_orders = len(row_groups)
    orders_processed = 0
    
    for order_key, group_rows in row_groups.items():
        # Extract row data and row numbers
        row_data_list = [r['data'] for r in group_rows]
        row_numbers = [r['row_number'] for r in group_rows]
        
        # Process order
        # Reset order_id before processing each order (will be set in process_single_order)
        if hasattr(api_client, '_current_order_id_ref'):
            api_client._current_order_id_ref[0] = None
        
        result = process_single_order(
            upload_id=upload_id,
            order_key=order_key,
            order_rows=row_data_list,
            row_numbers=row_numbers,
            column_mapping=column_mapping,
            settings=settings,
            api_client=api_client,
            builder=builder,
            credential_id_for_logging=credential_id_for_logging,
        )
        
        # Clear order_id after processing
        if hasattr(api_client, '_current_order_id_ref'):
            api_client._current_order_id_ref[0] = None
        
        if result['status'] == 'success':
            successful_count += 1
        else:
            failed_count += 1
        
        orders_processed += 1
        
        # Emit progress event after each order to refresh sidebar counts in real-time
        upload = SalesOrderUpload.query.get(upload_id)
        if upload:
            # Update counts in real-time after each order
            upload.successful_orders = successful_count
            upload.failed_orders = failed_count
            db.session.commit()
            # Emit event to refresh sidebar and queue after each order
            emit_upload_event('upload_status_changed', str(upload_id), str(upload.client_id) if upload.client_id else None)
        
        # Rate limiting delay between orders
        delay = settings.get('default_delay_between_orders', 0.7)
        time.sleep(delay)
    
    # Update upload record
    upload = SalesOrderUpload.query.get(upload_id)
    if upload:
        upload.successful_orders = successful_count
        upload.failed_orders = failed_count
        upload.status = 'completed' if failed_count == 0 else 'failed'  # Failed if any orders failed
        upload.completed_at = datetime.utcnow()
        upload.total_rows = len(rows)
        db.session.commit()
        # Emit event for real-time updates
        emit_upload_event('upload_status_changed', str(upload_id), str(upload.client_id) if upload.client_id else None)
    
    return {
        'successful': successful_count,
        'failed': failed_count,
        'total_orders': len(row_groups)
    }


@webhooks_bp.route('/email', methods=['POST'])
def receive_email_webhook():
    """
    Receive email webhook from Missive or other email services.
    Extracts client name from subject, downloads CSV, and processes orders.
    """
    try:
        # Get payload
        if request.is_json:
            payload = request.get_json()
        else:
            payload = request.form.to_dict()
        
        # Log incoming webhook payload (for debugging)
        logger.info(f"Received webhook payload: {str(payload)[:500]}")  # Log first 500 chars to avoid huge logs
        
        if not payload:
            return jsonify({'error': 'No payload received'}), 400
        
        # Normalize payload
        normalized = normalize_webhook_payload(payload, request)
        
        if not normalized:
            # Log the actual payload structure to help debug
            logger.error(f"Failed to normalize webhook payload. Payload keys: {list(payload.keys()) if isinstance(payload, dict) else 'not a dict'}")
            logger.error(f"Full payload structure: {str(payload)[:1000]}")
            return jsonify({
                'error': 'Unsupported webhook format or missing required fields',
                'received_keys': list(payload.keys()) if isinstance(payload, dict) else 'not a dict',
                'hint': 'Expected Missive format with "subject" and "latest_message.attachments"'
            }), 400
        
        # Log normalized payload
        logger.info(f"Normalized webhook payload - subject: {normalized.get('subject', 'N/A')}, attachments: {len(normalized.get('attachments', []))}")
        
        # Extract subject and client name
        subject = normalized.get('subject', '')
        if not subject:
            return jsonify({'error': 'No subject in email'}), 400
        
        client_name = extract_client_name_from_subject(subject)
        if not client_name:
            return jsonify({'error': f'Could not extract client name from subject: {subject}'}), 400
        
        # Lookup client
        client_erp_credentials_id = lookup_client_by_name(client_name)
        if not client_erp_credentials_id:
            logger.error(f"Client not found: {client_name}")
            return jsonify({'error': f'Client not found: {client_name}'}), 404
        
        logger.info(f"Client found - name: {client_name}, credentials_id: {client_erp_credentials_id}")
        
        # Extract CSV
        csv_content, filename, error = extract_csv_from_payload(normalized)
        if error:
            return jsonify({'error': f'Failed to extract CSV: {error}'}), 400
        
        # Get client_id for upload record
        client_query = text("""
            SELECT client_id FROM voyager.client_erp_credentials
            WHERE id = :cred_id
        """)
        client_result = db.session.execute(client_query, {'cred_id': client_erp_credentials_id})
        client_row = client_result.fetchone()
        client_id_for_upload = client_row.client_id if client_row and client_row.client_id else None
        
        # Check for duplicate upload (same filename + credentials within last hour) - idempotency
        # Use client_erp_credentials_id since that uniquely identifies the connection
        # (client_id can be None for standalone connections, causing false duplicates)
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        logger.info(f"Checking for duplicate upload - filename: {filename}, client_id: {client_id_for_upload}, client_erp_credentials_id: {client_erp_credentials_id}")
        recent_duplicate = SalesOrderUpload.query.filter_by(
            filename=filename,
            client_erp_credentials_id=client_erp_credentials_id
        ).filter(
            SalesOrderUpload.created_at >= one_hour_ago
        ).order_by(SalesOrderUpload.created_at.desc()).first()
        
        # Store CSV content as base64 for preview
        import base64
        csv_base64 = base64.b64encode(csv_content).decode('utf-8')
        
        # Create upload record immediately (even if duplicate, so it appears in UI)
        upload_id = uuid.uuid4()
        logger.info(f"Creating upload record - upload_id: {upload_id}, filename: {filename}, client_erp_credentials_id: {client_erp_credentials_id}, client_id: {client_id_for_upload}")
        
        # Check if this is a duplicate
        is_duplicate = recent_duplicate is not None
        if is_duplicate:
            logger.info(f"Duplicate webhook detected - filename: {filename}, existing upload_id: {recent_duplicate.id}")
            upload = SalesOrderUpload(
                id=upload_id,
                user_id=None,  # Webhook has no user context
                client_id=client_id_for_upload,  # May be None for standalone connections
                client_erp_credentials_id=client_erp_credentials_id,  # Store credentials ID for retry
                filename=filename,
                total_rows=0,
                successful_orders=0,
                failed_orders=0,
                status='duplicate',  # Mark as duplicate so it appears in UI
                error_log=[{
                    'message': f'This file was already processed recently',
                    'duplicate_of_upload_id': str(recent_duplicate.id),
                    'duplicate_of_created_at': recent_duplicate.created_at.isoformat() if recent_duplicate.created_at else None,
                    'duplicate_of_status': recent_duplicate.status
                }],
                csv_content=csv_base64  # Store CSV for preview
            )
        else:
            logger.info(f"No duplicate found, proceeding with new upload creation")
            upload = SalesOrderUpload(
                id=upload_id,
                user_id=None,  # Webhook has no user context
                client_id=client_id_for_upload,  # May be None for standalone connections
                client_erp_credentials_id=client_erp_credentials_id,  # Store credentials ID for retry
                filename=filename,
                total_rows=0,  # Will be updated after parsing
                successful_orders=0,
                failed_orders=0,
                status='processing',
                csv_content=csv_base64  # Store CSV for preview
            )
        db.session.add(upload)
        try:
            db.session.commit()
            # Emit event when upload starts processing
            emit_upload_event('upload_status_changed', str(upload_id), str(client_id_for_upload) if client_id_for_upload else None)
            logger.info(f"Upload record created successfully - upload_id: {upload_id}, is_duplicate: {is_duplicate}")
        except Exception as commit_error:
            logger.error(f"Failed to commit upload record - upload_id: {upload_id}, error: {str(commit_error)}", exc_info=True)
            db.session.rollback()
            raise
        
        # If duplicate, return early without processing
        if is_duplicate:
            return jsonify({
                'message': 'This file was already processed recently',
                'upload_id': str(upload_id),
                'duplicate_of_upload_id': str(recent_duplicate.id),
                'status': 'duplicate',
                'created_at': upload.created_at.isoformat() if upload.created_at else None,
                'duplicate': True
            }), 200  # Return 200 to prevent Missive from retrying
        
        # Return 200 immediately to acknowledge webhook receipt
        # Process CSV in background thread
        def process_in_background():
            """Process CSV in background thread"""
            app = None
            try:
                logger.info(f"Starting background processing for upload {upload_id}")
                # Create new database session for background thread
                from app import create_app
                from database import db  # Import db once at function level
                app = create_app('production' if os.environ.get('FLASK_ENV') == 'production' else 'development')
                with app.app_context():
                    # Ensure upload status is set to processing at the start
                    try:
                        upload_check = SalesOrderUpload.query.get(upload_id)
                        if upload_check and upload_check.status != 'processing':
                            upload_check.status = 'processing'
                            db.session.commit()
                            logger.info(f"Set upload {upload_id} status to processing at thread start")
                    except Exception as init_error:
                        logger.warning(f"Could not verify upload status at thread start: {str(init_error)}")
                    try:
                        result = process_webhook_csv(
                            upload_id=upload_id,
                            client_erp_credentials_id=client_erp_credentials_id,
                            csv_content=csv_content,
                            filename=filename
                        )
                        
                        upload = SalesOrderUpload.query.get(upload_id)
                        if upload:
                            if 'error' in result:
                                logger.error(f"Processing error for upload {upload_id}: {result.get('error')}")
                                upload.status = 'failed'
                                upload.error_log = [result.get('error')]
                                upload.completed_at = datetime.utcnow()
                            else:
                                # Check if there are any failed orders
                                failed_count = result.get('failed', 0)
                                upload.status = 'completed' if failed_count == 0 else 'failed'
                                upload.completed_at = datetime.utcnow()
                            db.session.commit()
                            # Emit event for real-time updates
                            emit_upload_event('upload_status_changed', str(upload_id), str(upload.client_id) if upload.client_id else None)
                            logger.info(f"Background processing completed - upload_id: {upload_id}, client: {client_name}, orders: {result.get('total_orders', 0)}, successful: {result.get('successful', 0)}, failed: {result.get('failed', 0)}")
                        else:
                            logger.error(f"Upload {upload_id} not found in database during background processing")
                    except Exception as process_error:
                        logger.error(f"Error in process_webhook_csv for upload {upload_id}: {str(process_error)}", exc_info=True)
                        try:
                            upload = SalesOrderUpload.query.get(upload_id)
                            if upload:
                                upload.status = 'failed'
                                upload.error_log = [f'Processing error: {str(process_error)}']
                                upload.completed_at = datetime.utcnow()
                                db.session.commit()
                        except Exception as db_error:
                            logger.error(f"Error updating upload status after process error: {str(db_error)}", exc_info=True)
                            raise
                        raise
                    finally:
                        # Ensure session is closed and connections are returned to pool
                        db.session.close()
            except Exception as e:
                logger.error(f"Error in background processing thread for upload {upload_id}: {str(e)}", exc_info=True)
                # Try to update upload status, but don't create another app instance if we already have one
                if app:
                    try:
                        with app.app_context():
                            upload = SalesOrderUpload.query.get(upload_id)
                            if upload:
                                upload.status = 'failed'
                                error_msg = str(e)[:500]  # Limit error message length
                                upload.error_log = [f'Background processing thread error: {error_msg}']
                                upload.completed_at = datetime.utcnow()
                                db.session.commit()
                                logger.info(f"Updated upload {upload_id} status to failed due to thread error")
                            db.session.close()
                    except Exception as db_error:
                        logger.error(f"Error updating upload status: {str(db_error)}", exc_info=True)
            finally:
                # Dispose of the engine to close all connections from this app instance
                if app and hasattr(app, 'extensions') and 'sqlalchemy' in app.extensions:
                    try:
                        with app.app_context():
                            db.engine.dispose()
                        logger.debug(f"Disposed database engine for background thread {upload_id}")
                    except Exception as dispose_error:
                        logger.warning(f"Error disposing database engine: {str(dispose_error)}")
        
        # Start background processing
        logger.info(f"Starting background thread for upload {upload_id}")
        thread = threading.Thread(target=process_in_background, daemon=True)
        thread.start()
        logger.info(f"Background thread started for upload {upload_id}")
        
        logger.info(f"Webhook received and queued for processing - upload_id: {upload_id}, client: {client_name}, filename: {filename}")
        
        # Return 200 immediately
        return jsonify({
            'message': 'Webhook received and processing started',
            'upload_id': str(upload_id),
            'status': 'processing',
            'client_name': client_name,
            'filename': filename
        }), 200
    
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@webhooks_bp.route('/upload', methods=['POST'])
@jwt_required()
def manual_upload():
    """
    Manual file upload endpoint - processes CSV file directly (similar to webhook but without email parsing).
    Follows the same workflow as webhook emails but skips preliminary steps since we're uploading directly.
    """
    try:
        # Get user_id
        user_id = get_jwt_identity()
        try:
            if isinstance(user_id, str):
                user_id = uuid.UUID(user_id)
        except (ValueError, AttributeError):
            user_id = None
        
        # Get client_id from request
        client_id = request.form.get('client_id')
        if not client_id:
            return jsonify({'error': 'client_id is required'}), 400
        
        try:
            client_uuid = uuid.UUID(client_id)
        except (ValueError, AttributeError):
            return jsonify({'error': 'Invalid client_id format'}), 400
        
        # Get file
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Read file content
        csv_content = file.read()
        filename = file.filename
        
        # Get client_erp_credentials_id from client_id
        # The client_id can be either a client_id or credential_id (for standalone connections)
        query = text("""
            SELECT 
                cec.id as credential_id,
                cec.client_id
            FROM voyager.client_erp_credentials cec
            WHERE cec.erp = 'cin7_core'
            AND (cec.client_id = :client_id OR cec.id = :client_id)
            LIMIT 1
        """)
        result = db.session.execute(query, {'client_id': client_uuid})
        cred_row = result.fetchone()
        
        if not cred_row:
            return jsonify({'error': 'Client not found or does not have Cin7 credentials configured'}), 404
        
        client_erp_credentials_id = cred_row.credential_id
        client_id_for_upload = cred_row.client_id  # May be None for standalone connections
        
        # Check access: non-admins must have access via UserClient
        # UserClient.client_id references voyager.client_erp_credentials.id (credential_id)
        if user_id:
            # Check if user is global admin
            user = User.query.get(user_id)
            is_admin = False
            if user:
                is_admin = (user.role == 'admin' or user.email == 'dan@paleblue.nyc')
            
            if not is_admin:
                # Check if user has access to this credential
                has_access = UserClient.query.filter_by(
                    user_id=user_id, 
                    client_id=client_erp_credentials_id
                ).first() is not None
                
                if not has_access:
                    return jsonify({'error': 'Access denied. You do not have access to this client.'}), 403
        
        logger.info(f"Manual upload - filename: {filename}, client_erp_credentials_id: {client_erp_credentials_id}, client_id: {client_id_for_upload}")
        
        # Check for duplicate upload (same filename + credentials within last hour) - idempotency
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent_duplicate = SalesOrderUpload.query.filter_by(
            filename=filename,
            client_erp_credentials_id=client_erp_credentials_id
        ).filter(
            SalesOrderUpload.created_at >= one_hour_ago
        ).order_by(SalesOrderUpload.created_at.desc()).first()
        
        # Store CSV content as base64 for preview
        import base64
        csv_base64 = base64.b64encode(csv_content).decode('utf-8')
        
        # Create upload record immediately (even if duplicate, so it appears in UI)
        upload_id = uuid.uuid4()
        
        # Check if this is a duplicate
        is_duplicate = recent_duplicate is not None
        if is_duplicate:
            logger.info(f"Duplicate upload detected - filename: {filename}, existing upload_id: {recent_duplicate.id}")
            upload = SalesOrderUpload(
                id=upload_id,
                user_id=user_id,  # Manual upload has user context
                client_id=client_id_for_upload,  # May be None for standalone connections
                client_erp_credentials_id=client_erp_credentials_id,
                filename=filename,
                total_rows=0,
                successful_orders=0,
                failed_orders=0,
                status='duplicate',
                error_log=[{
                    'message': f'This file was already processed recently',
                    'duplicate_of_upload_id': str(recent_duplicate.id),
                    'duplicate_of_created_at': recent_duplicate.created_at.isoformat() if recent_duplicate.created_at else None,
                    'duplicate_of_status': recent_duplicate.status
                }],
                csv_content=csv_base64
            )
        else:
            logger.info(f"No duplicate found, proceeding with new upload creation")
            upload = SalesOrderUpload(
                id=upload_id,
                user_id=user_id,  # Manual upload has user context
                client_id=client_id_for_upload,  # May be None for standalone connections
                client_erp_credentials_id=client_erp_credentials_id,
                filename=filename,
                total_rows=0,  # Will be updated after parsing
                successful_orders=0,
                failed_orders=0,
                status='processing',
                csv_content=csv_base64
            )
        
        db.session.add(upload)
        try:
            db.session.commit()
            # Emit event when upload starts processing
            emit_upload_event('upload_status_changed', str(upload_id), str(client_id_for_upload) if client_id_for_upload else None)
            logger.info(f"Upload record created successfully - upload_id: {upload_id}, is_duplicate: {is_duplicate}")
        except Exception as commit_error:
            logger.error(f"Failed to commit upload record - upload_id: {upload_id}, error: {str(commit_error)}", exc_info=True)
            db.session.rollback()
            raise
        
        # If duplicate, return early without processing
        if is_duplicate:
            return jsonify({
                'message': 'This file was already processed recently',
                'upload_id': str(upload_id),
                'duplicate_of_upload_id': str(recent_duplicate.id),
                'status': 'duplicate',
                'created_at': upload.created_at.isoformat() if upload.created_at else None,
                'duplicate': True
            }), 200
        
        # Return 200 immediately to acknowledge upload receipt
        # Process CSV in background thread (same as webhook)
        # Capture user_id for use in background thread
        captured_user_id = user_id
        def process_in_background():
            """Process CSV in background thread"""
            app = None
            try:
                logger.info(f"Starting background processing for manual upload {upload_id}")
                # Create new database session for background thread
                from app import create_app
                from database import db  # Import db once at function level
                app = create_app('production' if os.environ.get('FLASK_ENV') == 'production' else 'development')
                with app.app_context():
                    try:
                        result = process_webhook_csv(
                            upload_id=upload_id,
                            client_erp_credentials_id=client_erp_credentials_id,
                            csv_content=csv_content,
                            filename=filename,
                            trigger='upload',  # Manual upload uses 'upload' trigger
                            user_id=captured_user_id  # Pass the user_id for manual uploads
                        )
                        
                        upload = SalesOrderUpload.query.get(upload_id)
                        if upload:
                            if 'error' in result:
                                logger.error(f"Processing error for upload {upload_id}: {result.get('error')}")
                                upload.status = 'failed'
                                upload.error_log = [result.get('error')]
                                upload.completed_at = datetime.utcnow()
                            else:
                                # Check if there are any failed orders
                                failed_count = result.get('failed', 0)
                                upload.status = 'completed' if failed_count == 0 else 'failed'
                                upload.completed_at = datetime.utcnow()
                            db.session.commit()
                            # Emit event for real-time updates
                            emit_upload_event('upload_status_changed', str(upload_id), str(upload.client_id) if upload.client_id else None)
                            logger.info(f"Background processing completed - upload_id: {upload_id}, orders: {result.get('total_orders', 0)}, successful: {result.get('successful', 0)}, failed: {result.get('failed', 0)}")
                        else:
                            logger.error(f"Upload {upload_id} not found in database during background processing")
                    except Exception as process_error:
                        logger.error(f"Error in process_webhook_csv for upload {upload_id}: {str(process_error)}", exc_info=True)
                        try:
                            upload = SalesOrderUpload.query.get(upload_id)
                            if upload:
                                upload.status = 'failed'
                                upload.error_log = [f'Processing error: {str(process_error)}']
                                upload.completed_at = datetime.utcnow()
                                db.session.commit()
                        except Exception as db_error:
                            logger.error(f"Error updating upload status after process error: {str(db_error)}", exc_info=True)
                            raise
                        raise
                    finally:
                        # Ensure session is closed and connections are returned to pool
                        db.session.close()
            except Exception as e:
                logger.error(f"Error in background processing thread for upload {upload_id}: {str(e)}", exc_info=True)
                # Try to update upload status, but don't create another app instance if we already have one
                if app:
                    try:
                        with app.app_context():
                            upload = SalesOrderUpload.query.get(upload_id)
                            if upload:
                                upload.status = 'failed'
                                error_msg = str(e)[:500]  # Limit error message length
                                upload.error_log = [f'Background processing thread error: {error_msg}']
                                upload.completed_at = datetime.utcnow()
                                db.session.commit()
                                logger.info(f"Updated upload {upload_id} status to failed due to thread error")
                            db.session.close()
                    except Exception as db_error:
                        logger.error(f"Error updating upload status: {str(db_error)}", exc_info=True)
            finally:
                # Dispose of the engine to close all connections from this app instance
                if app and hasattr(app, 'extensions') and 'sqlalchemy' in app.extensions:
                    try:
                        with app.app_context():
                            db.engine.dispose()
                        logger.debug(f"Disposed database engine for background thread {upload_id}")
                    except Exception as dispose_error:
                        logger.warning(f"Error disposing database engine: {str(dispose_error)}")
        
        # Start background processing
        logger.info(f"Starting background thread for manual upload {upload_id}")
        thread = threading.Thread(target=process_in_background, daemon=True)
        thread.start()
        logger.info(f"Background thread started for manual upload {upload_id}")
        
        logger.info(f"Manual upload received and queued for processing - upload_id: {upload_id}, filename: {filename}")
        
        # Return 200 immediately
        return jsonify({
            'message': 'File uploaded and processing started',
            'upload_id': str(upload_id),
            'status': 'processing',
            'filename': filename
        }), 200
    
    except Exception as e:
        logger.error(f"Error processing manual upload: {str(e)}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


def _retry_order_internal(order_result: SalesOrderResult) -> Tuple[Dict, Optional[str]]:
    """
    Internal helper function to retry processing a failed order.
    Returns (result_dict, error_message)
    """
    try:
        if order_result.status == 'success':
            return None, 'Order already succeeded'
        
        # Get the upload to access CSV content
        upload = SalesOrderUpload.query.get(order_result.upload_id)
        if not upload:
            return None, 'Upload not found'
        
        # Get client credentials - use stored client_erp_credentials_id if available, otherwise try to look it up
        if upload.client_erp_credentials_id:
            client_erp_credentials_id = upload.client_erp_credentials_id
        else:
            # Fallback: try to find credentials by client_id (for older uploads)
            if upload.client_id:
                client_query = text("""
                    SELECT cec.id, cec.client_id
                    FROM voyager.client_erp_credentials cec
                    WHERE cec.client_id = :client_id
                    LIMIT 1
                """)
                result = db.session.execute(client_query, {'client_id': upload.client_id})
                cred_row = result.fetchone()
                
                if not cred_row:
                    return None, 'Client credentials not found'
                
                client_erp_credentials_id = cred_row.id
            else:
                return None, 'Client credentials not found'
        
        # Decode CSV content
        import base64
        csv_content = base64.b64decode(upload.csv_content) if upload.csv_content else None
        if not csv_content:
            return None, 'CSV content not available'
        
        # Parse CSV to get the specific rows for this order
        parser = CSVParser()
        rows, errors, skipped = parser.parse_file(csv_content, upload.filename)
        
        if errors:
            return None, f'Failed to parse CSV: {errors[0]}'
        
        # Filter rows by row_numbers from order_result
        order_rows = [r for r in rows if r['row_number'] in (order_result.row_numbers or [])]
        if not order_rows:
            return None, 'Order rows not found in CSV'
        
        # Get column mapping
        default_mapping_obj = ClientCsvMapping.query.filter_by(
            client_erp_credentials_id=client_erp_credentials_id,
            is_default=True
        ).first()
        
        if not default_mapping_obj:
            return None, 'Column mapping not found'
        
        column_mapping = default_mapping_obj.column_mapping or {}
        
        # Get settings and credentials
        check_customer_cols_query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'voyager' 
            AND table_name = 'client_erp_credentials' 
            AND column_name IN ('customer_account_receivable', 'customer_revenue_account', 'customer_tax_rule', 'customer_attribute_set')
        """)
        existing_customer_cols = {row[0] for row in db.session.execute(check_customer_cols_query).fetchall()}
        
        select_fields = [
            'cec.id',
            'cec.cin7_api_auth_accountid as account_id',
            'cec.cin7_api_auth_applicationkey as application_key',
            'cec.client_id',
            'cec.sale_type',
            'cec.tax_rule',
            'cec.default_status'
        ]
        
        if 'customer_account_receivable' in existing_customer_cols:
            select_fields.append('cec.customer_account_receivable')
        if 'customer_revenue_account' in existing_customer_cols:
            select_fields.append('cec.customer_revenue_account')
        if 'customer_tax_rule' in existing_customer_cols:
            select_fields.append('cec.customer_tax_rule')
        if 'customer_attribute_set' in existing_customer_cols:
            select_fields.append('cec.customer_attribute_set')
        
        cred_query = text(f"""
            SELECT {', '.join(select_fields)}
            FROM voyager.client_erp_credentials cec
            WHERE cec.id = :cred_id
        """)
        cred_result = db.session.execute(cred_query, {'cred_id': client_erp_credentials_id})
        cred_row = cred_result.fetchone()
        
        if not cred_row:
            return None, 'Credentials not found'
        
        # Extract values from cred_row
        account_id = cred_row.account_id
        application_key = cred_row.application_key
        sale_type = getattr(cred_row, 'sale_type', None)
        tax_rule = getattr(cred_row, 'tax_rule', None)
        default_status = getattr(cred_row, 'default_status', None)
        
        # Extract customer default fields
        customer_account_receivable = None
        customer_revenue_account = None
        customer_tax_rule = None
        customer_attribute_set = None
        
        if 'customer_account_receivable' in existing_customer_cols and hasattr(cred_row, 'customer_account_receivable'):
            customer_account_receivable = cred_row.customer_account_receivable if cred_row.customer_account_receivable else None
        if 'customer_revenue_account' in existing_customer_cols and hasattr(cred_row, 'customer_revenue_account'):
            customer_revenue_account = cred_row.customer_revenue_account if cred_row.customer_revenue_account else None
        if 'customer_tax_rule' in existing_customer_cols and hasattr(cred_row, 'customer_tax_rule'):
            customer_tax_rule = str(cred_row.customer_tax_rule) if cred_row.customer_tax_rule else None
        if 'customer_attribute_set' in existing_customer_cols and hasattr(cred_row, 'customer_attribute_set'):
            customer_attribute_set = cred_row.customer_attribute_set
        
        # Get settings
        settings_obj = None
        if cred_row.client_id:
            settings_obj = ClientSettings.query.filter_by(client_id=cred_row.client_id).first()
        
        settings = {}
        if settings_obj:
            settings = {
                'default_status': default_status or settings_obj.default_status,
                'default_currency': settings_obj.default_currency,
                'tax_inclusive': settings_obj.tax_inclusive,
                'default_location': settings_obj.default_location,
                'default_delay_between_orders': settings_obj.default_delay_between_orders,
                'sale_type': sale_type,
                'tax_rule': tax_rule,
                'customer_account_receivable': customer_account_receivable,
                'customer_revenue_account': customer_revenue_account,
                'customer_tax_rule': customer_tax_rule,
                'customer_attribute_set': customer_attribute_set
            }
        else:
            settings = {
                'default_status': default_status or 'DRAFT',
                'default_currency': 'USD',
                'tax_inclusive': False,
                'default_location': None,
                'default_delay_between_orders': 0.7,
                'sale_type': sale_type,
                'tax_rule': tax_rule,
                'customer_account_receivable': customer_account_receivable,
                'customer_revenue_account': customer_revenue_account,
                'customer_tax_rule': customer_tax_rule,
                'customer_attribute_set': customer_attribute_set
            }
        
        # Initialize API client and builder
        api_client = Cin7SalesAPI(
            account_id=str(cred_row.account_id),
            application_key=str(cred_row.application_key),
            base_url='https://inventory.dearsystems.com/ExternalApi/v2/',
            logger_callback=lambda **kwargs: None  # Disable logging for retry
        )
        
        # Preload customers and products from database cache for better performance
        validator_for_preload = SalesOrderValidator(api_client)
        try:
            customer_count, product_count = validator_for_preload.preload_customers_and_products(
                db_session=db.session,
                client_erp_credentials_id=client_erp_credentials_id
            )
            logger.info(f"Preloaded {customer_count} customers and {product_count} products for retry")
        except Exception as e:
            logger.warning(f"Warning: Failed to preload customers/products: {str(e)}")
        
        # Initialize builder with preloaded data
        builder = SalesOrderBuilder(
            settings, 
            api_client,
            preloaded_customers=getattr(validator_for_preload, 'customer_lookup', {}),
            preloaded_products=getattr(validator_for_preload, 'product_lookup', {})
        )
        
        # Extract row data
        row_data_list = [r['data'] for r in order_rows]
        row_numbers = [r['row_number'] for r in order_rows]
        
        # Update retry tracking before processing
        order_result.retry_count = (order_result.retry_count or 0) + 1
        order_result.last_retry_at = datetime.utcnow()
        db.session.commit()
        
        # Process the order (pass existing order_result so it gets updated in place)
        result = process_single_order(
            upload_id=order_result.upload_id,
            order_key=order_result.order_key,
            order_rows=row_data_list,
            row_numbers=row_numbers,
            column_mapping=column_mapping,
            settings=settings,
            api_client=api_client,
            builder=builder,
            credential_id_for_logging=client_erp_credentials_id,
            existing_order_result=order_result  # Pass existing record so it gets updated
        )
        
        # Clear manual resolution if it was resolved (since it's now actually successful)
        if result['status'] == 'success' and order_result.resolved_at:
            order_result.resolved_at = None
            order_result.resolved_by = None
            db.session.commit()
        
        return {
            'status': result['status'],
            'sale_id': result.get('sale_id'),
            'sale_order_id': result.get('sale_order_id'),
            'error_message': result.get('error_message')
        }, None
    
    except Exception as e:
        logger.error(f"Error retrying order {order_result.id}: {str(e)}", exc_info=True)
        return None, f'Internal server error: {str(e)}'


@webhooks_bp.route('/orders/<order_result_id>/api-logs', methods=['GET'])
@jwt_required()
def get_order_api_logs(order_result_id):
    """Get all API logs associated with a specific order result"""
    try:
        # Get user ID from JWT token
        user_identity = get_jwt_identity()
        if not user_identity:
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Get the order result
        try:
            order_result_uuid = uuid.UUID(order_result_id)
        except (ValueError, AttributeError):
            return jsonify({'error': 'Invalid order result ID format'}), 400
        
        order_result = SalesOrderResult.query.get(order_result_uuid)
        if not order_result:
            return jsonify({'error': 'Order result not found'}), 404
        
        # Get the upload to find API logs
        upload = SalesOrderUpload.query.get(order_result.upload_id)
        if not upload:
            return jsonify({'error': 'Upload not found'}), 404
        
        # Get API logs for this upload
        # Include both:
        # 1. Logs for this specific order (order_id = order_result_uuid)
        # 2. Phase 1 logs (order_id = None) for product/customer creation that happen before orders
        #    BUT only the ones related to this specific order (using mapping tables)
        logger.info(f"Fetching API logs for order {order_result_id}, upload_id: {order_result.upload_id}")
        
        # Use mapping tables to find which customers/products are related to this order
        related_customer_ids = set()
        related_product_ids = set()
        
        # Get customer IDs from mapping table
        customer_mappings = CustomerUploadMapping.query.filter_by(
            upload_id=order_result.upload_id
        ).all()
        for mapping in customer_mappings:
            if mapping.order_ids and str(order_result_uuid) in [str(oid) for oid in mapping.order_ids]:
                related_customer_ids.add(str(mapping.cin7_customer_id))
        
        # Get product IDs from mapping table
        product_mappings = ProductUploadMapping.query.filter_by(
            upload_id=order_result.upload_id
        ).all()
        for mapping in product_mappings:
            if mapping.order_ids and str(order_result_uuid) in [str(oid) for oid in mapping.order_ids]:
                related_product_ids.add(str(mapping.cin7_product_id))
        
        # Extract customer name and product SKUs from order_data for matching POST request bodies
        order_customer_name = None
        order_product_skus = set()
        
        # Fallback: If mapping tables don't have order_ids yet, extract from order_data
        if not related_customer_ids or not related_product_ids:
            if order_result.order_data:
                order_data = order_result.order_data
                # Try to get customer ID from sale_payload or order_data
                sale_payload = order_data.get('sale_payload') or {}
                if isinstance(sale_payload, dict) and sale_payload.get('Customer'):
                    related_customer_ids.add(str(sale_payload.get('Customer')))
                elif isinstance(order_data, dict) and order_data.get('Customer'):
                    related_customer_ids.add(str(order_data.get('Customer')))
                
                # Try to get product IDs from sale_order_payload
                sale_order_payload = order_data.get('sale_order_payload') or {}
                if isinstance(sale_order_payload, dict):
                    lines = sale_order_payload.get('Lines', [])
                    for line in lines:
                        if isinstance(line, dict) and 'ProductID' in line:
                            related_product_ids.add(str(line['ProductID']))
        
        # Extract customer name and product SKUs from matching_details for request body matching
        if order_result.order_data:
            order_data = order_result.order_data
            matching_details = order_data.get('matching_details') or {}
            
            # Get customer name
            customer_info = matching_details.get('customer') or {}
            if isinstance(customer_info, dict):
                order_customer_name = customer_info.get('name') or customer_info.get('customer_name')
            if not order_customer_name and isinstance(order_data, dict):
                order_customer_name = order_data.get('customer_name') or order_data.get('customername')
            
            # Get product SKUs
            products = matching_details.get('products') or []
            if isinstance(products, list):
                for product in products:
                    if isinstance(product, dict):
                        sku = product.get('sku')
                        if sku:
                            order_product_skus.add(str(sku))
        
        logger.info(f"Order uses customer_ids: {list(related_customer_ids)}, product_ids: {list(related_product_ids)}")
        logger.info(f"Order uses customer_name: {order_customer_name}, product_skus: {list(order_product_skus)}")
        
        from sqlalchemy import or_
        # Get all logs for this upload
        all_logs_query = Cin7ApiLog.query.filter(
            Cin7ApiLog.upload_id == order_result.upload_id
        ).filter(
            or_(
                Cin7ApiLog.order_id == order_result_uuid,  # Logs for this specific order
                Cin7ApiLog.order_id.is_(None)  # Phase 1 logs (product/customer creation)
            )
        )
        
        # Order by creation time (oldest first to see the sequence)
        all_logs_query = all_logs_query.order_by(Cin7ApiLog.created_at.asc())
        all_logs = all_logs_query.all()
        
        # Filter Phase 1 logs to only include those related to this order
        filtered_logs = []
        for log in all_logs:
            # Always include logs for this specific order (except /ref/tax which is not relevant)
            if log.order_id == order_result_uuid:
                # Filter out /ref/tax calls - they're not relevant to order creation
                if log.endpoint != '/ref/tax':
                    filtered_logs.append(log)
            # For Phase 1 logs (order_id=None), filter by customer/product using mapping tables
            elif log.order_id is None:
                # Filter out /ref/tax calls - they're not relevant to order creation
                if log.endpoint == '/ref/tax':
                    continue
                
                # Check if this is a POST customer/product call related to this order
                is_related = False
                
                if log.method == 'POST' and log.endpoint == '/customer':
                    # First try to match by customer ID in response
                    if related_customer_ids and log.response_body:
                        try:
                            import json
                            response = log.response_body
                            if isinstance(response, str):
                                response = json.loads(response)
                            
                            # Extract customer ID from response
                            customer_id_in_response = None
                            if isinstance(response, dict):
                                if 'ID' in response:
                                    customer_id_in_response = str(response['ID'])
                                elif 'CustomerList' in response and isinstance(response['CustomerList'], list) and len(response['CustomerList']) > 0:
                                    customer_id_in_response = str(response['CustomerList'][0].get('ID', ''))
                            
                            if customer_id_in_response and customer_id_in_response.lower() in [cid.lower() for cid in related_customer_ids]:
                                is_related = True
                        except Exception as e:
                            logger.debug(f"Error checking customer ID in response: {str(e)}")
                    
                    # Fallback: Match by customer name in request body
                    if not is_related and order_customer_name and log.request_body:
                        try:
                            import json
                            request = log.request_body
                            if isinstance(request, str):
                                request = json.loads(request)
                            
                            # Check if request body contains the customer name
                            if isinstance(request, dict):
                                request_name = request.get('Name') or request.get('name')
                                if request_name and str(request_name).strip().lower() == str(order_customer_name).strip().lower():
                                    is_related = True
                        except Exception as e:
                            logger.debug(f"Error checking customer name in request: {str(e)}")
                
                elif log.method == 'POST' and log.endpoint == '/product':
                    # First try to match by product ID in response
                    if related_product_ids and log.response_body:
                        try:
                            import json
                            response = log.response_body
                            if isinstance(response, str):
                                response = json.loads(response)
                            
                            # Extract product ID from response
                            product_id_in_response = None
                            if isinstance(response, dict):
                                if 'ID' in response:
                                    product_id_in_response = str(response['ID'])
                                elif 'ProductList' in response and isinstance(response['ProductList'], list) and len(response['ProductList']) > 0:
                                    product_id_in_response = str(response['ProductList'][0].get('ID', ''))
                            
                            if product_id_in_response and product_id_in_response.lower() in [pid.lower() for pid in related_product_ids]:
                                is_related = True
                        except Exception as e:
                            logger.debug(f"Error checking product ID in response: {str(e)}")
                    
                    # Fallback: Match by SKU in request body
                    if not is_related and order_product_skus and log.request_body:
                        try:
                            import json
                            request = log.request_body
                            if isinstance(request, str):
                                request = json.loads(request)
                            
                            # Check if request body contains any of the product SKUs
                            if isinstance(request, dict):
                                request_sku = request.get('SKU') or request.get('sku')
                                if request_sku and str(request_sku).strip().lower() in [sku.lower() for sku in order_product_skus]:
                                    is_related = True
                        except Exception as e:
                            logger.debug(f"Error checking product SKU in request: {str(e)}")
                
                # Include other Phase 1 logs (GET requests, etc.) but filter out unrelated POST customer/product calls
                if log.method != 'POST' or (log.endpoint not in ['/customer', '/product']):
                    is_related = True  # Include non-POST or non-customer/product POST calls
                
                if is_related:
                    filtered_logs.append(log)
        
        logs = filtered_logs
        logger.info(f"Found {len(logs)} API logs for upload_id {order_result.upload_id} (filtered to show only logs related to this order, excluding /ref/tax)")
        
        # Format response
        logs_data = []
        for log in logs:
            # Use response_body (raw_response_body_text column doesn't exist in current schema)
            response_body = log.response_body
            
            # Parse request_body if it's a string
            request_body = log.request_body
            if isinstance(request_body, str):
                try:
                    import json
                    request_body = json.loads(request_body)
                except (json.JSONDecodeError, TypeError):
                    # Keep as string if not valid JSON
                    pass
            
            logs_data.append({
                'id': str(log.id),
                'endpoint': log.endpoint,
                'method': log.method,
                'request_url': log.request_url,
                'request_headers': log.request_headers,
                'request_body': request_body,
                'response_status': log.response_status,
                'response_body': response_body,
                'error_message': log.error_message,
                'duration_ms': log.duration_ms,
                'trigger': log.trigger,
                'created_at': log.created_at.isoformat() if log.created_at else None
            })
        
        logger.info(f"Returning {len(logs_data)} API logs for order {order_result_id}")
        return jsonify({
            'logs': logs_data,
            'total': len(logs_data),
            'upload_id': str(order_result.upload_id),
            'order_id': str(order_result.id)
        }), 200
    
    except Exception as e:
        logger.error(f"Error fetching API logs for order {order_result_id}: {str(e)}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@webhooks_bp.route('/retry/<order_result_id>', methods=['POST'])
@jwt_required()
def retry_order(order_result_id):
    """
    Retry processing a failed order.
    """
    try:
        order_result = SalesOrderResult.query.get(uuid.UUID(order_result_id))
        if not order_result:
            return jsonify({'error': 'Order result not found'}), 404
        
        result, error = _retry_order_internal(order_result)
        if error:
            return jsonify({'error': error}), 400 if error in ['Order already succeeded', 'Upload not found', 'Client credentials not found', 'CSV content not available', 'Order rows not found in CSV', 'Column mapping not found', 'Credentials not found'] else 500
        
        return jsonify(result), 200
    
    except ValueError:
        return jsonify({'error': 'Invalid order ID format'}), 400
    except Exception as e:
        logger.error(f"Error retrying order: {str(e)}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@webhooks_bp.route('/orders/failed', methods=['GET'])
@jwt_required()
def get_failed_orders():
    """
    Get all failed orders across all uploads (unresolved only by default).
    Returns list of failed orders with upload context.
    """
    try:
        # Get query parameters
        client_id = request.args.get('client_id')
        error_type = request.args.get('error_type')
        include_resolved = request.args.get('include_resolved', 'false').lower() == 'true'
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        
        # Build query - include both failed orders and partial_success orders (orders with missing products)
        from sqlalchemy import or_
        query = SalesOrderResult.query.filter(
            or_(
                SalesOrderResult.status == 'failed',
                SalesOrderResult.error_type == 'partial_success'
            )
        )
        
        # Filter by resolved status
        if not include_resolved:
            query = query.filter(SalesOrderResult.resolved_at.is_(None))
        
        # Filter by error type
        if error_type:
            query = query.filter_by(error_type=error_type)
        
        # Filter by client_erp_credentials_id if provided
        if client_id:
            try:
                client_uuid = uuid.UUID(client_id)
                query = query.join(SalesOrderUpload).filter(SalesOrderUpload.client_erp_credentials_id == client_uuid)
            except ValueError:
                return jsonify({'error': 'Invalid client_id format'}), 400
        
        # Get total count
        total = query.count()
        
        # Order by created_at descending (most recent first)
        query = query.order_by(SalesOrderResult.created_at.desc())
        
        # Apply pagination
        failed_orders = query.limit(limit).offset(offset).all()
        
        # Build response
        result = []
        for order_result in failed_orders:
            upload = SalesOrderUpload.query.get(order_result.upload_id)
            client_name = None
            if upload and upload.client_id:
                try:
                    client = Client.query.get(upload.client_id)
                    if client:
                        client_name = client.name
                except Exception:
                    pass
            
            # Extract order details from order_data
            order_data = order_result.order_data or {}
            customer_name = order_data.get('customer_name') or order_data.get('customername', '')
            po_number = order_data.get('po_number') or order_data.get('customerreference', '')
            
            result.append({
                'id': str(order_result.id),
                'order_key': order_result.order_key,
                'customer_name': customer_name,
                'po_number': po_number,
                'error_type': order_result.error_type,
                'error_message': order_result.error_message,
                'sale_id': str(order_result.sale_id) if order_result.sale_id else None,
                'sale_order_id': str(order_result.sale_order_id) if order_result.sale_order_id else None,
                'retry_count': order_result.retry_count or 0,
                'last_retry_at': order_result.last_retry_at.isoformat() if order_result.last_retry_at else None,
                'resolved_at': order_result.resolved_at.isoformat() if order_result.resolved_at else None,
                'resolved_by': str(order_result.resolved_by) if order_result.resolved_by else None,
                'review_notes': order_result.review_notes,
                'upload': {
                    'id': str(upload.id) if upload else None,
                    'filename': upload.filename if upload else None,
                    'created_at': upload.created_at.isoformat() if upload and upload.created_at else None,
                    'client_name': client_name
                } if upload else None,
                'order_data': order_data,
                'matching_details': order_data.get('matching_details'),
                'sale_payload': order_data.get('sale_payload'),
                'sale_order_payload': order_data.get('sale_order_payload'),
                'what_is_needed': order_data.get('what_is_needed'),
                'created_at': order_result.created_at.isoformat() if order_result.created_at else None,
                'processed_at': order_result.processed_at.isoformat() if order_result.processed_at else None
            })
        
        return jsonify({
            'failed_orders': result,
            'total': total,
            'limit': limit,
            'offset': offset
        }), 200
    
    except Exception as e:
        logger.error(f"Error getting failed orders: {str(e)}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@webhooks_bp.route('/orders/bulk-retry', methods=['POST'])
@jwt_required()
def bulk_retry_orders():
    """
    Bulk retry multiple failed orders.
    """
    try:
        data = request.get_json()
        order_ids = data.get('order_ids', [])
        
        if not order_ids:
            return jsonify({'error': 'No order IDs provided'}), 400
        
        if not isinstance(order_ids, list):
            return jsonify({'error': 'order_ids must be a list'}), 400
        
        results = []
        for order_id_str in order_ids:
            try:
                order_id = uuid.UUID(order_id_str)
                order_result = SalesOrderResult.query.get(order_id)
                
                if not order_result:
                    results.append({
                        'order_id': order_id_str,
                        'status': 'error',
                        'error': 'Order not found'
                    })
                    continue
                
                if order_result.status == 'success':
                    results.append({
                        'order_id': order_id_str,
                        'status': 'skipped',
                        'error': 'Order already succeeded'
                    })
                    continue
                
                # Use internal retry function
                retry_result, retry_error = _retry_order_internal(order_result)
                
                if retry_error:
                    results.append({
                        'order_id': order_id_str,
                        'status': 'error',
                        'error': retry_error
                    })
                else:
                    results.append({
                        'order_id': order_id_str,
                        'status': retry_result.get('status'),
                        'sale_id': retry_result.get('sale_id'),
                        'sale_order_id': retry_result.get('sale_order_id'),
                        'error_message': retry_result.get('error_message')
                    })
            
            except ValueError:
                results.append({
                    'order_id': order_id_str,
                    'status': 'error',
                    'error': 'Invalid order ID format'
                })
            except Exception as e:
                logger.error(f"Error retrying order {order_id_str}: {str(e)}", exc_info=True)
                results.append({
                    'order_id': order_id_str,
                    'status': 'error',
                    'error': str(e)
                })
        
        return jsonify({
            'results': results,
            'total': len(results),
            'successful': len([r for r in results if r.get('status') == 'success']),
            'failed': len([r for r in results if r.get('status') in ['error', 'failed']])
        }), 200
    
    except Exception as e:
        logger.error(f"Error in bulk retry: {str(e)}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@webhooks_bp.route('/orders/<order_id>/resolve', methods=['POST'])
@jwt_required()
def resolve_order(order_id):
    """
    Manually mark a failed order as resolved (reviewed) or unresolved (unreviewed).
    """
    try:
        order_result = SalesOrderResult.query.get(uuid.UUID(order_id))
        if not order_result:
            return jsonify({'error': 'Order not found'}), 404
        
        # Allow resolving partial_success orders even though they have status='success'
        # They appear in the failed orders tab and should be resolvable
        if order_result.status == 'success' and order_result.error_type != 'partial_success':
            return jsonify({'error': 'Order already succeeded'}), 400
        
        data = request.get_json() or {}
        review_notes = data.get('review_notes', '').strip() if data.get('review_notes') else None
        unresolve = data.get('unresolve', False)
        
        # Require review_notes when marking as resolved (reviewed)
        if not unresolve and not review_notes:
            return jsonify({'error': 'Review notes are required when marking an order as reviewed'}), 400
        
        # Get current user
        current_user_id = get_jwt_identity()
        user_id = uuid.UUID(current_user_id) if current_user_id else None
        
        if unresolve:
            # Mark as unresolved (unreviewed)
            order_result.resolved_at = None
            order_result.resolved_by = None
            order_result.review_notes = None  # Clear review notes
            if order_result.order_data and 'resolution_reason' in order_result.order_data:
                del order_result.order_data['resolution_reason']
        else:
            # Mark as resolved (reviewed)
            order_result.resolved_at = datetime.utcnow()
            order_result.resolved_by = user_id
            order_result.review_notes = review_notes  # Store review notes
            
            # Also store in order_data for backward compatibility
            if review_notes:
                if not order_result.order_data:
                    order_result.order_data = {}
                order_result.order_data['resolution_reason'] = review_notes
        
        db.session.commit()
        
        return jsonify({
            'status': 'unresolved' if unresolve else 'resolved',
            'resolved_at': order_result.resolved_at.isoformat() if order_result.resolved_at else None,
            'resolved_by': str(order_result.resolved_by) if order_result.resolved_by else None,
            'review_notes': order_result.review_notes
        }), 200
    
    except ValueError:
        return jsonify({'error': 'Invalid order ID format'}), 400
    except Exception as e:
        logger.error(f"Error resolving order: {str(e)}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@webhooks_bp.route('/orders/<order_id>/notes', methods=['POST'])
@jwt_required()
def add_order_notes(order_id):
    """
    Add notes to an order without marking it as resolved.
    This allows adding notes to orders that are still being reviewed.
    """
    try:
        order_result = SalesOrderResult.query.get(uuid.UUID(order_id))
        if not order_result:
            return jsonify({'error': 'Order not found'}), 404
        
        data = request.get_json() or {}
        review_notes = data.get('review_notes', '').strip() if data.get('review_notes') else ''
        
        if not review_notes:
            return jsonify({'error': 'Notes are required'}), 400
        
        # Add notes without resolving
        order_result.review_notes = review_notes
        
        # Also store in order_data for backward compatibility
        if not order_result.order_data:
            order_result.order_data = {}
        order_result.order_data['resolution_reason'] = review_notes
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Notes added successfully',
            'review_notes': order_result.review_notes
        }), 200
    
    except ValueError:
        return jsonify({'error': 'Invalid order ID format'}), 400
    except Exception as e:
        logger.error(f"Error adding notes to order: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@webhooks_bp.route('/orders/completed', methods=['GET'])
@jwt_required()
def get_completed_orders():
    """
    Get all completed/successful orders across all uploads.
    Returns list of successful orders with upload context.
    """
    try:
        # Get query parameters
        client_id = request.args.get('client_id')
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        
        # Build query - exclude partial_success orders (they show up in failed orders)
        from sqlalchemy import or_
        query = SalesOrderResult.query.filter(
            SalesOrderResult.status == 'success',
            or_(
                SalesOrderResult.error_type.is_(None),
                SalesOrderResult.error_type != 'partial_success'
            )
        )
        
        # Filter by client_erp_credentials_id if provided
        if client_id:
            try:
                client_uuid = uuid.UUID(client_id)
                query = query.join(SalesOrderUpload).filter(SalesOrderUpload.client_erp_credentials_id == client_uuid)
            except ValueError:
                return jsonify({'error': 'Invalid client_id format'}), 400
        
        # Get total count
        total = query.count()
        
        # Order by created_at descending (most recent first)
        query = query.order_by(SalesOrderResult.created_at.desc())
        
        # Apply pagination
        completed_orders = query.limit(limit).offset(offset).all()
        
        # Build response
        result = []
        for order_result in completed_orders:
            upload = SalesOrderUpload.query.get(order_result.upload_id)
            client_name = None
            if upload and upload.client_id:
                try:
                    client = Client.query.get(upload.client_id)
                    if client:
                        client_name = client.name
                except Exception:
                    pass
            
            # Extract order details from order_data
            order_data = order_result.order_data or {}
            customer_name = order_data.get('customer_name') or order_data.get('customername', '')
            po_number = order_data.get('po_number') or order_data.get('customerreference', '')
            
            result.append({
                'id': str(order_result.id),
                'order_key': order_result.order_key,
                'customer_name': customer_name,
                'po_number': po_number,
                'sale_id': str(order_result.sale_id) if order_result.sale_id else None,
                'sale_order_id': str(order_result.sale_order_id) if order_result.sale_order_id else None,
                'retry_count': order_result.retry_count or 0,
                'reviewed': order_result.reviewed if order_result.reviewed is not None else False,
                'review_notes': order_result.review_notes,
                'upload': {
                    'id': str(upload.id) if upload else None,
                    'filename': upload.filename if upload else None,
                    'created_at': upload.created_at.isoformat() if upload and upload.created_at else None,
                    'client_name': client_name
                } if upload else None,
                'order_data': order_data,
                'matching_details': order_data.get('matching_details'),
                'sale_payload': order_data.get('sale_payload'),
                'sale_order_payload': order_data.get('sale_order_payload'),
                'created_at': order_result.created_at.isoformat() if order_result.created_at else None,
                'processed_at': order_result.processed_at.isoformat() if order_result.processed_at else None
            })
        
        return jsonify({
            'completed_orders': result,
            'total': total,
            'limit': limit,
            'offset': offset
        }), 200
    
    except Exception as e:
        logger.error(f"Error getting completed orders: {str(e)}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@webhooks_bp.route('/orders/completed/unreviewed-count', methods=['GET'])
@jwt_required()
def get_unreviewed_completed_orders_count():
    """
    Get count of unreviewed completed orders.
    Used for the badge count in the UI.
    """
    try:
        # Get query parameters
        client_id = request.args.get('client_id')
        
        # Build query for unreviewed completed orders - exclude partial_success (they show in failed orders)
        from sqlalchemy import or_
        query = SalesOrderResult.query.filter(
            SalesOrderResult.status == 'success',
            SalesOrderResult.reviewed == False,
            or_(
                SalesOrderResult.error_type.is_(None),
                SalesOrderResult.error_type != 'partial_success'
            )
        )
        
        # Filter by client_erp_credentials_id if provided
        if client_id:
            try:
                client_uuid = uuid.UUID(client_id)
                query = query.join(SalesOrderUpload).filter(SalesOrderUpload.client_erp_credentials_id == client_uuid)
            except ValueError:
                return jsonify({'error': 'Invalid client_id format'}), 400
        
        # Get count
        count = query.count()
        
        return jsonify({
            'unreviewed_count': count
        }), 200
    
    except Exception as e:
        logger.error(f"Error getting unreviewed count: {str(e)}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@webhooks_bp.route('/orders/failed/unreviewed-count', methods=['GET'])
@jwt_required()
def get_unreviewed_failed_orders_count():
    """
    Get count of unreviewed failed orders (unresolved orders).
    Used for the badge count in the UI.
    """
    try:
        # Get query parameters
        client_id = request.args.get('client_id')
        
        # Build query for unreviewed failed orders (orders that haven't been resolved/reviewed)
        # Include both failed orders and partial_success orders (orders with missing products)
        from sqlalchemy import or_
        query = SalesOrderResult.query.filter(
            or_(
                SalesOrderResult.status == 'failed',
                SalesOrderResult.error_type == 'partial_success'
            )
        )
        query = query.filter(SalesOrderResult.resolved_at.is_(None))
        
        # Filter by client_erp_credentials_id if provided
        if client_id:
            try:
                client_uuid = uuid.UUID(client_id)
                query = query.join(SalesOrderUpload).filter(SalesOrderUpload.client_erp_credentials_id == client_uuid)
            except ValueError:
                return jsonify({'error': 'Invalid client_id format'}), 400
        
        # Get count
        count = query.count()
        
        return jsonify({
            'unreviewed_count': count
        }), 200
    
    except Exception as e:
        logger.error(f"Error getting unreviewed failed count: {str(e)}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@webhooks_bp.route('/orders/<order_id>/review', methods=['POST'])
@jwt_required()
def mark_order_as_reviewed(order_id):
    """
    Mark a completed order as reviewed or unreviewed.
    Accepts a 'reviewed' boolean in the request body.
    Note: review_notes are only used for failed orders, not completed orders.
    """
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'error': 'Invalid user ID'}), 400
        
        # Get request data
        data = request.get_json() or {}
        reviewed = data.get('reviewed', True)  # Default to True for backward compatibility
        
        # Get order
        order_result = SalesOrderResult.query.get(uuid.UUID(order_id))
        if not order_result:
            return jsonify({'error': 'Order not found'}), 404
        
        # Only allow marking successful orders as reviewed/unreviewed
        if order_result.status != 'success':
            return jsonify({'error': 'Only completed orders can be marked as reviewed'}), 400
        
        # Update reviewed status (notes not used for completed orders)
        order_result.reviewed = reviewed
        order_result.review_notes = None  # Completed orders don't have review notes
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Order marked as {"reviewed" if reviewed else "unreviewed"}',
            'reviewed': reviewed
        }), 200
    
    except ValueError:
        return jsonify({'error': 'Invalid order ID format'}), 400
    except Exception as e:
        logger.error(f"Error updating order reviewed status: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@webhooks_bp.route('/upload/<upload_id>/csv', methods=['GET'])
@jwt_required()
def get_upload_csv(upload_id):
    """
    Get CSV content for an upload (for preview).
    """
    try:
        upload = SalesOrderUpload.query.get(uuid.UUID(upload_id))
        if not upload:
            return jsonify({'error': 'Upload not found'}), 404
        
        if not upload.csv_content:
            return jsonify({'error': 'CSV content not available'}), 404
        
        import base64
        csv_content = base64.b64decode(upload.csv_content)
        
        from flask import Response
        return Response(
            csv_content,
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename="{upload.filename}"'
            }
        )
    
    except Exception as e:
        logger.error(f"Error getting CSV: {str(e)}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@webhooks_bp.route('/events', methods=['GET'])
def stream_events():
    """
    Server-Sent Events (SSE) endpoint for real-time upload status updates.
    Clients connect to this endpoint and receive events when upload statuses change.
    
    Note: EventSource doesn't support custom headers, so we accept token as query param.
    """
    # Get token from query param (EventSource doesn't support custom headers)
    token = request.args.get('token')
    if not token:
        return jsonify({'error': 'Token required'}), 401
    
    # Verify token manually
    try:
        from flask_jwt_extended import decode_token
        from flask import current_app
        # Decode token using the app's JWT secret
        decoded_token = decode_token(token)
        user_id = decoded_token.get('sub')
        if not user_id:
            return jsonify({'error': 'Invalid token'}), 401
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        return jsonify({'error': 'Invalid token'}), 401
    def event_stream():
        """Generator function that yields SSE events"""
        try:
            while True:
                try:
                    # Wait for event with timeout to allow periodic keepalive
                    event_data = _event_queue.get(timeout=30)
                    
                    # Format as SSE event
                    event_json = json.dumps(event_data)
                    yield f"data: {event_json}\n\n"
                except queue.Empty:
                    # Send keepalive comment to keep connection alive
                    yield ": keepalive\n\n"
        except GeneratorExit:
            # Client disconnected
            logger.info("SSE client disconnected")
        except Exception as e:
            logger.error(f"Error in SSE stream: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
    
    response = Response(
        stream_with_context(event_stream()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',  # Disable buffering in nginx
            'Connection': 'keep-alive'
        }
    )
    return response

@webhooks_bp.route('/queue', methods=['GET'])
@jwt_required()
def get_queue():
    """
    Get upload history with order-level results.
    Returns list of SalesOrderUpload records with their SalesOrderResult records.
    """
    try:
        # Get query parameters
        client_id = request.args.get('client_id')
        status = request.args.get('status')
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        
        # Build query
        query = SalesOrderUpload.query
        
        if client_id:
            try:
                client_uuid = uuid.UUID(client_id)
                query = query.filter_by(client_erp_credentials_id=client_uuid)
            except ValueError:
                return jsonify({'error': 'Invalid client_id format'}), 400
        
        if status:
            query = query.filter_by(status=status)
        
        # Order by created_at descending
        query = query.order_by(SalesOrderUpload.created_at.desc())
        
        # Get total count
        total = query.count()
        
        # Apply pagination
        uploads = query.limit(limit).offset(offset).all()
        
        # Get all upload IDs for batch loading
        upload_ids = [upload.id for upload in uploads]
        
        # Batch load all order results in one query (avoid N+1)
        all_order_results = {}
        if upload_ids:
            order_results_query = SalesOrderResult.query.filter(
                SalesOrderResult.upload_id.in_(upload_ids)
            ).order_by(SalesOrderResult.created_at.asc()).all()
            
            # Group by upload_id
            for or_result in order_results_query:
                if or_result.upload_id not in all_order_results:
                    all_order_results[or_result.upload_id] = []
                all_order_results[or_result.upload_id].append(or_result)
        
        # Batch load client names (avoid N+1)
        client_ids = [upload.client_id for upload in uploads if upload.client_id]
        client_names = {}
        if client_ids:
            clients = Client.query.filter(Client.id.in_(client_ids)).all()
            for client in clients:
                client_names[client.id] = client.name
        
        # Build response
        result = []
        for upload in uploads:
            # Get order results from batch-loaded data
            order_results = all_order_results.get(upload.id, [])
            
            # Get client name from batch-loaded data
            client_name = client_names.get(upload.client_id) if upload.client_id else None
            
            result.append({
                'id': str(upload.id),
                'filename': upload.filename,
                'client_id': str(upload.client_id) if upload.client_id else None,
                'client_name': client_name,
                'total_rows': upload.total_rows,
                'successful_orders': upload.successful_orders,
                'failed_orders': upload.failed_orders,
                'status': upload.status,
                'has_csv': bool(upload.csv_content),  # Indicate if CSV is available for preview
                'created_at': upload.created_at.isoformat() if upload.created_at else None,
                'completed_at': upload.completed_at.isoformat() if upload.completed_at else None,
                'order_results': [{
                    'id': str(or_result.id),
                    'order_key': or_result.order_key,
                    'row_numbers': or_result.row_numbers,
                    'status': or_result.status,
                    'sale_id': str(or_result.sale_id) if or_result.sale_id else None,
                    'sale_order_id': str(or_result.sale_order_id) if or_result.sale_order_id else None,
                    'error_message': or_result.error_message,
                    'error_type': or_result.error_type,
                    'retry_count': or_result.retry_count or 0,
                    'last_retry_at': or_result.last_retry_at.isoformat() if or_result.last_retry_at else None,
                    'resolved_at': or_result.resolved_at.isoformat() if or_result.resolved_at else None,
                    'resolved_by': str(or_result.resolved_by) if or_result.resolved_by else None,
                    'order_data': or_result.order_data,
                    'matching_details': or_result.order_data.get('matching_details') if or_result.order_data else None,
                    'sale_payload': or_result.order_data.get('sale_payload') if or_result.order_data else None,
                    'sale_order_payload': or_result.order_data.get('sale_order_payload') if or_result.order_data else None,
                    'what_is_needed': or_result.order_data.get('what_is_needed') if or_result.order_data else None,
                    'created_at': or_result.created_at.isoformat() if or_result.created_at else None,
                    'processed_at': or_result.processed_at.isoformat() if or_result.processed_at else None
                } for or_result in order_results]
            })
        
        return jsonify({
            'uploads': result,
            'total': total,
            'limit': limit,
            'offset': offset
        }), 200
    
    except Exception as e:
        logger.error(f"Error getting queue: {str(e)}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

