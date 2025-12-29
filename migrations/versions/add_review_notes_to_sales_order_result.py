"""add review_notes to sales_order_result

Revision ID: add_review_notes
Revises: add_order_id_to_api_log
Create Date: 2025-12-28 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_review_notes'
down_revision = 'add_order_id_to_api_log'
branch_labels = None
depends_on = None


def upgrade():
    # Add review_notes column to sales_order_result table
    op.add_column(
        'sales_order_result',
        sa.Column('review_notes', sa.Text(), nullable=True),
        schema='cin7_uploader'
    )


def downgrade():
    # Drop column
    op.drop_column('sales_order_result', 'review_notes', schema='cin7_uploader')



