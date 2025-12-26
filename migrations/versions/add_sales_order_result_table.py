"""Add sales_order_result table and make user_id nullable in sales_order_upload

Revision ID: add_sales_order_result
Revises: 1766141001_add_user_role_column
Create Date: 2025-01-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = 'add_sales_order_result'
down_revision = 'remove_user_client_fkey'  # Points to latest migration
branch_labels = None
depends_on = None

def upgrade():
    # Make user_id nullable in sales_order_upload (for webhook uploads)
    op.alter_column('sales_order_upload', 'user_id',
                    existing_type=UUID(as_uuid=True),
                    nullable=True,
                    schema='cin7_uploader')
    
    # Make client_id nullable in sales_order_upload (for standalone connections)
    op.alter_column('sales_order_upload', 'client_id',
                    existing_type=UUID(as_uuid=True),
                    nullable=True,
                    schema='cin7_uploader')
    
    # Create sales_order_result table
    op.create_table(
        'sales_order_result',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('upload_id', UUID(as_uuid=True), nullable=False),
        sa.Column('order_key', sa.String(length=255), nullable=False),
        sa.Column('row_numbers', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('sale_id', UUID(as_uuid=True), nullable=True),
        sa.Column('sale_order_id', UUID(as_uuid=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('order_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['upload_id'], ['cin7_uploader.sales_order_upload.id'], ondelete='CASCADE'),
        schema='cin7_uploader'
    )
    
    # Create indexes
    op.create_index('ix_sales_order_result_upload_id', 'sales_order_result', ['upload_id'], schema='cin7_uploader')
    op.create_index('ix_sales_order_result_created_at', 'sales_order_result', ['created_at'], schema='cin7_uploader')

def downgrade():
    # Drop sales_order_result table
    op.drop_table('sales_order_result', schema='cin7_uploader')
    
    # Revert user_id to NOT NULL (note: this may fail if NULL values exist)
    op.alter_column('sales_order_upload', 'user_id',
                    existing_type=UUID(as_uuid=True),
                    nullable=False,
                    schema='cin7_uploader')
    
    # Revert client_id to NOT NULL (note: this may fail if NULL values exist)
    op.alter_column('sales_order_upload', 'client_id',
                    existing_type=UUID(as_uuid=True),
                    nullable=False,
                    schema='cin7_uploader')

