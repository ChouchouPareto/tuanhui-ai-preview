import io
from PIL import Image, ImageChops
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models import DesignPlan
from app.services.design_plan import build_design_plan
from app.services.image_generation import render_and_slice, build_visual_prompt
from test_m1_creations import setup_creation, submit, confirm


def test_chat_keeps_context_and_messages_but_not_assistant_as_facts(client):
    _, asset, base = setup_creation(client)
    first = submit(client, base, asset, text="店名：山城，突出家庭聚餐", input_mode="chat").json()
    second = submit(client, base, asset, text="不放店名和价格", expected_revision=1, input_mode="chat").json()
    snapshot = second["snapshot"]
    assert snapshot["facts"]["selling_points"] == "家庭聚餐"
    assert not snapshot["show_store_name"]
    assert len(snapshot["messages"]) == 4
    assert snapshot["messages"][0]["content"] == "店名：山城，突出家庭聚餐"
    assert snapshot["messages"][1]["role"] == "assistant"
    assert snapshot["text"] == "店名：山城，突出家庭聚餐\n不放店名和价格"
    assert client.get(base + "/review").json()["snapshot"]["messages"] == snapshot["messages"]
    assert confirm(client, base, first).status_code == 409


def test_text_illustration_explicit_choice_can_confirm(client):
    _, asset, base = setup_creation(client)
    first = submit(client, base, asset, asset_ids=[], text="主推：火锅", input_mode="chat").json()
    assert not first["snapshot"]["ready"]
    review = submit(client, base, asset, asset_ids=[], text="使用AI示意图", input_mode="chat", expected_revision=1).json()
    assert review["snapshot"]["ready"]
    assert confirm(client, base, review).status_code == 200
    with SessionLocal() as db:
        plan = db.scalar(select(DesignPlan)).plan
        assert plan["render_mode"] == "illustration"
        assert plan["selected_asset_ids"] == []
        assert "火锅" in build_visual_prompt(plan)


def test_illustration_decline_and_unknown_topic_do_not_generate(client):
    _, asset, base = setup_creation(client)
    one = submit(client, base, asset, asset_ids=[], text="使用AI示意图", input_mode="chat").json()
    assert not one["snapshot"]["ready"]
    two = submit(client, base, asset, asset_ids=[], text="主推：火锅，不要使用AI示意图", expected_revision=1, input_mode="chat").json()
    assert two["snapshot"]["render_mode"] == "real_assets"
    assert not two["snapshot"]["ready"]


def test_ai_receives_latest_message_and_loads_structured_context(client, monkeypatch):
    from app.services import intake_understanding
    _, asset, base = setup_creation(client)
    submit(client, base, asset, text="店名：山城", input_mode="chat")
    seen = []
    def understand(db, creation, text, request_hash):
        seen.append(text)
        return {"facts": {"selling_points": "聚餐"}, "uncertain_fields": []}
    monkeypatch.setattr(intake_understanding, "understand", understand)
    result = submit(client, base, asset, text="聚餐", input_mode="chat", expected_revision=1, use_ai=True, accepted_understanding_policy="text-understanding-paid-v1")
    assert result.status_code == 200
    assert seen == ["聚餐"]


def test_illustration_slices_are_exact_and_have_label(tmp_path):
    plan = build_design_plan({"hero_item": "火锅"})
    plan["render_mode"] = "illustration"
    buffer = io.BytesIO()
    Image.new("RGB", (2000, 300), "gray").save(buffer, "PNG")
    result = render_and_slice(buffer.getvalue(), plan, tmp_path, [])
    with Image.open(tmp_path / result["long_image"]) as master:
        for index, filename in enumerate(result["slices"]):
            with Image.open(tmp_path / filename) as part:
                assert ImageChops.difference(master.crop((800*index, 0, 800*(index+1), 600)), part).getbbox() is None
                # Label region is not a flat background; every exported slice has lettering.
                assert len(part.crop((28, 554, 238, 586)).getcolors(10000)) > 1


def test_style_reply_changes_plan_without_reasking_name(client):
    _, asset, base = setup_creation(client)
    submit(client, base, asset, text="突出家庭聚餐", input_mode="chat")
    review = submit(client, base, asset, text="温馨一点", input_mode="chat", expected_revision=1).json()
    assert review["snapshot"]["ready"]
    assert review["snapshot"]["style"] == "street"
    assert review["snapshot"]["facts"]["selling_points"] == "家庭聚餐"


def test_brand_only_illustration_does_not_repeat_store_question(client, monkeypatch):
    from app.services import intake_understanding
    _, asset, base = setup_creation(client)
    monkeypatch.setattr(intake_understanding, "understand", lambda *args: {"facts": {"store_name": "袁记云饺"}, "uncertain_fields": []})
    for revision, text in enumerate(["袁记云饺", "使用AI示意图", "袁记云饺，五图"]):
        review = submit(client, base, asset, asset_ids=[], text=text, input_mode="chat", expected_revision=revision, use_ai=True, accepted_understanding_policy="text-understanding-paid-v1").json()
        assert "想给什么店" not in review["snapshot"]["messages"][-1]["content"]
        if revision:
            assert review["snapshot"]["ready"]
            assert not review["snapshot"]["gaps"]
            assert not review["snapshot"]["facts"].get("hero_item")
    assert confirm(client, base, review).status_code == 200
    with SessionLocal() as db:
        plan = db.scalar(select(DesignPlan)).plan
        assert plan["copy"]["store_name"] == "袁记云饺"
        assert "不代表真实菜单" in build_visual_prompt(plan)
