import pytest
from app.services.design_plan import build_design_plan
from test_m1_creations import setup_creation, submit


@pytest.mark.parametrize("focus", ["卖点：现点现做", "特色：适合朋友聚餐", "本次重点：手工制作", "主推套餐：双人餐"])
def test_focus_accepts_product_or_feature(client, focus):
    _, asset, base = setup_creation(client)
    result = submit(client, base, asset, text="店名：测试店，" + focus, input_mode="replace")
    assert result.status_code == 200
    snapshot = result.json()["snapshot"]
    assert snapshot["ready"]
    plan = build_design_plan(snapshot["facts"])
    assert plan["copy"]["headline"] == focus.split("：")[1]
    assert plan["frames"][1]["role"] == "本次重点"


def test_feature_not_converted_to_dish_name(client):
    _, asset, base = setup_creation(client)
    snapshot = submit(client, base, asset, text="店名：测试店，卖点：现点现做", input_mode="replace").json()["snapshot"]
    assert not snapshot["facts"].get("hero_item")
    plan = build_design_plan(snapshot["facts"])
    assert plan["locked_facts"]["hero_item"] == ""
    assert plan["locked_facts"]["selling_points"] == ["现点现做"]


def test_ambiguous_feature_still_needs_reply(client):
    _, asset, base = setup_creation(client)
    snapshot = submit(client, base, asset, text="店名：测试店，特色：聚餐或者便捷外带", input_mode="replace").json()["snapshot"]
    assert not snapshot["ready"]
    assert any(g["field"] == "positioning" for g in snapshot["gaps"])
