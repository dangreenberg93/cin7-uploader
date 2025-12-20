"""Configuration settings for Cin7 Uploader app"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'jwt-secret-key-change-in-production'
    from datetime import timedelta
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=48)  # Tokens expire after 48 hours
    
    # Allow insecure transport for OAuth in development (HTTP instead of HTTPS)
    # Set OAUTHLIB_INSECURE_TRANSPORT=1 for development
    # In production, remove this and use HTTPS
    import os
    if os.environ.get('FLASK_ENV') == 'development':
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    
    # Database - same database as fireflies-tasks, different schema
    DATABASE_URL = os.environ.get('DATABASE_URL') or 'postgresql://user:password@localhost:5432/fireflies_tasks'
    
    # CORS - Add Cloud Run URL when deployed
    cors_origins = os.environ.get('CORS_ORIGINS', 'http://localhost:3000,http://localhost:5000,http://localhost:5001')
    CORS_ORIGINS = [origin.strip() for origin in cors_origins.split(',') if origin.strip()]
    
    # Google OAuth Configuration
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID') or ''
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET') or ''
    GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI') or 'http://localhost:5001/api/auth/google/callback'
    FRONTEND_URL = os.environ.get('FRONTEND_URL') or 'http://localhost:3000'
    
    # Supabase Configuration (if using Supabase for auth)
    SUPABASE_URL = os.environ.get('SUPABASE_URL') or ''
    SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY') or ''
    SUPABASE_JWT_SECRET = os.environ.get('SUPABASE_JWT_SECRET') or ''
    SUPABASE_SERVICE_ROLE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or ''
    
    # Email Configuration (Gmail SMTP)
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() in ['true', '1', 'yes']
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').lower() in ['true', '1', 'yes']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or ''
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or ''  # Gmail App Password
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or MAIL_USERNAME

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    # Cloud Run sets PORT automatically, but we'll use it if available
    # Flask app will read PORT from environment in app.py

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
