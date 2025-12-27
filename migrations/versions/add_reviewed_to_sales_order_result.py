"""Add reviewed column to sales_order_result table

Revision ID: add_reviewed_to_sales_order_result
Revises: 54298b1d230d
Create Date: 2025-01-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_reviewed_column'
down_revision = '54298b1d230d'
branch_labels = None
depends_on = None

def upgrade():
    # Add reviewed column to sales_order_result
    op.add_column('sales_order_result',
        sa.Column('reviewed', sa.Boolean(), nullable=False, server_default='false'),
        schema='cin7_uploader'
    )
    # Create index on reviewed for filtering
    op.create_index('ix_sales_order_result_reviewed', 'sales_order_result', ['reviewed'], schema='cin7_uploader')

def downgrade():
    # Drop index
    op.drop_index('ix_sales_order_result_reviewed', table_name='sales_order_result', schema='cin7_uploader')
    # Remove reviewed column
    op.drop_column('sales_order_result', 'reviewed', schema='cin7_uploader')

