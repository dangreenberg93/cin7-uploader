"""add csv_content to sales_order_upload

Revision ID: add_csv_content_to_upload
Revises: add_deployment_config_table
Create Date: 2025-12-26 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_csv_content_to_upload'
down_revision = 'add_deployment_config_table'
branch_labels = None
depends_on = None


def upgrade():
    # Add csv_content column to sales_order_upload
    op.add_column('sales_order_upload', 
                  sa.Column('csv_content', sa.Text(), nullable=True),
                  schema='cin7_uploader')


def downgrade():
    # Remove csv_content column
    op.drop_column('sales_order_upload', 'csv_content', schema='cin7_uploader')


