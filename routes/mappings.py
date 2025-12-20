"""CSV mapping template management routes"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db, ClientCsvMapping
from sqlalchemy import text
import uuid
from datetime import datetime

mappings_bp = Blueprint('mappings', __name__)

def get_user_id():
    """Helper to get and convert user ID from JWT"""
    user_id = get_jwt_identity()
    try:
        if isinstance(user_id, str):
            user_id = uuid.UUID(user_id)
    except (ValueError, AttributeError):
        return None
    return user_id

def has_client_access(user_id, client_erp_credentials_id):
    """Check if user has access to a client_erp_credentials (simplified - can enhance later)"""
    # For now, allow if user is authenticated
    # TODO: Add proper access control based on client_erp_credentials
    return user_id is not None

@mappings_bp.route('/clients/<client_erp_credentials_id>', methods=['GET'])
@jwt_required()
def get_mappings(client_erp_credentials_id):
    """Get all CSV mappings for a client_erp_credentials"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    try:
        cred_uuid = uuid.UUID(client_erp_credentials_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client_erp_credentials_id format'}), 400
    
    # Check access
    if not has_client_access(user_id, cred_uuid):
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        mappings = ClientCsvMapping.query.filter_by(
            client_erp_credentials_id=cred_uuid
        ).order_by(
            ClientCsvMapping.is_default.desc(),
            ClientCsvMapping.mapping_name
        ).all()
        
        return jsonify([{
            'id': str(m.id),
            'client_erp_credentials_id': str(m.client_erp_credentials_id),
            'mapping_name': m.mapping_name,
            'is_default': m.is_default,
            'column_mapping': m.column_mapping,
            'created_at': m.created_at.isoformat() if m.created_at else None,
            'updated_at': m.updated_at.isoformat() if m.updated_at else None
        } for m in mappings])
    except Exception as e:
        import traceback
        print(f"Error getting mappings: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@mappings_bp.route('/clients/<client_erp_credentials_id>/default', methods=['GET'])
@jwt_required()
def get_default_mapping(client_erp_credentials_id):
    """Get the default CSV mapping for a client_erp_credentials"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    try:
        cred_uuid = uuid.UUID(client_erp_credentials_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client_erp_credentials_id format'}), 400
    
    # Check access
    if not has_client_access(user_id, cred_uuid):
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        mapping = ClientCsvMapping.query.filter_by(
            client_erp_credentials_id=cred_uuid,
            is_default=True
        ).first()
        
        if not mapping:
            return jsonify({'error': 'No default mapping found'}), 404
        
        return jsonify({
            'id': str(mapping.id),
            'client_erp_credentials_id': str(mapping.client_erp_credentials_id),
            'mapping_name': mapping.mapping_name,
            'is_default': mapping.is_default,
            'column_mapping': mapping.column_mapping,
            'created_at': mapping.created_at.isoformat() if mapping.created_at else None,
            'updated_at': mapping.updated_at.isoformat() if mapping.updated_at else None
        })
    except Exception as e:
        import traceback
        print(f"Error getting default mapping: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@mappings_bp.route('', methods=['POST'])
@jwt_required()
def create_mapping():
    """Create a new CSV mapping"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400
    
    required_fields = ['client_erp_credentials_id', 'mapping_name', 'column_mapping']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'{field} is required'}), 400
    
    try:
        cred_uuid = uuid.UUID(data['client_erp_credentials_id'])
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client_erp_credentials_id format'}), 400
    
    # Check access
    if not has_client_access(user_id, cred_uuid):
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        # If this is set as default, unset other defaults
        if data.get('is_default', False):
            existing_defaults = ClientCsvMapping.query.filter_by(
                client_erp_credentials_id=cred_uuid,
                is_default=True
            ).all()
            for existing in existing_defaults:
                existing.is_default = False
        
        # Check if mapping with same name exists
        existing = ClientCsvMapping.query.filter_by(
            client_erp_credentials_id=cred_uuid,
            mapping_name=data['mapping_name']
        ).first()
        
        if existing:
            return jsonify({'error': f'Mapping with name "{data["mapping_name"]}" already exists'}), 400
        
        mapping = ClientCsvMapping(
            id=uuid.uuid4(),
            client_erp_credentials_id=cred_uuid,
            client_id=None,  # Can be set later if needed
            mapping_name=data['mapping_name'],
            is_default=data.get('is_default', False),
            column_mapping=data['column_mapping']
        )
        
        db.session.add(mapping)
        db.session.commit()
        
        return jsonify({
            'id': str(mapping.id),
            'client_erp_credentials_id': str(mapping.client_erp_credentials_id),
            'mapping_name': mapping.mapping_name,
            'is_default': mapping.is_default,
            'column_mapping': mapping.column_mapping,
            'created_at': mapping.created_at.isoformat() if mapping.created_at else None,
            'updated_at': mapping.updated_at.isoformat() if mapping.updated_at else None
        }), 201
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error creating mapping: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@mappings_bp.route('/<mapping_id>', methods=['PUT'])
@jwt_required()
def update_mapping(mapping_id):
    """Update an existing CSV mapping"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    try:
        mapping_uuid = uuid.UUID(mapping_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid mapping_id format'}), 400
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400
    
    try:
        mapping = ClientCsvMapping.query.get(mapping_uuid)
        if not mapping:
            return jsonify({'error': 'Mapping not found'}), 404
        
        # Check access
        if not has_client_access(user_id, mapping.client_erp_credentials_id):
            return jsonify({'error': 'Access denied'}), 403
        
        # If setting as default, unset other defaults
        if data.get('is_default', False) and not mapping.is_default:
            existing_defaults = ClientCsvMapping.query.filter_by(
                client_erp_credentials_id=mapping.client_erp_credentials_id,
                is_default=True
            ).all()
            for existing in existing_defaults:
                existing.is_default = False
        
        # Update fields
        if 'mapping_name' in data:
            # Check if new name conflicts with existing mapping
            if data['mapping_name'] != mapping.mapping_name:
                existing = ClientCsvMapping.query.filter_by(
                    client_erp_credentials_id=mapping.client_erp_credentials_id,
                    mapping_name=data['mapping_name']
                ).first()
                if existing:
                    return jsonify({'error': f'Mapping with name "{data["mapping_name"]}" already exists'}), 400
            mapping.mapping_name = data['mapping_name']
        
        if 'is_default' in data:
            mapping.is_default = data['is_default']
        
        if 'column_mapping' in data:
            mapping.column_mapping = data['column_mapping']
        
        mapping.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'id': str(mapping.id),
            'client_erp_credentials_id': str(mapping.client_erp_credentials_id),
            'mapping_name': mapping.mapping_name,
            'is_default': mapping.is_default,
            'column_mapping': mapping.column_mapping,
            'created_at': mapping.created_at.isoformat() if mapping.created_at else None,
            'updated_at': mapping.updated_at.isoformat() if mapping.updated_at else None
        })
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error updating mapping: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@mappings_bp.route('/<mapping_id>', methods=['DELETE'])
@jwt_required()
def delete_mapping(mapping_id):
    """Delete a CSV mapping"""
    user_id = get_user_id()
    if not user_id:
        return jsonify({'error': 'Invalid user ID format'}), 400
    
    try:
        mapping_uuid = uuid.UUID(mapping_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid mapping_id format'}), 400
    
    try:
        mapping = ClientCsvMapping.query.get(mapping_uuid)
        if not mapping:
            return jsonify({'error': 'Mapping not found'}), 404
        
        # Check access
        if not has_client_access(user_id, mapping.client_erp_credentials_id):
            return jsonify({'error': 'Access denied'}), 403
        
        db.session.delete(mapping)
        db.session.commit()
        
        return jsonify({'message': 'Mapping deleted successfully'}), 200
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error deleting mapping: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
