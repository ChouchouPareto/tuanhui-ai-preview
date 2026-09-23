"""Durable professional queue; additive, frozen table definition."""
from alembic import op
import sqlalchemy as sa

revision = "f4d8b0c2e6a1"
down_revision = "e3c7a9b1d2f4"
branch_labels = None
depends_on = None


def table_definition():
    meta = sa.MetaData()
    for name in ("store_projects", "workflow_tasks", "design_plans"):
        sa.Table(name, meta, sa.Column("id", sa.String(36), primary_key=True))
    return sa.Table("professional_generation_jobs", meta,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("store_projects.id"), nullable=False, index=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("workflow_tasks.id"), nullable=False, unique=True),
        sa.Column("plan_id", sa.String(36), sa.ForeignKey("design_plans.id"), nullable=False),
        sa.Column("snapshot", sa.JSON, nullable=False),
        sa.Column("state", sa.String(30), nullable=False, index=True),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))


def upgrade():
    bind = op.get_bind()
    table = table_definition()
    if not op.get_context().as_sql and sa.inspect(bind).has_table(table.name):
        actual = {c["name"] for c in sa.inspect(bind).get_columns(table.name)}
        if actual != {c.name for c in table.columns}:
            raise RuntimeError("Unexpected professional queue schema; review before migrating")
    else:
        table.create(bind, checkfirst=False)


def downgrade():
    raise RuntimeError("Paid execution records must be retained; roll back code, not job history.")
