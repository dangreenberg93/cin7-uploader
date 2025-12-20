#!/usr/bin/env python3
"""
Run database migrations
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from flask_migrate import upgrade

def run_migrations():
    """Run all pending migrations"""
    app = create_app()
    
    with app.app_context():
        print("Running database migrations...")
        try:
            upgrade()
            print("✓ Migrations completed successfully!")
            return True
        except Exception as e:
            print(f"✗ Migration failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == '__main__':
    if run_migrations():
        sys.exit(0)
    else:
        sys.exit(1)



