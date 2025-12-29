"""Add auto_create_customers and auto_create_products to client_settings

Revision ID: add_auto_create_settings
Revises: add_review_notes
Create Date: 2025-12-28 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_auto_create_settings'
down_revision = 'add_review_notes'
branch_labels = None
depends_on = None


def upgrade():
    # Add auto_create_customers column
    op.add_column(
        'client_settings',
        sa.Column('auto_create_customers', sa.Boolean(), nullable=False, server_default='false'),
        schema='cin7_uploader'
    )
    
    # Add auto_create_products column
    op.add_column(
        'client_settings',
        sa.Column('auto_create_products', sa.Boolean(), nullable=False, server_default='false'),
        schema='cin7_uploader'
    )


def downgrade():
    # Remove columns
    op.drop_column('client_settings', 'auto_create_products', schema='cin7_uploader')
    op.drop_column('client_settings', 'auto_create_customers', schema='cin7_uploader')



