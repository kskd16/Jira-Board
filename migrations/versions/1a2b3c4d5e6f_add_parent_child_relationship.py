"""Add parent-child relationship to tickets

Revision ID: 1a2b3c4d5e6f
Revises: 
Create Date: 2023-07-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '1a2b3c4d5e6f'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Add parent_id column to ticket table
    op.add_column('ticket', sa.Column('parent_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_ticket_parent', 'ticket', 'ticket', ['parent_id'], ['id'])

def downgrade():
    # Remove parent_id column from ticket table
    op.drop_constraint('fk_ticket_parent', 'ticket', type_='foreignkey')
    op.drop_column('ticket', 'parent_id')