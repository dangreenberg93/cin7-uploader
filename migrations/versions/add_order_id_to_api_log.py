"""add order_id to cin7_api_log

Revision ID: add_order_id_to_api_log
Revises: 
Create Date: 2025-12-28 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_order_id_to_api_log'
down_revision = 'remove_upload_fk'  # Latest head migration
branch_labels = None
depends_on = None


def upgrade():
    # Add order_id column to cin7_api_log table
    op.add_column(
        'cin7_api_log',
        sa.Column(
            'order_id',
            postgresql.UUID(as_uuid=True),
            nullable=True,
            index=True
        ),
        schema='cin7_uploader'
    )
    
    # Add foreign key constraint
    op.create_foreign_key(
        'fk_cin7_api_log_order_id',
        'cin7_api_log',
        'sales_order_result',
        ['order_id'],
        ['id'],
        source_schema='cin7_uploader',
        referent_schema='cin7_uploader',
        ondelete='SET NULL'  # If order is deleted, set order_id to NULL
    )
    
    # Note: Index is automatically created by add_column with index=True


def downgrade():
    # Drop foreign key constraint
    op.drop_constraint(
        'fk_cin7_api_log_order_id',
        'cin7_api_log',
        schema='cin7_uploader',
        type_='foreignkey'
    )
    
    # Drop column (index is automatically dropped with the column)
    op.drop_column('cin7_api_log', 'order_id', schema='cin7_uploader')

