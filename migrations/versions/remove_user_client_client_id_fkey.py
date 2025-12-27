"""Remove foreign key constraint from user_client.client_id

Revision ID: remove_user_client_fkey
Revises: 1766141001_add_user_role_column
Create Date: 2025-01-XX XX:XX:XX.XXXXXX

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'remove_user_client_fkey'
down_revision = 'add_active_to_cred'  # Points to latest migration
branch_labels = None
depends_on = None


def upgrade():
    # Drop the foreign key constraint from user_client.client_id
    # This allows client_id to reference voyager.client_erp_credentials.id directly
    # instead of requiring it to reference cin7_uploader.client.id
    # Use a single DO block to safely check and drop any existing constraint
    op.execute("""
        DO $$ 
        DECLARE
            constraint_name_var TEXT;
        BEGIN
            -- Find any foreign key constraint on client_id column
            SELECT constraint_name INTO constraint_name_var
            FROM information_schema.table_constraints 
            WHERE constraint_schema = 'cin7_uploader' 
            AND table_name = 'user_client' 
            AND constraint_type = 'FOREIGN KEY'
            AND constraint_name LIKE '%client_id%'
            LIMIT 1;
            
            -- Drop the constraint if it exists
            IF constraint_name_var IS NOT NULL THEN
                EXECUTE format('ALTER TABLE cin7_uploader.user_client DROP CONSTRAINT IF EXISTS %I', constraint_name_var);
            END IF;
        END $$;
    """)


def downgrade():
    # Re-add the foreign key constraint (if needed for rollback)
    # Note: This assumes the cin7_uploader.client table still exists
    try:
        op.create_foreign_key(
            'user_client_client_id_fkey',
            'user_client',
            'client',
            ['client_id'],
            ['id'],
            source_schema='cin7_uploader',
            referent_schema='cin7_uploader'
        )
    except Exception as e:
        print(f"Could not recreate foreign key constraint: {str(e)}")

