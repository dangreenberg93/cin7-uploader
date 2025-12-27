"""Webhook routes for email automation"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
import requests
import uuid
import time
import threading
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from database import db, SalesOrderUpload, SalesOrderResult, ClientSettings, ClientCsvMapping, Cin7ApiLog, Client
from cin7_sales.api_client import Cin7SalesAPI
from cin7_sales.csv_parser import CSVParser
from cin7_sales.validator import SalesOrderValidator
from cin7_sales.sales_order_builder import SalesOrderBuilder
from sqlalchemy import text, func
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
    
    # Keep backward compatibility with old field names
    order_data['customer_name'] = primary_row.get('CustomerName') or primary_row.get('customer_name', '') or order_data.get('customername', '')
    order_data['po_number'] = primary_row.get('CustomerReference') or primary_row.get('po_number', '') or order_data.get('customerreference', '')
    order_data['order_date'] = primary_row.get('SaleDate') or primary_row.get('order_date', '') or order_data.get('saledate', '')
    order_data['order_number'] = primary_row.get('SaleOrderNumber') or primary_row.get('order_number', '') or order_data.get('saleordernumber', '')
    
    try:
        # Always use combined approach (single API call with nested Order)
        use_combined_approach = True
        
        # Check customer lookup first (needed for TaxRule in combined call)
        customer_name = primary_row.get('CustomerName') or primary_row.get('customer_name') or ''
        customer_data = None
        
        # Collect detailed matching information before API call
        matching_details = {
            'customer': {},
            'products': [],
            'missing_fields': []
        }
        
        if customer_name:
            customer_data = builder._lookup_customer_by_name(customer_name)
            if customer_data:
                matching_details['customer'] = {
                    'name': customer_name,
                    'found': True,
                    'cin7_id': customer_data.get('ID'),
                    'cin7_name': customer_data.get('Name'),
                    'tax_rule': customer_data.get('TaxRule')  # Store TaxRule for later use
                }
            else:
                matching_details['customer'] = {
                    'name': customer_name,
                    'found': False,
                    'error': f'Customer "{customer_name}" not found in Cin7'
                }
        
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
                    if product:
                        matching_details['products'].append({
                            'sku': sku,
                            'found': True,
                            'cin7_id': product.get('ID'),
                            'cin7_name': product.get('Name')
                        })
                    else:
                        matching_details['products'].append({
                            'sku': sku,
                            'found': False,
                            'error': f'Product SKU "{sku}" not found in Cin7'
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
        if len(order_rows) > 1:
            sale_order_for_what_is_needed = builder.build_sale_order_from_rows(order_rows, column_mapping, '<SALE_ID_PLACEHOLDER>', customer_data=customer_data)
        else:
            sale_order_for_what_is_needed = builder.build_sale_order(order_rows[0], column_mapping, '<SALE_ID_PLACEHOLDER>', customer_data=customer_data)
        
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
        
        # Check if we should even attempt to send to Cin7
        # CustomerID is required - if we don't have it, don't send
        should_attempt_sale = 'CustomerID' in sale_data and sale_data.get('CustomerID')
        
        if not should_attempt_sale:
            # Don't send to Cin7 - customer not matched
            enhanced_error = 'Cannot create Sale: CustomerID is required but customer was not found in Cin7'
            if not matching_details['customer'].get('found'):
                enhanced_error += f" | Customer '{matching_details['customer'].get('name', 'N/A')}' not found in Cin7"
            
            order_result.status = 'failed'
            order_result.error_message = enhanced_error
            order_result.error_type = categorize_error(enhanced_error)
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
        
        # Step 1: Create Sale first
        logger.info(f"Creating Sale for order {order_key}...")
        sale_success, sale_message, sale_response = api_client.create_sale(sale_data)
        sale_api_response = sale_response if sale_response else None
        sale_id = None
        
        # Extract Sale ID from response
        if isinstance(sale_response, dict):
            sale_id = sale_response.get('ID')
        elif isinstance(sale_response, list) and len(sale_response) > 0:
            first_item = sale_response[0] if isinstance(sale_response[0], dict) else None
            if first_item:
                sale_id = first_item.get('ID')
        
        if not sale_success:
            # Enhance error message with matching details
            error_parts = [f'Failed to create Sale: {sale_message}']
            
            if not matching_details['customer'].get('found'):
                error_parts.append(f"Customer issue: {matching_details['customer'].get('error', 'Customer not found')}")
            
            missing_products = [p for p in matching_details['products'] if not p.get('found')]
            if missing_products:
                product_errors = [p.get('error', f"SKU {p.get('sku')} not found") for p in missing_products]
                error_parts.append(f"Product issues: {', '.join(product_errors)}")
            
            if matching_details['missing_fields']:
                error_parts.append(f"Missing required fields: {', '.join(matching_details['missing_fields'])}")
            
            enhanced_error = ' | '.join(error_parts)
            
            order_result.status = 'failed'
            order_result.error_message = enhanced_error
            order_result.error_type = categorize_error(enhanced_error)
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
        
        # Step 2: Get customer and sale data for TaxRule lookup (needed for sale order)
        sale_data_from_api = None
        if sale_id:
            try:
                sale_data_from_api = api_client.get_sale(str(sale_id))
            except Exception as sale_lookup_error:
                logger.warning(f"Warning: Could not retrieve Sale data for TaxRule: {str(sale_lookup_error)}")
        
        # Step 3: Build and create Sale Order with the Sale ID
        logger.info(f"Creating Sale Order for order {order_key} with Sale ID {sale_id}...")
        
        # Build sale order payload
        if len(order_rows) > 1:
            sale_order_data = builder.build_sale_order_from_rows(order_rows, column_mapping, str(sale_id), customer_data=customer_data, sale_data=sale_data_from_api)
        else:
            sale_order_data = builder.build_sale_order(order_rows[0], column_mapping, str(sale_id), customer_data=customer_data, sale_data=sale_data_from_api)
        
        # Create Sale Order via API
        so_success, so_message, so_response = api_client.create_sale_order(sale_order_data)
        sale_order_api_response = so_response if so_response else None
        sale_order_id = None
        
        # Extract Sale Order ID from response
        if isinstance(so_response, dict):
            sale_order_id = so_response.get('ID')
        elif isinstance(so_response, list) and len(so_response) > 0:
            first_item = so_response[0] if isinstance(so_response[0], dict) else None
            if first_item:
                sale_order_id = first_item.get('ID')
        
        if not so_success:
            # Sale was created but Sale Order failed
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
        order_result.status = 'success'
        order_result.sale_id = sale_id
        order_result.sale_order_id = sale_order_id if sale_order_id else None
        order_result.order_data = {
            **order_data,
            'matching_details': matching_details,
            'sale_payload': sale_data,
            'sale_order_payload': sale_order_data,
            'sale_api_response': sale_api_response,
            'sale_order_api_response': sale_order_api_response
        }
        order_result.processed_at = datetime.utcnow()
        db.session.commit()
        
        return {
            'status': 'success',
            'sale_id': str(sale_id),
            'sale_order_id': str(sale_order_id) if sale_order_id else None,
            'order_data': order_result.order_data
        }
    
    except Exception as e:
            if not sale_id:
                order_result.status = 'failed'
                order_result.error_message = 'Sale created but no ID returned'
                order_result.error_type = categorize_error('Sale created but no ID returned')
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
            
            # Get Sale data to extract TaxRule (if available)
            sale_data_from_api = None
            if api_client:
                try:
                    sale_data_from_api = api_client.get_sale(str(sale_id))
                    if sale_data_from_api:
                        logger.info(f"Retrieved Sale data for TaxRule lookup - TaxRule: {sale_data_from_api.get('TaxRule')}")
                except Exception as sale_lookup_error:
                    logger.warning(f"Could not retrieve Sale data for TaxRule lookup: {str(sale_lookup_error)}")
            
            # Step 2: Build and create Sale Order
            # Note: sale_order_data was already built above for "what_is_needed", but rebuild with actual sale_id
            # Pass customer_data and sale_data so builder can extract TaxRule
            logger.info(f"Step 2: Building Sale Order for order {order_key} with sale_id {sale_id}")
            row_data_list = order_rows
            sale_order_data = builder.build_sale_order_from_rows(row_data_list, column_mapping, str(sale_id), customer_data=customer_data, sale_data=sale_data_from_api)
            
            logger.info(f"Sale Order payload built for order {order_key}: SaleID={sale_order_data.get('SaleID')}, Lines count={len(sale_order_data.get('Lines', []))}, Total={sale_order_data.get('Total')}")
            
            # Create Sale Order via API
            logger.info(f"Creating Sale Order via API for order {order_key}...")
            so_success, so_message, so_response = api_client.create_sale_order(sale_order_data)
            logger.info(f"Sale Order API call result for order {order_key}: success={so_success}, message={so_message}")
            logger.info(f"Sale Order response type: {type(so_response)}, response: {so_response}")
            
            # Store API responses for display
            sale_order_api_response = so_response if so_response else None
            
            if so_success:
                sale_order_id = None
                if isinstance(so_response, dict):
                    # Try multiple possible ID fields
                    sale_order_id = (so_response.get('ID') or 
                                   so_response.get('SaleOrderID') or 
                                   so_response.get('SaleOrder') or
                                   so_response.get('id'))
                    logger.info(f"Extracted sale_order_id from dict: {sale_order_id}, response keys: {list(so_response.keys()) if isinstance(so_response, dict) else 'N/A'}")
                elif isinstance(so_response, list) and len(so_response) > 0:
                    first_item = so_response[0]
                    if isinstance(first_item, dict):
                        sale_order_id = (first_item.get('ID') or 
                                       first_item.get('SaleOrderID') or 
                                       first_item.get('SaleOrder') or
                                       first_item.get('id'))
                    logger.info(f"Extracted sale_order_id from list: {sale_order_id}")
                
                # If we still don't have an ID, log warning but don't fail - Sale Order might have been created
                if not sale_order_id:
                    logger.warning(f"Sale Order created successfully but no ID found in response for order {order_key}. Response: {so_response}")
                    # Still mark as success since the API call succeeded - the Sale Order was likely created
                    # The ID might be in the response but in an unexpected format
                
                order_result.status = 'success'
                order_result.sale_id = sale_id
                order_result.sale_order_id = sale_order_id if sale_order_id else None
                # Store sale_payload and API responses for successful orders too (for reference)
                order_result.order_data = {
                    **order_data,
                    'matching_details': matching_details,
                    'sale_payload': sale_data,  # Store the payload that was sent
                    'sale_api_response': sale_api_response,  # Store the API response
                    'sale_order_payload': sale_order_data,  # Store the sale order payload that was sent
                    'sale_order_api_response': sale_order_api_response  # Store the API response
                }
                order_result.processed_at = datetime.utcnow()
                db.session.commit()
                
                return {
                    'status': 'success',
                    'sale_id': str(sale_id),
                    'sale_order_id': str(sale_order_id) if sale_order_id else None,
                    'order_data': order_result.order_data
                }
            else:
                # Sale was created but Sale Order failed
                error_msg = f'Sale created (ID: {sale_id}) but Sale Order failed: {so_message}'
            order_result.status = 'failed'
            order_result.sale_id = sale_id
            order_result.error_message = error_msg
            order_result.error_type = categorize_error(error_msg)
            # Store sale_payload, sale_order_payload, API responses and matching details for reference
            order_result.order_data = {
                **order_data,
                'matching_details': matching_details,
                'sale_payload': sale_data,  # Store the payload that was sent
                'sale_api_response': sale_api_response,  # Store the API response
                'sale_order_payload': sale_order_data,  # Store the sale order payload that was sent
                'sale_order_api_response': sale_order_api_response  # Store the API response (even if failed)
            }
            order_result.processed_at = datetime.utcnow()
            db.session.commit()
            
            return {
                'status': 'failed',
                'sale_id': str(sale_id),
                'error_message': f'Sale created (ID: {sale_id}) but Sale Order failed: {so_message}',
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
        
        order_result.status = 'failed'
        order_result.error_message = error_msg
        order_result.error_type = categorize_error(error_msg)
        order_result.order_data = order_data
        order_result.processed_at = datetime.utcnow()
        db.session.commit()
        
        return {
            'status': 'failed',
            'error_message': error_msg,
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
        upload.status = 'completed' if failed_count == 0 else 'failed'  # Failed if any orders failed
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
                app = create_app('production' if os.environ.get('FLASK_ENV') == 'production' else 'development')
                with app.app_context():
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
        
        # Get all API logs for this upload
        # Get all logs for the upload - they're all related to processing orders from this upload
        logger.info(f"Fetching API logs for order {order_result_id}, upload_id: {order_result.upload_id}")
        logs_query = Cin7ApiLog.query.filter_by(upload_id=order_result.upload_id)
        
        # Order by creation time (oldest first to see the sequence)
        logs_query = logs_query.order_by(Cin7ApiLog.created_at.asc())
        
        logs = logs_query.all()
        logger.info(f"Found {len(logs)} API logs for upload_id {order_result.upload_id}")
        
        # Format response
        logs_data = []
        for log in logs:
            # Parse response_body if it's a string (JSON stored as text)
            response_body = log.response_body
            if isinstance(response_body, str):
                try:
                    import json
                    response_body = json.loads(response_body)
                except (json.JSONDecodeError, TypeError):
                    # Keep as string if not valid JSON
                    pass
            
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
        
        # Build query
        query = SalesOrderResult.query.filter_by(status='failed')
        
        # Filter by resolved status
        if not include_resolved:
            query = query.filter(SalesOrderResult.resolved_at.is_(None))
        
        # Filter by error type
        if error_type:
            query = query.filter_by(error_type=error_type)
        
        # Filter by client_id if provided
        if client_id:
            try:
                client_uuid = uuid.UUID(client_id)
                query = query.join(SalesOrderUpload).filter(SalesOrderUpload.client_id == client_uuid)
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
    Manually mark a failed order as resolved.
    """
    try:
        order_result = SalesOrderResult.query.get(uuid.UUID(order_id))
        if not order_result:
            return jsonify({'error': 'Order not found'}), 404
        
        if order_result.status == 'success':
            return jsonify({'error': 'Order already succeeded'}), 400
        
        data = request.get_json() or {}
        reason = data.get('reason', '')
        
        # Get current user
        current_user_id = get_jwt_identity()
        user_id = uuid.UUID(current_user_id) if current_user_id else None
        
        # Mark as resolved
        order_result.resolved_at = datetime.utcnow()
        order_result.resolved_by = user_id
        
        # Store resolution reason in order_data if provided
        if reason:
            if not order_result.order_data:
                order_result.order_data = {}
            order_result.order_data['resolution_reason'] = reason
        
        db.session.commit()
        
        return jsonify({
            'status': 'resolved',
            'resolved_at': order_result.resolved_at.isoformat(),
            'resolved_by': str(order_result.resolved_by) if order_result.resolved_by else None
        }), 200
    
    except ValueError:
        return jsonify({'error': 'Invalid order ID format'}), 400
    except Exception as e:
        logger.error(f"Error resolving order: {str(e)}", exc_info=True)
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
        
        # Build query
        query = SalesOrderResult.query.filter_by(status='success')
        
        # Filter by client_id if provided
        if client_id:
            try:
                client_uuid = uuid.UUID(client_id)
                query = query.join(SalesOrderUpload).filter(SalesOrderUpload.client_id == client_uuid)
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

