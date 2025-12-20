"""Cin7 credentials management routes - uses voyager.client_erp_credentials"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
from database import db, Cin7ApiLog
from sqlalchemy import text, desc
import uuid
import time
from cin7_sales.api_client import Cin7SalesAPI

credentials_bp = Blueprint('credentials', __name__)

@credentials_bp.route('/clients/<client_id>', methods=['GET'])
@jwt_required()
def get_credentials(client_id):
    """Get Cin7 credentials - supports both client_id and credential_id (for standalone connections)"""
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client ID format'}), 400
    
    try:
        # Get credentials - can match by client_id or credential_id (for standalone)
        query = text("""
            SELECT 
                cec.id,
                cec.client_id,
                cec.connection_name,
                cec.cin7_api_auth_accountid as account_id,
                cec.cin7_api_auth_applicationkey as application_key,
                cec.sale_type,
                cec.tax_rule,
                cec.default_status,
                c.name as client_name
            FROM voyager.client_erp_credentials cec
            LEFT JOIN voyager.client c ON c.id = cec.client_id
            WHERE cec.erp = 'cin7_core'
            AND (cec.client_id = :client_id OR cec.id = :client_id)
        """)
        
        result = db.session.execute(query, {'client_id': client_uuid})
        row = result.fetchone()
        
        if not row or not row.account_id or not row.application_key:
            return jsonify({'error': 'Credentials not found'}), 404
        
        # For now, always show full credentials (can add role-based masking later)
        return jsonify({
            'id': str(row.id),
            'client_id': str(row.client_id) if row.client_id else None,
            'connection_name': row.connection_name,
            'account_id': str(row.account_id),
            'application_key': str(row.application_key),
            'base_url': 'https://inventory.dearsystems.com/ExternalApi/v2/',  # Default base URL
            'sale_type': row.sale_type,
            'tax_rule': row.tax_rule,
            'default_status': row.default_status
        })
    except Exception as e:
        import traceback
        print(f"Error getting credentials: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@credentials_bp.route('/clients/<client_id>', methods=['POST', 'PUT'])
@jwt_required()
def set_credentials(client_id):
    """Set or update Cin7 credentials for a client in voyager.client_erp_credentials"""
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client ID format'}), 400
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400
    
    # Validate required fields
    if 'account_id' not in data:
        return jsonify({'error': 'account_id is required'}), 400
    if 'application_key' not in data:
        return jsonify({'error': 'application_key is required'}), 400
    
    try:
        account_id = uuid.UUID(data['account_id'])
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid account_id format (must be UUID)'}), 400
    
    application_key_uuid = uuid.UUID(data['application_key'].strip())
    
    try:
        # Check if credentials already exist
        check_query = text("""
            SELECT id FROM voyager.client_erp_credentials
            WHERE client_id = :client_id AND erp = 'cin7_core'
        """)
        existing = db.session.execute(check_query, {'client_id': client_uuid}).fetchone()
        
        if existing:
            # Update existing
            update_query = text("""
                UPDATE voyager.client_erp_credentials
                SET cin7_api_auth_accountid = :account_id,
                    cin7_api_auth_applicationkey = :application_key
                WHERE id = :id
                RETURNING id, client_id, cin7_api_auth_accountid, cin7_api_auth_applicationkey
            """)
            result = db.session.execute(update_query, {
                'id': existing.id,
                'account_id': account_id,
                'application_key': application_key_uuid
            })
        else:
            # Create new
            cred_id = uuid.uuid4()
            insert_query = text("""
                INSERT INTO voyager.client_erp_credentials 
                (id, client_id, erp, cin7_api_auth_accountid, cin7_api_auth_applicationkey, created_at)
                VALUES (:id, :client_id, 'cin7_core', :account_id, :application_key, NOW())
                RETURNING id, client_id, cin7_api_auth_accountid, cin7_api_auth_applicationkey
            """)
            result = db.session.execute(insert_query, {
                'id': cred_id,
                'client_id': client_uuid,
                'account_id': account_id,
                'application_key': application_key_uuid
            })
        
        db.session.commit()
        row = result.fetchone()
        
        return jsonify({
            'id': str(row.id),
            'client_id': str(row.client_id),
            'account_id': str(row.cin7_api_auth_accountid),
            'application_key': str(row.cin7_api_auth_applicationkey),
            'base_url': 'https://inventory.dearsystems.com/ExternalApi/v2/'
        }), 201 if not existing else 200
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error setting credentials: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@credentials_bp.route('/clients/<client_id>', methods=['DELETE'])
@jwt_required()
def delete_credentials(client_id):
    """Delete Cin7 credentials for a client"""
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client ID format'}), 400
    
    try:
        delete_query = text("""
            DELETE FROM voyager.client_erp_credentials
            WHERE client_id = :client_id AND erp = 'cin7_core'
        """)
        result = db.session.execute(delete_query, {'client_id': client_uuid})
        db.session.commit()
        
        if result.rowcount == 0:
            return jsonify({'error': 'Credentials not found'}), 404
        
        return jsonify({'message': 'Credentials deleted successfully'}), 200
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error deleting credentials: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@credentials_bp.route('/clients/<client_id>/settings', methods=['PUT'])
@jwt_required()
def update_credential_settings(client_id):
    """Update sale_type, tax_rule, and default_status for client_erp_credentials"""
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client ID format'}), 400
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400
    
    try:
        # Build update query
        updates = []
        params = {'client_id': client_uuid}
        
        if 'sale_type' in data:
            updates.append('sale_type = :sale_type')
            params['sale_type'] = data['sale_type']
        
        if 'tax_rule' in data:
            updates.append('tax_rule = :tax_rule')
            params['tax_rule'] = data['tax_rule']
        
        if 'default_status' in data:
            updates.append('default_status = :default_status')
            params['default_status'] = data['default_status']
        
        if not updates:
            return jsonify({'error': 'No fields to update'}), 400
        
        query = text(f"""
            UPDATE voyager.client_erp_credentials
            SET {', '.join(updates)}
            WHERE erp = 'cin7_core'
            AND (client_id = :client_id OR id = :client_id)
            RETURNING id, sale_type, tax_rule, default_status
        """)
        
        result = db.session.execute(query, params)
        db.session.commit()
        
        row = result.fetchone()
        if not row:
            return jsonify({'error': 'Credentials not found'}), 404
        
        return jsonify({
            'id': str(row.id),
            'sale_type': row.sale_type,
            'tax_rule': row.tax_rule,
            'default_status': row.default_status
        })
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error updating credential settings: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@credentials_bp.route('/clients/<client_id>/test', methods=['POST'])
@jwt_required()
def test_credentials(client_id):
    """Test Cin7 credentials by making a simple API call - supports both client_id and credential_id"""
    logger = logging.getLogger(__name__)
    
    try:
        # Get user_id
        user_id = get_jwt_identity()
        try:
            if isinstance(user_id, str):
                user_id = uuid.UUID(user_id)
        except (ValueError, AttributeError):
            user_id = None
        
        # Parse client_id
        try:
            client_uuid = uuid.UUID(client_id)
        except (ValueError, AttributeError):
            return jsonify({'error': 'Invalid client ID format'}), 400
        
        # Get credentials - can match by client_id or credential_id (for standalone)
        query = text("""
            SELECT 
                id as credential_id,
                cin7_api_auth_accountid as account_id,
                cin7_api_auth_applicationkey as application_key
            FROM voyager.client_erp_credentials
            WHERE erp = 'cin7_core'
            AND (client_id = :client_id OR id = :client_id)
        """)
        
        result = db.session.execute(query, {'client_id': client_uuid})
        row = result.fetchone()
        
        if not row or not row.account_id or not row.application_key:
            return jsonify({'error': 'Credentials not found'}), 404
        
        # Use the actual credential_id from the query result for logging
        credential_id_for_logging = row.credential_id
        
        # Define logger callback function
        def log_api_call(endpoint, method, request_url, request_headers, request_body,
                         response_status, response_body, error_message, duration_ms):
            """Callback to log API calls to database"""
            logger.info(f"LOG_API_CALL CALLED: {method} {endpoint}, credential_id: {credential_id_for_logging}, user_id: {user_id}")
            try:
                # Ensure request_headers is a dict (not a string)
                if isinstance(request_headers, str):
                    try:
                        import json
                        request_headers = json.loads(request_headers)
                    except:
                        request_headers = {}
                
                # Ensure request_body is properly formatted
                if request_body is not None and isinstance(request_body, str):
                    try:
                        import json
                        request_body = json.loads(request_body)
                    except:
                        pass  # Keep as string if not JSON
                
                logger.info(f"Creating log entry with trigger='connection_test', credential_id={credential_id_for_logging}")
                
                # Create log entry - always include trigger
                log_entry = Cin7ApiLog(
                    id=uuid.uuid4(),
                    client_id=credential_id_for_logging,
                    user_id=user_id,
                    upload_id=None,
                    trigger='connection_test',  # Always set trigger
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
                logger.info(f"Log entry created, ID: {log_entry.id}, about to add to session")
                db.session.add(log_entry)
                logger.info(f"Log entry added to session, about to commit")
                db.session.commit()
                logger.info(f"✓ COMMITTED: Logged API call: {method} {endpoint} - Status: {response_status}, credential_id: {credential_id_for_logging}, user_id: {user_id}, trigger: connection_test, log_id: {log_entry.id}")
            except Exception as e:
                logger.error(f"✗ Error logging API call: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                try:
                    db.session.rollback()
                    logger.error(f"Rolled back database session after error")
                except Exception as rollback_error:
                    logger.error(f"Error during rollback: {str(rollback_error)}")
        
        # Initialize API client with logging
        logger.info(f"Initializing API client with logger_callback for connection test")
        logger.info(f"credential_id_for_logging: {credential_id_for_logging}, user_id: {user_id}")
        api_client = Cin7SalesAPI(
            account_id=str(row.account_id),
            application_key=str(row.application_key),
            base_url='https://inventory.dearsystems.com/ExternalApi/v2/',
            logger_callback=log_api_call
        )
        logger.info(f"API client initialized, logger_callback set: {api_client.logger_callback is not None}")
        
        # Make API call using the client (this will automatically log via callback)
        company_info = api_client.get_company()
        
        # Return response
        if company_info:
            return jsonify({
                'success': True,
                'message': 'Credentials are valid',
                'company_info': company_info
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve company information - credentials may be invalid'
            }), 200
            
    except Exception as e:
        logger.error(f"ERROR in test_credentials endpoint: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Try to log the error to database
        try:
            error_log = Cin7ApiLog(
                id=uuid.uuid4(),
                client_id=None,
                user_id=user_id if 'user_id' in locals() else None,
                upload_id=None,
                trigger='endpoint_error',
                endpoint='/test_error',
                method='POST',
                request_url=f'/clients/{client_id}/test',
                request_headers={},
                request_body={},
                response_status=500,
                response_body={'error': str(e)},
                error_message=str(e),
                duration_ms=0
            )
            db.session.add(error_log)
            db.session.commit()
        except Exception as db_error:
            try:
                db.session.rollback()
            except:
                pass
        
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'An error occurred while testing credentials'
        }), 500
