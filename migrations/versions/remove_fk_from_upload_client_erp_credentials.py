"""remove foreign key from sales_order_upload.client_erp_credentials_id

Revision ID: remove_fk_from_upload_client_erp_credentials
Revises: add_csv_content_to_upload
Create Date: 2025-01-XX XX:XX:XX.XXXXXX

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'remove_upload_fk'
down_revision = 'add_customer_defaults_to_cred'
branch_labels = None
depends_on = None


def upgrade():
    # Drop foreign key constraint if it exists
    # This handles the case where the previous migration created the FK
    # We're removing it because client_erp_credentials is in voyager schema
    # and cross-schema foreign keys can cause issues
    try:
        op.drop_constraint(
            'fk_sales_order_upload_client_erp_credentials_id', 
                          'sales_order_upload', 
                          type_='foreignkey',
                          schema='cin7_uploader')
    except Exception:
        # Constraint might not exist if migration was run after we removed it
        pass


def downgrade():
    # Re-add foreign key constraint (if needed for rollback)
    # Note: This will only work if the constraint was previously dropped
    op.create_foreign_key(
        'fk_sales_order_upload_client_erp_credentials_id',
        'sales_order_upload', 'client_erp_credentials',
        ['client_erp_credentials_id'], ['id'],
        source_schema='cin7_uploader',
        referent_schema='voyager'
    )

