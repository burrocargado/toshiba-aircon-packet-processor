"""fix length of clean

Revision ID: 2f092db1dd86
Revises: a93520d18c6f
Create Date: 2022-08-12 16:00:23.333471

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2f092db1dd86'
down_revision = 'a93520d18c6f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('status', schema=None) as batch_op:
        batch_op.alter_column('clean',
               existing_type=sa.VARCHAR(length=2),
               type_=sa.String(length=3),
               existing_nullable=True)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('status', schema=None) as batch_op:
        batch_op.alter_column('clean',
               existing_type=sa.String(length=3),
               type_=sa.VARCHAR(length=2),
               existing_nullable=True)
    # ### end Alembic commands ###
