import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Creation(Base):
    __tablename__ = "creations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("store_projects.id"), index=True)
    mode: Mapped[str] = mapped_column(String(20), default="oneclick")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class GenerationWorkerHeartbeat(Base):
    __tablename__ = "generation_worker_heartbeats"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IntakeRevision(Base):
    __tablename__ = "intake_revisions"
    __table_args__ = (UniqueConstraint("creation_id", "revision"), UniqueConstraint("creation_id", "request_key"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    creation_id: Mapped[str] = mapped_column(ForeignKey("creations.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    request_key: Mapped[str] = mapped_column(String(120))
    request_hash: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSON)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CreationConfirmation(Base):
    __tablename__ = "creation_confirmations"
    __table_args__ = (UniqueConstraint("creation_id", "revision"), UniqueConstraint("creation_id", "request_key"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    creation_id: Mapped[str] = mapped_column(ForeignKey("creations.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    request_key: Mapped[str] = mapped_column(String(120))
    snapshot: Mapped[dict] = mapped_column(JSON)
    task_id: Mapped[str] = mapped_column(ForeignKey("workflow_tasks.id"), unique=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("design_plans.id"))
    state: Mapped[str] = mapped_column(String(30), default="QUEUED")
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProjectStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ASSETS_UPLOADED = "ASSETS_UPLOADED"
    ANALYZING = "ANALYZING"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    NEEDS_FACT_CONFIRMATION = "NEEDS_FACT_CONFIRMATION"
    FACTS_CONFIRMED = "FACTS_CONFIRMED"
    DESIGN_PLAN_DRAFT = "DESIGN_PLAN_DRAFT"
    DESIGN_PLAN_CONFIRMED = "DESIGN_PLAN_CONFIRMED"
    GENERATING = "GENERATING"
    GENERATED = "GENERATED"


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED_FINAL = "FAILED_FINAL"
    NEEDS_USER = "NEEDS_USER"


class StoreProject(Base):
    __tablename__ = "store_projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    industry: Mapped[str] = mapped_column(String(60), default="餐饮")
    platforms: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus), default=ProjectStatus.DRAFT)
    current_fact_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ProjectDisplayState(Base):
    __tablename__ = "project_display_states"
    project_id: Mapped[str] = mapped_column(ForeignKey("store_projects.id"), primary_key=True)
    visibility: Mapped[str] = mapped_column(String(20), default="visible")
    custom_name: Mapped[bool] = mapped_column(Boolean, default=False)


class SourceAsset(Base):
    __tablename__ = "source_assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("store_projects.id"), index=True)
    asset_type: Mapped[str] = mapped_column(String(40))
    semantic_role: Mapped[str] = mapped_column(String(40), default="other")
    subcategory: Mapped[str | None] = mapped_column(String(60), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    is_hero: Mapped[bool] = mapped_column(Boolean, default=False)
    original_name: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(80))
    byte_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FactVersion(Base):
    __tablename__ = "business_fact_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("store_projects.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    facts: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DesignPlan(Base):
    __tablename__ = "design_plans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("store_projects.id"), index=True)
    fact_version: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    plan: Mapped[dict] = mapped_column(JSON, default=dict)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ClarificationRound(Base):
    __tablename__ = "clarification_rounds"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("store_projects.id"), index=True)
    round_index: Mapped[int] = mapped_column(Integer)
    questions: Mapped[list] = mapped_column(JSON, default=list)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WorkflowTask(Base):
    __tablename__ = "workflow_tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("store_projects.id"), index=True)
    task_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.PENDING)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ModelCallRecord(Base):
    __tablename__ = "model_call_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("store_projects.id"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("workflow_tasks.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(120))
    contract: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IntakeRunLock(Base):
    """One in-flight understanding per creation, independent of message identity."""
    __tablename__ = "intake_run_locks"
    creation_id: Mapped[str] = mapped_column(ForeignKey("creations.id"), primary_key=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class WorkflowEvent(Base):
    """Append-only stage telemetry. Never stores raw prompts, photos or secrets."""
    __tablename__ = "workflow_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("store_projects.id"), index=True)
    creation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    stage: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(120), default="local")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
