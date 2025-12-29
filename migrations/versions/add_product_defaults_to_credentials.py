"""Add product default columns to voyager.client_erp_credentials table

Revision ID: add_product_defaults_to_cred
Revises: add_cache_new_flags
Create Date: 2025-12-28 18:02:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_product_defaults_to_cred'
down_revision = 'add_cache_new_flags'
branch_labels = None
depends_on = None


def upgrade():
    # Add product_costing_method column (String, nullable) - Default costing method (e.g., "FIFO", "LIFO", "Average")
    op.add_column('client_erp_credentials',
        sa.Column('product_costing_method', sa.String(255), nullable=True),
        schema='voyager'
    )
    
    # Add product_default_price_tier column (String, nullable) - Default price tier name (e.g., "Tier 1")
    op.add_column('client_erp_credentials',
        sa.Column('product_default_price_tier', sa.String(255), nullable=True),
        schema='voyager'
    )
    
    # Add product_default_price column (Float, nullable) - Default price for new products (defaults to 0.0)
    op.add_column('client_erp_credentials',
        sa.Column('product_default_price', sa.Float(), nullable=True),
        schema='voyager'
    )
    
    # Add product_currency column (String, nullable) - Currency for products (defaults to "USD" if not set)
    op.add_column('client_erp_credentials',
        sa.Column('product_currency', sa.String(10), nullable=True),
        schema='voyager'
    )


def downgrade():
    # Remove all added columns
    op.drop_column('client_erp_credentials', 'product_currency', schema='voyager')
    op.drop_column('client_erp_credentials', 'product_default_price', schema='voyager')
    op.drop_column('client_erp_credentials', 'product_default_price_tier', schema='voyager')
    op.drop_column('client_erp_credentials', 'product_costing_method', schema='voyager')



