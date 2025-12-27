"""Add task tracking fields to sales_order_result table

Revision ID: add_task_tracking_to_sales_order_result
Revises: add_sales_order_result
Create Date: 2025-01-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = 'add_task_tracking_to_sales_order_result'
down_revision = 'add_sales_order_result'
branch_labels = None
depends_on = None

def upgrade():
    # Add task tracking columns to sales_order_result
    op.add_column('sales_order_result',
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        schema='cin7_uploader'
    )
    op.add_column('sales_order_result',
        sa.Column('last_retry_at', sa.DateTime(), nullable=True),
        schema='cin7_uploader'
    )
    op.add_column('sales_order_result',
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        schema='cin7_uploader'
    )
    op.add_column('sales_order_result',
        sa.Column('resolved_by', UUID(as_uuid=True), nullable=True),
        schema='cin7_uploader'
    )
    op.add_column('sales_order_result',
        sa.Column('error_type', sa.String(length=50), nullable=True),
        schema='cin7_uploader'
    )
    
    # Add foreign key constraint for resolved_by
    op.create_foreign_key(
        'fk_sales_order_result_resolved_by',
        'sales_order_result', 'users',
        ['resolved_by'], ['id'],
        source_schema='cin7_uploader',
        referent_schema='fireflies'
    )
    
    # Create index on error_type for filtering
    op.create_index('ix_sales_order_result_error_type', 'sales_order_result', ['error_type'], schema='cin7_uploader')
    # Create index on resolved_at for filtering unresolved orders
    op.create_index('ix_sales_order_result_resolved_at', 'sales_order_result', ['resolved_at'], schema='cin7_uploader')

def downgrade():
    # Drop indexes
    op.drop_index('ix_sales_order_result_resolved_at', table_name='sales_order_result', schema='cin7_uploader')
    op.drop_index('ix_sales_order_result_error_type', table_name='sales_order_result', schema='cin7_uploader')
    
    # Drop foreign key
    op.drop_constraint('fk_sales_order_result_resolved_by', 'sales_order_result', schema='cin7_uploader', type_='foreignkey')
    
    # Drop columns
    op.drop_column('sales_order_result', 'error_type', schema='cin7_uploader')
    op.drop_column('sales_order_result', 'resolved_by', schema='cin7_uploader')
    op.drop_column('sales_order_result', 'resolved_at', schema='cin7_uploader')
    op.drop_column('sales_order_result', 'last_retry_at', schema='cin7_uploader')
    op.drop_column('sales_order_result', 'retry_count', schema='cin7_uploader')


