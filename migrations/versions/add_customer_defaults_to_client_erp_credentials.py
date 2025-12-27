"""Add customer default columns to voyager.client_erp_credentials table

Revision ID: add_customer_defaults_to_cred
Revises: add_raw_response_body
Create Date: 2025-12-27 07:53:57.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_customer_defaults_to_cred'
down_revision = 'add_raw_response_body'
branch_labels = None
depends_on = None


def upgrade():
    # Add default_location column (UUID, nullable) - references Cin7 location ID
    op.add_column('client_erp_credentials',
        sa.Column('default_location', postgresql.UUID(as_uuid=True), nullable=True),
        schema='voyager'
    )
    
    # Add customer_account_receivable column (String, nullable) - stores account code
    op.add_column('client_erp_credentials',
        sa.Column('customer_account_receivable', sa.String(255), nullable=True),
        schema='voyager'
    )
    
    # Add customer_revenue_account column (String, nullable) - stores account code
    op.add_column('client_erp_credentials',
        sa.Column('customer_revenue_account', sa.String(255), nullable=True),
        schema='voyager'
    )
    
    # Add customer_tax_rule column (UUID, nullable) - references Cin7 tax rule ID
    op.add_column('client_erp_credentials',
        sa.Column('customer_tax_rule', postgresql.UUID(as_uuid=True), nullable=True),
        schema='voyager'
    )
    
    # Add customer_attribute_set column (String, nullable) - stores attribute set name
    op.add_column('client_erp_credentials',
        sa.Column('customer_attribute_set', sa.String(255), nullable=True),
        schema='voyager'
    )


def downgrade():
    # Remove all added columns
    op.drop_column('client_erp_credentials', 'customer_attribute_set', schema='voyager')
    op.drop_column('client_erp_credentials', 'customer_tax_rule', schema='voyager')
    op.drop_column('client_erp_credentials', 'customer_revenue_account', schema='voyager')
    op.drop_column('client_erp_credentials', 'customer_account_receivable', schema='voyager')
    op.drop_column('client_erp_credentials', 'default_location', schema='voyager')

