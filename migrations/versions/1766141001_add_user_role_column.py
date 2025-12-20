"""Add role column to fireflies.users table

Revision ID: add_user_role
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_user_role'
down_revision = 'fa1f6ce1b016'  # Points to initial migration
branch_labels = None
depends_on = None

def upgrade():
    # Add role column to fireflies.users table
    op.add_column('users', 
        sa.Column('role', sa.String(length=50), nullable=True),
        schema='fireflies'
    )
    
    # Set dan@paleblue.nyc as admin
    op.execute("""
        UPDATE fireflies.users 
        SET role = 'admin' 
        WHERE email = 'dan@paleblue.nyc'
    """)

def downgrade():
    op.drop_column('users', 'role', schema='fireflies')
