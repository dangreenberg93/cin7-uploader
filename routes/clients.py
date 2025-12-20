"""Client management routes - uses voyager.client table"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db, UserClient
from sqlalchemy import text
from routes.admin import provision_admins_to_client, is_global_admin, get_user_id
from routes.auth import User
import uuid

clients_bp = Blueprint('clients', __name__)

@clients_bp.route('', methods=['GET'])
@jwt_required()
def get_clients():
    """Get clients that have Cin7 credentials configured (includes standalone connections with connection_name)
    Non-admin users only see clients they have access to via UserClient table"""
    try:
        user_id = get_user_id()
        if not user_id:
            return jsonify({'error': 'Invalid user ID format'}), 400
        
        # Check if user is global admin
        is_admin = is_global_admin(user_id)
        
        # Get user's accessible credential IDs if not admin
        # client_id in UserClient now references voyager.client_erp_credentials.id
        accessible_credential_ids = set()
        if not is_admin:
            user_clients = UserClient.query.filter_by(user_id=user_id).all()
            accessible_credential_ids = {str(uc.client_id) for uc in user_clients}
        
        # Return both client-based connections and standalone connections (with connection_name)
        # Show all connections with credentials, regardless of client active status
        query = text("""
            SELECT 
                cec.id as credential_id,
                cec.client_id,
                cec.connection_name,
                cec.active as credential_active,
                c.name as client_name,
                c.active as client_active,
                COALESCE(c.name, cec.connection_name, 'Unnamed Connection') as display_name
            FROM voyager.client_erp_credentials cec
            LEFT JOIN voyager.client c ON c.id = cec.client_id
            WHERE cec.erp = 'cin7_core'
            AND cec.cin7_api_auth_accountid IS NOT NULL
            AND cec.cin7_api_auth_applicationkey IS NOT NULL
            ORDER BY display_name
        """)
        
        result = db.session.execute(query)
        clients = []
        for row in result:
            # For standalone connections, use credential_id as the client identifier
            # For client-based connections, use the client_id
            client_id = str(row.client_id) if row.client_id else str(row.credential_id)
            
            # Filter: non-admins only see clients/connections they have access to
            if not is_admin:
                # client_id in the response can be either client_id or credential_id
                # UserClient.client_id references voyager.client_erp_credentials.id (credential_id)
                # So we check if the credential_id is in the accessible list
                credential_id_str = str(row.credential_id)
                if credential_id_str not in accessible_credential_ids:
                    continue
            
            display_name = row.client_name if row.client_id else (row.connection_name or 'Unnamed Connection')
            # Use client.active if it's a client-based connection, otherwise use credential.active
            is_active = row.client_active if row.client_id else (row.credential_active if row.credential_active is not None else True)
            
            clients.append({
                'id': client_id,
                'name': display_name,
                'active': is_active,
                'credential_id': str(row.credential_id) if row.credential_id else None,
                'client_id': str(row.client_id) if row.client_id else None,
                'connection_name': row.connection_name,
                'is_standalone': row.client_id is None
            })
        
        return jsonify(clients)
    except Exception as e:
        import traceback
        print(f"Error in get_clients: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@clients_bp.route('', methods=['POST'])
@jwt_required()
def create_client():
    """Create a new client in voyager.client table (admin only)"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    # Only admins can create clients
    if not is_global_admin(user_id):
        return jsonify({'error': 'Access denied. Admin role required to create clients.'}), 403
    
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': 'Client name is required'}), 400
    
    try:
        client_id = uuid.uuid4()
        query = text("""
            INSERT INTO voyager.client (id, name, active, created_at)
            VALUES (:id, :name, :active, NOW())
            RETURNING id, name, active
        """)
        
        result = db.session.execute(query, {
            'id': client_id,
            'name': data['name'],
            'active': data.get('active', True)
        })
        db.session.commit()
        
        row = result.fetchone()
        
        # Automatically provision all admin users to this new client
        provision_admins_to_client(client_id)
        
        return jsonify({
            'id': str(row.id),
            'name': row.name,
            'active': row.active
        }), 201
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error creating client: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@clients_bp.route('/<client_id>', methods=['GET'])
@jwt_required()
def get_client(client_id):
    """Get a specific client by ID (supports both client_id and credential_id for standalone connections)
    Non-admin users can only access clients they have been provisioned to"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client ID format'}), 400
    
    try:
        # Check if it's a client-based connection or standalone connection
        query = text("""
            SELECT DISTINCT
                cec.id as credential_id,
                cec.client_id,
                cec.connection_name,
                cec.active as credential_active,
                c.name as client_name,
                c.active as client_active
            FROM voyager.client_erp_credentials cec
            LEFT JOIN voyager.client c ON c.id = cec.client_id
            WHERE cec.erp = 'cin7_core'
            AND cec.cin7_api_auth_accountid IS NOT NULL
            AND cec.cin7_api_auth_applicationkey IS NOT NULL
            AND (c.id = :client_id OR cec.id = :client_id)
        """)
        
        result = db.session.execute(query, {'client_id': client_uuid})
        row = result.fetchone()
        
        if not row:
            return jsonify({'error': 'Client not found or does not have Cin7 credentials configured'}), 404
        
        # Check access: non-admins must have access via UserClient
        # UserClient.client_id references voyager.client_erp_credentials.id (credential_id)
        is_admin = is_global_admin(user_id)
        if not is_admin:
            credential_id = row.credential_id
            has_access = UserClient.query.filter_by(user_id=user_id, client_id=credential_id).first() is not None
            
            if not has_access:
                return jsonify({'error': 'Access denied. You do not have access to this client.'}), 403
        
        # For standalone connections, use credential_id as the client identifier
        # For client-based connections, use the client_id
        return_client_id = str(row.client_id) if row.client_id else str(row.credential_id)
        display_name = row.client_name if row.client_id else (row.connection_name or 'Unnamed Connection')
        # Use client.active if it's a client-based connection, otherwise use credential.active
        is_active = row.client_active if row.client_id else (row.credential_active if row.credential_active is not None else True)
        
        return jsonify({
            'id': return_client_id,
            'name': display_name,
            'active': is_active,
            'credential_id': str(row.credential_id) if row.credential_id else None,
            'client_id': str(row.client_id) if row.client_id else None,
            'connection_name': row.connection_name,
            'is_standalone': row.client_id is None
        })
    except Exception as e:
        import traceback
        print(f"Error getting client: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@clients_bp.route('/<client_id>', methods=['PUT'])
@jwt_required()
def update_client(client_id):
    """Update a client - supports both voyager.client and standalone connections in voyager.client_erp_credentials
    Non-admin users can only update clients they have been provisioned to"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client ID format'}), 400
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400
    
    try:
        # First, determine if this is a client-based connection or standalone connection
        check_query = text("""
            SELECT cec.id as credential_id, cec.client_id, c.name as client_name, cec.connection_name
            FROM voyager.client_erp_credentials cec
            LEFT JOIN voyager.client c ON c.id = cec.client_id
            WHERE cec.erp = 'cin7_core'
            AND (c.id = :client_id OR cec.id = :client_id)
            LIMIT 1
        """)
        check_result = db.session.execute(check_query, {'client_id': client_uuid}).fetchone()
        
        if not check_result:
            return jsonify({'error': 'Client or connection not found'}), 404
        
        is_standalone = check_result.client_id is None
        actual_client_id = check_result.client_id if check_result.client_id else None
        credential_id = check_result.credential_id
        
        # Check access: non-admins must have access via UserClient
        # UserClient.client_id references voyager.client_erp_credentials.id (credential_id)
        is_admin = is_global_admin(user_id)
        if not is_admin:
            credential_id = check_result.credential_id
            has_access = UserClient.query.filter_by(user_id=user_id, client_id=credential_id).first() is not None
            
            if not has_access:
                return jsonify({'error': 'Access denied. You do not have access to this client.'}), 403
        
        if is_standalone:
            # Update standalone connection in client_erp_credentials
            updates = []
            params = {'credential_id': credential_id}
            
            if 'name' in data and data.get('name'):
                updates.append('connection_name = :name')
                params['name'] = data['name']
            
            if 'active' in data:
                updates.append('active = :active')
                params['active'] = data['active']
            
            if not updates:
                return jsonify({'error': 'No fields to update'}), 400
            
            query = text(f"""
                UPDATE voyager.client_erp_credentials
                SET {', '.join(updates)}
                WHERE id = :credential_id
                RETURNING id, connection_name as name, active
            """)
        else:
            # Update client in voyager.client
            updates = []
            params = {'client_id': actual_client_id}
            
            if 'name' in data:
                updates.append('name = :name')
                params['name'] = data['name']
            
            if 'active' in data:
                updates.append('active = :active')
                params['active'] = data['active']
            
            if not updates:
                return jsonify({'error': 'No fields to update'}), 400
            
            # Note: voyager.client table doesn't have updated_at column, so we don't update it
            query = text(f"""
                UPDATE voyager.client
                SET {', '.join(updates)}
                WHERE id = :client_id
                RETURNING id, name, active
            """)
        
        result = db.session.execute(query, params)
        db.session.commit()
        
        row = result.fetchone()
        if not row:
            return jsonify({'error': 'Update failed'}), 500
        
        return jsonify({
            'id': str(row.id),
            'name': row.name,
            'active': row.active
        })
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error updating client: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
