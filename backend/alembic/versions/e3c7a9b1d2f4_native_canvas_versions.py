"""Native canvas objects; additive, frozen schema, safe after create_all bootstrap."""
from alembic import op
import sqlalchemy as sa

revision = "e3c7a9b1d2f4"
down_revision = "d8a1b2c3d4e5"
branch_labels = None
depends_on = None


def tables():
    meta = sa.MetaData()
    sa.Table("store_projects", meta, sa.Column("id", sa.String(36), primary_key=True))
    documents = sa.Table("canvas_documents", meta,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("store_projects.id"), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("head_version_id", sa.String(36)),
        sa.Column("source", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    versions = sa.Table("canvas_versions", meta,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("canvas_documents.id"), nullable=False, index=True),
        sa.Column("parent_id", sa.String(36)),
        sa.Column("content", sa.JSON, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("render_manifest", sa.JSON, nullable=False),
        sa.Column("reason", sa.String(60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    mutations = sa.Table("canvas_mutations", meta,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("canvas_documents.id"), nullable=False, index=True),
        sa.Column("request_key", sa.String(120), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("version_id", sa.String(36), sa.ForeignKey("canvas_versions.id"), nullable=False),
        sa.UniqueConstraint("document_id", "request_key"))
    proposals = sa.Table("canvas_proposals", meta,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("canvas_documents.id"), nullable=False, index=True),
        sa.Column("base_version_id", sa.String(36), sa.ForeignKey("canvas_versions.id"), nullable=False),
        sa.Column("proposal", sa.JSON, nullable=False),
        sa.Column("applied_version_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    return documents, versions, mutations, proposals


def upgrade():
    bind = op.get_bind()
    offline = op.get_context().as_sql
    for table in tables():
        if not offline and sa.inspect(bind).has_table(table.name):
            present = {c["name"] for c in sa.inspect(bind).get_columns(table.name)}
            if present != {c.name for c in table.columns}:
                raise RuntimeError(f"Unexpected schema for {table.name}; stop for review")
        else:
            table.create(bind, checkfirst=False)


def downgrade():
    raise RuntimeError("Canvas history must be retained. Roll back application code, not user versions.")
