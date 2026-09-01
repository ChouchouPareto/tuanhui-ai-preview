"""add optional asset subcategory

Revision ID: c2a5d6e7f8b9
Revises: 9f4c8e2a1d7b
Create Date: 2026-09-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2a5d6e7f8b9"
down_revision: Union[str, Sequence[str], None] = "9f4c8e2a1d7b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("source_assets") as batch_op:
        batch_op.add_column(sa.Column("subcategory", sa.String(length=60), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("source_assets") as batch_op:
        batch_op.drop_column("subcategory")
