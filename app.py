"""Main Flask application for Cin7 Uploader"""
import os
from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from config import config

def create_app(config_name=None):
    """Create and configure Flask app"""
    app = Flask(__name__, static_folder='frontend/build', static_url_path='')
    
    # Load configuration
    config_name = config_name or os.environ.get('FLASK_ENV', 'development')
    app.config.from_object(config[config_name])
    
    # Configure Flask to trust X-Forwarded-* headers from Cloud Run proxy
    if config_name == 'production':
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_for=1)
        app.config['PREFERRED_URL_SCHEME'] = 'https'
    
    # Configure database
    # Normalize postgres:// to postgresql:// (SQLAlchemy prefers postgresql://)
    database_url = app.config['DATABASE_URL']
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
        app.config['DATABASE_URL'] = database_url
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # Configure connection pool for Cloud Run (serverless) - optimized for transaction pooler
    # Transaction pooler handles connection pooling at the database level, so we use smaller pools
    # Supabase transaction pooler requires SSL connections
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 2,  # Small pool for transaction pooler (connections are pooled at DB level)
        'max_overflow': 5,  # Minimal overflow since transaction pooler handles pooling
        'pool_pre_ping': True,  # Verify connections before using them
        'pool_recycle': 1800,  # Recycle connections after 30 minutes (shorter for serverless)
        'connect_args': {
            'connect_timeout': 10,  # 10 second connection timeout
            'sslmode': 'require',  # Supabase transaction pooler requires SSL
        }
    }
    
    # Initialize database connection
    from database import db
    db.init_app(app)
    
    # Initialize extensions
    CORS(app, origins=app.config['CORS_ORIGINS'], supports_credentials=True, 
         allow_headers=['Content-Type', 'Authorization'],
         methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
    jwt = JWTManager(app)
    
    # Initialize Flask-Mail
    from extensions import mail
    mail.init_app(app)
    
    # Initialize Flask-Migrate
    from flask_migrate import Migrate
    migrate = Migrate(app, db)
    
    # Register blueprints
    from routes.auth import auth_bp
    from routes.clients import clients_bp
    from routes.credentials import credentials_bp
    from routes.mappings import mappings_bp
    from routes.settings import settings_bp
    from routes.sales import sales_bp
    from routes.admin import admin_bp
    from routes.webhooks import webhooks_bp
    
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    
    app.register_blueprint(clients_bp, url_prefix='/api/clients')
    app.register_blueprint(credentials_bp, url_prefix='/api/credentials')
    app.register_blueprint(mappings_bp, url_prefix='/api/mappings')
    app.register_blueprint(settings_bp, url_prefix='/api/settings')
    app.register_blueprint(sales_bp, url_prefix='/api/sales')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(webhooks_bp, url_prefix='/api/webhooks')
    
    # Error handler to ensure CORS headers are included in error responses
    @app.errorhandler(500)
    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def handle_error(error):
        from flask import jsonify
        response = jsonify({
            'error': str(error.description) if hasattr(error, 'description') else str(error),
            'code': error.code if hasattr(error, 'code') else 500
        })
        response.status_code = error.code if hasattr(error, 'code') else 500
        # Add CORS headers
        response.headers.add('Access-Control-Allow-Origin', app.config['CORS_ORIGINS'][0] if app.config['CORS_ORIGINS'] else '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response
    
    # Serve React app - catch-all route for frontend
    # Note: Flask routes are matched by specificity first, so blueprint routes (like /api/sales/validate)
    # will be matched before this catch-all. This route only handles non-API paths.
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve(path):
        # For non-API routes, serve static files if they exist, otherwise serve index.html
        # API routes are handled by blueprints registered above, so they won't reach here
        if path != "" and os.path.exists(app.static_folder + '/' + path):
            return app.send_static_file(path)
        else:
            return app.send_static_file('index.html')
    
    return app

if __name__ == '__main__':
    app = create_app()
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=True, host='0.0.0.0', port=port)
