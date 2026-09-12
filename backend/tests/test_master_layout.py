import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image, ImageChops, ImageDraw

from app.services.design_plan import build_design_plan
from app.services.image_generation import _font, build_visual_prompt, render_and_slice
from app.services.master_layout import eligible_dishes, fitted_text


def test_only_explicit_dish_products_can_render():
    rows = [SimpleNamespace(asset_type=t, semantic_role=r) for t, r in [
        ("storefront", "dish"), ("menu", "dish"), ("product", "storefront"),
        ("product", "other"), ("product", "dish"), ("product", "signature_dish")]]
    assert eligible_dishes(rows) == rows[-2:]


def test_background_prompt_ignores_old_scene_instructions():
    plan = build_design_plan({"store_name": "测试店", "hero_item": "蒸鱼"})
    plan["frames"][0]["visual"] = "旧版强制门头场景"
    assert "旧版强制门头场景" not in build_visual_prompt(plan)
    assert "不绘制食物" in build_visual_prompt(plan)


def test_master_uses_real_asset_and_exact_slices(tmp_path):
    path = tmp_path / "dish.png"
    Image.new("RGB", (300, 200), (11, 211, 71)).save(path)
    dish = SimpleNamespace(id="real-dish", storage_path=str(path), asset_type="product", semantic_role="dish")
    background = io.BytesIO()
    Image.new("RGB", (1000, 150), "gray").save(background, "PNG")
    plan = build_design_plan({"store_name": "测试餐厅", "hero_item": "招牌蒸鱼", "selling_points": ["现点现做"]})
    result = render_and_slice(background.getvalue(), plan, tmp_path / "out", [dish])
    with Image.open(tmp_path / "out" / result["long_image"]) as master:
        region = next(r["box"] for r in plan["layout"]["regions"] if r["role"] == "visual")
        assert master.getpixel((round((region[0]+region[2]/2)*4000), round((region[1]+region[3]/2)*600))) == (11, 211, 71)
        for index, filename in enumerate(result["slices"]):
            with Image.open(tmp_path / "out" / filename) as part:
                assert ImageChops.difference(master.crop((800*index, 0, 800*(index+1), 600)), part).getbbox() is None
    spec = json.loads((tmp_path / "out" / "design-spec.json").read_text())
    assert spec["asset_ids"] == ["real-dish"]


def test_overflow_is_reported_not_truncated():
    draw = ImageDraw.Draw(Image.new("RGB", (100, 100)))
    with pytest.raises(ValueError, match="未截断"):
        fitted_text(draw, "不可截断的门店名称" * 100, (0, 0, 20, 20), _font, "white")


def test_missing_dish_stops_before_paid_call(client, monkeypatch):
    from app.core.database import SessionLocal
    from app.models import StoreProject, WorkflowTask, TaskStatus
    from app.services import image_generation

    def forbidden(*args, **kwargs):
        pytest.fail("缺少菜品时不应调用模型")

    monkeypatch.setattr(image_generation, "call_qwen", forbidden)
    project_id = client.post("/api/v1/projects", json={"name": "测试餐厅", "industry": "餐饮", "platforms": ["meituan"]}).json()["project_id"]
    with SessionLocal() as db:
        project = db.get(StoreProject, project_id)
        task = WorkflowTask(project_id=project_id, task_type="group_buying_image_generation")
        db.add(task)
        db.commit()
        image_generation.run_generation(db, project, task, SimpleNamespace(plan=build_design_plan({})), "qwen", False)
        assert task.status == TaskStatus.FAILED_FINAL
        assert task.error_code == "DISH_ASSET_REQUIRED"
