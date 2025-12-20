"""Client settings/defaults management routes"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db, ClientSettings, Client, UserClient, Cin7ApiLog
from routes.auth import User  # Import User model from auth
from sqlalchemy import desc, text
import uuid

settings_bp = Blueprint('settings', __name__)

def get_user_id():
    """Helper to get and convert user ID from JWT"""
    user_id = get_jwt_identity()
    try:
        if isinstance(user_id, str):
            user_id = uuid.UUID(user_id)
    except (ValueError, AttributeError):
        return None
    return user_id

def has_client_access(user_id, client_id):
    """Check if user has access to a client"""
    user_client = UserClient.query.filter_by(user_id=user_id, client_id=client_id).first()
    return user_client is not None

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

def is_client_admin(user_id, client_id):
    """Check if user is admin of a client (global admin has access to everything)"""
    # Global admin has access to everything
    if is_global_admin(user_id):
        return True
    # For non-admins, check if they have access to the client
    user_client = UserClient.query.filter_by(user_id=user_id, client_id=client_id).first()
    return user_client is not None

@settings_bp.route('/clients/<client_id>', methods=['GET'])
@jwt_required()
def get_settings(client_id):
    """Get client settings (any user with access)"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client ID format'}), 400
    
    # Check if user has access to this client
    if not has_client_access(user_id, client_uuid):
        return jsonify({'error': 'Access denied'}), 403
    
    settings = ClientSettings.query.filter_by(client_id=client_uuid).first()
    
    # If no settings exist, return defaults
    if not settings:
        return jsonify({
            'client_id': str(client_uuid),
            'default_status': 'AUTHORISED',
            'default_location': None,
            'default_currency': 'USD',
            'tax_inclusive': False,
            'auto_fulfill': False,
            'default_fulfillment_status': None,
            'require_customer_reference': False,
            'require_invoice_number': False,
            'date_format': 'YYYY-MM-DD',
            'default_delay_between_orders': 0.7,
            'default_batch_size': 50,
            'default_batch_delay': 45.0,
            'created_at': None,
            'updated_at': None
        }), 200
    
    return jsonify({
        'id': str(settings.id),
        'client_id': str(settings.client_id),
        'default_status': settings.default_status,
        'default_location': str(settings.default_location) if settings.default_location else None,
        'default_currency': settings.default_currency,
        'tax_inclusive': settings.tax_inclusive,
        'auto_fulfill': settings.auto_fulfill,
        'default_fulfillment_status': settings.default_fulfillment_status,
        'require_customer_reference': settings.require_customer_reference,
        'require_invoice_number': settings.require_invoice_number,
        'date_format': settings.date_format,
        'default_delay_between_orders': settings.default_delay_between_orders,
        'default_batch_size': settings.default_batch_size,
        'default_batch_delay': settings.default_batch_delay,
        'created_at': settings.created_at.isoformat() if settings.created_at else None,
        'updated_at': settings.updated_at.isoformat() if settings.updated_at else None
    })

@settings_bp.route('/clients/<client_id>', methods=['POST', 'PUT'])
@jwt_required()
def set_settings(client_id):
    """Set or update client settings (admin only)"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client ID format'}), 400
    
    # Check if user is admin of this client
    if not is_client_admin(user_id, client_uuid):
        return jsonify({'error': 'Access denied. Admin role required.'}), 403
    
    # Verify client exists
    client = Client.query.get(client_uuid)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400
    
    # Get or create settings
    settings = ClientSettings.query.filter_by(client_id=client_uuid).first()
    
    if settings:
        # Update existing
        if 'default_status' in data:
            settings.default_status = data['default_status']
        if 'default_location' in data:
            settings.default_location = uuid.UUID(data['default_location']) if data['default_location'] else None
        if 'default_currency' in data:
            settings.default_currency = data['default_currency']
        if 'tax_inclusive' in data:
            settings.tax_inclusive = bool(data['tax_inclusive'])
        if 'auto_fulfill' in data:
            settings.auto_fulfill = bool(data['auto_fulfill'])
        if 'default_fulfillment_status' in data:
            settings.default_fulfillment_status = data['default_fulfillment_status']
        if 'require_customer_reference' in data:
            settings.require_customer_reference = bool(data['require_customer_reference'])
        if 'require_invoice_number' in data:
            settings.require_invoice_number = bool(data['require_invoice_number'])
        if 'date_format' in data:
            settings.date_format = data['date_format']
        if 'default_delay_between_orders' in data:
            settings.default_delay_between_orders = float(data['default_delay_between_orders'])
        if 'default_batch_size' in data:
            settings.default_batch_size = int(data['default_batch_size'])
        if 'default_batch_delay' in data:
            settings.default_batch_delay = float(data['default_batch_delay'])
        
        settings.updated_at = db.func.now()
    else:
        # Create new with defaults
        settings = ClientSettings(
            id=uuid.uuid4(),
            client_id=client_uuid,
            default_status=data.get('default_status', 'DRAFT'),
            default_location=uuid.UUID(data['default_location']) if data.get('default_location') else None,
            default_currency=data.get('default_currency', 'USD'),
            tax_inclusive=data.get('tax_inclusive', False),
            auto_fulfill=data.get('auto_fulfill', False),
            default_fulfillment_status=data.get('default_fulfillment_status'),
            require_customer_reference=data.get('require_customer_reference', False),
            require_invoice_number=data.get('require_invoice_number', False),
            date_format=data.get('date_format', 'YYYY-MM-DD'),
            default_delay_between_orders=data.get('default_delay_between_orders', 0.7),
            default_batch_size=data.get('default_batch_size', 50),
            default_batch_delay=data.get('default_batch_delay', 45.0)
        )
        db.session.add(settings)
    
    db.session.commit()
    
    return jsonify({
        'id': str(settings.id),
        'client_id': str(settings.client_id),
        'default_status': settings.default_status,
        'default_location': str(settings.default_location) if settings.default_location else None,
        'default_currency': settings.default_currency,
        'tax_inclusive': settings.tax_inclusive,
        'auto_fulfill': settings.auto_fulfill,
        'default_fulfillment_status': settings.default_fulfillment_status,
        'require_customer_reference': settings.require_customer_reference,
        'require_invoice_number': settings.require_invoice_number,
        'date_format': settings.date_format,
        'default_delay_between_orders': settings.default_delay_between_orders,
        'default_batch_size': settings.default_batch_size,
        'default_batch_delay': settings.default_batch_delay,
        'created_at': settings.created_at.isoformat() if settings.created_at else None,
        'updated_at': settings.updated_at.isoformat() if settings.updated_at else None
    }), 201 if not settings.id else 200

@settings_bp.route('/clients/<client_id>/reset', methods=['POST'])
@jwt_required()
def reset_settings(client_id):
    """Reset client settings to defaults (admin only)"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client ID format'}), 400
    
    # Check if user is admin of this client
    if not is_client_admin(user_id, client_uuid):
        return jsonify({'error': 'Access denied. Admin role required.'}), 403
    
    settings = ClientSettings.query.filter_by(client_id=client_uuid).first()
    
    if settings:
        # Reset to defaults
        settings.default_status = 'DRAFT'
        settings.default_location = None
        settings.default_currency = 'USD'
        settings.tax_inclusive = False
        settings.auto_fulfill = False
        settings.default_fulfillment_status = None
        settings.require_customer_reference = False
        settings.require_invoice_number = False
        settings.date_format = 'YYYY-MM-DD'
        settings.default_delay_between_orders = 0.7
        settings.default_batch_size = 50
        settings.default_batch_delay = 45.0
        settings.updated_at = db.func.now()
        db.session.commit()
    else:
        # No settings to reset
        return jsonify({'message': 'No settings to reset'}), 200
    
    return jsonify({
        'id': str(settings.id),
        'client_id': str(settings.client_id),
        'default_status': settings.default_status,
        'default_location': None,
        'default_currency': settings.default_currency,
        'tax_inclusive': settings.tax_inclusive,
        'auto_fulfill': settings.auto_fulfill,
        'default_fulfillment_status': settings.default_fulfillment_status,
        'require_customer_reference': settings.require_customer_reference,
        'require_invoice_number': settings.require_invoice_number,
        'date_format': settings.date_format,
        'default_delay_between_orders': settings.default_delay_between_orders,
        'default_batch_size': settings.default_batch_size,
        'default_batch_delay': settings.default_batch_delay,
        'message': 'Settings reset to defaults'
    }), 200

@settings_bp.route('/api-logs/test', methods=['POST'])
@jwt_required()
def test_api_logging():
    """Test endpoint to create a log entry"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    try:
        # Create a test log entry
        # Create test log entry - try with trigger first, fallback without if column doesn't exist
        try:
            test_log = Cin7ApiLog(
                id=uuid.uuid4(),
                client_id=None,
                user_id=user_id,
                upload_id=None,
                trigger='test',
                endpoint="/test",
                method="GET",
                request_url="https://test.example.com/test",
                request_headers={},
                request_body=None,
                response_status=200,
                response_body={"test": True},
                error_message=None,
                duration_ms=100
            )
            db.session.add(test_log)
            db.session.commit()
        except Exception as trigger_error:
            # If trigger column doesn't exist, try without it
            error_str = str(trigger_error).lower()
            if 'trigger' in error_str or 'column' in error_str:
                db.session.rollback()
                test_log = Cin7ApiLog(
                    id=uuid.uuid4(),
                    client_id=None,
                    user_id=user_id,
                    upload_id=None,
                    endpoint="/test",
                    method="GET",
                    request_url="https://test.example.com/test",
                    request_headers={},
                    request_body=None,
                    response_status=200,
                    response_body={"test": True},
                    error_message=None,
                    duration_ms=100
                )
                db.session.add(test_log)
                db.session.commit()
            else:
                raise
        
        return jsonify({'success': True, 'message': 'Test log created', 'log_id': str(test_log.id)}), 200
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/api-logs', methods=['GET'])
@jwt_required()
def get_api_logs():
    """Get API logs for the current user's accessible clients"""
    try:
        user_id = get_user_id()
        if not user_id:
            return jsonify({'error': 'Invalid user ID format'}), 400
        
        # Debug: Check total logs in database
        try:
            total_logs_in_db = Cin7ApiLog.query.count()
            print(f"DEBUG: Total logs in database: {total_logs_in_db}")
            print(f"DEBUG: User ID: {user_id}")
        except Exception as db_error:
            print(f"DEBUG: Error querying database: {str(db_error)}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Database error: {str(db_error)}'}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error initializing: {str(e)}'}), 500
    
    # Get query parameters
    client_id = request.args.get('client_id')
    show_all = request.args.get('show_all', 'false').lower() == 'true'  # Admin override
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    print(f"DEBUG: Request params - client_id: {client_id}, show_all: {show_all}, limit: {limit}, offset: {offset}")
    
    # Build query
    query = Cin7ApiLog.query
    
    # If show_all is true and user is admin, show all logs without filtering
    if show_all and is_global_admin(user_id):
        print(f"DEBUG: Admin override - showing all logs")
        # No filter applied
    
    # Filter by client_id (which actually stores credential_id)
    if client_id:
        try:
            client_uuid = uuid.UUID(client_id)
            print(f"DEBUG: Filtering by client_id (credential_id): {client_uuid}")
            
            # The client_id parameter is actually a credential_id, so we can filter directly
            # But we should also check if user has access to the client associated with this credential
            # First, get the actual client_id from the credential
            cred_query = text("""
                SELECT client_id 
                FROM voyager.client_erp_credentials 
                WHERE id = :cred_id
            """)
            cred_result = db.session.execute(cred_query, {'cred_id': client_uuid})
            cred_row = cred_result.fetchone()
            
            if cred_row and cred_row.client_id:
                # Check if user has access to the actual client
                if not is_client_admin(user_id, cred_row.client_id):
                    print(f"DEBUG: Access denied for user {user_id} to client {cred_row.client_id}")
                    return jsonify({'error': 'Access denied'}), 403
            
            # Filter by credential_id (stored in client_id field)
            query = query.filter(Cin7ApiLog.client_id == client_uuid)
            print(f"DEBUG: Query filter applied for credential_id: {client_uuid}")
        except (ValueError, AttributeError):
            return jsonify({'error': 'Invalid client ID format'}), 400
    else:
        # If no client_id specified, show logs for all clients user has access to
        # Get list of client IDs user has access to
        user_clients = UserClient.query.filter_by(user_id=user_id).all()
        client_ids = [uc.client_id for uc in user_clients]
        
        # If user is global admin, show all logs (including NULL client_id)
        if is_global_admin(user_id):
            # No filter needed - show all logs
            print(f"DEBUG: User is global admin, showing all logs")
            pass
        elif client_ids:
            # Get all credential_ids for the user's accessible clients
            # The logs store credential_id in the client_id field, so we need to find
            # all credentials for the user's clients
            credential_ids = []
            try:
                # Query one by one (more reliable than ANY with array)
                for client_id in client_ids:
                    try:
                        cred_query = text("""
                            SELECT id as credential_id
                            FROM voyager.client_erp_credentials
                            WHERE client_id = :client_id
                            AND erp = 'cin7_core'
                        """)
                        cred_result = db.session.execute(cred_query, {'client_id': client_id})
                        for row in cred_result:
                            credential_ids.append(str(row.credential_id))
                    except Exception as e:
                        print(f"Warning: Could not get credential for client {client_id}: {str(e)}")
                
                print(f"DEBUG: Found {len(credential_ids)} credential_ids for user's clients")
            except Exception as e:
                print(f"Warning: Could not get credential IDs: {str(e)}")
                import traceback
                traceback.print_exc()
            
            if credential_ids:
                # Filter by credential_ids (stored in client_id field) or NULL for this user
                from sqlalchemy import or_
                # Convert string UUIDs to UUID objects for comparison
                credential_uuids = [uuid.UUID(cid) for cid in credential_ids]
                query = query.filter(or_(
                    Cin7ApiLog.client_id.in_(credential_uuids),
                    Cin7ApiLog.client_id.is_(None)  # Include logs with no client_id if user made them
                ))
                print(f"DEBUG: Filtering by {len(credential_uuids)} credential_ids")
            else:
                # No credentials found for user's clients, but still show logs with NULL client_id for this user
                print(f"DEBUG: No credential_ids found, showing only NULL client_id logs for user")
                query = query.filter(
                    Cin7ApiLog.client_id.is_(None)
                )
        else:
            # User has no client access, but show logs with NULL client_id if they made them
            print(f"DEBUG: User has no client access, showing only NULL client_id logs")
            query = query.filter(
                Cin7ApiLog.client_id.is_(None)
            )
    
    # Get total count
    try:
        total = query.count()
        print(f"DEBUG: Query returned {total} logs")
    except Exception as count_error:
        print(f"DEBUG: Error counting logs: {str(count_error)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error counting logs: {str(count_error)}'}), 500
    
    # Debug: Show sample of what's in the database
    try:
        if total_logs_in_db > 0:
            sample_logs = Cin7ApiLog.query.order_by(desc(Cin7ApiLog.created_at)).limit(5).all()
            print(f"DEBUG: Sample logs in DB (most recent 5):")
            for log in sample_logs:
                print(f"  - Log ID: {log.id}, client_id (credential_id): {log.client_id}, user_id: {log.user_id}, endpoint: {log.endpoint}, trigger: {getattr(log, 'trigger', 'N/A')}, created_at: {log.created_at}")
    except Exception as sample_error:
        print(f"DEBUG: Error getting sample logs: {str(sample_error)}")
        import traceback
        traceback.print_exc()
    
    # Order by created_at descending and apply pagination
    try:
        logs = query.order_by(desc(Cin7ApiLog.created_at)).limit(limit).offset(offset).all()
        print(f"DEBUG: Retrieved {len(logs)} logs after pagination")
        
        if len(logs) > 0:
            print(f"DEBUG: First log - client_id: {logs[0].client_id}, user_id: {logs[0].user_id}")
    except Exception as query_error:
        print(f"DEBUG: Error querying logs: {str(query_error)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error querying logs: {str(query_error)}'}), 500
    
    # Get credential_ids from logs to look up client names
    credential_ids = list(set([log.client_id for log in logs if log.client_id]))  # Get unique IDs
    client_names_map = {}
    
    if credential_ids:
        try:
            # Query each credential to get client name (simple and reliable)
            for cred_id in credential_ids:
                client_query = text("""
                    SELECT 
                        cec.id as credential_id,
                        c.id as client_id,
                        c.name as client_name
                    FROM voyager.client_erp_credentials cec
                    LEFT JOIN voyager.client c ON c.id = cec.client_id
                    WHERE cec.id = :cred_id
                """)
                client_result = db.session.execute(client_query, {'cred_id': cred_id})
                row = client_result.fetchone()
                if row:
                    client_names_map[str(row.credential_id)] = {
                        'client_id': str(row.client_id) if row.client_id else None,
                        'client_name': row.client_name if row.client_name else 'Unknown Client'
                    }
        except Exception as e:
            print(f"Warning: Could not load client names: {str(e)}")
            import traceback
            traceback.print_exc()
    
    # Format response
    logs_data = []
    try:
        for log in logs:
            credential_id = str(log.client_id) if log.client_id else None
            client_info = client_names_map.get(credential_id, {}) if credential_id else {}
            
            # Safely get trigger field (may not exist if migration hasn't run)
            trigger_value = None
            try:
                trigger_value = log.trigger
            except AttributeError:
                # Column doesn't exist yet, use None
                trigger_value = None
            
            logs_data.append({
                'id': str(log.id),
                'client_id': credential_id,  # This is actually credential_id
                'actual_client_id': client_info.get('client_id'),
                'client_name': client_info.get('client_name'),
                'user_id': str(log.user_id) if log.user_id else None,
                'upload_id': str(log.upload_id) if log.upload_id else None,
                'trigger': trigger_value,  # Source of the API call
                'endpoint': log.endpoint,
                'method': log.method,
                'request_url': log.request_url,
                'request_headers': log.request_headers,
                'request_body': log.request_body,
                'response_status': log.response_status,
                'response_body': log.response_body,
                'error_message': log.error_message,
                'duration_ms': log.duration_ms,
                'created_at': log.created_at.isoformat() if log.created_at else None
            })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error formatting logs: {str(e)}'}), 500
    
    return jsonify({
        'logs': logs_data,
        'total': total,
        'limit': limit,
        'offset': offset
    }), 200
