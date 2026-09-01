from io import BytesIO

from PIL import Image
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import SourceAsset, TaskStatus, WorkflowTask
from app.services.analysis import recover_analysis_tasks
from app.schemas import OCRPayload
from app.services.model_gateway import ModelGatewayError, parse_json_object
from app.services.design_plan import build_design_plan
from app.services.image_generation import render_and_slice


def image_bytes(width=1200, height=900):
    stream = BytesIO()
    Image.new("RGB", (width, height), "#dbff65").save(stream, format="PNG")
    return stream.getvalue()


def create_project(client):
    response = client.post("/api/v1/projects", json={"name": "山城酸菜鱼", "industry": "餐饮", "platforms": ["douyin", "meituan"]})
    assert response.status_code == 201
    return response.json()["project_id"]


def upload_required_assets(client, project_id):
    for asset_type in ("menu", "storefront"):
        response = client.post(
            f"/api/v1/projects/{project_id}/assets",
            data={"asset_type": asset_type},
            files={"file": (f"{asset_type}.png", image_bytes(), "image/png")},
        )
        assert response.status_code == 201
        assert response.json()["quality"]["resolution_ok"] is True


def test_stage1_happy_path(client):
    project_id = create_project(client)
    upload_required_assets(client, project_id)
    analysis = client.post(f"/api/v1/projects/{project_id}/analysis-runs")
    assert analysis.status_code == 202
    task = client.get(f"/api/v1/tasks/{analysis.json()['task_id']}").json()
    assert task["status"] == "NEEDS_USER"
    coverage = client.get(f"/api/v1/projects/{project_id}/coverage").json()
    assert len(coverage["questions"]) <= 3
    assert set(coverage["missing_fields"]) == {"positioning", "hero_item", "selling_points", "hero_price"}
    assert len(coverage["questions"]) == 3
    clarified = client.post(
        f"/api/v1/projects/{project_id}/clarifications",
        json={"answers": {"positioning": "川味江湖菜，突出鲜香现做", "hero_item": "酸菜鱼面双人套餐", "selling_points": "活鱼现做，酸香开胃"}},
    )
    assert clarified.status_code == 200
    assert clarified.json()["coverage"]["ready_for_confirmation"] is False
    priced = client.post(
        f"/api/v1/projects/{project_id}/clarifications",
        json={"answers": {"hero_price": "99元"}},
    )
    assert priced.status_code == 200
    assert priced.json()["coverage"]["ready_for_confirmation"] is True
    version = priced.json()["fact_version"]
    confirmed = client.post(f"/api/v1/projects/{project_id}/fact-versions/{version}/confirm", json={"confirmed": True})
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "FACTS_CONFIRMED"


def test_design_plan_requires_confirmed_facts(client):
    project_id = create_project(client)
    response = client.post(f"/api/v1/projects/{project_id}/design-plans", json={"style": "appetite"})
    assert response.status_code == 409


def test_confirmed_facts_create_edit_and_confirm_five_image_plan(client):
    project_id = create_project(client)
    upload_required_assets(client, project_id)
    client.post(f"/api/v1/projects/{project_id}/analysis-runs")
    clarified = client.post(
        f"/api/v1/projects/{project_id}/clarifications",
        json={"answers": {"positioning": "川味江湖菜", "hero_item": "酸菜鱼双人餐", "selling_points": "活鱼现做，酸香开胃"}},
    ).json()
    priced = client.post(f"/api/v1/projects/{project_id}/clarifications", json={"answers": {"hero_price": "99元"}}).json()
    client.post(f"/api/v1/projects/{project_id}/fact-versions/{priced['fact_version']}/confirm", json={"confirmed": True})

    created = client.post(f"/api/v1/projects/{project_id}/design-plans", json={"style": "appetite"})
    assert created.status_code == 201
    payload = created.json()
    assert payload["plan"]["canvas"] == {"ratio": "20:3", "recommended_size": "4000x600", "slice_count": 5, "slice_ratio": "4:3", "slice_size": "800x600"}
    assert len(payload["plan"]["frames"]) == 5
    assert payload["plan"]["locked_facts"]["store_name"] == "山城酸菜鱼"
    assert payload["plan"]["locked_facts"]["hero_price"] == "99元"
    assert "不得编造价格与优惠" in payload["plan"]["guardrails"]

    patched = client.patch(
        f"/api/v1/projects/{project_id}/design-plans/{payload['id']}",
        json={"style": "brand", "headline": "酸菜鱼双人餐"},
    )
    assert patched.status_code == 200
    assert patched.json()["plan"]["style"]["key"] == "brand"
    confirmed = client.post(
        f"/api/v1/projects/{project_id}/design-plans/{payload['id']}/confirm",
        json={"confirmed": True},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "CONFIRMED"


def test_renderer_outputs_exact_long_canvas_and_five_slices(tmp_path):
    plan = build_design_plan({"store_name": "山城酸菜鱼", "positioning": "川味江湖菜", "hero_item": "酸菜鱼双人餐", "hero_price": "99元", "selling_points": ["活鱼现做"]})
    result = render_and_slice(image_bytes(1600, 900), plan, tmp_path)
    assert result["width"] == 4000
    assert result["height"] == 600
    assert len(result["slices"]) == 5
    with Image.open(tmp_path / result["long_image"]) as long_image:
        assert long_image.size == (4000, 600)
    for filename in result["slices"]:
        with Image.open(tmp_path / filename) as item:
            assert item.size == (800, 600)


def test_analysis_requires_both_assets(client):
    project_id = create_project(client)
    response = client.post(f"/api/v1/projects/{project_id}/analysis-runs")
    assert response.status_code == 409


def test_dialogue_intake_accepts_storefront_and_dish_without_menu(client):
    project_id = create_project(client)
    for asset_type, role in (("storefront", "storefront"), ("product", "dish")):
        response = client.post(
            f"/api/v1/projects/{project_id}/assets",
            data={"asset_type": asset_type, "semantic_role": role},
            files={"file": (f"{role}.png", image_bytes(), "image/png")},
        )
        assert response.status_code == 201
    response = client.post(f"/api/v1/projects/{project_id}/analysis-runs")
    assert response.status_code == 202
    coverage = client.get(f"/api/v1/projects/{project_id}/coverage")
    assert coverage.status_code == 200


def test_dialogue_intake_is_default_and_uses_no_analyzer(client):
    project_id = create_project(client)
    upload_required_assets(client, project_id)
    response = client.post(f"/api/v1/projects/{project_id}/analysis-runs")
    assert response.status_code == 202
    assert response.json()["use_ai"] is False
    task = client.get(f"/api/v1/tasks/{response.json()['task_id']}").json()
    assert task["result"]["analyzer_mode"] == "dialogue"


def test_invalid_upload_is_rejected(client):
    project_id = create_project(client)
    response = client.post(
        f"/api/v1/projects/{project_id}/assets",
        data={"asset_type": "menu"},
        files={"file": ("menu.txt", b"not-an-image", "text/plain")},
    )
    assert response.status_code == 422


def test_uploaded_asset_has_private_preview(client):
    project_id = create_project(client)
    uploaded = client.post(
        f"/api/v1/projects/{project_id}/assets",
        data={"asset_type": "menu", "semantic_role": "menu"},
        files={"file": ("menu.png", image_bytes(), "image/png")},
    )
    assert uploaded.status_code == 201
    asset = client.get(f"/api/v1/projects/{project_id}/assets").json()[0]
    assert asset["preview_path"].endswith(f"/{asset['id']}/content")
    preview = client.get(f"/api/v1{asset['preview_path']}")
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    assert preview.headers["cache-control"] == "private, max-age=3600"


def test_mvp_rejects_non_restaurant_project(client):
    response = client.post("/api/v1/projects", json={"name": "测试店", "industry": "零售", "platforms": ["douyin"]})
    assert response.status_code == 422


def test_asset_metadata_and_unique_hero(client):
    project_id = create_project(client)
    asset_ids = []
    for index, role in enumerate(("signature_dish", "dish"), start=1):
        response = client.post(
            f"/api/v1/projects/{project_id}/assets",
            data={"asset_type": "product", "semantic_role": role, "subcategory": "招牌菜" if index == 1 else "", "priority": str(index * 10), "is_hero": "true"},
            files={"file": (f"dish-{index}.png", image_bytes(), "image/png")},
        )
        assert response.status_code == 201
        asset_ids.append(response.json()["asset_id"])
    listed = client.get(f"/api/v1/projects/{project_id}/assets").json()
    assert [item["priority"] for item in listed] == [10, 20]
    assert listed[0]["subcategory"] == "招牌菜"
    assert listed[1]["subcategory"] is None
    assert sum(item["is_hero"] for item in listed) == 1
    assert next(item for item in listed if item["is_hero"])["id"] == asset_ids[1]
    patched = client.patch(
        f"/api/v1/projects/{project_id}/assets/{asset_ids[0]}",
        json={"semantic_role": "signature_dish", "subcategory": "本店必点", "priority": 5, "is_hero": True},
    )
    assert patched.status_code == 200
    assert patched.json()["priority"] == 5
    assert patched.json()["subcategory"] == "本店必点"


def test_model_json_parser_accepts_fence_and_rejects_invalid():
    assert parse_json_object('```json\n{"hero_item":"酸菜鱼"}\n```')["hero_item"] == "酸菜鱼"
    assert parse_json_object('模型结果：{"store_name":"山城酸菜鱼"}，请确认')["store_name"] == "山城酸菜鱼"
    try:
        parse_json_object("没有结构化结果")
    except ModelGatewayError as exc:
        assert exc.code == "MODEL_BAD_OUTPUT"
    else:
        raise AssertionError("invalid model output should be rejected")


def test_multiple_storefront_candidates_require_confirmation():
    payload = OCRPayload.model_validate({
        "visible_text": "吃好喝好 BBQ Chicken",
        "store_name": "吃好喝好",
        "store_name_candidates": [
            {"name": "吃好喝好", "aliases": [], "region": "左侧", "evidence": "吃好喝好", "confidence": 0.96},
            {"name": "BBQ Chicken", "aliases": ["比比客"], "region": "右侧", "evidence": "BBQ Chicken", "confidence": 0.98},
        ],
        "needs_confirmation": False,
        "products": [],
    })
    assert payload.store_name is None
    assert payload.needs_confirmation is True


def test_store_name_without_candidate_evidence_is_rejected():
    payload = OCRPayload.model_validate({"visible_text": "李先生", "store_name": "汉庭酒店", "store_name_candidates": [], "products": []})
    assert payload.store_name is None
    assert payload.needs_confirmation is True


def test_single_high_confidence_candidate_is_selected():
    payload = OCRPayload.model_validate({
        "visible_text": "PALA 派乐汉堡",
        "store_name": None,
        "store_name_candidates": [{"name": "PALA派乐汉堡", "aliases": ["PALA"], "region": "中央", "evidence": "PALA 派乐汉堡", "confidence": 0.98}],
        "needs_confirmation": True,
        "products": [],
    })
    assert payload.store_name == "PALA派乐汉堡"
    assert payload.needs_confirmation is False


def test_menu_price_requires_original_evidence():
    payload = OCRPayload.model_validate({
        "visible_text": "酸菜鱼 38元/份",
        "products": [{
            "name": "酸菜鱼", "price_original": None, "price_value": "38", "unit": "份",
            "evidence": "酸菜鱼 38元/份", "confidence": 0.96, "needs_confirmation": False,
        }],
    })
    assert payload.products[0].price_value is None
    assert payload.products[0].needs_confirmation is True


def test_menu_preserves_price_and_package_evidence():
    payload = OCRPayload.model_validate({
        "visible_text": "双人套餐 99元 含酸菜鱼、米饭2份",
        "products": [{
            "name": "双人套餐", "price_original": "99元", "price_value": "99", "is_package": True,
            "package_items": ["酸菜鱼", "米饭2份"], "evidence": "双人套餐 99元 含酸菜鱼、米饭2份", "confidence": 0.98,
        }],
    })
    assert payload.products[0].price_original == "99元"
    assert payload.products[0].price_value == "99"
    assert payload.products[0].package_items == ["酸菜鱼", "米饭2份"]
    assert payload.products[0].needs_confirmation is True


def test_menu_normalizes_unusable_bbox_and_missing_evidence():
    payload = OCRPayload.model_validate({
        "visible_text": "鱼片粥 $37",
        "products": [{"name": "鱼片粥", "price_original": "$37", "price_value": "37", "evidence": "", "bbox": [[1, 2, 3], [4, 5, 6]], "confidence": 0.99}],
    })
    assert payload.products[0].bbox is None
    assert payload.products[0].evidence == "鱼片粥 $37"


def test_incomplete_facts_cannot_be_confirmed(client):
    project_id = create_project(client)
    upload_required_assets(client, project_id)
    client.post(f"/api/v1/projects/{project_id}/analysis-runs")
    coverage = client.get(f"/api/v1/projects/{project_id}/coverage").json()
    response = client.post(f"/api/v1/projects/{project_id}/fact-versions/{coverage['fact_version']}/confirm", json={"confirmed": True})
    assert response.status_code == 409


def test_pending_analysis_recovers_after_restart(client):
    project_id = create_project(client)
    upload_required_assets(client, project_id)
    with SessionLocal() as db:
        task = WorkflowTask(project_id=project_id, task_type="asset_analysis", status=TaskStatus.PENDING)
        db.add(task)
        db.commit()
        task_id = task.id
    with SessionLocal() as db:
        assert recover_analysis_tasks(db) == 1
        recovered = db.get(WorkflowTask, task_id)
        assert recovered.status == TaskStatus.NEEDS_USER
