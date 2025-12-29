"""Add customer_upload_mapping and product_upload_mapping tables

Revision ID: add_upload_mapping_tables
Revises: add_auto_create_to_cred
Create Date: 2025-12-28 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_upload_mapping_tables'
down_revision = 'add_auto_create_to_cred'
branch_labels = None
depends_on = None


def upgrade():
    # Create customer_upload_mapping table
    op.create_table(
        'customer_upload_mapping',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('client_erp_credentials_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('cin7_customer_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('upload_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('order_ids', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['upload_id'], ['cin7_uploader.sales_order_upload.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='cin7_uploader'
    )
    op.create_index('ix_customer_upload_mapping_client_erp_credentials_id', 'customer_upload_mapping', ['client_erp_credentials_id'], schema='cin7_uploader')
    op.create_index('ix_customer_upload_mapping_cin7_customer_id', 'customer_upload_mapping', ['cin7_customer_id'], schema='cin7_uploader')
    op.create_index('ix_customer_upload_mapping_upload_id', 'customer_upload_mapping', ['upload_id'], schema='cin7_uploader')
    op.create_index('ix_customer_upload_mapping_created_at', 'customer_upload_mapping', ['created_at'], schema='cin7_uploader')
    
    # Create product_upload_mapping table
    op.create_table(
        'product_upload_mapping',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('client_erp_credentials_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('cin7_product_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('upload_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('order_ids', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['upload_id'], ['cin7_uploader.sales_order_upload.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='cin7_uploader'
    )
    op.create_index('ix_product_upload_mapping_client_erp_credentials_id', 'product_upload_mapping', ['client_erp_credentials_id'], schema='cin7_uploader')
    op.create_index('ix_product_upload_mapping_cin7_product_id', 'product_upload_mapping', ['cin7_product_id'], schema='cin7_uploader')
    op.create_index('ix_product_upload_mapping_upload_id', 'product_upload_mapping', ['upload_id'], schema='cin7_uploader')
    op.create_index('ix_product_upload_mapping_created_at', 'product_upload_mapping', ['created_at'], schema='cin7_uploader')


def downgrade():
    # Drop product_upload_mapping table
    op.drop_index('ix_product_upload_mapping_created_at', 'product_upload_mapping', schema='cin7_uploader')
    op.drop_index('ix_product_upload_mapping_upload_id', 'product_upload_mapping', schema='cin7_uploader')
    op.drop_index('ix_product_upload_mapping_cin7_product_id', 'product_upload_mapping', schema='cin7_uploader')
    op.drop_index('ix_product_upload_mapping_client_erp_credentials_id', 'product_upload_mapping', schema='cin7_uploader')
    op.drop_table('product_upload_mapping', schema='cin7_uploader')
    
    # Drop customer_upload_mapping table
    op.drop_index('ix_customer_upload_mapping_created_at', 'customer_upload_mapping', schema='cin7_uploader')
    op.drop_index('ix_customer_upload_mapping_upload_id', 'customer_upload_mapping', schema='cin7_uploader')
    op.drop_index('ix_customer_upload_mapping_cin7_customer_id', 'customer_upload_mapping', schema='cin7_uploader')
    op.drop_index('ix_customer_upload_mapping_client_erp_credentials_id', 'customer_upload_mapping', schema='cin7_uploader')
    op.drop_table('customer_upload_mapping', schema='cin7_uploader')



