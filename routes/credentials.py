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
        # Check if customer default columns exist
        check_columns_query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'voyager' 
            AND table_name = 'client_erp_credentials' 
            AND column_name IN ('default_location', 'customer_account_receivable', 'customer_revenue_account', 'customer_tax_rule', 'customer_attribute_set')
        """)
        existing_columns = {row[0] for row in db.session.execute(check_columns_query).fetchall()}
        
        has_default_location = 'default_location' in existing_columns
        has_customer_account_receivable = 'customer_account_receivable' in existing_columns
        has_customer_revenue_account = 'customer_revenue_account' in existing_columns
        has_customer_tax_rule = 'customer_tax_rule' in existing_columns
        has_customer_attribute_set = 'customer_attribute_set' in existing_columns
        
        # Build SELECT fields
        select_fields = [
            'cec.id',
            'cec.client_id',
            'cec.connection_name',
            'cec.cin7_api_auth_accountid as account_id',
            'cec.cin7_api_auth_applicationkey as application_key',
            'cec.sale_type',
            'cec.tax_rule',
            'cec.default_status'
        ]
        
        if has_default_location:
            select_fields.append('cec.default_location')
        else:
            select_fields.append('NULL as default_location')
        
        if has_customer_account_receivable:
            select_fields.append('cec.customer_account_receivable')
        else:
            select_fields.append('NULL as customer_account_receivable')
        
        if has_customer_revenue_account:
            select_fields.append('cec.customer_revenue_account')
        else:
            select_fields.append('NULL as customer_revenue_account')
        
        if has_customer_tax_rule:
            select_fields.append('cec.customer_tax_rule')
        else:
            select_fields.append('NULL as customer_tax_rule')
        
        if has_customer_attribute_set:
            select_fields.append('cec.customer_attribute_set')
        else:
            select_fields.append('NULL as customer_attribute_set')
        
        select_fields.append('c.name as client_name')
        
        query = text(f"""
            SELECT 
                {', '.join(select_fields)}
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
        response_data = {
            'id': str(row.id),
            'client_id': str(row.client_id) if row.client_id else None,
            'connection_name': row.connection_name,
            'account_id': str(row.account_id),
            'application_key': str(row.application_key),
            'base_url': 'https://inventory.dearsystems.com/ExternalApi/v2/',  # Default base URL
            'sale_type': row.sale_type,
            'tax_rule': row.tax_rule,
            'default_status': row.default_status,
            'default_location': str(row.default_location) if has_default_location and row.default_location else None
        }
        
        # Add customer default fields if columns exist
        if has_customer_account_receivable and hasattr(row, 'customer_account_receivable'):
            # Account codes are stored as strings
            response_data['customer_account_receivable'] = row.customer_account_receivable if row.customer_account_receivable else None
        else:
            response_data['customer_account_receivable'] = None
        
        if has_customer_revenue_account and hasattr(row, 'customer_revenue_account'):
            # Account codes are stored as strings
            response_data['customer_revenue_account'] = row.customer_revenue_account if row.customer_revenue_account else None
        else:
            response_data['customer_revenue_account'] = None
        
        if has_customer_tax_rule and hasattr(row, 'customer_tax_rule'):
            response_data['customer_tax_rule'] = str(row.customer_tax_rule) if row.customer_tax_rule else None
        else:
            response_data['customer_tax_rule'] = None
        
        if has_customer_attribute_set and hasattr(row, 'customer_attribute_set'):
            response_data['customer_attribute_set'] = row.customer_attribute_set
        else:
            response_data['customer_attribute_set'] = None
        
        return jsonify(response_data)
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
        
        # Check which columns exist for customer defaults
        check_columns_query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'voyager' 
            AND table_name = 'client_erp_credentials' 
            AND column_name IN ('default_location', 'customer_account_receivable', 'customer_revenue_account', 'customer_tax_rule', 'customer_attribute_set')
        """)
        existing_columns = {row[0] for row in db.session.execute(check_columns_query).fetchall()}
        
        if 'default_location' in data and 'default_location' in existing_columns:
            if data['default_location']:
                try:
                    location_uuid = uuid.UUID(data['default_location'])
                    updates.append('default_location = :default_location')
                    params['default_location'] = location_uuid
                except (ValueError, AttributeError):
                    return jsonify({'error': 'Invalid default_location format (must be UUID)'}), 400
            else:
                updates.append('default_location = NULL')
        
        if 'customer_account_receivable' in data and 'customer_account_receivable' in existing_columns:
            if data['customer_account_receivable']:
                # Account codes are strings, not UUIDs
                updates.append('customer_account_receivable = :customer_account_receivable')
                params['customer_account_receivable'] = str(data['customer_account_receivable']).strip()
            else:
                updates.append('customer_account_receivable = NULL')
        
        if 'customer_revenue_account' in data and 'customer_revenue_account' in existing_columns:
            if data['customer_revenue_account']:
                # Account codes are strings, not UUIDs
                updates.append('customer_revenue_account = :customer_revenue_account')
                params['customer_revenue_account'] = str(data['customer_revenue_account']).strip()
            else:
                updates.append('customer_revenue_account = NULL')
        
        if 'customer_tax_rule' in data and 'customer_tax_rule' in existing_columns:
            if data['customer_tax_rule']:
                try:
                    tax_uuid = uuid.UUID(data['customer_tax_rule'])
                    updates.append('customer_tax_rule = :customer_tax_rule')
                    params['customer_tax_rule'] = tax_uuid
                except (ValueError, AttributeError):
                    return jsonify({'error': 'Invalid customer_tax_rule format (must be UUID)'}), 400
            else:
                updates.append('customer_tax_rule = NULL')
        
        if 'customer_attribute_set' in data and 'customer_attribute_set' in existing_columns:
            updates.append('customer_attribute_set = :customer_attribute_set')
            params['customer_attribute_set'] = data['customer_attribute_set'] or None
        
        if not updates:
            return jsonify({'error': 'No fields to update'}), 400
        
        # Build RETURNING clause with available columns
        return_fields_list = ['id', 'sale_type', 'tax_rule', 'default_status']
        if 'default_location' in existing_columns:
            return_fields_list.append('default_location')
        if 'customer_account_receivable' in existing_columns:
            return_fields_list.append('customer_account_receivable')
        if 'customer_revenue_account' in existing_columns:
            return_fields_list.append('customer_revenue_account')
        if 'customer_tax_rule' in existing_columns:
            return_fields_list.append('customer_tax_rule')
        if 'customer_attribute_set' in existing_columns:
            return_fields_list.append('customer_attribute_set')
        return_fields = ', '.join(return_fields_list)
        
        query = text(f"""
            UPDATE voyager.client_erp_credentials
            SET {', '.join(updates)}
            WHERE erp = 'cin7_core'
            AND (client_id = :client_id OR id = :client_id)
            RETURNING {return_fields}
        """)
        
        result = db.session.execute(query, params)
        db.session.commit()
        
        row = result.fetchone()
        if not row:
            return jsonify({'error': 'Credentials not found'}), 404
        
        response_data = {
            'id': str(row.id),
            'sale_type': row.sale_type,
            'tax_rule': row.tax_rule,
            'default_status': row.default_status
        }
        
        if 'default_location' in existing_columns and hasattr(row, 'default_location'):
            response_data['default_location'] = str(row.default_location) if row.default_location else None
        
        if 'customer_account_receivable' in existing_columns and hasattr(row, 'customer_account_receivable'):
            response_data['customer_account_receivable'] = str(row.customer_account_receivable) if row.customer_account_receivable else None
        
        if 'customer_revenue_account' in existing_columns and hasattr(row, 'customer_revenue_account'):
            response_data['customer_revenue_account'] = str(row.customer_revenue_account) if row.customer_revenue_account else None
        
        if 'customer_tax_rule' in existing_columns and hasattr(row, 'customer_tax_rule'):
            response_data['customer_tax_rule'] = str(row.customer_tax_rule) if row.customer_tax_rule else None
        
        if 'customer_attribute_set' in existing_columns and hasattr(row, 'customer_attribute_set'):
            response_data['customer_attribute_set'] = row.customer_attribute_set
        
        return jsonify(response_data)
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error updating credential settings: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@credentials_bp.route('/clients/<client_id>/accounts', methods=['GET'])
@jwt_required()
def get_accounts(client_id):
    """Get accounts from Cin7 for client"""
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client ID format'}), 400
    
    try:
        # Get credentials
        query = text("""
            SELECT 
                cec.cin7_api_auth_accountid as account_id,
                cec.cin7_api_auth_applicationkey as application_key
            FROM voyager.client_erp_credentials cec
            WHERE cec.erp = 'cin7_core'
            AND (cec.client_id = :client_id OR cec.id = :client_id)
        """)
        result = db.session.execute(query, {'client_id': client_uuid})
        cred_row = result.fetchone()
        
        if not cred_row or not cred_row.account_id or not cred_row.application_key:
            return jsonify({'error': 'Cin7 credentials not configured'}), 404
        
        # Create API client
        api_client = Cin7SalesAPI(
            account_id=str(cred_row.account_id),
            application_key=str(cred_row.application_key),
            base_url='https://inventory.dearsystems.com/ExternalApi/v2/'
        )
        
        accounts = api_client.get_accounts()
        import sys
        
        # Build debug info similar to locations endpoint
        debug_info = {
            'account_id': f"{str(cred_row.account_id)[:8]}...",
            'api_url': 'https://inventory.dearsystems.com/ExternalApi/v2/ref/account',
            'parsed_accounts': accounts[:3] if accounts else [],  # First 3 for debugging
            'parsed_accounts_count': len(accounts) if accounts else 0
        }
        
        # Get debug info from API client if available (similar to locations)
        if hasattr(api_client, '_last_account_response'):
            debug_info['raw_response'] = api_client._last_account_response
        
        print(f"DEBUG get_accounts endpoint: Returning {len(accounts) if accounts else 0} accounts", file=sys.stderr)
        return jsonify({
            'accounts': accounts if accounts else [],
            '_debug': debug_info
        }), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@credentials_bp.route('/clients/<client_id>/tax-rules', methods=['GET'])
@jwt_required()
def get_tax_rules(client_id):
    """Get tax rules from Cin7 for client"""
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client ID format'}), 400
    
    try:
        # Get credentials
        query = text("""
            SELECT 
                cec.cin7_api_auth_accountid as account_id,
                cec.cin7_api_auth_applicationkey as application_key
            FROM voyager.client_erp_credentials cec
            WHERE cec.erp = 'cin7_core'
            AND (cec.client_id = :client_id OR cec.id = :client_id)
        """)
        result = db.session.execute(query, {'client_id': client_uuid})
        cred_row = result.fetchone()
        
        if not cred_row or not cred_row.account_id or not cred_row.application_key:
            return jsonify({'error': 'Cin7 credentials not configured'}), 404
        
        # Create API client
        api_client = Cin7SalesAPI(
            account_id=str(cred_row.account_id),
            application_key=str(cred_row.application_key),
            base_url='https://inventory.dearsystems.com/ExternalApi/v2/'
        )
        
        tax_rules = api_client.get_tax_rules()
        import sys
        
        # Build debug info similar to locations endpoint
        debug_info = {
            'account_id': f"{str(cred_row.account_id)[:8]}...",
            'api_url': 'https://inventory.dearsystems.com/ExternalApi/v2/ref/tax',
            'parsed_tax_rules': tax_rules if tax_rules else [],
            'parsed_tax_rules_count': len(tax_rules) if tax_rules else 0
        }
        
        print(f"DEBUG get_tax_rules endpoint: Returning {len(tax_rules) if tax_rules else 0} tax rules", file=sys.stderr)
        return jsonify({
            'tax_rules': tax_rules if tax_rules else [],
            '_debug': debug_info
        }), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@credentials_bp.route('/clients/<client_id>/attribute-sets', methods=['GET'])
@jwt_required()
def get_attribute_sets(client_id):
    """Get attribute sets from Cin7 for client"""
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client ID format'}), 400
    
    try:
        # Get credentials
        query = text("""
            SELECT 
                cec.cin7_api_auth_accountid as account_id,
                cec.cin7_api_auth_applicationkey as application_key
            FROM voyager.client_erp_credentials cec
            WHERE cec.erp = 'cin7_core'
            AND (cec.client_id = :client_id OR cec.id = :client_id)
        """)
        result = db.session.execute(query, {'client_id': client_uuid})
        cred_row = result.fetchone()
        
        if not cred_row or not cred_row.account_id or not cred_row.application_key:
            return jsonify({'error': 'Cin7 credentials not configured'}), 404
        
        # Create API client
        api_client = Cin7SalesAPI(
            account_id=str(cred_row.account_id),
            application_key=str(cred_row.application_key),
            base_url='https://inventory.dearsystems.com/ExternalApi/v2/'
        )
        
        attribute_sets = api_client.get_attribute_sets()
        import sys
        
        # Build debug info similar to locations endpoint
        debug_info = {
            'account_id': f"{str(cred_row.account_id)[:8]}...",
            'api_url': 'https://inventory.dearsystems.com/ExternalApi/v2/ref/attributeset',
            'parsed_attribute_sets': attribute_sets[:3] if attribute_sets else [],  # First 3 for debugging
            'parsed_attribute_sets_count': len(attribute_sets) if attribute_sets else 0
        }
        
        # Get debug info from API client if available (similar to locations)
        if hasattr(api_client, '_last_attribute_set_response'):
            debug_info['raw_response'] = api_client._last_attribute_set_response
        
        print(f"DEBUG get_attribute_sets endpoint: Returning {len(attribute_sets) if attribute_sets else 0} attribute sets", file=sys.stderr)
        return jsonify({
            'attribute_sets': attribute_sets if attribute_sets else [],
            '_debug': debug_info
        }), 200
    except Exception as e:
        import traceback
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
                
                # If response_body is a string (raw JSON), store it in raw_response_body_text
                # and parse it for response_body column
                raw_response_text = None
                parsed_response_body = response_body
                if isinstance(response_body, str):
                    raw_response_text = response_body
                    try:
                        import json
                        parsed_response_body = json.loads(response_body)
                    except (json.JSONDecodeError, TypeError):
                        # If parsing fails, keep as string
                        parsed_response_body = response_body
                
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
                    response_body=parsed_response_body,
                    raw_response_body_text=raw_response_text,
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

@credentials_bp.route('/clients/<client_id>/locations', methods=['GET'])
@jwt_required()
def get_locations(client_id):
    """Get available locations from Cin7 for a client"""
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid client ID format'}), 400
    
    try:
        # Get credentials
        query = text("""
            SELECT 
                cec.cin7_api_auth_accountid as account_id,
                cec.cin7_api_auth_applicationkey as application_key
            FROM voyager.client_erp_credentials cec
            WHERE cec.erp = 'cin7_core'
            AND (cec.client_id = :client_id OR cec.id = :client_id)
        """)
        
        result = db.session.execute(query, {'client_id': client_uuid})
        row = result.fetchone()
        
        if not row or not row.account_id or not row.application_key:
            return jsonify({'error': 'Credentials not found'}), 404
        
        # Initialize API client (with logging to verify the call)
        def log_api_call(endpoint, method, request_url, request_headers, request_body,
                         response_status, response_body, error_message, duration_ms):
            import sys
            print(f"\n{'='*60}", file=sys.stderr)
            print(f"API CALL TO CIN7: {method} {endpoint}", file=sys.stderr)
            print(f"  URL: {request_url}", file=sys.stderr)
            print(f"  Status: {response_status}", file=sys.stderr)
            print(f"  Response body: {response_body}", file=sys.stderr)
            print(f"  Response body type: {type(response_body)}", file=sys.stderr)
            if error_message:
                print(f"  Error: {error_message}", file=sys.stderr)
            print(f"{'='*60}\n", file=sys.stderr)
        
        api_client = Cin7SalesAPI(
            account_id=str(row.account_id),
            application_key=str(row.application_key),
            base_url='https://inventory.dearsystems.com/ExternalApi/v2/',
            logger_callback=log_api_call  # Enable logging to verify the call
        )
        
        print(f"DEBUG get_locations endpoint: Initialized API client")
        print(f"DEBUG get_locations endpoint: Account ID: {row.account_id}")
        print(f"DEBUG get_locations endpoint: Base URL: {api_client.base_url}")
        print(f"DEBUG get_locations endpoint: Full location URL will be: {api_client.base_url}ref/location")
        
        # Fetch locations from Cin7
        print(f"DEBUG get_locations endpoint: About to call api_client.get_locations()")
        
        # Store debug info to include in response
        base_url_clean = api_client.base_url.rstrip('/')
        debug_info = {
            'api_url': f'{base_url_clean}/ref/location',
            'account_id': str(row.account_id)[:8] + '...',
            'raw_response': None,
            'parsed_locations_count': 0
        }
        
        locations = api_client.get_locations()
        
        # Get debug info from API client if available
        if hasattr(api_client, '_last_location_response'):
            debug_info['raw_response'] = api_client._last_location_response
        
        debug_info['parsed_locations_count'] = len(locations) if locations else 0
        debug_info['parsed_locations'] = locations[:3] if locations else []  # First 3 for debugging
        
        print(f"DEBUG get_locations endpoint: Received {len(locations) if locations else 0} locations from API client")
        print(f"DEBUG get_locations endpoint: Locations data: {locations}")
        
        if not locations:
            # If no locations returned, return empty list (might be normal - account has no locations configured)
            print("DEBUG get_locations endpoint: No locations returned from API - this is OK if account has no locations")
            return jsonify({
                'locations': [],
                '_debug': debug_info  # Include debug info in response
            }), 200
        
        # Format locations for frontend
        formatted_locations = []
        for loc in locations:
            if isinstance(loc, dict):
                # Cin7 location structure: ID, Name, IsDefault, AddressLine1, etc.
                address_parts = []
                if loc.get('AddressLine1'):
                    address_parts.append(loc.get('AddressLine1'))
                if loc.get('AddressLine2'):
                    address_parts.append(loc.get('AddressLine2'))
                if loc.get('AddressCitySuburb'):
                    address_parts.append(loc.get('AddressCitySuburb'))
                if loc.get('AddressStateProvince'):
                    address_parts.append(loc.get('AddressStateProvince'))
                if loc.get('AddressZipPostCode'):
                    address_parts.append(loc.get('AddressZipPostCode'))
                
                formatted_locations.append({
                    'id': str(loc.get('ID', '')),
                    'name': loc.get('Name', ''),
                    'code': loc.get('Code', ''),  # May not exist in response
                    'address': ', '.join(filter(None, address_parts)) if address_parts else '',
                    'is_default': loc.get('IsDefault', False)
                })
        
        return jsonify({
            'locations': formatted_locations,
            '_debug': {
                **debug_info,
                'formatted_count': len(formatted_locations)
            }
        }), 200
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error fetching locations: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
