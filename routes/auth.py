"""Simple email/password authentication"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from sqlalchemy import text
from database import db
from werkzeug.security import generate_password_hash, check_password_hash
from utils.email import send_password_reset_email
import uuid
import secrets
import os
from datetime import datetime, timedelta
import bcrypt

auth_bp = Blueprint('auth', __name__)

# Reference to fireflies.users table (cross-schema)
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from database import db

class User(db.Model):
    """User model from fireflies schema - shared with fireflies-tasks"""
    __tablename__ = 'users'
    __table_args__ = {'schema': 'fireflies', 'extend_existing': True}
    
    id = Column(UUID(as_uuid=True), primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)
    name = Column(String(255))
    google_id = Column(String(255), unique=True, nullable=True, index=True)
    avatar_url = Column(String(500), nullable=True)
    role = Column(String(50), nullable=True, default='user')  # Global role: 'admin', 'user', or None
    last_active = Column(DateTime, nullable=True)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

@auth_bp.route('/login', methods=['POST'])
def login():
    """Login with email and password"""
    try:
        data = request.get_json()
        
        if not data:
            print("Login attempt: No request data")
            return jsonify({'error': 'Email and password are required'}), 400
        
        if not data.get('email') or not data.get('password'):
            print(f"Login attempt: Missing fields - email: {bool(data.get('email'))}, password: {bool(data.get('password'))}")
            return jsonify({'error': 'Email and password are required'}), 400
        
        email = data.get('email', '').lower().strip()
        password = data.get('password')
        
        print(f"Login attempt for email: {email}")
        
        # Find user by email
        user = User.query.filter_by(email=email).first()
        
        if not user:
            print(f"Login failed: User not found for email {email}")
            return jsonify({'error': 'Invalid email or password'}), 401
        
        print(f"User found: {user.email}, has password_hash: {bool(user.password_hash)}")
        
        # Check password
        if not user.password_hash:
            print(f"Login failed: No password hash for user {email}")
            return jsonify({'error': 'Invalid email or password'}), 401
        
        # Check password - support both Werkzeug (pbkdf2) and Supabase (bcrypt) formats
        password_valid = False
        hash_str = user.password_hash
        
        # Try Werkzeug format first (pbkdf2:sha256:...)
        if hash_str.startswith('pbkdf2:'):
            password_valid = check_password_hash(hash_str, password)
            print(f"Password check (pbkdf2) result: {password_valid}")
        # Try bcrypt format (Supabase uses bcrypt - starts with $2a$, $2b$, or $2y$)
        elif hash_str.startswith('$2'):
            try:
                # bcrypt expects bytes
                password_bytes = password.encode('utf-8')
                hash_bytes = hash_str.encode('utf-8')
                password_valid = bcrypt.checkpw(password_bytes, hash_bytes)
                print(f"Password check (bcrypt) result: {password_valid}")
            except Exception as e:
                print(f"Error checking bcrypt password: {str(e)}")
                password_valid = False
        else:
            # Fallback to Werkzeug for unknown formats
            password_valid = check_password_hash(hash_str, password)
            print(f"Password check (fallback) result: {password_valid}")
        
        if not password_valid:
            print(f"Login failed: Invalid password for user {email}")
            return jsonify({'error': 'Invalid email or password'}), 401
        
        # Update last_active
        user.last_active = datetime.utcnow()
        db.session.commit()
        
        # Create access token
        access_token = create_access_token(identity=str(user.id))
        
        print(f"Login successful for user {email}")
        
        return jsonify({
            'token': access_token,
            'user': {
                'id': str(user.id),
                'email': user.email,
                'name': user.name,
                'avatar_url': user.avatar_url
            }
        }), 200
        
    except Exception as e:
        print(f"Error logging in: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to login: {str(e)}'}), 500

@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Get current authenticated user"""
    import uuid as uuid_lib
    
    try:
        user_id = get_jwt_identity()
        
        # Convert string UUID to UUID object if needed
        try:
            if isinstance(user_id, str):
                user_id = uuid_lib.UUID(user_id)
        except (ValueError, AttributeError) as e:
            return jsonify({'error': 'Invalid user ID format'}), 400
        
        user = User.query.filter_by(id=user_id).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        user.last_active = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'id': str(user.id),
            'email': user.email,
            'name': user.name,
            'avatar_url': user.avatar_url
        })
    except Exception as e:
        print(f"ERROR in get_current_user: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# Use database table for password reset tokens (persists across server restarts)
from database import PasswordResetToken

@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    """Request password reset - generates a reset token"""
    data = request.get_json()
    
    if not data or not data.get('email'):
        return jsonify({'error': 'Email is required'}), 400
    
    email = data.get('email', '').lower().strip()
    
    try:
        # Check if user exists
        user = User.query.filter_by(email=email).first()
        
        # Always return success (don't reveal if email exists)
        # But only generate token if user exists
        if user:
            # Generate secure token
            token = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(hours=1)  # Token valid for 1 hour
            
            # Store token in database
            reset_token = PasswordResetToken(
                token=token,
                email=email,
                expires_at=expires_at,
                used=False
            )
            db.session.add(reset_token)
            db.session.commit()
            
            # Clean up expired tokens
            cleanup_expired_tokens()
            
            # Send password reset email
            email_sent = False
            try:
                email_sent = send_password_reset_email(email, token)
                if email_sent:
                    print(f"Password reset email sent successfully to {email}")
            except Exception as email_error:
                # Suppress broken pipe and other email errors - don't let them crash the request
                error_msg = str(email_error)
                print(f"ERROR sending email to {email}: {error_msg}")
                # Only print traceback if it's not a broken pipe (which is usually just a connection issue)
                if 'Broken pipe' not in error_msg and 'BrokenPipeError' not in error_msg:
                    try:
                        import traceback
                        traceback.print_exc()
                    except:
                        pass  # Even traceback printing can fail with broken pipe
            
            # Always return success response (don't reveal if email failed)
            response_data = {
                'message': 'If an account exists with this email, a password reset link has been sent'
            }
            
            # In development, always return the token for testing
            is_dev = (os.environ.get('FLASK_ENV') == 'development' or 
                     not os.environ.get('MAIL_USERNAME') or 
                     not email_sent)
            if is_dev:
                frontend_url = os.environ.get('FRONTEND_URL', 'http://localhost:3000')
                reset_link = f"{frontend_url}/reset-password?token={token}"
                response_data['dev_reset_link'] = reset_link
                response_data['dev_token'] = token
                print(f"DEV MODE: Reset link: {reset_link}")
            
            return jsonify(response_data), 200
        else:
            # Return same response to prevent email enumeration
            return jsonify({
                'message': 'If an account exists with this email, a reset token has been generated'
            }), 200
        
    except Exception as e:
        error_msg = str(e)
        print(f"Error in forgot_password: {error_msg}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to process request: {error_msg}'}), 500

@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    """Reset password using a reset token"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'Request body is required'}), 400
    
    token = data.get('token')
    password = data.get('password')
    
    if not token:
        return jsonify({'error': 'Token is required'}), 400
    
    if not password:
        return jsonify({'error': 'Password is required'}), 400
    
    # Validate password length
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    
    try:
        # Clean up expired tokens first
        cleanup_expired_tokens()
        
        # Check if token exists and is valid in database
        reset_token = PasswordResetToken.query.filter_by(
            token=token,
            used=False
        ).first()
        
        if not reset_token:
            return jsonify({'error': 'Invalid or expired reset token'}), 400
        
        # Check if token has expired
        if datetime.utcnow() > reset_token.expires_at:
            reset_token.used = True  # Mark as used so it won't be found again
            db.session.commit()
            return jsonify({'error': 'Reset token has expired'}), 400
        
        email = reset_token.email
        
        # Find user
        user = User.query.filter_by(email=email).first()
        if not user:
            reset_token.used = True
            db.session.commit()
            return jsonify({'error': 'User not found'}), 404
        
        # Update password - use pbkdf2:sha256 method for compatibility
        new_password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        db.session.execute(
            text("""
                UPDATE fireflies.users 
                SET password_hash = :password_hash, updated_at = :updated_at
                WHERE id = :user_id
            """),
            {
                'password_hash': new_password_hash,
                'updated_at': datetime.utcnow(),
                'user_id': user.id
            }
        )
        
        # Mark token as used
        reset_token.used = True
        db.session.commit()
        
        # Create access token for automatic login
        access_token = create_access_token(identity=str(user.id))
        
        # Return token and user data for automatic login
        return jsonify({
            'message': 'Password reset successfully',
            'token': access_token,
            'user': {
                'id': str(user.id),
                'email': user.email,
                'name': user.name
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        error_msg = str(e)
        print(f"Error resetting password: {error_msg}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to reset password: {error_msg}'}), 500

def cleanup_expired_tokens():
    """Remove expired tokens from database"""
    now = datetime.utcnow()
    # Mark expired tokens as used (they won't be usable anyway)
    PasswordResetToken.query.filter(
        PasswordResetToken.expires_at < now,
        PasswordResetToken.used == False
    ).update({'used': True}, synchronize_session=False)
    db.session.commit()
