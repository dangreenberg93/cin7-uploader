"""Add cached customer and product tables

Revision ID: add_cached_tables
Revises: add_task_tracking_to_sales_order_result
Create Date: 2025-12-27 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_cached_tables'
down_revision = 'add_csv_content_to_upload'
branch_labels = None
depends_on = None


def upgrade():
    # Create cached_customer table
    op.create_table(
        'cached_customer',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('client_erp_credentials_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('cin7_customer_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('customer_data', postgresql.JSON, nullable=False),
        sa.Column('cached_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        schema='cin7_uploader'
    )
    op.create_index('ix_cached_customer_client_erp_credentials_id', 'cached_customer', ['client_erp_credentials_id'], schema='cin7_uploader')
    op.create_index('ix_cached_customer_cin7_customer_id', 'cached_customer', ['cin7_customer_id'], schema='cin7_uploader')
    op.create_index('ix_cached_customer_cached_at', 'cached_customer', ['cached_at'], schema='cin7_uploader')
    op.create_unique_constraint('cached_customer_cred_customer_unique', 'cached_customer', ['client_erp_credentials_id', 'cin7_customer_id'], schema='cin7_uploader')
    
    # Create cached_product table
    op.create_table(
        'cached_product',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('client_erp_credentials_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('cin7_product_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sku', sa.String(255), nullable=False),
        sa.Column('product_data', postgresql.JSON, nullable=False),
        sa.Column('cached_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        schema='cin7_uploader'
    )
    op.create_index('ix_cached_product_client_erp_credentials_id', 'cached_product', ['client_erp_credentials_id'], schema='cin7_uploader')
    op.create_index('ix_cached_product_cin7_product_id', 'cached_product', ['cin7_product_id'], schema='cin7_uploader')
    op.create_index('ix_cached_product_sku', 'cached_product', ['sku'], schema='cin7_uploader')
    op.create_index('ix_cached_product_cached_at', 'cached_product', ['cached_at'], schema='cin7_uploader')
    op.create_unique_constraint('cached_product_cred_sku_unique', 'cached_product', ['client_erp_credentials_id', 'sku'], schema='cin7_uploader')


def downgrade():
    op.drop_table('cached_product', schema='cin7_uploader')
    op.drop_table('cached_customer', schema='cin7_uploader')

