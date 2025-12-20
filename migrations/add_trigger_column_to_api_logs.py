"""Add trigger column to cin7_api_log table

Revision ID: add_trigger_column
Revises: 
Create Date: 2024-12-19

"""
import sys
import os

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app import create_app
from database import db

def upgrade():
    """Add trigger column to cin7_api_log table"""
    with db.engine.connect() as conn:
        # Check if column already exists
        check_query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'cin7_uploader' 
            AND table_name = 'cin7_api_log' 
            AND column_name = 'trigger'
        """)
        result = conn.execute(check_query)
        if result.fetchone():
            print("Column 'trigger' already exists, skipping migration")
            return
        
        # Add the trigger column
        alter_query = text("""
            ALTER TABLE cin7_uploader.cin7_api_log 
            ADD COLUMN trigger VARCHAR(50)
        """)
        conn.execute(alter_query)
        
        # Create index on trigger column for faster filtering
        index_query = text("""
            CREATE INDEX IF NOT EXISTS idx_cin7_api_log_trigger 
            ON cin7_uploader.cin7_api_log(trigger)
        """)
        conn.execute(index_query)
        
        conn.commit()
        print("Successfully added 'trigger' column to cin7_api_log table")

def downgrade():
    """Remove trigger column from cin7_api_log table"""
    with db.engine.connect() as conn:
        # Drop index first
        drop_index_query = text("""
            DROP INDEX IF EXISTS cin7_uploader.idx_cin7_api_log_trigger
        """)
        conn.execute(drop_index_query)
        
        # Drop the column
        alter_query = text("""
            ALTER TABLE cin7_uploader.cin7_api_log 
            DROP COLUMN IF EXISTS trigger
        """)
        conn.execute(alter_query)
        
        conn.commit()
        print("Successfully removed 'trigger' column from cin7_api_log table")

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        upgrade()


