from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ClarificationRound, FactVersion, ModelCallRecord, ProjectStatus, SourceAsset, StoreProject, TaskStatus, WorkflowTask
from app.services.model_gateway import ModelGatewayError, infer_store_facts, recognize_image


CORE_FIELDS = {
    "store_name": "门店对外使用的完整名称是什么？",
    "positioning": "门店主要做什么，希望顾客记住什么特色？",
    "hero_item": "本次团购首页最想主推哪道菜或哪个套餐？",
    "selling_points": "请用一句话说明本次主推菜品或套餐最值得推荐的真实卖点。",
    "hero_price": "本次主推菜品或套餐的真实售价是多少？没有确定价格时请填写“暂未定价”。",
}


def _has_value(value) -> bool:
    if isinstance(value, list):
        return any(str(item).strip() for item in value)
    return value is not None and bool(str(value).strip())


def coverage_for(facts: dict) -> dict:
    missing = [key for key in CORE_FIELDS if not _has_value(facts.get(key))]
    return {
        "present_fields": [key for key in CORE_FIELDS if key not in missing],
        "missing_fields": missing,
        "blocking_fields": missing,
        "questions": [{"field": key, "question": CORE_FIELDS[key]} for key in missing[:3]],
        "ready_for_confirmation": not missing,
    }


def _start_analysis(db: Session, project: StoreProject, task: WorkflowTask):
    task.status = TaskStatus.RUNNING
    task.progress = 20
    project.status = ProjectStatus.ANALYZING
    db.commit()


def _persist_analysis(db: Session, project: StoreProject, task: WorkflowTask, facts: dict, evidence: dict, mode: str) -> dict:
    latest = db.scalar(select(FactVersion).where(FactVersion.project_id == project.id).order_by(FactVersion.version.desc()))
    version = 1 if latest is None else latest.version + 1
    fact_version = FactVersion(project_id=project.id, version=version, facts=facts, evidence=evidence)
    db.add(fact_version)
    coverage = coverage_for(facts)
    round_count = db.scalar(select(func.count()).select_from(ClarificationRound).where(ClarificationRound.project_id == project.id)) or 0
    clarification = ClarificationRound(project_id=project.id, round_index=round_count + 1, questions=coverage["questions"])
    db.add(clarification)
    project.current_fact_version = version
    project.status = ProjectStatus.NEEDS_CLARIFICATION if coverage["questions"] else ProjectStatus.NEEDS_FACT_CONFIRMATION
    task.status = TaskStatus.NEEDS_USER if coverage["questions"] else TaskStatus.SUCCEEDED
    task.progress = 100
    task.result = {"fact_version": version, "coverage": coverage, "analyzer_mode": mode}
    db.commit()
    return task.result


def run_mock_analysis(db: Session, project: StoreProject, task: WorkflowTask) -> dict:
    _start_analysis(db, project, task)
    assets = db.scalars(select(SourceAsset).where(SourceAsset.project_id == project.id)).all()
    types = {item.asset_type for item in assets}
    facts = {"store_name": project.name if project.name.strip() else None, "positioning": None, "hero_item": None, "selling_points": [], "hero_price": None, "package_contents": [], "expression_view": "brand_official", "products": []}
    evidence = {"store_name": {"source": "project_input", "confidence": 1.0}}
    coverage = coverage_for(facts)
    if "menu" not in types:
        coverage["questions"].insert(0, {"field": "menu_asset", "question": "请补传一张清晰的菜单或价目表图片。"})
    if "storefront" not in types:
        coverage["questions"].insert(0, {"field": "storefront_asset", "question": "请补传一张正面、清晰的门头图片。"})
    coverage["questions"] = coverage["questions"][:3]
    return _persist_analysis(db, project, task, facts, evidence, "mock")


def run_dialogue_intake(db: Session, project: StoreProject, task: WorkflowTask) -> dict:
    """Create the fact-confirmation conversation without calling any model."""
    _start_analysis(db, project, task)
    facts = {
        "store_name": project.name.strip() or None,
        "positioning": None,
        "hero_item": None,
        "selling_points": [],
        "hero_price": None,
        "package_contents": [],
        "expression_view": "brand_official",
        "products": [],
    }
    evidence = {"store_name": {"source": "project_input", "confidence": 1.0}}
    return _persist_analysis(db, project, task, facts, evidence, "dialogue")


def _record_call(db: Session, project_id: str, task_id: str, contract: str, meta: dict, status: str = "SUCCEEDED", error_code: str | None = None):
    usage = meta.get("usage") or {}
    db.add(ModelCallRecord(
        project_id=project_id,
        task_id=task_id,
        provider="bailian",
        model=meta.get("model", "unknown"),
        contract=contract,
        status=status,
        duration_ms=meta.get("duration_ms", 0),
        input_tokens=usage.get("prompt_tokens") or usage.get("input_tokens"),
        output_tokens=usage.get("completion_tokens") or usage.get("output_tokens"),
        error_code=error_code,
    ))


def run_bailian_analysis(db: Session, project: StoreProject, task: WorkflowTask) -> dict:
    _start_analysis(db, project, task)
    assets = db.scalars(select(SourceAsset).where(SourceAsset.project_id == project.id).order_by(SourceAsset.priority, SourceAsset.created_at)).all()
    ocr_results = []
    products = []
    try:
        for asset in assets:
            if asset.asset_type not in {"menu", "storefront"}:
                continue
            result, meta = recognize_image(asset.storage_path, asset.mime_type, asset.asset_type)
            _record_call(db, project.id, task.id, f"ocr:{asset.asset_type}", meta)
            item = result.model_dump()
            item["asset_id"] = asset.id
            item["asset_type"] = asset.asset_type
            ocr_results.append(item)
            products.extend(item.model_dump() for item in result.products)
            db.commit()
        visual, meta = infer_store_facts(project.name, ocr_results)
        _record_call(db, project.id, task.id, "store_facts", meta)
        storefront_candidates = []
        storefront_needs_confirmation = False
        for item in ocr_results:
            if item.get("asset_type") != "storefront":
                continue
            storefront_candidates.extend(item.get("store_name_candidates") or [])
            storefront_needs_confirmation = storefront_needs_confirmation or bool(item.get("needs_confirmation"))
        facts = {
            "store_name": project.name.strip() or None,
            "detected_store_name_candidates": storefront_candidates,
            "detected_store_name_needs_confirmation": storefront_needs_confirmation,
            "positioning": visual.positioning,
            "hero_item": visual.hero_item,
            "hero_price": None,
            "package_contents": [],
            "selling_points": visual.selling_points,
            "restaurant_category": visual.restaurant_category,
            "brand_color": visual.brand_color,
            "expression_view": "brand_official",
            "products": products,
        }
        evidence = {
            "store_name": {"source": "project_input", "confidence": 1.0},
            "model_analysis": {"source_assets": [item["asset_id"] for item in ocr_results], "provider": "bailian", "ocr_model": settings.bailian_ocr_model, "vision_model": settings.bailian_vision_model},
        }
        return _persist_analysis(db, project, task, facts, evidence, "bailian")
    except ModelGatewayError as exc:
        model = settings.bailian_vision_model if ocr_results else settings.bailian_ocr_model
        _record_call(db, project.id, task.id, "asset_analysis", {"model": model}, status="FAILED", error_code=exc.code)
        task.status = TaskStatus.FAILED_FINAL
        task.progress = 100
        task.error_code = exc.code
        task.error_message = exc.safe_message
        project.status = ProjectStatus.ASSETS_UPLOADED
        db.commit()
        return {"error": {"code": exc.code, "message": exc.safe_message}}


def run_analysis(db: Session, project: StoreProject, task: WorkflowTask) -> dict:
    if settings.analyzer_mode == "mock":
        return run_mock_analysis(db, project, task)
    if settings.analyzer_mode == "bailian":
        return run_bailian_analysis(db, project, task)
    task.status = TaskStatus.FAILED_FINAL
    task.error_code = "ANALYZER_MODE_INVALID"
    task.error_message = "分析器模式配置无效"
    project.status = ProjectStatus.ASSETS_UPLOADED
    db.commit()
    return {"error": {"code": task.error_code, "message": task.error_message}}


def merge_answers(facts: dict, answers: dict[str, str]) -> dict:
    merged = dict(facts)
    for field in CORE_FIELDS:
        value = answers.get(field)
        if value and value.strip():
            merged[field] = [value.strip()] if field == "selling_points" else value.strip()
    return merged


def recover_analysis_tasks(db: Session) -> int:
    tasks = db.scalars(
        select(WorkflowTask).where(
            WorkflowTask.task_type == "asset_analysis",
            WorkflowTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
        )
    ).all()
    recovered = 0
    for task in tasks:
        project = db.get(StoreProject, task.project_id)
        if project is None:
            task.status = TaskStatus.FAILED_FINAL
            task.error_code = "PROJECT_NOT_FOUND"
            task.error_message = "关联项目不存在"
            db.commit()
            continue
        run_analysis(db, project, task)
        recovered += 1
    return recovered
