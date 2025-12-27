"""merge cached tables and client erp credentials branches

Revision ID: 54298b1d230d
Revises: add_cached_tables, add_client_erp_credentials_id_to_upload
Create Date: 2025-12-27 05:53:17.654267

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '54298b1d230d'
down_revision = ('add_cached_tables', 'add_client_erp_credentials_id_to_upload')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
