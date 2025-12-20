"""Add client_erp_credentials_id to client_csv_mapping table

Revision ID: add_client_erp_credentials_id
Revises: 1766141001
Create Date: 2025-01-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_client_erp_credentials_id'
down_revision = 'add_user_role'  # Points to add_user_role_column migration
branch_labels = None
depends_on = None


def upgrade():
    # Make client_id nullable (it was required before)
    op.alter_column('client_csv_mapping', 'client_id',
                    existing_type=postgresql.UUID(as_uuid=True),
                    nullable=True,
                    schema='cin7_uploader')
    
    # Add client_erp_credentials_id column (nullable first)
    op.add_column('client_csv_mapping',
        sa.Column('client_erp_credentials_id', postgresql.UUID(as_uuid=True), nullable=True),
        schema='cin7_uploader'
    )
    
    # Update existing rows to set client_erp_credentials_id based on client_id
    # This assumes existing mappings have a client_id that can be used to find the credential
    op.execute("""
        UPDATE cin7_uploader.client_csv_mapping ccm
        SET client_erp_credentials_id = (
            SELECT cec.id
            FROM voyager.client_erp_credentials cec
            WHERE cec.client_id = ccm.client_id
            AND cec.erp = 'cin7_core'
            LIMIT 1
        )
        WHERE ccm.client_id IS NOT NULL
    """)
    
    # Now make it non-nullable
    op.alter_column('client_csv_mapping', 'client_erp_credentials_id',
                    existing_type=postgresql.UUID(as_uuid=True),
                    nullable=False,
                    schema='cin7_uploader')
    
    # Create index on client_erp_credentials_id
    op.create_index(
        'ix_cin7_uploader_client_csv_mapping_client_erp_credentials_id',
        'client_csv_mapping',
        ['client_erp_credentials_id'],
        schema='cin7_uploader'
    )
    
    # Drop old unique constraint and create new one
    op.drop_constraint('client_csv_mapping_client_name_unique', 'client_csv_mapping', schema='cin7_uploader', type_='unique')
    op.create_unique_constraint(
        'client_csv_mapping_cred_name_unique',
        'client_csv_mapping',
        ['client_erp_credentials_id', 'mapping_name'],
        schema='cin7_uploader'
    )


def downgrade():
    # Drop new unique constraint and restore old one
    op.drop_constraint('client_csv_mapping_cred_name_unique', 'client_csv_mapping', schema='cin7_uploader', type_='unique')
    op.create_unique_constraint(
        'client_csv_mapping_client_name_unique',
        'client_csv_mapping',
        ['client_id', 'mapping_name'],
        schema='cin7_uploader'
    )
    
    # Drop index
    op.drop_index(
        'ix_cin7_uploader_client_csv_mapping_client_erp_credentials_id',
        'client_csv_mapping',
        schema='cin7_uploader'
    )
    
    # Drop client_erp_credentials_id column
    op.drop_column('client_csv_mapping', 'client_erp_credentials_id', schema='cin7_uploader')
    
    # Make client_id required again
    op.alter_column('client_csv_mapping', 'client_id',
                    existing_type=postgresql.UUID(as_uuid=True),
                    nullable=False,
                    schema='cin7_uploader')



