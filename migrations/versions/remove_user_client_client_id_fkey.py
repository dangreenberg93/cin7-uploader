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
    try:
        op.drop_constraint(
            'user_client_client_id_fkey',
            'user_client',
            schema='cin7_uploader',
            type_='foreignkey'
        )
        print("Successfully dropped foreign key constraint 'user_client_client_id_fkey'")
    except Exception as e:
        # Constraint might not exist or have a different name
        print(f"Could not drop constraint 'user_client_client_id_fkey': {str(e)}")
        # Try alternative constraint names
        try:
            op.drop_constraint(
                'cin7_uploader_user_client_client_id_fkey',
                'user_client',
                schema='cin7_uploader',
                type_='foreignkey'
            )
            print("Successfully dropped foreign key constraint 'cin7_uploader_user_client_client_id_fkey'")
        except Exception as e2:
            print(f"Could not drop alternative constraint: {str(e2)}")
            # Try using raw SQL as fallback
            op.execute("""
                DO $$ 
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.table_constraints 
                        WHERE constraint_schema = 'cin7_uploader' 
                        AND table_name = 'user_client' 
                        AND constraint_type = 'FOREIGN KEY'
                        AND constraint_name LIKE '%client_id%'
                    ) THEN
                        ALTER TABLE cin7_uploader.user_client 
                        DROP CONSTRAINT IF EXISTS user_client_client_id_fkey;
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

