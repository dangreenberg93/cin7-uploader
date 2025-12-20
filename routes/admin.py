"""Admin/user provisioning routes"""
from flask import Blueprint, jsonify, request, current_app as app
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db, UserClient, Cin7ApiLog, ClientCsvMapping
from routes.auth import User  # Import User model from auth
import uuid
from datetime import datetime

admin_bp = Blueprint('admin', __name__)

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

def is_client_admin(user_id, client_id):
    """Check if user is admin of a client/connection (global admin has access to everything)
    client_id can be either a client_id or credential_id from voyager.client_erp_credentials"""
    # Global admin has access to everything
    if is_global_admin(user_id):
        return True
    # For non-admins, check if they have access to the client/connection
    # client_id references voyager.client_erp_credentials.id (either client_id or credential_id)
    user_client = UserClient.query.filter_by(user_id=user_id, client_id=client_id).first()
    return user_client is not None

def provision_admins_to_client(client_id):
    """Provision all admin users to a client/connection (ensures admins have access to all clients)
    client_id can be either a client_id or credential_id from voyager.client_erp_credentials"""
    try:
        # Get the credential_id from voyager.client_erp_credentials
        from sqlalchemy import text
        check_query = text("""
            SELECT cec.id as credential_id
            FROM voyager.client_erp_credentials cec
            LEFT JOIN voyager.client c ON c.id = cec.client_id
            WHERE cec.erp = 'cin7_core'
            AND (c.id = :client_id OR cec.id = :client_id)
            LIMIT 1
        """)
        check_result = db.session.execute(check_query, {'client_id': client_id}).fetchone()
        
        if not check_result:
            print(f"Client/connection {client_id} not found in voyager.client_erp_credentials")
            return 0
        
        credential_id = check_result.credential_id
        
        # Get all admin users (including legacy admin dan@paleblue.nyc)
        admin_users = User.query.filter(
            (User.role == 'admin') | (User.email == 'dan@paleblue.nyc')
        ).all()
        
        provisioned_count = 0
        for admin_user in admin_users:
            # Check if admin is already provisioned to this credential
            existing = UserClient.query.filter_by(user_id=admin_user.id, client_id=credential_id).first()
            if not existing:
                # Create new provisioning
                # UserClient.client_id references voyager.client_erp_credentials.id
                user_client = UserClient(
                    id=uuid.uuid4(),
                    user_id=admin_user.id,
                    client_id=credential_id
                )
                db.session.add(user_client)
                provisioned_count += 1
        
        if provisioned_count > 0:
            db.session.commit()
            print(f"Provisioned {provisioned_count} admin user(s) to credential {credential_id}")
        
        return provisioned_count
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error provisioning admins to client {client_id}: {str(e)}")
        traceback.print_exc()
        return 0

@admin_bp.route('/clients/<client_id>/users', methods=['GET'])
@jwt_required()
def get_client_users(client_id):
    """Get all users provisioned to a client/connection (admin only)
    client_id can be either a client_id or credential_id from voyager.client_erp_credentials"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client ID format'}), 400
    
    # Verify the connection exists and get the credential_id
    from sqlalchemy import text
    check_query = text("""
        SELECT cec.id as credential_id
        FROM voyager.client_erp_credentials cec
        LEFT JOIN voyager.client c ON c.id = cec.client_id
        WHERE cec.erp = 'cin7_core'
        AND (c.id = :client_id OR cec.id = :client_id)
        LIMIT 1
    """)
    check_result = db.session.execute(check_query, {'client_id': client_uuid}).fetchone()
    
    if not check_result:
        return jsonify({'error': 'Client or connection not found'}), 404
    
    credential_id = check_result.credential_id
    
    # Check if user is admin of this client/connection
    if not is_client_admin(user_id, credential_id):
        return jsonify({'error': 'Access denied. Admin role required.'}), 403
    
    # Get all user-client relationships for this credential
    # UserClient.client_id references voyager.client_erp_credentials.id
    user_clients = UserClient.query.filter_by(client_id=credential_id).all()
    
    # Fetch user details
    users_data = []
    for uc in user_clients:
        user = User.query.get(uc.user_id)
        if user:
            users_data.append({
                'user_id': str(user.id),
                'email': user.email,
                'name': user.name,
                'avatar_url': user.avatar_url,
                'role': user.role or 'user',  # Global role
                'provisioned_at': uc.created_at.isoformat() if uc.created_at else None
            })
    
    return jsonify(users_data)

@admin_bp.route('/clients/<client_id>/users', methods=['POST'])
@jwt_required()
def provision_user_to_client(client_id):
    """Provision a user to a client (admin only)"""
    try:
        user_id = get_user_id()
        if not user_id:
            return jsonify({'error': 'Invalid user ID format'}), 400
        
        try:
            client_uuid = uuid.UUID(client_id)
        except (ValueError, AttributeError):
            return jsonify({'error': 'Invalid client ID format'}), 400
        
        # Verify the connection exists in voyager.client_erp_credentials
        # client_id can be either a client_id or credential_id from voyager.client_erp_credentials
        from sqlalchemy import text
        check_client_query = text("""
            SELECT 
                c.id as client_id,
                cec.id as credential_id,
                cec.client_id as erp_client_id,
                cec.connection_name,
                c.name as client_name
            FROM voyager.client_erp_credentials cec
            LEFT JOIN voyager.client c ON c.id = cec.client_id
            WHERE cec.erp = 'cin7_core'
            AND (c.id = :client_id OR cec.id = :client_id)
            LIMIT 1
        """)
        check_result = db.session.execute(check_client_query, {'client_id': client_uuid}).fetchone()
        
        if not check_result:
            return jsonify({'error': 'Client or connection not found'}), 404
        
        # Determine the credential_id to use for UserClient
        # For client-based connections, use the client_id (which matches a credential's client_id)
        # For standalone connections, use the credential_id
        # In both cases, we use the credential_id from voyager.client_erp_credentials
        credential_id = check_result.credential_id
        
        # Check if user is admin of this client/connection
        if not is_client_admin(user_id, credential_id):
            return jsonify({'error': 'Access denied. Admin role required.'}), 403
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400
        
        # Get user by email or user_id
        target_user = None
        if data.get('user_id'):
            try:
                target_user_id = uuid.UUID(data['user_id'])
                target_user = User.query.get(target_user_id)
            except (ValueError, AttributeError):
                return jsonify({'error': 'Invalid user_id format'}), 400
        elif data.get('email'):
            target_user = User.query.filter_by(email=data['email'].lower()).first()
        else:
            return jsonify({'error': 'Either user_id or email is required'}), 400
        
        if not target_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Check if user is already provisioned
        existing = UserClient.query.filter_by(user_id=target_user.id, client_id=credential_id).first()
        if existing:
            return jsonify({
                'user_id': str(target_user.id),
                'email': target_user.email,
                'name': target_user.name,
                'message': 'User already provisioned to this client'
            }), 200
        
        # Create new provisioning (no role, just access)
        # client_id references voyager.client_erp_credentials.id
        user_client = UserClient(
            id=uuid.uuid4(),
            user_id=target_user.id,
            client_id=credential_id
        )
        db.session.add(user_client)
        db.session.commit()
        
        return jsonify({
            'user_id': str(target_user.id),
            'email': target_user.email,
            'name': target_user.name,
            'provisioned_at': user_client.created_at.isoformat() if user_client.created_at else None
        }), 201
    except Exception as e:
        db.session.rollback()
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in provision_user_to_client: {str(e)}")
        print(error_trace)
        # Get debug mode from request context
        debug_mode = request.environ.get('FLASK_ENV') == 'development' or request.environ.get('FLASK_DEBUG') == '1'
        return jsonify({
            'error': f'Failed to assign user to client: {str(e)}',
            'details': error_trace if debug_mode else None
        }), 500

@admin_bp.route('/clients/<client_id>/users/<user_id>', methods=['DELETE'])
@jwt_required()
def remove_user_from_client(client_id, user_id):
    """Remove a user from a client/connection (admin only)
    client_id can be either a client_id or credential_id from voyager.client_erp_credentials"""
    admin_user_id = get_user_id()
    if not admin_user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    try:
        client_uuid = uuid.UUID(client_id)
        target_user_uuid = uuid.UUID(user_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid ID format'}), 400
    
    # Verify the connection exists and get the credential_id
    from sqlalchemy import text
    check_query = text("""
        SELECT cec.id as credential_id
        FROM voyager.client_erp_credentials cec
        LEFT JOIN voyager.client c ON c.id = cec.client_id
        WHERE cec.erp = 'cin7_core'
        AND (c.id = :client_id OR cec.id = :client_id)
        LIMIT 1
    """)
    check_result = db.session.execute(check_query, {'client_id': client_uuid}).fetchone()
    
    if not check_result:
        return jsonify({'error': 'Client or connection not found'}), 404
    
    credential_id = check_result.credential_id
    
    # Check if user is admin of this client/connection
    if not is_client_admin(admin_user_id, credential_id):
        return jsonify({'error': 'Access denied. Admin role required.'}), 403
    
    # Prevent removing yourself if you're the only admin
    if admin_user_id == target_user_uuid:
        # Check if there are other admins
        other_admins = UserClient.query.filter(
            UserClient.client_id == credential_id,
            UserClient.user_id != target_user_uuid,
            UserClient.role == 'admin'
        ).count()
        if other_admins == 0:
            return jsonify({'error': 'Cannot remove the last admin from a client'}), 400
    
    # Remove provisioning
    # UserClient.client_id references voyager.client_erp_credentials.id
    user_client = UserClient.query.filter_by(user_id=target_user_uuid, client_id=credential_id).first()
    if not user_client:
        return jsonify({'error': 'User is not provisioned to this client'}), 404
    
    db.session.delete(user_client)
    db.session.commit()
    
    return jsonify({'message': 'User removed from client successfully'}), 200


@admin_bp.route('/users', methods=['GET'])
@jwt_required()
def get_all_users():
    """Get all users with their client assignments (admin only)"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    # Check if user is global admin
    if not is_global_admin(user_id):
        current_user = User.query.get(user_id)
        user_email = current_user.email if current_user else 'unknown'
        print(f"Access denied for user {user_email} (ID: {user_id}) - not a global admin")
        return jsonify({'error': 'Access denied. Admin role required.'}), 403
    
    try:
        # Get all users
        users = User.query.order_by(User.email).all()
        
        # Get all user-client relationships
        all_user_clients = UserClient.query.all()
        
        # Build a map of user_id -> list of client assignments (no roles, just access)
        user_assignments_map = {}
        for uc in all_user_clients:
            if uc.user_id not in user_assignments_map:
                user_assignments_map[uc.user_id] = []
            user_assignments_map[uc.user_id].append({
                'client_id': str(uc.client_id)
            })
        
        # Build response
        users_data = []
        for user in users:
            users_data.append({
                'id': str(user.id),
                'email': user.email,
                'name': user.name,
                'avatar_url': user.avatar_url,
                'role': user.role or 'user',  # Global role
                'clients': user_assignments_map.get(user.id, [])
            })
        
        return jsonify(users_data)
    except Exception as e:
        import traceback
        print(f"Error in get_all_users: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/users/<user_id>/role', methods=['PUT'])
@jwt_required()
def update_user_role(user_id):
    """Update a user's global role (admin only)"""
    admin_user_id = get_user_id()
    if not admin_user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    # Check if user is global admin
    if not is_global_admin(admin_user_id):
        return jsonify({'error': 'Access denied. Admin role required.'}), 403
    
    try:
        target_user_uuid = uuid.UUID(user_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    data = request.get_json()
    if not data or 'role' not in data:
        return jsonify({'error': 'Role is required'}), 400
    
    new_role = data['role']
    if new_role not in ['admin', 'user']:
        return jsonify({'error': 'Role must be either "admin" or "user"'}), 400
    
    # Prevent removing admin role from yourself if you're the only admin
    if admin_user_id == target_user_uuid and new_role != 'admin':
        other_admins = User.query.filter(
            User.role == 'admin',
            User.id != target_user_uuid,
            User.email != 'dan@paleblue.nyc'  # Legacy admin
        ).count()
        if other_admins == 0:
            return jsonify({'error': 'Cannot remove admin role from the last admin'}), 400
    
    user = User.query.get(target_user_uuid)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    old_role = user.role
    user.role = new_role
    db.session.commit()
    
    # If user was just promoted to admin, provision them to all existing credentials
    if new_role == 'admin' and old_role != 'admin':
        from sqlalchemy import text
        # Get all credentials from voyager.client_erp_credentials
        get_credentials_query = text("""
            SELECT id FROM voyager.client_erp_credentials
            WHERE erp = 'cin7_core'
            AND cin7_api_auth_accountid IS NOT NULL
            AND cin7_api_auth_applicationkey IS NOT NULL
        """)
        credentials_result = db.session.execute(get_credentials_query)
        
        provisioned_count = 0
        for row in credentials_result:
            if not row.id:  # Skip null IDs
                continue
            credential_id = row.id
            # Check if user is already provisioned to this credential
            existing = UserClient.query.filter_by(user_id=target_user_uuid, client_id=credential_id).first()
            if not existing:
                # Create new provisioning
                # UserClient.client_id references voyager.client_erp_credentials.id
                user_client = UserClient(
                    id=uuid.uuid4(),
                    user_id=target_user_uuid,
                    client_id=credential_id
                )
                db.session.add(user_client)
                provisioned_count += 1
        
        if provisioned_count > 0:
            db.session.commit()
            print(f"Provisioned newly promoted admin {target_user_uuid} to {provisioned_count} existing credential(s)")
    
    return jsonify({
        'user_id': str(target_user_uuid),
        'role': user.role,
        'message': 'Role updated successfully'
    }), 200

@admin_bp.route('/users/search', methods=['GET'])
@jwt_required()
def search_users():
    """Search for users by email (for provisioning) - admin only"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    # Check if user is global admin
    if not is_global_admin(user_id):
        return jsonify({'error': 'Access denied. Admin role required.'}), 403
    
    query = request.args.get('q', '').strip()
    if not query or len(query) < 2:
        return jsonify({'error': 'Search query must be at least 2 characters'}), 400
    
    # Search users by email (case-insensitive)
    users = User.query.filter(User.email.ilike(f'%{query}%')).limit(20).all()
    
    return jsonify([{
        'id': str(user.id),
        'email': user.email,
        'name': user.name,
        'avatar_url': user.avatar_url
    } for user in users])


@admin_bp.route('/clients/<client_id>/api-logs', methods=['GET'])
@jwt_required()
def get_api_logs(client_id):
    """Get API logs for a client (admin only)"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client ID format'}), 400
    
    # Check if user has access to this client
    if not is_client_admin(user_id, client_uuid):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    per_page = min(per_page, 100)  # Limit to 100 per page
    
    # Get filter parameters
    endpoint_filter = request.args.get('endpoint')
    status_filter = request.args.get('status', type=int)
    
    # Build query - client_id can be null, so we need to handle both cases
    # The client_id might be a credential_id (for standalone connections)
    # Get the credential_id from voyager.client_erp_credentials
    # UserClient.client_id references voyager.client_erp_credentials.id
    from sqlalchemy import text
    cred_query = text("""
        SELECT id as credential_id FROM voyager.client_erp_credentials
        WHERE (client_id = :client_id OR id = :client_id)
        AND erp = 'cin7_core'
        LIMIT 1
    """)
    cred_result = db.session.execute(cred_query, {'client_id': client_uuid})
    cred_row = cred_result.fetchone()
    
    if not cred_row:
        return jsonify({'error': 'Client or connection not found'}), 404
    
    credential_id = cred_row.credential_id
    
    # Build query - filter by credential_id
    # Note: Cin7ApiLog.client_id actually stores credential_id (see database.py comments)
    try:
        query = Cin7ApiLog.query.filter(
            Cin7ApiLog.client_id == credential_id
        )
        
        if endpoint_filter:
            query = query.filter(Cin7ApiLog.endpoint.ilike(f'%{endpoint_filter}%'))
        
        if status_filter:
            query = query.filter_by(response_status=status_filter)
        
        # Order by most recent first
        query = query.order_by(Cin7ApiLog.created_at.desc())
        
        # Paginate
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    except Exception as e:
        # If table doesn't exist yet, return empty result
        import traceback
        print(f"Error querying API logs: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'logs': [],
            'pagination': {
                'page': 1,
                'per_page': per_page,
                'total': 0,
                'pages': 0
            },
            'error': 'API logs table may not exist yet. Run database migration.'
        })
    
    logs_data = []
    for log in pagination.items:
        logs_data.append({
            'id': str(log.id),
            'endpoint': log.endpoint,
            'method': log.method,
            'request_url': log.request_url,
            'request_headers': log.request_headers,
            'request_body': log.request_body,
            'response_status': log.response_status,
            'response_body': log.response_body,
            'error_message': log.error_message,
            'duration_ms': log.duration_ms,
            'created_at': log.created_at.isoformat() if log.created_at else None,
            'upload_id': str(log.upload_id) if log.upload_id else None
        })
    
    return jsonify({
        'logs': logs_data,
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages
        }
    })


@admin_bp.route('/workflow', methods=['GET'])
@jwt_required()
def get_workflow():
    """Get global API workflow structure (admin only)"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    # Check if user is global admin
    if not is_global_admin(user_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Return the global API workflow structure
    workflow = {
        'flow': [
            {
                'step': 1,
                'name': 'CSV Upload',
                'description': 'CSV file is uploaded and parsed'
            },
            {
                'step': 2,
                'name': 'Validation',
                'description': 'Data is validated against Cin7 (customers, products, etc.)'
            },
            {
                'step': 3,
                'name': 'Create Sale',
                'description': 'POST /sale - Creates the sale record in Cin7'
            },
            {
                'step': 4,
                'name': 'Create Sale Order',
                'description': 'POST /saleorder - Creates the sale order with line items'
            }
        ],
        'api_calls': [
            {
                'endpoint': '/sale',
                'method': 'POST',
                'base_url': 'https://inventory.dearsystems.com/ExternalApi/v2/',
                'description': 'Creates a Sale record in Cin7',
                'required_fields': [
                    'CustomerID',
                    'Type'
                ],
                'optional_fields': [
                    'Customer',
                    'BillingAddress',
                    'ShippingAddress',
                    'ShipBy',
                    'CustomerReference'
                ],
                'notes': [
                    'CustomerID is set via customer lookup by name (CustomerName)',
                    'If customer is found and has BillingAddress/ShippingAddress with valid IDs, they are automatically set from customer record',
                    'Type can be "Advanced Sale" or "Simple Sale" based on client settings'
                ],
                'example_payload': {
                    'CustomerID': 'uuid-here',
                    'Type': 'Simple Sale',
                    'Customer': 'Customer Name',
                    'BillingAddress': 'uuid-here',
                    'ShippingAddress': 'uuid-here',
                    'CustomerReference': 'PO123',
                    'ShipBy': '2024-01-20'
                }
            },
            {
                'endpoint': '/saleorder',
                'method': 'POST',
                'base_url': 'https://inventory.dearsystems.com/ExternalApi/v2/',
                'description': 'Creates a Sale Order with line items',
                'required_fields': [
                    'SaleID',
                    'Status',
                    'Lines'
                ],
                'optional_fields': [
                    'Total',
                    'Tax'
                ],
                'line_item_fields': {
                    'required': [
                        'ProductID',
                        'Name',
                        'Quantity',
                        'Price',
                        'Tax',
                        'TaxRule'
                    ],
                    'optional': [
                        'SKU',
                        'Discount'
                    ]
                },
                'notes': [
                    'SaleID comes from the Sale created in step 3',
                    'Status: For POST only DRAFT and AUTHORISED values accepted',
                    'Lines array contains line items with products',
                    'ProductID and Name are set via product lookup by SKU',
                    'Name comes from Cin7 product record',
                    'TaxRule is set from client settings (tax_rule)',
                    'Total and Tax are calculated from line items if not provided'
                ],
                'example_payload': {
                    'SaleID': 'uuid-from-sale-response',
                    'Status': 'DRAFT',
                    'Lines': [
                        {
                            'ProductID': 'uuid-here',
                            'Name': 'Product Name from Cin7',
                            'Quantity': 1,
                            'Price': 1000.00,
                            'Tax': 100.00,
                            'TaxRule': 'TaxExclusive'
                        }
                    ]
                }
            }
        ]
    }
    
    return jsonify(workflow)
