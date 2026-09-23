"""Versioned edit contract; normalized geometry never accepts executable markup."""
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Output = Literal["five_panel", "three_panel", "logo", "package_main", "voucher_main", "dish", "promotion", "store_decoration", "detail"]
Role = Literal["headline", "subheadline", "store_name", "price", "body", "photo", "decoration"]
SIZES = {"five_panel": (4000, 600, 5), "three_panel": (2400, 600, 3)}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Node(Strict):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    kind: Literal["text", "image", "shape"] = "text"
    role: Role = "body"
    box: tuple[float, float, float, float]
    text: str = Field(default="", max_length=500)
    asset_id: str | None = Field(default=None, max_length=36)
    color: str = Field(default="#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")
    font_size: int = Field(default=50, ge=18, le=200)
    z_index: int = Field(default=0, ge=-1000, le=1000)
    locked: bool = False
    visible: bool = True

    @field_validator("box")
    @classmethod
    def valid_box(cls, b):
        x, y, w, h = b
        if not all(math.isfinite(v) for v in b) or x < 0 or y < 0 or w <= 0 or h <= 0 or x+w > 1.00000001 or y+h > 1.00000001:
            raise ValueError("区域坐标必须位于画布内")
        return b

    @model_validator(mode="after")
    def kind_fields(self):
        if self.kind == "image" and not self.asset_id:
            raise ValueError("图片层需要素材 ID")
        if self.kind != "image" and self.asset_id:
            raise ValueError("只有图片层可以引用素材")
        if self.kind != "text" and self.text:
            raise ValueError("只有文字层可以包含文字")
        if self.kind == "text" and any(ord(c) < 32 and c != "\n" for c in self.text):
            raise ValueError("文字包含不支持的控制字符")
        return self


class Scene(Strict):
    schema_version: Literal["editable-scene-v1"] = "editable-scene-v1"
    output_type: Output = "five_panel"
    width: int = 4000
    height: int = 600
    slice_count: int = 5
    background_color: str = Field(default="#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")
    ai_generated: bool = False
    nodes: list[Node] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def dimensions(self):
        if (self.width, self.height, self.slice_count) != SIZES.get(self.output_type, (800, 600, 1)):
            raise ValueError("画布尺寸与输出类型不一致")
        if len({n.id for n in self.nodes}) != len(self.nodes):
            raise ValueError("对象 ID 不得重复")
        return self


class CreateCanvas(Strict):
    name: str = Field(default="新建画布", min_length=1, max_length=120)
    scene: Scene


class ImportCanvas(Strict):
    task_id: str = Field(min_length=1, max_length=36)
    deliverable_id: str | None = Field(default=None, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")


class NodePatch(Strict):
    text: str | None = Field(default=None, max_length=500)
    box: tuple[float, float, float, float] | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    font_size: int | None = Field(default=None, ge=18, le=200)
    z_index: int | None = Field(default=None, ge=-1000, le=1000)
    visible: bool | None = None
    asset_id: str | None = Field(default=None, max_length=36)


class Operation(Strict):
    op: Literal["update", "add", "remove", "lock", "unlock"]
    object_id: str = Field(min_length=1, max_length=80)
    patch: NodePatch | None = None
    node: Node | None = None

    @model_validator(mode="after")
    def correct_payload(self):
        if self.op == "add":
            if not self.node or self.node.id != self.object_id or self.patch:
                raise ValueError("新增对象内容不匹配")
        elif self.op == "update":
            if not self.patch or not self.patch.model_dump(exclude_none=True) or self.node:
                raise ValueError("修改内容不能为空")
        elif self.patch or self.node:
            raise ValueError("此操作不接受额外内容")
        return self


class MutateCanvas(Strict):
    base_version_id: str = Field(min_length=1, max_length=36)
    request_key: str = Field(min_length=8, max_length=120)
    operations: list[Operation] = Field(min_length=1, max_length=100)


class RestoreCanvas(Strict):
    base_version_id: str = Field(min_length=1, max_length=36)
    target_version_id: str = Field(min_length=1, max_length=36)
    request_key: str = Field(min_length=8, max_length=120)


class ResolveEdit(Strict):
    version_id: str = Field(min_length=1, max_length=36)
    message: str = Field(default="", max_length=8000)
    selected_object_id: str | None = Field(default=None, max_length=80)
    quote: str | None = Field(default=None, max_length=500)
    role: Role | None = None
    slice_index: int | None = Field(default=None, ge=1, le=5)
    replacement: str | None = Field(default=None, max_length=500)


class ApplyProposal(Strict):
    base_version_id: str = Field(min_length=1, max_length=36)
    request_key: str = Field(min_length=8, max_length=120)
