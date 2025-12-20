"""Add active column to voyager.client_erp_credentials table

Revision ID: add_active_to_client_erp_credentials
Revises: add_client_erp_credentials_id
Create Date: 2025-01-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_active_to_cred'
down_revision = 'add_client_erp_credentials_id'
branch_labels = None
depends_on = None


def upgrade():
    # Add active column to voyager.client_erp_credentials table (default to true)
    op.add_column('client_erp_credentials',
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        schema='voyager'
    )


def downgrade():
    op.drop_column('client_erp_credentials', 'active', schema='voyager')


