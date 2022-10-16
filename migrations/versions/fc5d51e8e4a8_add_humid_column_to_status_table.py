"""Add humid column to status table

Revision ID: fc5d51e8e4a8
Revises: 87c71b8652b5
Create Date: 2022-09-24 10:13:38.652846

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fc5d51e8e4a8'
down_revision = '87c71b8652b5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('status', sa.Column('humid', sa.String(length=3), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('status', 'humid')
    # ### end Alembic commands ###