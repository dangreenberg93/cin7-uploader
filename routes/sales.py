"""Sales order upload/creation routes"""
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
from database import db, Client, ClientCin7Credentials, ClientSettings, ClientCsvMapping, SalesOrderUpload, UserClient, Cin7ApiLog, CachedCustomer, CachedProduct
from cin7_sales.api_client import Cin7SalesAPI
from cin7_sales.csv_parser import CSVParser
from cin7_sales.validator import SalesOrderValidator
from cin7_sales.sales_order_builder import SalesOrderBuilder
from routes.auth import User
from sqlalchemy import text
import uuid
import os
from datetime import datetime
import json
from collections import OrderedDict

sales_bp = Blueprint('sales', __name__)

# Upload folder for CSV files
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cin7_uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
    logger = logging.getLogger(__name__)
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

# In-memory storage for upload sessions (in production, use Redis or database)
upload_sessions = {}

def get_user_id():
    """Helper to get and convert user ID from JWT"""
    user_id = get_jwt_identity()
    try:
        if isinstance(user_id, str):
            user_id = uuid.UUID(user_id)
    except (ValueError, AttributeError):
        return None
    return user_id

def is_global_admin(user_id):
    """Check if user is a global admin (has role='admin' or is dan@paleblue.nyc)"""
    if not user_id:
        return False
    user = User.query.get(user_id)
    if not user:
        return False
    # Legacy: dan@paleblue.nyc is always admin
    if user.email == 'dan@paleblue.nyc':
        return True
    # Check global role
    return user.role == 'admin'

def has_client_access(user_id, client_id):
    """Check if user has access to a client (global admin or provisioned user)"""
    # Global admin has access to everything
    if is_global_admin(user_id):
        return True
    # Check if user is provisioned to this client
    user_client = UserClient.query.filter_by(user_id=user_id, client_id=client_id).first()
    return user_client is not None

@sales_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_csv():
    """Upload and parse CSV file"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    # Get client_id from request
    client_id = request.form.get('client_id')
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client_id format'}), 400
    
    # Check access
    if not has_client_access(user_id, client_uuid):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get file
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Read file content
    file_content = file.read()
    filename = file.filename
    
    # Parse CSV
    try:
        parser = CSVParser()
        rows, errors, skipped_rows = parser.parse_file(file_content, filename)
    except Exception as e:
        import traceback
        return jsonify({
            'error': 'CSV parsing failed',
            'errors': [f'Exception during parsing: {str(e)}'],
            'traceback': traceback.format_exc() if os.environ.get('FLASK_ENV') == 'development' else None
        }), 400
    
    if errors:
        return jsonify({'error': 'CSV parsing failed', 'errors': errors}), 400
    
    if not rows:
        return jsonify({
            'error': 'CSV file is empty or all rows were incomplete',
            'skipped_rows': skipped_rows
        }), 400
    
    # Transform dates in rows if SaleDate is mapped
    # We'll do this after mapping is set, but for now just parse CSV as-is
    # Dates will be transformed during validation/building
    
    # Detect columns
    detected_mappings = parser.detect_columns(rows)
    
    # Get default mapping if available
    default_mapping = {}
    default_mapping_obj = ClientCsvMapping.query.filter_by(
        client_erp_credentials_id=client_uuid,
        is_default=True
    ).first()
    
    template_name = None
    if default_mapping_obj:
        default_mapping = default_mapping_obj.column_mapping or {}
        template_name = default_mapping_obj.mapping_name
    
    # Merge detected mappings with default mapping (default takes precedence)
    initial_mapping = {}
    # First, use detected mappings
    for cin7_field, matches in detected_mappings.items():
        if matches and len(matches) > 0:
            initial_mapping[cin7_field] = matches[0]
    # Then, override with default mapping if it exists
    for cin7_field, csv_column in default_mapping.items():
        if csv_column:
            initial_mapping[cin7_field] = csv_column
    
    # Get client_id for upload record (may be None for standalone connections)
    # The client_uuid here is actually client_erp_credentials_id, so we need to look up the actual client_id
    client_id_for_upload = None
    client_query = text("""
        SELECT client_id FROM voyager.client_erp_credentials
        WHERE id = :cred_id
    """)
    client_result = db.session.execute(client_query, {'cred_id': client_uuid})
    client_row = client_result.fetchone()
    if client_row and client_row.client_id:
        client_id_for_upload = client_row.client_id
    
    # Create upload record early so we can log all API calls with upload_id
    upload = SalesOrderUpload(
        id=uuid.uuid4(),
        user_id=user_id,
        client_id=client_id_for_upload,  # May be None for standalone connections
        client_erp_credentials_id=client_uuid,
        filename=filename,
        total_rows=len(rows),
        successful_orders=0,
        failed_orders=0,
        status='pending'  # Will be updated to 'processing' when create is called
    )
    db.session.add(upload)
    db.session.commit()
    
    # Create session
    session_id = str(uuid.uuid4())
    upload_sessions[session_id] = {
        'user_id': user_id,
        'client_id': client_uuid,  # This is actually client_erp_credentials_id
        'client_erp_credentials_id': client_uuid,
        'upload_id': upload.id,  # Store upload_id in session for API logging
        'filename': filename,
        'rows': rows,
        'detected_mappings': detected_mappings,
        'column_mapping': initial_mapping,
        'validated_rows': None,
        'created_at': datetime.utcnow()
    }
    
    # Get CSV columns
    csv_columns = list(rows[0]['data'].keys()) if rows else []
    
    return jsonify({
        'session_id': session_id,
        'filename': filename,
        'row_count': len(rows),
        'csv_columns': csv_columns,
        'detected_mappings': detected_mappings,
        'initial_mapping': initial_mapping,  # Auto-detected mapping (default template merged with detected)
        'default_mapping_loaded': bool(default_mapping_obj),
        'template_name': template_name,  # Name of the template that was auto-loaded
        'skipped_rows': skipped_rows  # Rows that were skipped as incomplete/summary rows
    }), 200

@sales_bp.route('/rows', methods=['GET'])
@jwt_required()
def get_csv_rows():
    """Get CSV rows from session"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    session_id = request.args.get('session_id')
    if not session_id:
        return jsonify({'error': 'session_id is required'}), 400
    
    # Get session
    if session_id not in upload_sessions:
        return jsonify({'error': 'Session not found'}), 404
    
    session = upload_sessions[session_id]
    
    # Check access
    if session['user_id'] != user_id:
        return jsonify({'error': 'Access denied'}), 403
    
    # Return rows (limit to first 100 for preview)
    rows = session.get('rows', [])
    preview_rows = rows[:100] if len(rows) > 100 else rows
    
    # Convert rows to JSON-serializable format
    serializable_rows = []
    for row in preview_rows:
        serializable_rows.append({
            'row_number': row.get('row_number'),
            'data': row.get('data', {})
        })
    
    return jsonify({
        'rows': serializable_rows,
        'total_rows': len(rows),
        'showing_preview': len(rows) > 100
    }), 200

@sales_bp.route('/mapping', methods=['POST'])
@jwt_required()
def set_mapping():
    """Set column mapping for CSV"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    data = request.get_json()
    if not data or 'session_id' not in data or 'column_mapping' not in data:
        return jsonify({'error': 'session_id and column_mapping are required'}), 400
    
    session_id = data['session_id']
    column_mapping = data['column_mapping']
    
    # Get session
    if session_id not in upload_sessions:
        # Log available sessions for debugging (only in development)
        import os
        if os.environ.get('FLASK_ENV') == 'development':
            available_sessions = list(upload_sessions.keys())[:5]  # First 5 for debugging
            return jsonify({
                'error': 'Session not found',
                'session_id_received': session_id,
                'available_sessions_count': len(upload_sessions),
                'available_sessions_sample': available_sessions
            }), 404
        return jsonify({'error': 'Session not found. Please re-upload your CSV file.'}), 404
    
    session = upload_sessions[session_id]
    
    # Verify user owns this session
    if session['user_id'] != user_id:
        return jsonify({'error': 'Access denied'}), 403
    
    # Update mapping
    session['column_mapping'] = column_mapping
    
    # Optionally save as template
    if data.get('save_as_template'):
        template_name = data.get('template_name', 'default')
        client_erp_credentials_id = session.get('client_erp_credentials_id', session['client_id'])
        
        # Save mapping template
        existing = ClientCsvMapping.query.filter_by(
            client_erp_credentials_id=client_erp_credentials_id,
            mapping_name=template_name
        ).first()
        
        if existing:
            existing.column_mapping = column_mapping
            existing.is_default = data.get('is_default', False)
        else:
            # If setting as default, unset other defaults
            if data.get('is_default', False):
                existing_defaults = ClientCsvMapping.query.filter_by(
                    client_erp_credentials_id=client_erp_credentials_id,
                    is_default=True
                ).all()
                for existing_default in existing_defaults:
                    existing_default.is_default = False
            
            mapping = ClientCsvMapping(
                id=uuid.uuid4(),
                client_erp_credentials_id=client_erp_credentials_id,
                client_id=None,
                mapping_name=template_name,
                column_mapping=column_mapping,
                is_default=data.get('is_default', False)
            )
            db.session.add(mapping)
        
        db.session.commit()
    
    return jsonify({'message': 'Mapping saved'}), 200

@sales_bp.route('/mapping/templates/<client_id>', methods=['GET'])
@jwt_required()
def get_mapping_templates(client_id):
    """Get saved mapping templates for a client_erp_credentials"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client_id format'}), 400
    
    # Check access
    if not has_client_access(user_id, client_uuid):
        return jsonify({'error': 'Access denied'}), 403
    
    templates = ClientCsvMapping.query.filter_by(client_erp_credentials_id=client_uuid).all()
    
    return jsonify([{
        'id': str(t.id),
        'name': t.mapping_name,
        'is_default': t.is_default,
        'column_mapping': t.column_mapping,
        'created_at': t.created_at.isoformat() if t.created_at else None,
        'updated_at': t.updated_at.isoformat() if t.updated_at else None
    } for t in templates])

@sales_bp.route('/validate', methods=['POST'])
@jwt_required()
def validate_data():
    """Validate CSV data against Cin7 API"""
    logger = logging.getLogger(__name__)
    logger.info("=" * 50)
    logger.info("VALIDATE DATA ENDPOINT CALLED")
    logger.info("=" * 50)
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    data = request.get_json()
    if not data or 'session_id' not in data:
        return jsonify({'error': 'session_id is required'}), 400
    
    session_id = data['session_id']
    
    # Update column mapping if provided in request (allows updating without separate API call)
    if 'column_mapping' in data and data['column_mapping']:
        if session_id in upload_sessions:
            upload_sessions[session_id]['column_mapping'] = data['column_mapping']
    
    # Get session
    if session_id not in upload_sessions:
        # Log available sessions for debugging (only in development)
        import os
        if os.environ.get('FLASK_ENV') == 'development':
            available_sessions = list(upload_sessions.keys())[:5]  # First 5 for debugging
            return jsonify({
                'error': 'Session not found',
                'session_id_received': session_id,
                'available_sessions_count': len(upload_sessions),
                'available_sessions_sample': available_sessions
            }), 404
        return jsonify({'error': 'Session not found. Please re-upload your CSV file.'}), 404
    
    session = upload_sessions[session_id]
    
    # Verify user owns this session
    if session['user_id'] != user_id:
        return jsonify({'error': 'Access denied'}), 403
    
    # Get credentials from voyager.client_erp_credentials
    client_erp_credentials_id = session.get('client_erp_credentials_id', session['client_id'])
    
    # Check which customer default columns exist
    check_customer_cols_query = text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_schema = 'voyager' 
        AND table_name = 'client_erp_credentials' 
        AND column_name IN ('customer_account_receivable', 'customer_revenue_account', 'customer_tax_rule', 'customer_attribute_set')
    """)
    existing_customer_cols = {row[0] for row in db.session.execute(check_customer_cols_query).fetchall()}
    
    # Build SELECT fields
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
        return jsonify({'error': 'Cin7 credentials not configured for this client'}), 400
    
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
        # Account codes are stored as strings
        customer_account_receivable = cred_row.customer_account_receivable if cred_row.customer_account_receivable else None
    if 'customer_revenue_account' in existing_customer_cols and hasattr(cred_row, 'customer_revenue_account'):
        # Account codes are stored as strings
        customer_revenue_account = cred_row.customer_revenue_account if cred_row.customer_revenue_account else None
    if 'customer_tax_rule' in existing_customer_cols and hasattr(cred_row, 'customer_tax_rule'):
        customer_tax_rule = str(cred_row.customer_tax_rule) if cred_row.customer_tax_rule else None
    if 'customer_attribute_set' in existing_customer_cols and hasattr(cred_row, 'customer_attribute_set'):
        customer_attribute_set = cred_row.customer_attribute_set
    
    # Get settings
    settings_obj = ClientSettings.query.filter_by(client_id=session['client_id']).first()
    settings = {}
    if settings_obj:
        settings = {
            'default_status': default_status or settings_obj.default_status,
            'default_currency': settings_obj.default_currency,
            'tax_inclusive': settings_obj.tax_inclusive,
            'default_location': str(settings_obj.default_location) if settings_obj.default_location else None,
            'require_customer_reference': settings_obj.require_customer_reference,
            'require_invoice_number': settings_obj.require_invoice_number,
            'sale_type': sale_type,
            'tax_rule': tax_rule,
            'customer_account_receivable': customer_account_receivable,
            'customer_revenue_account': customer_revenue_account,
            'customer_tax_rule': customer_tax_rule,
            'customer_attribute_set': customer_attribute_set
        }
    else:
        # Use defaults from client_erp_credentials
        settings = {
            'default_status': default_status or 'DRAFT',
            'default_currency': 'USD',
            'tax_inclusive': False,
            'default_location': None,
            'require_customer_reference': False,
            'require_invoice_number': False,
            'sale_type': sale_type,
            'tax_rule': tax_rule,
            'customer_account_receivable': customer_account_receivable,
            'customer_revenue_account': customer_revenue_account,
            'customer_tax_rule': customer_tax_rule,
            'customer_attribute_set': customer_attribute_set
        }
    
    # Use the credential_id (client_erp_credentials.id) for logging, not client_id
    # This is the ID that identifies which credentials are being used
    credential_id_for_logging = client_erp_credentials_id
    
    # Get upload_id from session (should exist if upload was created)
    upload_id = session.get('upload_id')
    
    if not upload_id:
        logger.warning(f"WARNING: upload_id not found in session! Session keys: {list(session.keys())}")
        logger.warning("This may be an old session created before the fix. API calls will be logged without upload_id.")
    
    logger.info(f"DEBUG: Using credential_id {credential_id_for_logging} for API logging, upload_id: {upload_id}")
    
    # Create logging callback for validation API calls
    def log_api_call(endpoint, method, request_url, request_headers, request_body,
                     response_status, response_body, error_message, duration_ms):
        """Callback to log API calls to database"""
        try:
            # Create log entry - try with trigger first, fallback without if column doesn't exist
            try:
                log_entry = Cin7ApiLog(
                    id=uuid.uuid4(),
                    client_id=credential_id_for_logging,
                    user_id=user_id,
                    upload_id=upload_id,  # Use upload_id from session
                    order_id=None,  # Validation doesn't have specific order_id
                    trigger='validation',
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
                # If trigger column doesn't exist, try without it
                error_str = str(trigger_error).lower()
                if 'trigger' in error_str or 'column' in error_str:
                    db.session.rollback()
                    log_entry = Cin7ApiLog(
                        id=uuid.uuid4(),
                        client_id=credential_id_for_logging,
                        user_id=user_id,
                        upload_id=upload_id,  # Use upload_id from session
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
            
            logger.info(f"✓ Logged API call: {method} {endpoint} - Status: {response_status}, credential_id: {credential_id_for_logging}, user_id: {user_id}, upload_id: {upload_id}, trigger: validation")
        except Exception as e:
            logger.error(f"✗ Error logging API call: {str(e)}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
    
    # Initialize API client with logging
    logger.info(f"DEBUG: Initializing API client with logger_callback for validation")
    logger.info(f"DEBUG: credential_id_for_logging: {credential_id_for_logging}, user_id: {user_id}")
    api_client = Cin7SalesAPI(
        account_id=str(account_id),
        application_key=str(application_key),
        base_url='https://inventory.dearsystems.com/ExternalApi/v2/',
        logger_callback=log_api_call
    )
    logger.info(f"DEBUG: API client initialized, logger_callback set: {api_client.logger_callback is not None}")
    
    # Validate
    validator = SalesOrderValidator(api_client)
    column_mapping = session.get('column_mapping', {})
    
    if not column_mapping:
        return jsonify({
            'error': 'Column mapping not set in session',
            'session_keys': list(session.keys()) if session else []
        }), 400
    
    # Preload latest customers and products from Cin7
    logger.info("DEBUG: About to call preload_customers_and_products()")
    try:
        customer_count, product_count = validator.preload_customers_and_products()
        logger.info(f"Preloaded {customer_count} customers and {product_count} products for validation")
        logger.info(f"DEBUG: preload completed successfully - this should have created API logs")
    except Exception as e:
        logger.warning(f"Warning: Failed to preload customers/products: {str(e)}")
        import traceback
        traceback.print_exc()
        # Continue with validation anyway (will use API calls as fallback)
    
    # Initialize builder for preview payloads with preloaded data to avoid additional API calls
    builder = SalesOrderBuilder(
        settings, 
        api_client,
        preloaded_customers=getattr(validator, 'customer_lookup', {}),  # Pass preloaded customer lookup
        preloaded_products=getattr(validator, 'product_lookup', {})  # Pass preloaded product lookup
    )
    
    valid_rows, invalid_rows = validator.validate_batch(
        session['rows'],
        column_mapping,
        settings,
        builder=builder  # Pass builder to generate preview payloads
    )
    
    # Store validated rows
    session['validated_rows'] = {
        'valid': valid_rows,
        'invalid': invalid_rows
    }
    
    # Get counts of loaded data
    customer_count = len(validator.customer_lookup) if validator.customers_loaded else None
    product_count = len(validator.product_lookup) if validator.products_loaded else None
    
    return jsonify({
        'valid_count': len(valid_rows),
        'invalid_count': len(invalid_rows),
        'valid_rows': valid_rows,  # Return all validated rows
        'invalid_rows': invalid_rows,  # Return all invalid rows
        'customer_count': customer_count,
        'product_count': product_count
    }), 200

@sales_bp.route('/create', methods=['POST'])
@jwt_required()
def create_sales_orders():
    """Create sales orders from validated CSV data"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    data = request.get_json()
    if not data or 'session_id' not in data:
        return jsonify({'error': 'session_id is required'}), 400
    
    session_id = data['session_id']
    
    # Get session
    if session_id not in upload_sessions:
        return jsonify({'error': 'Session not found'}), 404
    
    session = upload_sessions[session_id]
    
    # Verify user owns this session
    if session['user_id'] != user_id:
        return jsonify({'error': 'Access denied'}), 403
    
    # Get credentials from voyager.client_erp_credentials
    client_erp_credentials_id = session.get('client_erp_credentials_id', session['client_id'])
    # Check which customer default columns exist
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
    
    # Build SELECT fields
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
        return jsonify({'error': 'Cin7 credentials not configured'}), 400
    
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
        # Account codes are stored as strings
        customer_account_receivable = cred_row.customer_account_receivable if cred_row.customer_account_receivable else None
    if 'customer_revenue_account' in existing_customer_cols and hasattr(cred_row, 'customer_revenue_account'):
        # Account codes are stored as strings
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
    
    # Get settings (try to find by client_id from client_erp_credentials, or use defaults)
    settings_obj = None
    # Try to get client_id from client_erp_credentials
    client_query = text("""
        SELECT client_id FROM voyager.client_erp_credentials
        WHERE id = :cred_id
    """)
    client_result = db.session.execute(client_query, {'cred_id': client_erp_credentials_id})
    client_row = client_result.fetchone()
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
        # Use defaults from client_erp_credentials
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
    
    builder = SalesOrderBuilder(settings, None)  # Will set api_client later
    column_mapping = session.get('column_mapping', {})
    
    if not column_mapping:
        return jsonify({'error': 'Column mapping not set'}), 400
    
    # Get credential_id for logging (from client_erp_credentials)
    credential_id_for_logging = client_erp_credentials_id
    
    # Get existing upload record from session (created during CSV upload)
    upload_id = session.get('upload_id')
    if not upload_id:
        return jsonify({'error': 'Upload record not found in session. Please re-upload your CSV file.'}), 400
    
    # Retrieve the existing upload record
    upload = SalesOrderUpload.query.get(upload_id)
    if not upload:
        return jsonify({'error': 'Upload record not found in database'}), 404
    
    # Update upload status to processing
    upload.status = 'processing'
    db.session.commit()
    # Emit event for real-time updates
    from routes.webhooks import emit_upload_event
    emit_upload_event('upload_status_changed', str(upload.id), str(upload.client_id) if upload.client_id else None)
    
    # Create logging callback (after upload is created)
    def log_api_call(endpoint, method, request_url, request_headers, request_body,
                     response_status, response_body, error_message, duration_ms):
        """Callback to log API calls to database"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"log_api_call invoked: {method} {endpoint}, upload_id: {upload.id}, response_status: {response_status}")
        try:
            # Create log entry - handle trigger column gracefully if it doesn't exist yet
            # Create log entry - try with trigger first, fallback without if column doesn't exist
            try:
                log_entry = Cin7ApiLog(
                    id=uuid.uuid4(),
                    client_id=credential_id_for_logging,
                    user_id=user_id,
                    upload_id=upload.id,
                    order_id=None,  # Sales.py flow doesn't create SalesOrderResult records
                    trigger='upload',
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
                logger.info(f"✓ Successfully logged API call: {method} {endpoint} - Status: {response_status}, upload_id: {upload.id}")
            except Exception as trigger_error:
                # If trigger column doesn't exist, try without it
                error_str = str(trigger_error).lower()
                if 'trigger' in error_str or 'column' in error_str:
                    db.session.rollback()
                    log_entry = Cin7ApiLog(
                        id=uuid.uuid4(),
                        client_id=credential_id_for_logging,
                        user_id=user_id,
                        upload_id=upload.id,
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
                    logger.info(f"✓ Successfully logged API call (fallback): {method} {endpoint} - Status: {response_status}, upload_id: {upload.id}")
                else:
                    raise
        except Exception as e:
            logger.error(f"✗ Error logging API call: {str(e)}", exc_info=True)
            # Don't fail the request if logging fails
            db.session.rollback()
    
    # Initialize API client and builder with logging
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Initializing API client with logger_callback for upload_id: {upload.id}")
    
    # Get logger for auto-create logic
    import logging as logger_module
    logger = logger_module.getLogger(__name__)
    api_client = Cin7SalesAPI(
        account_id=str(account_id),
        application_key=str(application_key),
        base_url='https://inventory.dearsystems.com/ExternalApi/v2/',
        logger_callback=log_api_call
    )
    logger.info(f"API client initialized - logger_callback set: {api_client.logger_callback is not None}")
    
    # Update builder with API client
    builder.api_client = api_client
    
    # Get validated rows (or validate now)
    if session.get('validated_rows'):
        valid_rows = session['validated_rows']['valid']
        logger.info(f"Using cached validated_rows: {len(valid_rows)} valid rows")
    else:
        # Validate now
        logger.info(f"Validating {len(session.get('rows', []))} rows from session")
        validator = SalesOrderValidator(api_client)
        
        # Preload latest customers and products from Cin7
        try:
            customer_count, product_count = validator.preload_customers_and_products()
            logger.info(f"Preloaded {customer_count} customers and {product_count} products for validation")
        except Exception as e:
            logger.warning(f"Warning: Failed to preload customers/products: {str(e)}")
            # Continue with validation anyway (will use API calls as fallback)
        
        valid_rows, invalid_rows = validator.validate_batch(
            session['rows'],
            column_mapping,
            settings
        )
        logger.info(f"Validation completed: {len(valid_rows)} valid rows, {len(invalid_rows)} invalid rows")
    
    if not valid_rows:
        logger.warning(f"No valid rows to process - returning error. Total rows in session: {len(session.get('rows', []))}")
        # Update upload status to failed since there are no valid rows
        upload.status = 'failed'
        upload.error_log = ['No valid rows to process - all rows failed validation']
        upload.completed_at = datetime.utcnow()
        db.session.commit()
        from routes.webhooks import emit_upload_event
        emit_upload_event('upload_status_changed', str(upload.id), str(upload.client_id) if upload.client_id else None)
        return jsonify({'error': 'No valid rows to process'}), 400
    
    # Process rows
    successful = []
    failed = []
    errors = []
    
    import time
    delay = settings.get('default_delay_between_orders', 0.7)
    
    for row_result in valid_rows:
        try:
            # Auto-create customers/products if enabled and not found (before building sale)
            auto_create_customers_products = settings.get('auto_create_customers_products', False)
            
            if auto_create_customers_products:
                # Get customer name from row
                customer_name_col = column_mapping.get('CustomerName', '')
                customer_name = None
                if customer_name_col and customer_name_col in row_result['data']:
                    customer_name = str(row_result['data'][customer_name_col]).strip() if row_result['data'][customer_name_col] else None
                
                    # Check if customer exists
                    if customer_name:
                        # Extract additional_attribute1 if available for proper cache key
                        additional_attribute1 = None
                        # Get customer code field from column_mapping (optional - if not set, will match by name only)
                        customer_code_field = column_mapping.get('_customer_code_field')
                        customer_code_value = None
                        if customer_code_field and customer_code_field in column_mapping and column_mapping[customer_code_field]:
                            attr_col = column_mapping[customer_code_field]
                            if attr_col in row_result['data'] and row_result['data'][attr_col]:
                                customer_code_value = str(row_result['data'][attr_col]).strip()
                        
                        customer_data = builder._lookup_customer_by_name(
                            customer_name, 
                            customer_code_field=customer_code_field,
                            customer_code_value=customer_code_value
                        )
                        
                        # Auto-create customer if not found
                        if not customer_data:
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
                                    attr_col = column_mapping[customer_code_field]
                                    if attr_col in row_result['data']:
                                        attr_value = row_result['data'][attr_col]
                                        if attr_value and str(attr_value).strip():
                                            customer_payload[customer_code_field] = str(attr_value).strip()
                                
                                # Create customer
                                create_success, create_message, create_response = api_client.create_customer(customer_payload)
                                
                                if create_success and create_response:
                                    customer_id = create_response.get('ID')
                                    if customer_id:
                                        try:
                                            customer_id_uuid = uuid.UUID(str(customer_id))
                                            # Refresh customer cache in database
                                            refresh_single_customer_cache(client_erp_credentials_id, customer_id_uuid, create_response, is_new=True)
                                            logger.info(f"Successfully auto-created customer '{customer_name}' with ID {customer_id}")
                                            
                                            # Small delay to ensure database cache is updated
                                            time.sleep(0.1)
                                            
                                            # Update builder's preloaded_customers so it can be found immediately
                                            customer_name_clean = customer_name.strip()
                                            builder.preloaded_customers[customer_name_clean] = create_response
                                            builder.preloaded_customers[customer_name_clean.upper()] = create_response
                                            builder.preloaded_customers[customer_name_clean.lower()] = create_response
                                            # Clear ALL cache entries for this customer name (to handle any additional_attribute1 variations)
                                            cache_keys_to_remove = [key for key in builder._customer_cache.keys() if key.startswith(f"{customer_name_clean}|")]
                                            for key in cache_keys_to_remove:
                                                del builder._customer_cache[key]
                                            # Update cache with the new customer (with and without additional_attribute1)
                                            cache_key_with_attr = f"{customer_name_clean}|{additional_attribute1}"
                                            cache_key_no_attr = f"{customer_name_clean}|None"
                                            builder._customer_cache[cache_key_with_attr] = create_response
                                            builder._customer_cache[cache_key_no_attr] = create_response
                                            
                                            # Force refresh from database cache to ensure consistency
                                            db.session.commit()  # Ensure cache write is committed
                                            from database import CachedCustomer
                                            cached_customer = CachedCustomer.query.filter_by(
                                                client_erp_credentials_id=client_erp_credentials_id,
                                                cin7_id=customer_id_uuid
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
                                        except (ValueError, AttributeError):
                                            logger.error(f"Invalid customer ID format: {customer_id}")
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
                                                        refresh_single_customer_cache(client_erp_credentials_id, customer_id_uuid, existing_customer, is_new=False)
                                                        logger.info(f"Found existing customer '{customer_name}' with ID {customer_id}")
                                                        # Update builder's preloaded_customers so it can be found immediately
                                                        customer_name_clean = customer_name.strip()
                                                        builder.preloaded_customers[customer_name_clean] = existing_customer
                                                        builder.preloaded_customers[customer_name_clean.upper()] = existing_customer
                                                        builder.preloaded_customers[customer_name_clean.lower()] = existing_customer
                                                        # Clear ALL cache entries for this customer name (to handle any additional_attribute1 variations)
                                                        cache_keys_to_remove = [key for key in builder._customer_cache.keys() if key.startswith(f"{customer_name_clean}|")]
                                                        for key in cache_keys_to_remove:
                                                            del builder._customer_cache[key]
                                                        # Update cache with the existing customer (with and without additional_attribute1)
                                                        cache_key_with_attr = f"{customer_name_clean}|{additional_attribute1}"
                                                        cache_key_no_attr = f"{customer_name_clean}|None"
                                                        builder._customer_cache[cache_key_with_attr] = existing_customer
                                                        builder._customer_cache[cache_key_no_attr] = existing_customer
                                                    except (ValueError, AttributeError):
                                                        logger.error(f"Invalid customer ID format: {customer_id}")
                                            else:
                                                logger.warning(f"Customer '{customer_name}' reported as existing but not found in search")
                                        except Exception as e:
                                            logger.error(f"Error looking up existing customer '{customer_name}': {str(e)}", exc_info=True)
                                    else:
                                        logger.error(f"Failed to auto-create customer '{customer_name}': {create_message}")
                            except Exception as e:
                                logger.error(f"Error auto-creating customer '{customer_name}': {str(e)}", exc_info=True)
                
                # Check and auto-create products
                # Get rows to check (could be a single row or grouped rows)
                # Note: group_rows is already a list of data dictionaries (not wrapped in {'data': ...})
                rows_to_check = [row_result['data']]
                if 'group_rows' in row_result and row_result['group_rows']:
                    rows_to_check = row_result['group_rows']  # Already list of data dicts
                
                # Track auto-created product IDs to refresh from database
                auto_created_product_ids = []
                
                sku_col = column_mapping.get('SKU') or column_mapping.get('ProductCode')
                if sku_col:
                    for row_data in rows_to_check:
                        sku = row_data.get(sku_col, '')
                        if sku:
                            sku = str(sku).strip()
                            if sku:
                                # Check if product exists
                                product = builder._lookup_product_by_sku(sku)
                                
                                # Auto-create product if not found
                                if not product:
                                    logger.info(f"Auto-creating product with SKU '{sku}' (auto_create_customers_products enabled)")
                                    try:
                                        # Get product name from CSV or use SKU
                                        product_name_col = column_mapping.get('ProductName') or column_mapping.get('Name')
                                        product_name = None
                                        if product_name_col and product_name_col in row_data:
                                            product_name = str(row_data[product_name_col]).strip() if row_data[product_name_col] else None
                                        
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
                                            product_id = create_response.get('ID')
                                            if product_id:
                                                try:
                                                    product_id_uuid = uuid.UUID(str(product_id))
                                                    # Refresh product cache in database
                                                    refresh_single_product_cache(client_erp_credentials_id, product_id_uuid, sku, create_response, is_new=True)
                                                    logger.info(f"Successfully auto-created product SKU '{sku}' with ID {product_id}")
                                                    
                                                    # Small delay to ensure database cache is updated
                                                    time.sleep(0.1)
                                                    
                                                    # Update builder's preloaded_products so it can be found immediately
                                                    sku_clean = sku.strip()
                                                    builder.preloaded_products[sku_clean] = create_response
                                                    builder.preloaded_products[sku_clean.upper()] = create_response
                                                    builder.preloaded_products[sku_clean.lower()] = create_response
                                                    # Clear any cached None entries and update cache with the new product
                                                    if sku_clean in builder._product_cache:
                                                        del builder._product_cache[sku_clean]
                                                    if sku in builder._product_cache:
                                                        del builder._product_cache[sku]
                                                    builder._product_cache[sku_clean] = create_response
                                                    
                                                    # Force commit to ensure cache is persisted
                                                    db.session.commit()
                                                    
                                                    # Track product ID for cache refresh
                                                    auto_created_product_ids.append(product_id_uuid)
                                                except (ValueError, AttributeError):
                                                    logger.error(f"Invalid product ID format: {product_id}")
                                        else:
                                            # Check if product already exists (409 error)
                                            if '409' in str(create_message) or 'already exists' in str(create_message).lower():
                                                logger.info(f"Product SKU '{sku}' already exists (409), attempting to look it up")
                                                # Try to look up the existing product using API search
                                                try:
                                                    products = api_client.search_product(sku=sku)
                                                    if products and len(products) > 0:
                                                        existing_product = products[0]
                                                        product_id = existing_product.get('ID')
                                                        if product_id:
                                                            try:
                                                                product_id_uuid = uuid.UUID(str(product_id))
                                                                # Refresh product cache with existing product
                                                                refresh_single_product_cache(client_erp_credentials_id, product_id_uuid, sku, existing_product, is_new=False)
                                                                logger.info(f"Found existing product SKU '{sku}' with ID {product_id}")
                                                                
                                                                # Small delay
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
                                                            except (ValueError, AttributeError):
                                                                logger.error(f"Invalid product ID format: {product_id}")
                                                    else:
                                                        logger.warning(f"Product SKU '{sku}' reported as existing but not found in search")
                                                except Exception as e:
                                                    logger.error(f"Error looking up existing product SKU '{sku}': {str(e)}", exc_info=True)
                                            else:
                                                logger.error(f"Failed to auto-create product SKU '{sku}': {create_message}")
                                    except Exception as e:
                                        logger.error(f"Error auto-creating product SKU '{sku}': {str(e)}", exc_info=True)
            
            # After all auto-creates, refresh product cache from database using product IDs to ensure all newly created products are available
            if auto_create_customers_products and auto_created_product_ids:
                try:
                    from database import CachedProduct
                    db.session.commit()  # Ensure all cache writes are committed
                    # Refresh builder's product cache from database using product IDs
                    for product_id_uuid in auto_created_product_ids:
                        cached_product = CachedProduct.query.filter_by(
                            client_erp_credentials_id=client_erp_credentials_id,
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
            
            # Step 1: Build and create Sale
            sale_data = builder.build_sale(row_result['data'], column_mapping)
            
            # Get customer data for passing to build_sale_order (needed for TaxRule lookup)
            customer_name_col = column_mapping.get('CustomerName', '')
            customer_data_for_sale_order = None
            if customer_name_col and customer_name_col in row_result['data']:
                customer_name = str(row_result['data'][customer_name_col]).strip() if row_result['data'][customer_name_col] else None
                if customer_name:
                    additional_attribute1 = None
                    # Get customer code field from column_mapping (optional - if not set, will match by name only)
                    customer_code_field = column_mapping.get('_customer_code_field')
                    customer_code_value = None
                    if customer_code_field and customer_code_field in column_mapping and column_mapping[customer_code_field]:
                        attr_col = column_mapping[customer_code_field]
                        if attr_col in row_result['data'] and row_result['data'][attr_col]:
                            customer_code_value = str(row_result['data'][attr_col]).strip()
                    customer_data_for_sale_order = builder._lookup_customer_by_name(
                        customer_name, 
                        customer_code_field=customer_code_field,
                        customer_code_value=customer_code_value
                    )
            
            # Create Sale via API
            success, message, response = api_client.create_sale(sale_data)
            
            if not success:
                failed.append({
                    'row_number': row_result['row_number'],
                    'error': f'Failed to create Sale: {message}'
                })
                errors.append({
                    'row': row_result['row_number'],
                    'error': f'Failed to create Sale: {message}'
                })
                # Rate limiting delay even on failure
                time.sleep(delay)
                continue
            
            # Extract Sale ID from response
            sale_id = None
            sale_data_from_response = None
            if isinstance(response, dict):
                sale_id = response.get('ID')
                sale_data_from_response = response
            elif isinstance(response, list) and len(response) > 0:
                sale_id = response[0].get('ID') if isinstance(response[0], dict) else None
                sale_data_from_response = response[0] if isinstance(response[0], dict) else None
            
            if not sale_id:
                failed.append({
                    'row_number': row_result['row_number'],
                    'error': 'Sale created but no ID returned'
                })
                errors.append({
                    'row': row_result['row_number'],
                    'error': 'Sale created but no ID returned'
                })
                time.sleep(delay)
                continue
            
            # Rate limiting delay between Sale and Sale Order
            time.sleep(delay)
            
            # Step 2: Build and create Sale Order
            # Check if this is a grouped order (multiple rows)
            if 'group_rows' in row_result and row_result['group_rows']:
                # Use grouped rows to build sale order with all line items
                sale_order_data = builder.build_sale_order_from_rows(row_result['group_rows'], column_mapping, sale_id, customer_data=customer_data_for_sale_order, sale_data=sale_data_from_response)
            else:
                # Single row order
                sale_order_data = builder.build_sale_order(row_result['data'], column_mapping, sale_id, customer_data=customer_data_for_sale_order, sale_data=sale_data_from_response)
            
            # Create Sale Order via API
            so_success, so_message, so_response = api_client.create_sale_order(sale_order_data)
            
            if so_success:
                successful.append({
                    'row_number': row_result['row_number'],
                    'sale_id': sale_id,
                    'sale_order_id': so_response.get('ID') if isinstance(so_response, dict) else None
                })
            else:
                # Sale was created but Sale Order failed
                failed.append({
                    'row_number': row_result['row_number'],
                    'error': f'Sale created (ID: {sale_id}) but Sale Order failed: {so_message}'
                })
                errors.append({
                    'row': row_result['row_number'],
                    'error': f'Sale created (ID: {sale_id}) but Sale Order failed: {so_message}'
                })
            
            # Rate limiting delay
            time.sleep(delay)
            
        except Exception as e:
            failed.append({
                'row_number': row_result['row_number'],
                'error': str(e)
            })
            errors.append({
                'row': row_result['row_number'],
                'error': str(e)
            })
    
    # Update upload record
    logger.info(f"Processing complete: {len(successful)} successful, {len(failed)} failed orders")
    upload.successful_orders = len(successful)
    upload.failed_orders = len(failed)
    upload.status = 'completed'
    upload.completed_at = datetime.utcnow()
    upload.error_log = errors
    db.session.commit()
    
    return jsonify({
        'upload_id': str(upload.id),
        'successful': len(successful),
        'failed': len(failed),
        'successful_rows': successful[:10],  # Preview
        'failed_rows': failed[:10]  # Preview
    }), 200

@sales_bp.route('/history', methods=['GET'])
@jwt_required()
def get_upload_history():
    """Get upload history for a client"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    client_id = request.args.get('client_id')
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client_id format'}), 400
    
    # Check access
    if not has_client_access(user_id, client_uuid):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get uploads - can be by client_id or we need to check client_erp_credentials_id
    # For now, query by client_id (which may be None for standalone)
    uploads = SalesOrderUpload.query.filter_by(client_id=client_uuid).order_by(
        SalesOrderUpload.created_at.desc()
    ).limit(50).all()
    
    # If no results and this might be a client_erp_credentials_id, we'd need to join
    # For now, just return what we have
    
    return jsonify([{
        'id': str(u.id),
        'filename': u.filename,
        'total_rows': u.total_rows,
        'successful_orders': u.successful_orders,
        'failed_orders': u.failed_orders,
        'status': u.status,
        'created_at': u.created_at.isoformat() if u.created_at else None,
        'completed_at': u.completed_at.isoformat() if u.completed_at else None
    } for u in uploads])

@sales_bp.route('/cached-customers', methods=['GET'])
@jwt_required()
def get_cached_customers():
    """Get cached customers for a client"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    client_id = request.args.get('client_id')
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client_id format'}), 400
    
    # Check access
    if not has_client_access(user_id, client_uuid):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get cached customers from database
    from database import CachedCustomer
    search_query = request.args.get('search', '').strip().lower()
    filter_new = request.args.get('filter', '').strip().lower() == 'new'
    
    query = CachedCustomer.query.filter_by(
        client_erp_credentials_id=client_uuid
    )
    
    if filter_new:
        query = query.filter_by(is_new=True)
    
    cached_customers = query.all()
    
    customers = []
    # Use the known API response order (from backend logs, this is the actual order)
    # This is the order we captured when storing, so we should use it when retrieving
    api_customer_key_order = [
        'ID', 'Name', 'DisplayName', 'Currency', 'PaymentTerm', 'Discount', 'TaxRule', 'Carrier',
        'SalesRepresentative', 'Location', 'Comments', 'AccountReceivable', 'RevenueAccount', 'PriceTier',
        'TaxNumber', 'AdditionalAttribute1', 'AdditionalAttribute2', 'AdditionalAttribute3', 'AdditionalAttribute4',
        'AdditionalAttribute5', 'AdditionalAttribute6', 'AdditionalAttribute7', 'AdditionalAttribute8',
        'AdditionalAttribute9', 'AdditionalAttribute10', 'AttributeSet', 'Tags', 'Status', 'CreditLimit',
        'IsOnCreditHold', 'LastModifiedOn', 'Addresses', 'Contacts', 'ProductPrices'
    ]
    
    for cached in cached_customers:
        customer_data = cached.customer_data
        if customer_data:
            # Apply search filter if provided
            if search_query:
                # Search in common fields
                searchable_text = ' '.join([
                    str(customer_data.get('Name', '')),
                    str(customer_data.get('Email', '')),
                    str(customer_data.get('Phone', '')),
                    str(customer_data.get('ID', ''))
                ]).lower()
                if search_query not in searchable_text:
                    continue
            
            # Reorder customer_data to match API response order
            if isinstance(customer_data, dict):
                ordered_customer = OrderedDict()
                # Add keys in API response order
                for key in api_customer_key_order:
                    if key in customer_data:
                        ordered_customer[key] = customer_data[key]
                # Add any additional keys that weren't in the standard order (preserve their relative order)
                seen_keys = set(api_customer_key_order)
                for key, value in customer_data.items():
                    if key not in seen_keys:
                        ordered_customer[key] = value
                        seen_keys.add(key)
                customer_dict = dict(ordered_customer)  # Convert to dict (preserves order in Python 3.7+)
                # Add metadata fields
                customer_dict['_is_new'] = cached.is_new
                customer_dict['_created_via_auto_create'] = cached.created_via_auto_create
                customer_dict['_cache_id'] = str(cached.id)
                customers.append(customer_dict)
            else:
                # If not a dict, wrap it and add metadata
                customer_dict = customer_data if isinstance(customer_data, dict) else {'data': customer_data}
                customer_dict['_is_new'] = cached.is_new
                customer_dict['_created_via_auto_create'] = cached.created_via_auto_create
                customer_dict['_cache_id'] = str(cached.id)
                customers.append(customer_dict)
    
    # Get last updated timestamp
    last_updated = None
    if cached_customers:
        last_updated = max(c.cached_at for c in cached_customers if c.cached_at)
    
    return jsonify({
        'customers': customers,
        'last_updated': last_updated.isoformat() if last_updated else None
    }), 200

@sales_bp.route('/cached-products', methods=['GET'])
@jwt_required()
def get_cached_products():
    """Get cached products for a client"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    client_id = request.args.get('client_id')
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client_id format'}), 400
    
    # Check access
    if not has_client_access(user_id, client_uuid):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get cached products from database
    from database import CachedProduct
    search_query = request.args.get('search', '').strip().lower()
    filter_new = request.args.get('filter', '').strip().lower() == 'new'
    
    query = CachedProduct.query.filter_by(
        client_erp_credentials_id=client_uuid
    )
    
    if filter_new:
        query = query.filter_by(is_new=True)
    
    # First check count
    product_count = query.count()
    current_app.logger.info(f"Query found {product_count} cached products for client {client_uuid}")
    
    cached_products = query.all()
    
    current_app.logger.info(f"Retrieved {len(cached_products)} cached product records for client {client_uuid}")
    
    products = []
    # Use the known API response order (from backend logs, this is the actual order)
    # This is the order we captured when storing, so we should use it when retrieving
    api_product_key_order = [
        'ID', 'SKU', 'Name', 'Category', 'Brand', 'Type', 'CostingMethod', 'DropShipMode', 'DefaultLocation',
        'Length', 'Width', 'Height', 'Weight', 'UOM', 'WeightUnits', 'DimensionsUnits', 'Barcode',
        'MinimumBeforeReorder', 'ReorderQuantity', 'PriceTier1', 'PriceTier2', 'PriceTier3', 'PriceTier4',
        'PriceTier5', 'PriceTier6', 'PriceTier7', 'PriceTier8', 'PriceTier9', 'PriceTier10', 'PriceTiers',
        'AverageCost', 'ShortDescription', 'InternalNote', 'Description', 'AdditionalAttribute1',
        'AdditionalAttribute2', 'AdditionalAttribute3', 'AdditionalAttribute4', 'AdditionalAttribute5',
        'AdditionalAttribute6', 'AdditionalAttribute7', 'AdditionalAttribute8', 'AdditionalAttribute9',
        'AdditionalAttribute10', 'AttributeSet', 'DiscountRule', 'Tags', 'Status', 'StockLocator',
        'COGSAccount', 'RevenueAccount', 'ExpenseAccount', 'InventoryAccount', 'PurchaseTaxRule',
        'SaleTaxRule', 'LastModifiedOn', 'Sellable', 'PickZones', 'BillOfMaterial', 'AutoAssembly',
        'AutoDisassembly', 'QuantityToProduce', 'AlwaysShowQuantity', 'AssemblyInstructionURL',
        'AssemblyCostEstimationMethod', 'Suppliers', 'ReorderLevels', 'BillOfMaterialsProducts',
        'BillOfMaterialsServices', 'Movements', 'Attachments', 'BOMType', 'WarrantyName', 'CustomPrices',
        'CartonHeight', 'CartonWidth', 'CartonLength', 'CartonQuantity', 'CartonInnerQuantity', 'HSCode',
        'CountryOfOrigin', 'CountryOfOriginCode', 'CreatedDate'
    ]
    
    for cached in cached_products:
        product_data = cached.product_data
        if product_data:
            # Apply search filter if provided
            if search_query:
                # Search in common fields
                searchable_text = ' '.join([
                    str(product_data.get('Name', '')),
                    str(product_data.get('SKU', '')),
                    str(product_data.get('Barcode', '')),
                    str(product_data.get('ID', ''))
                ]).lower()
                if search_query not in searchable_text:
                    continue
            
            # Reorder product_data to match API response order
            if isinstance(product_data, dict):
                ordered_product = OrderedDict()
                # Add keys in API response order
                for key in api_product_key_order:
                    if key in product_data:
                        ordered_product[key] = product_data[key]
                # Add any additional keys that weren't in the standard order (preserve their relative order)
                seen_keys = set(api_product_key_order)
                for key, value in product_data.items():
                    if key not in seen_keys:
                        ordered_product[key] = value
                        seen_keys.add(key)
                product_dict = dict(ordered_product)  # Convert to dict (preserves order in Python 3.7+)
                # Add metadata fields
                product_dict['_is_new'] = cached.is_new
                product_dict['_created_via_auto_create'] = cached.created_via_auto_create
                product_dict['_cache_id'] = str(cached.id)
                products.append(product_dict)
            else:
                # If not a dict, wrap it and add metadata
                product_dict = product_data if isinstance(product_data, dict) else {'data': product_data}
                product_dict['_is_new'] = cached.is_new
                product_dict['_created_via_auto_create'] = cached.created_via_auto_create
                product_dict['_cache_id'] = str(cached.id)
                products.append(product_dict)
        else:
            current_app.logger.warning(f"Cached product {cached.id} has no product_data")
    
    # Get last updated timestamp
    last_updated = None
    if cached_products:
        last_updated = max(p.cached_at for p in cached_products if p.cached_at)
    
    return jsonify({
        'products': products,
        'last_updated': last_updated.isoformat() if last_updated else None
    }), 200

@sales_bp.route('/refresh-cache', methods=['POST'])
@jwt_required()
def refresh_cache():
    """Refresh customer and product cache from Cin7 API"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    data = request.get_json()
    if not data or 'client_id' not in data:
        return jsonify({'error': 'client_id is required'}), 400
    
    try:
        client_uuid = uuid.UUID(data['client_id'])
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client_id format'}), 400
    
    # Check access
    if not has_client_access(user_id, client_uuid):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get credentials
    query = text("""
        SELECT 
            cec.id,
            cec.cin7_api_auth_accountid as account_id,
            cec.cin7_api_auth_applicationkey as application_key
        FROM voyager.client_erp_credentials cec
        WHERE cec.erp = 'cin7_core'
        AND cec.id = :cred_id
    """)
    result = db.session.execute(query, {'cred_id': client_uuid})
    cred_row = result.fetchone()
    
    if not cred_row or not cred_row.account_id or not cred_row.application_key:
        return jsonify({'error': 'Cin7 credentials not configured for this client'}), 400
    
    # Initialize API client
    api_client = Cin7SalesAPI(
        account_id=str(cred_row.account_id),
        application_key=str(cred_row.application_key),
        base_url='https://inventory.dearsystems.com/ExternalApi/v2/'
    )
    
    # Load customers and products from API
    from database import CachedCustomer, CachedProduct
    
    customer_count = 0
    product_count = 0
    
    try:
        # Get all customers
        customers_response = api_client.get_all_customers()
        if customers_response and isinstance(customers_response, list):
            # Track which customer IDs we've seen for deletion of stale records
            seen_customer_ids = set()
            
            # Capture key order from first customer (API response order)
            first_customer_order = None
            if customers_response and len(customers_response) > 0:
                first_customer = customers_response[0]
                if isinstance(first_customer, dict):
                    first_customer_order = list(first_customer.keys())
                    current_app.logger.info(f"First customer key order (first 20): {first_customer_order[:20]}")
                    current_app.logger.info(f"First customer key order (all {len(first_customer_order)}): {first_customer_order}")
            
            # Upsert customers (update existing or insert new)
            for customer in customers_response:
                if customer.get('ID'):
                    customer_id = uuid.UUID(str(customer['ID']))
                    seen_customer_ids.add(customer_id)
                    
                    # Reorder customer dict to match API response order if we have it
                    if first_customer_order and isinstance(customer, dict):
                        ordered_customer = OrderedDict()
                        # Add keys in original API order
                        for key in first_customer_order:
                            if key in customer:
                                ordered_customer[key] = customer[key]
                        # Add any additional keys that weren't in first customer
                        for key, value in customer.items():
                            if key not in ordered_customer:
                                ordered_customer[key] = value
                        customer = dict(ordered_customer)  # Convert back to regular dict (preserves order in Python 3.7+)
                    
                    # Check if customer already exists
                    existing = CachedCustomer.query.filter_by(
                        client_erp_credentials_id=client_uuid,
                        cin7_customer_id=customer_id
                    ).first()
                    
                    if existing:
                        # Update existing record - preserve is_new flag if it was set
                        existing.customer_data = customer
                        existing.updated_at = datetime.utcnow()
                        # cached_at stays the same (when it was first cached)
                        # Don't modify is_new or created_via_auto_create on refresh
                    else:
                        # Insert new record
                        cached = CachedCustomer(
                            id=uuid.uuid4(),
                            client_erp_credentials_id=client_uuid,
                            cin7_customer_id=customer_id,
                            customer_data=customer,
                            is_new=False,  # Regular refresh, not auto-created
                            created_via_auto_create=False
                        )
                        db.session.add(cached)
                    customer_count += 1
            
            # Delete customers that are no longer in Cin7 (exist in cache but not in API response)
            if seen_customer_ids:
                deleted_count = CachedCustomer.query.filter(
                    CachedCustomer.client_erp_credentials_id == client_uuid,
                    ~CachedCustomer.cin7_customer_id.in_(seen_customer_ids)
                ).delete(synchronize_session=False)
                current_app.logger.info(f"Deleted {deleted_count} stale cached customers for client {client_uuid}")
            else:
                # If no customers were seen, delete all (API returned empty)
                deleted_count = CachedCustomer.query.filter_by(client_erp_credentials_id=client_uuid).delete()
                current_app.logger.info(f"Deleted {deleted_count} cached customers (API returned no customers)")
            
            db.session.commit()
            current_app.logger.info(f"Successfully cached {customer_count} customers for client {client_uuid}")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error refreshing customers: {str(e)}")
    
    try:
        # Get all products
        current_app.logger.info(f"Starting product refresh for client {client_uuid}")
        products_response = api_client.get_all_products()
        current_app.logger.info(f"Received {len(products_response) if products_response else 0} products from API")
        
        if products_response and isinstance(products_response, list):
            # Track which product IDs we've seen for deletion of stale records
            seen_product_ids = set()
            
            # Capture key order from first product (API response order)
            first_product_order = None
            if products_response and len(products_response) > 0:
                first_product = products_response[0]
                if isinstance(first_product, dict):
                    first_product_order = list(first_product.keys())
                    current_app.logger.info(f"First product key order (first 20): {first_product_order[:20]}")
                    current_app.logger.info(f"First product key order (all {len(first_product_order)}): {first_product_order}")
            
            # Upsert products (update existing or insert new)
            for product in products_response:
                if product.get('ID'):
                    product_id = uuid.UUID(str(product['ID']))
                    seen_product_ids.add(product_id)
                    
                    # Extract SKU from product data, use empty string if not present
                    sku = product.get('SKU') or ''
                    if not sku:
                        current_app.logger.warning(f"Product {product_id} has no SKU, using empty string")
                    
                    # Reorder product dict to match API response order if we have it
                    if first_product_order and isinstance(product, dict):
                        ordered_product = OrderedDict()
                        # Add keys in original API order
                        for key in first_product_order:
                            if key in product:
                                ordered_product[key] = product[key]
                        # Add any additional keys that weren't in first product
                        for key, value in product.items():
                            if key not in ordered_product:
                                ordered_product[key] = value
                        product = dict(ordered_product)  # Convert back to regular dict (preserves order in Python 3.7+)
                    
                    # Use PostgreSQL ON CONFLICT for efficient upsert
                    # Check if product already exists
                    existing = CachedProduct.query.filter_by(
                        client_erp_credentials_id=client_uuid,
                        cin7_product_id=product_id
                    ).first()
                    
                    if existing:
                        # Update existing record - preserve is_new flag if it was set
                        existing.sku = sku
                        existing.product_data = product
                        existing.updated_at = datetime.utcnow()
                        # cached_at stays the same (when it was first cached)
                        # Don't modify is_new or created_via_auto_create on refresh
                    else:
                        # Insert new record
                        cached = CachedProduct(
                            id=uuid.uuid4(),
                            client_erp_credentials_id=client_uuid,
                            cin7_product_id=product_id,
                            sku=sku,
                            product_data=product,
                            is_new=False,  # Regular refresh, not auto-created
                            created_via_auto_create=False
                        )
                        db.session.add(cached)
                    product_count += 1
            
            # Delete products that are no longer in Cin7 (exist in cache but not in API response)
            if seen_product_ids:
                deleted_count = CachedProduct.query.filter(
                    CachedProduct.client_erp_credentials_id == client_uuid,
                    ~CachedProduct.cin7_product_id.in_(seen_product_ids)
                ).delete(synchronize_session=False)
                current_app.logger.info(f"Deleted {deleted_count} stale cached products for client {client_uuid}")
            else:
                # If no products were seen, delete all (API returned empty)
                deleted_count = CachedProduct.query.filter_by(client_erp_credentials_id=client_uuid).delete()
                current_app.logger.info(f"Deleted {deleted_count} cached products (API returned no products)")
            
            db.session.commit()
            current_app.logger.info(f"Successfully cached {product_count} products for client {client_uuid}")
            
            # Verify they were saved
            verify_count = CachedProduct.query.filter_by(client_erp_credentials_id=client_uuid).count()
            current_app.logger.info(f"Verification: Found {verify_count} products in database after commit for client {client_uuid}")
        else:
            current_app.logger.warning(f"Products response was not a list or was empty: {type(products_response)}")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error refreshing products: {str(e)}", exc_info=True)
    
    return jsonify({
        'customer_count': customer_count,
        'product_count': product_count
    }), 200


def refresh_single_customer_cache(client_erp_credentials_id: uuid.UUID, customer_id: uuid.UUID, customer_data: dict, is_new: bool = False):
    """
    Refresh cache for a single customer (used after auto-creation).
    
    Args:
        client_erp_credentials_id: Credential ID
        customer_id: Cin7 customer ID
        customer_data: Customer data from Cin7 API
        is_new: Whether to mark as new (for auto-created customers)
    """
    try:
        existing = CachedCustomer.query.filter_by(
            client_erp_credentials_id=client_erp_credentials_id,
            cin7_customer_id=customer_id
        ).first()
        
        if existing:
            # Update existing record - preserve is_new flag if it was set
            existing.customer_data = customer_data
            existing.updated_at = datetime.utcnow()
            if is_new:
                existing.is_new = True
                existing.created_via_auto_create = True
            # If is_new=False, preserve existing flag values (don't modify them)
        else:
            # Insert new record
            cached = CachedCustomer(
                id=uuid.uuid4(),
                client_erp_credentials_id=client_erp_credentials_id,
                cin7_customer_id=customer_id,
                customer_data=customer_data,
                is_new=is_new,
                created_via_auto_create=is_new
            )
            db.session.add(cached)
        
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error refreshing single customer cache: {str(e)}", exc_info=True)
        raise


@sales_bp.route('/cached-customers/new-count', methods=['GET'])
@jwt_required()
def get_new_customers_count():
    """Get count of new customers for a client"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    client_id = request.args.get('client_id')
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client_id format'}), 400
    
    # Check access
    if not has_client_access(user_id, client_uuid):
        return jsonify({'error': 'Access denied'}), 403
    
    # Count new customers
    from database import CachedCustomer
    count = CachedCustomer.query.filter_by(
        client_erp_credentials_id=client_uuid,
        is_new=True
    ).count()
    
    return jsonify({'count': count}), 200


@sales_bp.route('/cached-products/new-count', methods=['GET'])
@jwt_required()
def get_new_products_count():
    """Get count of new products for a client"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    client_id = request.args.get('client_id')
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400
    
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client_id format'}), 400
    
    # Check access
    if not has_client_access(user_id, client_uuid):
        return jsonify({'error': 'Access denied'}), 403
    
    # Count new products
    from database import CachedProduct
    count = CachedProduct.query.filter_by(
        client_erp_credentials_id=client_uuid,
        is_new=True
    ).count()
    
    return jsonify({'count': count}), 200


@sales_bp.route('/cached-customers/<customer_id>/review', methods=['POST'])
@jwt_required()
def mark_customer_reviewed(customer_id):
    """Mark a customer as reviewed (clear is_new flag)"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    try:
        customer_uuid = uuid.UUID(customer_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid customer_id format'}), 400
    
    # Get customer and check access
    from database import CachedCustomer
    customer = CachedCustomer.query.get(customer_uuid)
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404
    
    # Check access to the client
    if not has_client_access(user_id, customer.client_erp_credentials_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Mark as reviewed
    customer.is_new = False
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Customer marked as reviewed'}), 200


@sales_bp.route('/cached-products/<product_id>/review', methods=['POST'])
@jwt_required()
def mark_product_reviewed(product_id):
    """Mark a product as reviewed (clear is_new flag)"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    try:
        product_uuid = uuid.UUID(product_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid product_id format'}), 400
    
    # Get product and check access
    from database import CachedProduct
    product = CachedProduct.query.get(product_uuid)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    # Check access to the client
    if not has_client_access(user_id, product.client_erp_credentials_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Mark as reviewed
    product.is_new = False
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Product marked as reviewed'}), 200


def refresh_single_product_cache(client_erp_credentials_id: uuid.UUID, product_id: uuid.UUID, sku: str, product_data: dict, is_new: bool = False):
    """
    Refresh cache for a single product (used after auto-creation).
    
    Args:
        client_erp_credentials_id: Credential ID
        product_id: Cin7 product ID
        sku: Product SKU
        product_data: Product data from Cin7 API
        is_new: Whether to mark as new (for auto-created products)
    """
    # #region agent log
    debug_log("debug-product-flags", "run1", "H1", "routes/sales.py:refresh_single_product_cache", 
              "refresh_single_product_cache entry", {"sku": sku, "product_id": str(product_id), "is_new": is_new})
    # #endregion
    
    try:
        existing = CachedProduct.query.filter_by(
            client_erp_credentials_id=client_erp_credentials_id,
            cin7_product_id=product_id
        ).first()
        
        # #region agent log
        debug_log("debug-product-flags", "run1", "H1", "routes/sales.py:refresh_single_product_cache",
                  "Product lookup result", {
                      "sku": sku,
                      "product_id": str(product_id),
                      "existing_found": existing is not None,
                      "existing_is_new": existing.is_new if existing else None,
                      "existing_created_via_auto_create": existing.created_via_auto_create if existing else None
                  })
        # #endregion
        
        if existing:
            # Update existing record
            # #region agent log
            debug_log("debug-product-flags", "run1", "H1", "routes/sales.py:refresh_single_product_cache",
                      "Updating existing product record", {
                          "sku": sku,
                          "product_id": str(product_id),
                          "is_new": is_new,
                          "before_is_new": existing.is_new,
                          "before_created_via_auto_create": existing.created_via_auto_create
                      })
            # #endregion
            
            existing.sku = sku
            existing.product_data = product_data
            existing.updated_at = datetime.utcnow()
            if is_new:
                existing.is_new = True
                existing.created_via_auto_create = True
                current_app.logger.info(f"Updated existing product cache for SKU '{sku}' (ID: {product_id}) - set is_new=True, created_via_auto_create=True")
                # #region agent log
                debug_log("debug-product-flags", "run1", "H1", "routes/sales.py:refresh_single_product_cache",
                          "Set flags on existing record", {
                              "sku": sku,
                              "product_id": str(product_id),
                              "after_is_new": existing.is_new,
                              "after_created_via_auto_create": existing.created_via_auto_create
                          })
                # #endregion
            else:
                # Preserve existing is_new and created_via_auto_create flags when is_new=False
                # Don't modify them - they should remain as they were
                current_app.logger.debug(f"Updated existing product cache for SKU '{sku}' (ID: {product_id}) - flags preserved (is_new={existing.is_new}, created_via_auto_create={existing.created_via_auto_create})")
                # #region agent log
                debug_log("debug-product-flags", "run1", "H1", "routes/sales.py:refresh_single_product_cache",
                          "Flags preserved (is_new=False)", {
                              "sku": sku,
                              "product_id": str(product_id),
                              "preserved_is_new": existing.is_new,
                              "preserved_created_via_auto_create": existing.created_via_auto_create
                          })
                # #endregion
        else:
            # Insert new record
            # #region agent log
            debug_log("debug-product-flags", "run1", "H1", "routes/sales.py:refresh_single_product_cache",
                      "Creating new product record", {"sku": sku, "product_id": str(product_id), "is_new": is_new})
            # #endregion
            
            cached = CachedProduct(
                id=uuid.uuid4(),
                client_erp_credentials_id=client_erp_credentials_id,
                cin7_product_id=product_id,
                sku=sku,
                product_data=product_data,
                is_new=is_new,
                created_via_auto_create=is_new
            )
            db.session.add(cached)
            if is_new:
                current_app.logger.info(f"Created new product cache for SKU '{sku}' (ID: {product_id}) - set is_new=True, created_via_auto_create=True")
                # #region agent log
                debug_log("debug-product-flags", "run1", "H1", "routes/sales.py:refresh_single_product_cache",
                          "New record created with flags", {
                              "sku": sku,
                              "product_id": str(product_id),
                              "cached_is_new": cached.is_new,
                              "cached_created_via_auto_create": cached.created_via_auto_create
                          })
                # #endregion
            else:
                current_app.logger.debug(f"Created new product cache for SKU '{sku}' (ID: {product_id}) - flags not set")
                # #region agent log
                debug_log("debug-product-flags", "run1", "H1", "routes/sales.py:refresh_single_product_cache",
                          "New record created without flags", {"sku": sku, "product_id": str(product_id)})
                # #endregion
        
        # #region agent log
        debug_log("debug-product-flags", "run1", "H4", "routes/sales.py:refresh_single_product_cache",
                  "Before commit", {"sku": sku, "product_id": str(product_id), "is_new": is_new})
        # #endregion
        
        db.session.commit()
        
        # #region agent log
        debug_log("debug-product-flags", "run1", "H4", "routes/sales.py:refresh_single_product_cache",
                  "After commit", {"sku": sku, "product_id": str(product_id)})
        # #endregion
        
        # Verify the flags were set
        if is_new:
            db.session.expire_all()  # Force refresh from database
            verify = CachedProduct.query.filter_by(
                client_erp_credentials_id=client_erp_credentials_id,
                cin7_product_id=product_id
            ).first()
            # #region agent log
            debug_log("debug-product-flags", "run1", "H1", "routes/sales.py:refresh_single_product_cache",
                      "Verification after commit", {
                          "sku": sku,
                          "product_id": str(product_id),
                          "verify_found": verify is not None,
                          "verify_is_new": verify.is_new if verify else None,
                          "verify_created_via_auto_create": verify.created_via_auto_create if verify else None
                      })
            # #endregion
            
            if verify:
                if not verify.is_new or not verify.created_via_auto_create:
                    current_app.logger.warning(f"WARNING: Product cache flags not set correctly for SKU '{sku}' (ID: {product_id}) - is_new={verify.is_new}, created_via_auto_create={verify.created_via_auto_create}")
                    # #region agent log
                    debug_log("debug-product-flags", "run1", "H1", "routes/sales.py:refresh_single_product_cache",
                              "VERIFICATION FAILED - flags not set", {
                                  "sku": sku,
                                  "product_id": str(product_id),
                                  "is_new": verify.is_new,
                                  "created_via_auto_create": verify.created_via_auto_create
                              })
                    # #endregion
                else:
                    current_app.logger.info(f"Verified: Product cache flags set correctly for SKU '{sku}' (ID: {product_id})")
                    # #region agent log
                    debug_log("debug-product-flags", "run1", "H1", "routes/sales.py:refresh_single_product_cache",
                              "VERIFICATION SUCCESS - flags set correctly", {"sku": sku, "product_id": str(product_id)})
                    # #endregion
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error refreshing single product cache: {str(e)}", exc_info=True)
        raise
