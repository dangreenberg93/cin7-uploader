"""Webhook routes for email automation"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
import requests
import uuid
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from database import db, SalesOrderUpload, SalesOrderResult, ClientSettings, ClientCsvMapping, Cin7ApiLog, Client
from cin7_sales.api_client import Cin7SalesAPI
from cin7_sales.csv_parser import CSVParser
from cin7_sales.validator import SalesOrderValidator
from cin7_sales.sales_order_builder import SalesOrderBuilder
from sqlalchemy import text
from routes.auth import User

webhooks_bp = Blueprint('webhooks', __name__)
logger = logging.getLogger(__name__)


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
            if client_part:
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


def process_single_order(
    upload_id: uuid.UUID,
    order_key: str,
    order_rows: List[Dict],
    row_numbers: List[int],
    column_mapping: Dict,
    settings: Dict,
    api_client: Cin7SalesAPI,
    builder: SalesOrderBuilder,
    credential_id_for_logging: uuid.UUID
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
        
    Returns:
        Result dict with status, sale_id, sale_order_id, error_message, order_data
    """
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
    
    # Extract order data snapshot (from first row)
    primary_row = order_rows[0] if order_rows else {}
    order_data = {
        'customer_name': primary_row.get('CustomerName') or primary_row.get('customer_name', ''),
        'po_number': primary_row.get('CustomerReference') or primary_row.get('po_number', ''),
        'order_date': primary_row.get('SaleDate') or primary_row.get('order_date', ''),
        'order_number': primary_row.get('SaleOrderNumber') or primary_row.get('order_number', '')
    }
    
    try:
        # Step 1: Build and create Sale
        sale_data = builder.build_sale(primary_row, column_mapping)
        
        # Create Sale via API
        success, message, response = api_client.create_sale(sale_data)
        
        if not success:
            order_result.status = 'failed'
            order_result.error_message = f'Failed to create Sale: {message}'
            order_result.order_data = order_data
            order_result.processed_at = datetime.utcnow()
            db.session.commit()
            return {
                'status': 'failed',
                'error_message': f'Failed to create Sale: {message}',
                'order_data': order_data
            }
        
        # Extract Sale ID from response
        sale_id = None
        if isinstance(response, dict):
            sale_id = response.get('ID')
        elif isinstance(response, list) and len(response) > 0:
            sale_id = response[0].get('ID') if isinstance(response[0], dict) else None
        
        if not sale_id:
            order_result.status = 'failed'
            order_result.error_message = 'Sale created but no ID returned'
            order_result.order_data = order_data
            order_result.processed_at = datetime.utcnow()
            db.session.commit()
            return {
                'status': 'failed',
                'error_message': 'Sale created but no ID returned',
                'order_data': order_data
            }
        
        # Rate limiting delay between Sale and Sale Order
        delay = settings.get('default_delay_between_orders', 0.7)
        time.sleep(delay)
        
        # Step 2: Build and create Sale Order
        if len(order_rows) > 1:
            # Multiple rows - use grouped rows
            row_data_list = order_rows
            sale_order_data = builder.build_sale_order_from_rows(row_data_list, column_mapping, str(sale_id))
        else:
            # Single row order
            sale_order_data = builder.build_sale_order(primary_row, column_mapping, str(sale_id))
        
        # Create Sale Order via API
        so_success, so_message, so_response = api_client.create_sale_order(sale_order_data)
        
        if so_success:
            sale_order_id = None
            if isinstance(so_response, dict):
                sale_order_id = so_response.get('ID')
            elif isinstance(so_response, list) and len(so_response) > 0:
                sale_order_id = so_response[0].get('ID') if isinstance(so_response[0], dict) else None
            
            order_result.status = 'success'
            order_result.sale_id = sale_id
            order_result.sale_order_id = sale_order_id
            order_result.order_data = order_data
            order_result.processed_at = datetime.utcnow()
            db.session.commit()
            
            return {
                'status': 'success',
                'sale_id': str(sale_id),
                'sale_order_id': str(sale_order_id) if sale_order_id else None,
                'order_data': order_data
            }
        else:
            # Sale was created but Sale Order failed
            order_result.status = 'failed'
            order_result.sale_id = sale_id
            order_result.error_message = f'Sale created (ID: {sale_id}) but Sale Order failed: {so_message}'
            order_result.order_data = order_data
            order_result.processed_at = datetime.utcnow()
            db.session.commit()
            
            return {
                'status': 'failed',
                'sale_id': str(sale_id),
                'error_message': f'Sale created (ID: {sale_id}) but Sale Order failed: {so_message}',
                'order_data': order_data
            }
    
    except Exception as e:
        logger.error(f"Error processing order {order_key}: {str(e)}", exc_info=True)
        order_result.status = 'failed'
        order_result.error_message = str(e)
        order_result.order_data = order_data
        order_result.processed_at = datetime.utcnow()
        db.session.commit()
        
        return {
            'status': 'failed',
            'error_message': str(e),
            'order_data': order_data
        }


def process_webhook_csv(
    upload_id: uuid.UUID,
    client_erp_credentials_id: uuid.UUID,
    csv_content: bytes,
    filename: str
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
    column_mapping = {}
    # First, use detected mappings
    for cin7_field, matches in detected_mappings.items():
        if matches and len(matches) > 0:
            column_mapping[cin7_field] = matches[0]
    # Then, override with default mapping if it exists
    for cin7_field, csv_column in default_mapping.items():
        if csv_column:
            column_mapping[cin7_field] = csv_column
    
    if not column_mapping:
        return {'error': 'No column mapping found or detected'}
    
    # Get credentials and settings
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
    
    # Create logging callback
    credential_id_for_logging = client_erp_credentials_id
    
    def log_api_call(endpoint, method, request_url, request_headers, request_body,
                     response_status, response_body, error_message, duration_ms):
        """Callback to log API calls to database"""
        try:
            try:
                log_entry = Cin7ApiLog(
                    id=uuid.uuid4(),
                    client_id=credential_id_for_logging,
                    user_id=None,  # Webhook has no user
                    upload_id=upload_id,
                    trigger='webhook',
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
            except Exception as trigger_error:
                error_str = str(trigger_error).lower()
                if 'trigger' in error_str or 'column' in error_str:
                    db.session.rollback()
                    log_entry = Cin7ApiLog(
                        id=uuid.uuid4(),
                        client_id=credential_id_for_logging,
                        user_id=None,
                        upload_id=upload_id,
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
                else:
                    raise
        except Exception as e:
            logger.error(f"Error logging API call: {str(e)}")
            db.session.rollback()
    
    # Initialize API client
    api_client = Cin7SalesAPI(
        account_id=str(account_id),
        application_key=str(application_key),
        base_url='https://inventory.dearsystems.com/ExternalApi/v2/',
        logger_callback=log_api_call
    )
    
    # Group rows into orders
    validator = SalesOrderValidator(api_client)
    row_groups = validator._group_rows_by_order(rows, column_mapping)
    
    # Initialize builder
    builder = SalesOrderBuilder(settings, api_client)
    
    # Process each order
    successful_count = 0
    failed_count = 0
    
    for order_key, group_rows in row_groups.items():
        # Extract row data and row numbers
        row_data_list = [r['data'] for r in group_rows]
        row_numbers = [r['row_number'] for r in group_rows]
        
        # Process order
        result = process_single_order(
            upload_id=upload_id,
            order_key=order_key,
            order_rows=row_data_list,
            row_numbers=row_numbers,
            column_mapping=column_mapping,
            settings=settings,
            api_client=api_client,
            builder=builder,
            credential_id_for_logging=credential_id_for_logging
        )
        
        if result['status'] == 'success':
            successful_count += 1
        else:
            failed_count += 1
        
        # Rate limiting delay between orders
        delay = settings.get('default_delay_between_orders', 0.7)
        time.sleep(delay)
    
    # Update upload record
    upload = SalesOrderUpload.query.get(upload_id)
    if upload:
        upload.successful_orders = successful_count
        upload.failed_orders = failed_count
        upload.status = 'completed' if failed_count == 0 else 'completed'  # Still completed even with failures
        upload.completed_at = datetime.utcnow()
        upload.total_rows = len(rows)
        db.session.commit()
    
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
            return jsonify({'error': f'Client not found: {client_name}'}), 404
        
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
        
        # Create upload record immediately
        upload = SalesOrderUpload(
            id=uuid.uuid4(),
            user_id=None,  # Webhook has no user context
            client_id=client_id_for_upload,  # May be None for standalone connections
            filename=filename,
            total_rows=0,  # Will be updated after parsing
            successful_orders=0,
            failed_orders=0,
            status='processing'
        )
        db.session.add(upload)
        db.session.commit()
        
        # Process CSV (this will update the upload record)
        result = process_webhook_csv(
            upload_id=upload.id,
            client_erp_credentials_id=client_erp_credentials_id,
            csv_content=csv_content,
            filename=filename
        )
        
        if 'error' in result:
            upload.status = 'failed'
            upload.error_log = [result.get('error')]
            upload.completed_at = datetime.utcnow()
            db.session.commit()
            return jsonify(result), 400
        
        logger.info(f"Webhook processed successfully - upload_id: {upload.id}, client: {client_name}, orders: {result.get('total_orders', 0)}")
        
        return jsonify({
            'upload_id': str(upload.id),
            'successful': result.get('successful', 0),
            'failed': result.get('failed', 0),
            'total_orders': result.get('total_orders', 0),
            'client_name': client_name
        }), 200
    
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


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
                query = query.filter_by(client_id=client_uuid)
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
        
        # Build response
        result = []
        for upload in uploads:
            # Get order results
            order_results = SalesOrderResult.query.filter_by(upload_id=upload.id).order_by(SalesOrderResult.created_at.asc()).all()
            
            # Get client name
            client_name = None
            if upload.client_id:
                try:
                    client = Client.query.get(upload.client_id)
                    if client:
                        client_name = client.name
                except Exception:
                    pass
            
            result.append({
                'id': str(upload.id),
                'filename': upload.filename,
                'client_id': str(upload.client_id) if upload.client_id else None,
                'client_name': client_name,
                'total_rows': upload.total_rows,
                'successful_orders': upload.successful_orders,
                'failed_orders': upload.failed_orders,
                'status': upload.status,
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
                    'order_data': or_result.order_data,
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

