"""Add customer_code_field column to voyager.client_erp_credentials table

Revision ID: add_customer_code_field
Revises: add_auto_create_to_cred
Create Date: 2025-01-02 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_customer_code_field'
down_revision = 'add_upload_mapping_tables'  # Point to the other head
branch_labels = None
depends_on = None


def upgrade():
    # Add customer_code_field column (String, nullable) - stores which Cin7 field to use for customer code matching
    # Examples: 'Tags', 'AdditionalAttribute1', 'AdditionalAttribute4', etc.
    # Defaults to 'AdditionalAttribute1' for backward compatibility
    op.add_column('client_erp_credentials',
        sa.Column('customer_code_field', sa.String(255), nullable=True),
        schema='voyager'
    )


def downgrade():
    # Remove the column
    op.drop_column('client_erp_credentials', 'customer_code_field', schema='voyager')

