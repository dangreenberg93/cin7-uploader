"""Add is_new and created_via_auto_create flags to cached_customer and cached_product

Revision ID: add_cache_new_flags
Revises: add_auto_create_settings
Create Date: 2025-12-28 18:01:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_cache_new_flags'
down_revision = 'add_auto_create_settings'
branch_labels = None
depends_on = None


def upgrade():
    # Add flags to cached_customer
    op.add_column(
        'cached_customer',
        sa.Column('is_new', sa.Boolean(), nullable=False, server_default='false'),
        schema='cin7_uploader'
    )
    op.add_column(
        'cached_customer',
        sa.Column('created_via_auto_create', sa.Boolean(), nullable=False, server_default='false'),
        schema='cin7_uploader'
    )
    op.create_index('ix_cached_customer_is_new', 'cached_customer', ['is_new'], schema='cin7_uploader')
    
    # Add flags to cached_product
    op.add_column(
        'cached_product',
        sa.Column('is_new', sa.Boolean(), nullable=False, server_default='false'),
        schema='cin7_uploader'
    )
    op.add_column(
        'cached_product',
        sa.Column('created_via_auto_create', sa.Boolean(), nullable=False, server_default='false'),
        schema='cin7_uploader'
    )
    op.create_index('ix_cached_product_is_new', 'cached_product', ['is_new'], schema='cin7_uploader')


def downgrade():
    # Remove indexes
    op.drop_index('ix_cached_product_is_new', 'cached_product', schema='cin7_uploader')
    op.drop_index('ix_cached_customer_is_new', 'cached_customer', schema='cin7_uploader')
    
    # Remove columns from cached_product
    op.drop_column('cached_product', 'created_via_auto_create', schema='cin7_uploader')
    op.drop_column('cached_product', 'is_new', schema='cin7_uploader')
    
    # Remove columns from cached_customer
    op.drop_column('cached_customer', 'created_via_auto_create', schema='cin7_uploader')
    op.drop_column('cached_customer', 'is_new', schema='cin7_uploader')



