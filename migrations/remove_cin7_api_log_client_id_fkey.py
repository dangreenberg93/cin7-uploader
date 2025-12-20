"""Remove incorrect foreign key constraint on cin7_api_log.client_id

The client_id column actually stores credential_id (from voyager.client_erp_credentials),
not client_id (from cin7_uploader.client), so the foreign key constraint is incorrect.

Revision ID: remove_client_id_fkey
Revises: 
Create Date: 2025-12-19
"""
import sys
import os

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app import create_app
from database import db

def upgrade():
    """Remove the incorrect foreign key constraint on cin7_api_log.client_id"""
    app = create_app()
    with app.app_context():
        with db.engine.connect() as conn:
            # Check if constraint exists
            check_query = text("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_schema = 'cin7_uploader' 
                AND table_name = 'cin7_api_log' 
                AND constraint_name = 'cin7_api_log_client_id_fkey'
            """)
            result = conn.execute(check_query)
            if result.fetchone():
                # Drop the foreign key constraint
                drop_constraint_query = text("""
                    ALTER TABLE cin7_uploader.cin7_api_log 
                    DROP CONSTRAINT IF EXISTS cin7_api_log_client_id_fkey
                """)
                conn.execute(drop_constraint_query)
                conn.commit()
                print("Successfully removed foreign key constraint 'cin7_api_log_client_id_fkey'")
            else:
                print("Foreign key constraint 'cin7_api_log_client_id_fkey' does not exist, skipping")

def downgrade():
    """Re-add the foreign key constraint (not recommended, but included for completeness)"""
    app = create_app()
    with app.app_context():
        with db.engine.connect() as conn:
            # Note: This would fail if credential_ids don't match client_ids
            # So we'll skip this in downgrade
            print("Skipping downgrade - foreign key constraint should not be re-added")
            pass

if __name__ == '__main__':
    upgrade()


