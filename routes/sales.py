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
    
    # Get all available templates for this client
    all_templates = ClientCsvMapping.query.filter_by(
        client_erp_credentials_id=client_uuid
    ).order_by(
        ClientCsvMapping.is_default.desc(),  # Default templates first
        ClientCsvMapping.mapping_name
    ).all()
    
    templates_list = [{
        'id': str(t.id),
        'name': t.mapping_name,
        'is_default': t.is_default,
        'column_mapping': t.column_mapping
    } for t in all_templates]
    
    # Determine default template ID (either the default one, or the only one if there's just one)
    default_template_id = None
    if default_mapping_obj:
        default_template_id = str(default_mapping_obj.id)
    elif len(templates_list) == 1:
        default_template_id = templates_list[0]['id']
    
    return jsonify({
        'session_id': session_id,
        'upload_id': str(upload.id),  # Include upload_id so frontend can reuse it
        'filename': filename,
        'row_count': len(rows),
        'csv_columns': csv_columns,
        'detected_mappings': detected_mappings,
        'initial_mapping': initial_mapping,  # Auto-detected mapping (default template merged with detected)
        'default_mapping_loaded': bool(default_mapping_obj),
        'template_name': template_name,  # Name of the template that was auto-loaded
        'default_template_id': default_template_id,  # ID of the template to use by default
        'templates': templates_list,  # All available templates
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
