"""add client_erp_credentials_id to sales_order_upload

Revision ID: add_client_erp_credentials_id_to_upload
Revises: add_task_tracking_to_sales_order_result
Create Date: 2025-12-26 17:25:58.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'add_client_erp_credentials_id_to_upload'
down_revision = 'add_task_tracking_to_sales_order_result'
branch_labels = None
depends_on = None


def upgrade():
    # Add client_erp_credentials_id column to sales_order_upload
    op.add_column('sales_order_upload', 
                  sa.Column('client_erp_credentials_id', postgresql.UUID(as_uuid=True), nullable=True),
                  schema='cin7_uploader')
    
    # Create index for the new column
    op.create_index('ix_sales_order_upload_client_erp_credentials_id', 
                    'sales_order_upload', 
                    ['client_erp_credentials_id'],
                    schema='cin7_uploader')
    
    # Add foreign key constraint
    op.create_foreign_key(
        'fk_sales_order_upload_client_erp_credentials_id',
        'sales_order_upload', 'client_erp_credentials',
        ['client_erp_credentials_id'], ['id'],
        source_schema='cin7_uploader',
        referent_schema='voyager'
    )


def downgrade():
    # Remove foreign key constraint
    op.drop_constraint('fk_sales_order_upload_client_erp_credentials_id', 
                      'sales_order_upload', 
                      type_='foreignkey',
                      schema='cin7_uploader')
    
    # Remove index
    op.drop_index('ix_sales_order_upload_client_erp_credentials_id', 
                  'sales_order_upload',
                  schema='cin7_uploader')
    
    # Remove client_erp_credentials_id column
    op.drop_column('sales_order_upload', 'client_erp_credentials_id', schema='cin7_uploader')


