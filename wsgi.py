"""WSGI entry point for production"""
import os
from app import create_app

app = create_app('production')

# Cloud Run sets PORT environment variable
# Gunicorn will use it automatically via --bind :$PORT
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
