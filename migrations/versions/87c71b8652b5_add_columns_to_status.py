"""add columns to status

Revision ID: 87c71b8652b5
Revises: 2f092db1dd86
Create Date: 2022-08-12 16:14:26.166583

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '87c71b8652b5'
down_revision = '2f092db1dd86'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('status', sa.Column('filter_time', sa.Integer(), nullable=True))
    op.add_column('status', sa.Column('filter', sa.String(length=3), nullable=True))
    op.add_column('status', sa.Column('vent', sa.String(length=3), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('status', 'vent')
    op.drop_column('status', 'filter')
    op.drop_column('status', 'filter_time')
    # ### end Alembic commands ###
