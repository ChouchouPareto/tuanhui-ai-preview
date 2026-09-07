"""M1 creations and durable confirmation outbox; additive only."""
from alembic import op
import sqlalchemy as sa

revision = "d8a1b2c3d4e5"
down_revision = "c2a5d6e7f8b9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("creations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("store_projects.id"), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_creations_project_id", "creations", ["project_id"])
    op.create_table("intake_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("creation_id", sa.String(36), sa.ForeignKey("creations.id"), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("request_key", sa.String(120), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("snapshot", sa.JSON, nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("creation_id", "revision"), sa.UniqueConstraint("creation_id", "request_key"))
    op.create_index("ix_intake_revisions_creation_id", "intake_revisions", ["creation_id"])
    op.create_table("creation_confirmations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("creation_id", sa.String(36), sa.ForeignKey("creations.id"), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("request_key", sa.String(120), nullable=False),
        sa.Column("snapshot", sa.JSON, nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("workflow_tasks.id"), nullable=False, unique=True),
        sa.Column("plan_id", sa.String(36), sa.ForeignKey("design_plans.id"), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("creation_id", "revision"), sa.UniqueConstraint("creation_id", "request_key"))
    op.create_index("ix_creation_confirmations_creation_id", "creation_confirmations", ["creation_id"])


def downgrade():
    # Only for a backed-up migration rehearsal, never for deleting live creations.
    op.drop_table("creation_confirmations")
    op.drop_table("intake_revisions")
    op.drop_table("creations")
