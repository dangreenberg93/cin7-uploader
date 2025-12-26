"""Sales order upload/creation routes"""
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
from database import db, Client, ClientCin7Credentials, ClientSettings, ClientCsvMapping, SalesOrderUpload, UserClient, Cin7ApiLog
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

sales_bp = Blueprint('sales', __name__)

# Upload folder for CSV files
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cin7_uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
    
    # Create session
    session_id = str(uuid.uuid4())
    upload_sessions[session_id] = {
        'user_id': user_id,
        'client_id': client_uuid,  # This is actually client_erp_credentials_id
        'client_erp_credentials_id': client_uuid,
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
    query = text("""
        SELECT 
            cec.id,
            cec.cin7_api_auth_accountid as account_id,
            cec.cin7_api_auth_applicationkey as application_key,
            cec.sale_type,
            cec.tax_rule,
            cec.default_status
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
    
    logger.info(f"DEBUG: Using credential_id {credential_id_for_logging} for API logging")
    
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
                    upload_id=None,
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
                        upload_id=None,
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
            
            logger.info(f"✓ Logged API call: {method} {endpoint} - Status: {response_status}, credential_id: {credential_id_for_logging}, user_id: {user_id}, trigger: validation")
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
            'customer_attribute_set': customer_attribute_set
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
            'customer_attribute_set': customer_attribute_set
        }
    
    builder = SalesOrderBuilder(settings, None)  # Will set api_client later
    column_mapping = session.get('column_mapping', {})
    
    if not column_mapping:
        return jsonify({'error': 'Column mapping not set'}), 400
    
    # Get credential_id for logging (from client_erp_credentials)
    credential_id_for_logging = client_erp_credentials_id
    
    # Get client_id for upload record (may be None for standalone connections)
    client_id_for_upload = None
    if client_row and client_row.client_id:
        client_id_for_upload = client_row.client_id
    
    # Create upload record first (client_id can be None for standalone connections)
    upload = SalesOrderUpload(
        id=uuid.uuid4(),
        user_id=user_id,
        client_id=client_id_for_upload,  # May be None
        filename=session['filename'],
        total_rows=len(session['rows']),
        successful_orders=0,
        failed_orders=0,
        status='processing'
    )
    db.session.add(upload)
    db.session.commit()
    
    # Create logging callback (after upload is created)
    def log_api_call(endpoint, method, request_url, request_headers, request_body,
                     response_status, response_body, error_message, duration_ms):
        """Callback to log API calls to database"""
        try:
            # Create log entry - handle trigger column gracefully if it doesn't exist yet
            # Create log entry - try with trigger first, fallback without if column doesn't exist
            try:
                log_entry = Cin7ApiLog(
                    id=uuid.uuid4(),
                    client_id=credential_id_for_logging,
                    user_id=user_id,
                    upload_id=upload.id,
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
                else:
                    raise
        except Exception as e:
            print(f"Error logging API call: {str(e)}")
            # Don't fail the request if logging fails
            db.session.rollback()
    
    # Initialize API client and builder with logging
    api_client = Cin7SalesAPI(
        account_id=str(account_id),
        application_key=str(application_key),
        base_url='https://inventory.dearsystems.com/ExternalApi/v2/',
        logger_callback=log_api_call
    )
    
    # Update builder with API client
    builder.api_client = api_client
    
    # Get validated rows (or validate now)
    if session.get('validated_rows'):
        valid_rows = session['validated_rows']['valid']
    else:
        # Validate now
        validator = SalesOrderValidator(api_client)
        
        # Preload latest customers and products from Cin7
        try:
            customer_count, product_count = validator.preload_customers_and_products()
            print(f"Preloaded {customer_count} customers and {product_count} products for validation")
        except Exception as e:
            print(f"Warning: Failed to preload customers/products: {str(e)}")
            # Continue with validation anyway (will use API calls as fallback)
        
        valid_rows, _ = validator.validate_batch(
            session['rows'],
            column_mapping,
            settings
        )
    
    if not valid_rows:
        return jsonify({'error': 'No valid rows to process'}), 400
    
    # Process rows
    successful = []
    failed = []
    errors = []
    
    import time
    delay = settings.get('default_delay_between_orders', 0.7)
    
    for row_result in valid_rows:
        try:
            # Step 1: Build and create Sale
            sale_data = builder.build_sale(row_result['data'], column_mapping)
            
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
            if isinstance(response, dict):
                sale_id = response.get('ID')
            elif isinstance(response, list) and len(response) > 0:
                sale_id = response[0].get('ID') if isinstance(response[0], dict) else None
            
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
                sale_order_data = builder.build_sale_order_from_rows(row_result['group_rows'], column_mapping, sale_id)
            else:
                # Single row order
                sale_order_data = builder.build_sale_order(row_result['data'], column_mapping, sale_id)
            
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
