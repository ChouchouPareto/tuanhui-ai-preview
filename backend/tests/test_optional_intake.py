"""One-click readiness follows available material, not a mandatory text form."""
import pytest
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models import DesignPlan
from test_m1_creations import setup_creation, submit, confirm


@pytest.mark.parametrize("text", ["", "做首页五图", "突出家庭聚餐，不要价格和店名"])
def test_asset_led_creation_can_confirm_without_name_or_dish_label(client, text):
    _, asset, base = setup_creation(client)
    response = submit(client, base, asset, text=text, input_mode="replace")
    assert response.status_code == 200
    review = response.json()
    assert review["snapshot"]["ready"]
    assert not review["snapshot"]["show_store_name"]
    assert not review["snapshot"]["show_price"]
    assert confirm(client, base, review).status_code == 200
    with SessionLocal() as db:
        plan = db.scalar(select(DesignPlan)).plan
        assert plan["selected_asset_ids"] == [asset]
        assert plan["copy"]["store_name"] == ""
        assert plan["copy"]["price"] == ""
        assert not plan["locked_facts"]["hero_item"]
        if "家庭聚餐" in text:
            assert plan["copy"]["headline"] == "家庭聚餐"


@pytest.mark.parametrize("directive,field", [("展示店名", "store_name"), ("写上价格", "hero_price")])
def test_explicit_display_still_requires_real_value(client, directive, field):
    _, asset, base = setup_creation(client)
    review = submit(client, base, asset, text=directive, input_mode="replace").json()
    assert {g["field"] for g in review["snapshot"]["gaps"]} == {field}
    assert confirm(client, base, review).status_code == 409


def test_explicit_api_store_requirement_is_respected(client):
    _, asset, base = setup_creation(client)
    review = submit(client, base, asset, text="", input_mode="replace", show_store_name=True).json()
    assert {g["field"] for g in review["snapshot"]["gaps"]} == {"store_name"}


def test_combined_hide_directive_overrides_provided_values(client):
    _, asset, base = setup_creation(client)
    review = submit(client, base, asset, text="店名：测试店，价格：99元，不放店名和价格", input_mode="replace").json()
    assert review["snapshot"]["ready"]
    assert not review["snapshot"]["show_store_name"]
    assert not review["snapshot"]["show_price"]


def test_no_usable_image_does_not_get_false_ready(client):
    _, asset, base = setup_creation(client, dish=False)
    review = submit(client, base, asset, text="", input_mode="replace").json()
    assert not review["snapshot"]["ready"]
    assert "store_name" not in {g["field"] for g in review["snapshot"]["gaps"]}
    assert confirm(client, base, review).status_code == 409


def test_professional_shares_conditional_requirements(client):
    project, asset, _ = setup_creation(client)
    root = f"/api/v1/projects/{project}/creations"
    cid = client.post(root, json={"mode": "pro"}).json()["creation_id"]
    review = submit(client, root + "/" + cid, asset, text="", input_mode="replace").json()
    assert review["snapshot"]["ready"]
    assert review["entry_mode"] == "professional"
    assert not review["snapshot"]["show_store_name"]
    assert confirm(client, root + "/" + cid, review).status_code == 200
    with SessionLocal() as db:
        plan = db.scalar(select(DesignPlan)).plan
        assert plan["entry_mode"] == "professional"
        assert plan["canvas"]["ratio"] == "20:3"
        assert plan["canvas"]["slice_count"] == 5


@pytest.mark.parametrize("mode,output,entry", [("oneclick", "five_panel", "oneclick"), ("pro", "five_panel", "professional"), ("oneclick", "full_plan", "fullplan")])
def test_shared_creation_restores_entry_and_new_revision(client, mode, output, entry):
    project, asset, _ = setup_creation(client)
    root = f"/api/v1/projects/{project}/creations"
    cid = client.post(root, json={"mode": mode}).json()["creation_id"]
    base = root + "/" + cid
    result = submit(client, base, asset, asset_ids=[], text="主推：面食，不展示价格", input_mode="chat", allow_illustration=True, output_type=output, delivery_types=["five_panel"]).json()
    assert result["snapshot"]["ready"]
    assert result["entry_mode"] == entry
    original = confirm(client, base, result).json()
    assert client.get(base + "/review").json()["task_id"] == original["task_id"]
    child = client.post(root, json={"mode": mode, "parent_creation_id": cid}).json()
    response = submit(client, root + "/" + child["creation_id"], asset, asset_ids=[], text="重新生成一版，主推：米饭", input_mode="chat", allow_illustration=True, output_type=output, delivery_types=["five_panel"])
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["snapshot"]["facts"]["hero_item"] == "米饭"
    assert updated["entry_mode"] == entry
    assert client.get(base + "/review").json()["snapshot"]["facts"]["hero_item"] == "面食"


def test_professional_explicit_name_request_still_needs_evidence(client):
    project, asset, _ = setup_creation(client)
    root = f"/api/v1/projects/{project}/creations"
    cid = client.post(root, json={"mode": "pro"}).json()["creation_id"]
    result = submit(client, root + "/" + cid, asset, text="展示店名", input_mode="chat").json()
    assert {g["field"] for g in result["snapshot"]["gaps"]} == {"store_name"}
