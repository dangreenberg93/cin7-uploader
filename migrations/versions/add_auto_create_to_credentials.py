"""Add auto_create_customers_products column to voyager.client_erp_credentials table

Revision ID: add_auto_create_to_cred
Revises: add_product_defaults_to_cred
Create Date: 2025-12-29 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_auto_create_to_cred'
down_revision = 'add_product_defaults_to_cred'
branch_labels = None
depends_on = None


def upgrade():
    # Add auto_create_customers_products column (Boolean, nullable, default False)
    # This single setting controls both customer and product auto-creation
    op.add_column('client_erp_credentials',
        sa.Column('auto_create_customers_products', sa.Boolean(), nullable=True, server_default='false'),
        schema='voyager'
    )


def downgrade():
    # Remove the column
    op.drop_column('client_erp_credentials', 'auto_create_customers_products', schema='voyager')



