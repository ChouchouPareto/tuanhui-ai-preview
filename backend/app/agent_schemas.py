"""Bounded orchestration: model proposals cannot authorize tools or fees."""
from typing import Literal
from pydantic import Field, model_validator
from app.canvas_schemas import Strict, Output


class AgentInput(Strict):
    request_key: str = Field(min_length=8, max_length=120, pattern=r"^[A-Za-z0-9_-]+$")
    text: str = Field(min_length=1, max_length=8000)
    entry_mode: Literal["oneclick", "professional", "fullplan"] = "oneclick"
    output_type: Output = "five_panel"
    delivery_types: list[Output] = Field(default_factory=lambda: ["voucher_main", "five_panel", "logo"], min_length=1, max_length=9)
    detail_count: int = Field(default=1, ge=1, le=9)
    asset_ids: list[str] = Field(default_factory=list, max_length=20)
    facts: dict[str, str] = Field(default_factory=dict, max_length=5)
    style: Literal["appetite", "brand", "street", "minimal"] = "minimal"
    show_price: bool = False
    show_store_name: bool = True
    allow_illustration: bool = True
    task_id: str | None = Field(default=None, max_length=36)
    document_id: str | None = Field(default=None, max_length=36)
    version_id: str | None = Field(default=None, max_length=36)
    object_id: str | None = Field(default=None, max_length=80)
    replacement: str | None = Field(default=None, max_length=500)
    approved_text_calls: int = Field(default=0, ge=0, le=2)
    accepted_policy: Literal["qwen-agent-text-v1"] | None = None

    @model_validator(mode="after")
    def authorization(self):
        if self.approved_text_calls and not self.accepted_policy:
            raise ValueError("请先确认本次语言模型调用次数")
        if bool(self.document_id) != bool(self.version_id):
            raise ValueError("画布与版本必须一起指定")
        if (self.object_id or self.replacement is not None) and not self.document_id:
            raise ValueError("请先选择要修改的画布与版本")
        if any(k not in {"store_name", "hero_item", "hero_price", "positioning", "selling_points"} or len(v) > 500 for k,v in self.facts.items()):
            raise ValueError("事实字段不支持或过长")
        return self


class FactClaim(Strict):
    value: str = Field(min_length=1, max_length=500)
    quote: str = Field(min_length=1, max_length=1000)


class AgentDecision(Strict):
    intent: Literal["prepare", "inspect", "answer", "edit_text", "clarify"]
    reply: str = Field(min_length=1, max_length=1500)
    facts: dict[str, FactClaim] = Field(default_factory=dict, max_length=5)
    creative_draft: dict[str, str] | None = None
    replacement: str | None = Field(default=None, max_length=500)
    target_object_id: str | None = Field(default=None, max_length=80)


class AgentExecute(Strict):
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_image_calls: int = Field(ge=0, le=9)
    materials_confirmed: bool
    accepted_policy: Literal["local-paid-generation-v1"]


class WorkspaceUpdate(Strict):
    expected_revision: int = Field(ge=0)
    positions: dict[str, tuple[float, float]] = Field(default_factory=dict, max_length=100)
    viewport: tuple[float, float, float] = (0, 0, 1)

    @model_validator(mode="after")
    def bounds(self):
        if any(abs(v) > 100000 for xy in self.positions.values() for v in xy) or not .1 <= self.viewport[2] <= 4:
            raise ValueError("画布位置或缩放超出范围")
        if any(abs(v) > 100000 for v in self.viewport[:2]):
            raise ValueError("视口超出范围")
        return self


class ReviewTemplate(Strict):
    template_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    state: Literal["draft", "approved", "rejected"]
    notes: str = Field(default="", max_length=2000)
