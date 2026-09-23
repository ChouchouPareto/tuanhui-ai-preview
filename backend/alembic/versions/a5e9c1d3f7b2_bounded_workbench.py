"""Add bounded orchestration and editor workspace, preserving existing records."""
from alembic import op
import sqlalchemy as sa

revision = "a5e9c1d3f7b2"
down_revision = "f4d8b0c2e6a1"
branch_labels = None
depends_on = None


def tables():
    meta = sa.MetaData()
    for name in ("store_projects", "workflow_tasks"):
        sa.Table(name, meta, sa.Column("id", sa.String(36), primary_key=True))
    return [
        sa.Table("agent_runs", meta,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("store_projects.id"), nullable=False, index=True),
            sa.Column("task_id", sa.String(36), sa.ForeignKey("workflow_tasks.id"), nullable=False, unique=True),
            sa.Column("request_key", sa.String(120), nullable=False),
            sa.Column("request_hash", sa.String(64), nullable=False),
            sa.Column("request", sa.JSON, nullable=False), sa.Column("result", sa.JSON, nullable=False),
            sa.Column("state", sa.String(30), nullable=False, index=True),
            sa.Column("lease_until", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("project_id", "request_key")),
        sa.Table("workspace_states", meta,
            sa.Column("project_id", sa.String(36), sa.ForeignKey("store_projects.id"), primary_key=True),
            sa.Column("revision", sa.Integer, nullable=False), sa.Column("content", sa.JSON, nullable=False)),
        sa.Table("template_reviews", meta,
            sa.Column("template_id", sa.String(120), primary_key=True),
            sa.Column("template_hash", sa.String(64), nullable=False),
            sa.Column("state", sa.String(30), nullable=False), sa.Column("notes", sa.Text, nullable=False),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False))]


def upgrade():
    bind = op.get_bind()
    for table in tables():
        if not op.get_context().as_sql and sa.inspect(bind).has_table(table.name):
            if {c["name"] for c in sa.inspect(bind).get_columns(table.name)} != {c.name for c in table.columns}:
                raise RuntimeError(f"Unexpected existing schema: {table.name}")
        else:
            table.create(bind, checkfirst=False)


def downgrade():
    raise RuntimeError("Preserve paid task and edit history; roll back code, not data.")
