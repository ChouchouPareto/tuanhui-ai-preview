"""stage2a asset semantics and model calls

Revision ID: 9f4c8e2a1d7b
Revises: b43354dc1cda
Create Date: 2026-08-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9f4c8e2a1d7b"
down_revision: Union[str, Sequence[str], None] = "b43354dc1cda"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("source_assets") as batch_op:
        batch_op.add_column(sa.Column("semantic_role", sa.String(length=40), nullable=False, server_default="other"))
        batch_op.add_column(sa.Column("priority", sa.Integer(), nullable=False, server_default="100"))
        batch_op.add_column(sa.Column("is_hero", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        "model_call_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("contract", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["store_projects.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["workflow_tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_model_call_records_project_id"), "model_call_records", ["project_id"], unique=False)
    op.create_index(op.f("ix_model_call_records_task_id"), "model_call_records", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_model_call_records_task_id"), table_name="model_call_records")
    op.drop_index(op.f("ix_model_call_records_project_id"), table_name="model_call_records")
    op.drop_table("model_call_records")
    with op.batch_alter_table("source_assets") as batch_op:
        batch_op.drop_column("is_hero")
        batch_op.drop_column("priority")
        batch_op.drop_column("semantic_role")
