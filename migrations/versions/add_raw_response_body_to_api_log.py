"""Add raw_response_body_text column to cin7_api_log table

Revision ID: add_raw_response_body
Revises: add_reviewed_column
Create Date: 2025-01-27 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_raw_response_body'
down_revision = 'add_reviewed_column'
branch_labels = None
depends_on = None

def upgrade():
    # Add raw_response_body_text column to store raw JSON string (preserves key order)
    op.add_column('cin7_api_log',
        sa.Column('raw_response_body_text', sa.Text(), nullable=True),
        schema='cin7_uploader'
    )

def downgrade():
    # Remove raw_response_body_text column
    op.drop_column('cin7_api_log', 'raw_response_body_text', schema='cin7_uploader')

