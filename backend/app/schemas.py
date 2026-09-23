from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


Platform = Literal["douyin", "meituan"]
SemanticRole = Literal["storefront", "menu", "signature_dish", "dish", "environment", "logo", "credential", "other"]
ExpressionView = Literal["brand_official", "owner_recommendation", "diner_seed"]


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    industry: str = Field(default="餐饮", min_length=1, max_length=60)
    platforms: list[Platform] = Field(default_factory=lambda: ["douyin", "meituan"])

    @field_validator("platforms")
    @classmethod
    def unique_platforms(cls, value: list[str]):
        if not value:
            raise ValueError("至少选择一个目标平台")
        return list(dict.fromkeys(value))

    @field_validator("industry")
    @classmethod
    def restaurant_only(cls, value: str):
        if value.strip() != "餐饮":
            raise ValueError("MVP当前仅支持餐饮行业")
        return "餐饮"


class ClarificationSubmit(BaseModel):
    answers: dict[str, str]


class AnalysisRunRequest(BaseModel):
    use_ai: bool = False


class FactUpdate(BaseModel):
    show_price: bool | None = None
    store_name: str | None = None
    positioning: str | None = None
    hero_item: str | None = None
    hero_price: str | None = None
    package_contents: list[str] | None = None
    products: list[dict] = Field(default_factory=list)
    selling_points: list[str] | None = None
    expression_view: ExpressionView | None = None
    restaurant_category: str | None = None
    brand_color: str | None = None

    @field_validator("selling_points")
    @classmethod
    def clean_selling_points(cls, value: list[str] | None):
        if value is None:
            return None
        cleaned = [item.strip() for item in value if item.strip()]
        return list(dict.fromkeys(cleaned))[:5]

    @field_validator("package_contents")
    @classmethod
    def clean_package_contents(cls, value: list[str] | None):
        if value is None:
            return None
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))[:20]


class AssetMetadataUpdate(BaseModel):
    semantic_role: SemanticRole | None = None
    subcategory: str | None = Field(default=None, max_length=60)
    priority: int | None = Field(default=None, ge=1, le=999)
    is_hero: bool | None = None


class MenuProduct(BaseModel):
    name: str
    category: str | None = None
    price_original: str | None = None
    price_value: str | None = None
    unit: str | None = None
    specification: str | None = None
    is_package: bool = False
    package_items: list[str] = Field(default_factory=list)
    evidence: str
    bbox: list[int] | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)
    needs_confirmation: bool = True

    @model_validator(mode="before")
    @classmethod
    def normalize_ocr_shape(cls, data):
        if not isinstance(data, dict):
            return data
        value = dict(data)
        if not str(value.get("evidence") or "").strip():
            value["evidence"] = " ".join(str(part).strip() for part in (value.get("name"), value.get("price_original")) if part)
        bbox = value.get("bbox")
        if not (isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(item, (int, float)) for item in bbox)):
            value["bbox"] = None
        for key in ("category", "unit", "specification"):
            if value.get(key) == "":
                value[key] = None
        return value

    @field_validator("name", "evidence")
    @classmethod
    def required_menu_text(cls, value: str):
        value = value.strip()
        if not value:
            raise ValueError("菜品名称和证据不能为空")
        return value

    @field_validator("package_items")
    @classmethod
    def clean_package_items(cls, value: list[str]):
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))

    @model_validator(mode="after")
    def preserve_price_evidence(self):
        claimed_price = bool(self.price_original or self.price_value)
        if self.price_value and not self.price_original:
            self.price_value = None
        if claimed_price or self.is_package or self.package_items:
            self.needs_confirmation = True
        return self


class OCRPayload(BaseModel):
    visible_text: str = ""
    store_name: str | None = None
    store_name_candidates: list["StoreNameCandidate"] = Field(default_factory=list)
    needs_confirmation: bool = False
    products: list[MenuProduct] = Field(default_factory=list)
    visual_observations: list["VisualObservation"] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_storefront_selection(self):
        def compact(value):
            return "".join(value.split()).casefold()
        visible = compact(self.visible_text)
        invalid = any(compact(item.name) not in visible or compact(item.evidence) not in visible
                      for item in self.store_name_candidates)
        if invalid:
            self.store_name = None
            self.needs_confirmation = True
            return self
        names = {item.name for item in self.store_name_candidates}
        if len(names) == 1 and any(item.confidence < .9 for item in self.store_name_candidates):
            self.store_name = None
            self.needs_confirmation = True
            return self
        if len(names) > 1:
            self.store_name = None
            self.needs_confirmation = True
        elif self.store_name and self.store_name not in names:
            self.store_name = None
            self.needs_confirmation = True
        elif not self.store_name and len(self.store_name_candidates) == 1 and self.store_name_candidates[0].confidence >= 0.9:
            self.store_name = self.store_name_candidates[0].name
            self.needs_confirmation = False
        elif not self.store_name and names:
            self.needs_confirmation = True
        return self


class VisualObservation(BaseModel):
    kind: Literal["color", "style", "logo_hint"]
    value: str = Field(min_length=1, max_length=200)
    region: str = Field(min_length=1, max_length=200)
    evidence: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1)
    # Visual clues are not verified logo assets or business claims.
    status: Literal["candidate"] = "candidate"


class StoreNameCandidate(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    region: str | None = None
    evidence: str
    confidence: float = Field(default=0.5, ge=0, le=1)

    @field_validator("name", "evidence")
    @classmethod
    def non_empty_text(cls, value: str):
        value = value.strip()
        if not value:
            raise ValueError("候选名称和证据不能为空")
        return value

    @field_validator("aliases")
    @classmethod
    def clean_aliases(cls, value: list[str]):
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))


class VisualFactPayload(BaseModel):
    positioning: str | None = None
    hero_item: str | None = None
    selling_points: list[str] = Field(default_factory=list)
    restaurant_category: str | None = None
    brand_color: str | None = None

    @field_validator("selling_points")
    @classmethod
    def cap_points(cls, value: list[str]):
        return [str(item).strip() for item in value if str(item).strip()][:5]


class FactConfirm(BaseModel):
    confirmed: bool


DesignStyle = Literal["appetite", "brand", "street", "minimal"]


class DesignPlanCreate(BaseModel):
    style: DesignStyle = "appetite"
    output_type: Literal["five_panel", "three_panel", "logo", "package_main", "voucher_main", "dish", "promotion", "store_decoration", "detail"] = "five_panel"
    render_mode: Literal["real_assets", "illustration"] = "real_assets"


class DesignPlanUpdate(BaseModel):
    style: DesignStyle | None = None
    headline: str | None = Field(default=None, max_length=30)
    subheadline: str | None = Field(default=None, max_length=50)

    @field_validator("headline", "subheadline")
    @classmethod
    def clean_design_copy(cls, value: str | None):
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("文案不能为空")
        return normalized


class DesignPlanConfirm(BaseModel):
    confirmed: bool
    plan_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class GenerationRunRequest(BaseModel):
    provider: Literal["qwen", "doubao"] = "qwen"
    # Accepted for old clients, but never authorizes automatic paid failover.
    allow_fallback: bool = False
    plan_id: str | None = Field(default=None, min_length=1, max_length=36)
    plan_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    request_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,128}$")

    @model_validator(mode="after")
    def require_plan_binding_pair(self):
        if (self.plan_id is None) != (self.plan_hash is None):
            raise ValueError("plan_id 和 plan_hash 必须一起提供")
        return self
