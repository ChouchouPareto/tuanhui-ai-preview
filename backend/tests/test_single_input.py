import json
import pytest
from sqlalchemy import select
from app.core.database import SessionLocal
from app.core.config import settings
from app.models import WorkflowTask, ModelCallRecord
from app.services.intake import parse_text
from app.services.model_gateway import ModelGatewayError
from test_m1_creations import setup_creation, submit, confirm

@pytest.mark.parametrize("text", [
    "我的店叫山城酸菜鱼，主推酸菜鱼双人餐，99元，不展示价格",
    "门店名称：山城酸菜鱼；主推菜品或套餐：酸菜鱼双人餐；真实价格：99元；不展示价格",
])
def test_single_input_extracts_without_second_form(client, text):
    _, asset, base = setup_creation(client)
    result = submit(client, base, asset, text=text, input_mode="replace").json()["snapshot"]
    assert result["facts"]["store_name"] == "山城酸菜鱼"
    assert result["facts"]["hero_item"] == "酸菜鱼双人餐"
    assert result["ready"] and not result["show_price"]

def test_replacing_text_does_not_keep_removed_old_fields(client):
    _, asset, base = setup_creation(client)
    old = submit(client, base, asset, input_mode="replace").json()
    new = submit(client, base, asset, expected_revision=1, input_mode="replace", text="店名：新店").json()
    assert "hero_item" not in new["snapshot"]["facts"]
    assert not new["snapshot"]["ready"]
    assert confirm(client, base, old).status_code == 409

def test_reply_merges_into_original_text_and_preserves_other_facts(client):
    _, asset, base = setup_creation(client)
    submit(client, base, asset, text="店名：川味小馆，不展示价格", input_mode="replace")
    response = submit(client, base, asset, expected_revision=1, text="清蒸鲈鱼", input_mode="reply", reply_field="hero_item")
    assert response.status_code == 200
    snapshot = response.json()["snapshot"]
    assert snapshot["facts"]["store_name"] == "川味小馆"
    assert snapshot["facts"]["hero_item"] == "清蒸鲈鱼"
    assert "川味小馆" in snapshot["text"] and "清蒸鲈鱼" in snapshot["text"]
    assert snapshot["ready"]
    assert client.get(base + "/review").json()["snapshot"] == snapshot

def test_price_directives_and_conflict_resolution(client):
    _, asset, base = setup_creation(client)
    first = submit(client, base, asset, input_mode="replace", text="店名是川味馆，主推清蒸鱼或者酸菜鱼，不展示价格").json()
    assert any(g["kind"] == "conflict" for g in first["snapshot"]["gaps"])
    second = submit(client, base, asset, expected_revision=1, input_mode="reply", reply_field="hero_item", text="酸菜鱼").json()
    assert second["snapshot"]["ready"]
    third = submit(client, base, asset, expected_revision=2, input_mode="reply", text="展示价格，价格99元").json()
    assert third["snapshot"]["show_price"] and third["snapshot"]["facts"]["hero_price"] == "99元"

def test_unknown_answer_is_not_invented(client):
    _, asset, base = setup_creation(client)
    submit(client, base, asset, text="店名：测试店", input_mode="replace")
    assert submit(client, base, asset, expected_revision=1, text="你决定", input_mode="reply", reply_field="hero_item").status_code == 422

def test_ai_requires_explicit_authorization_before_any_call(client, monkeypatch):
    from app.services import intake_understanding
    monkeypatch.setattr(intake_understanding, "_post_chat", lambda *a: pytest.fail("must not call"))
    _, asset, base = setup_creation(client)
    assert submit(client, base, asset, use_ai=True).status_code == 409

def test_ai_grounded_output_is_cached_and_audited(client, monkeypatch):
    from app.services import intake_understanding
    monkeypatch.setattr(settings, "dashscope_api_key", "offline-test")
    calls = []
    def model(*args):
        calls.append(args)
        return json.dumps({"facts": {"store_name": {"value": "山城", "quote": "山城"}, "hero_item": {"value": "清蒸鱼", "quote": "清蒸鱼"}}, "uncertain_fields": []}), {"prompt_tokens": 10, "completion_tokens": 5}, 20
    monkeypatch.setattr(intake_understanding, "_post_chat", model)
    _, asset, base = setup_creation(client)
    kwargs = dict(text="给山城制作清蒸鱼的五图", input_mode="replace", use_ai=True, accepted_understanding_policy="text-understanding-paid-v1")
    response = submit(client, base, asset, **kwargs)
    assert response.status_code == 200, response.text
    assert response.json()["snapshot"]["ready"]
    submit(client, base, asset, **kwargs)
    assert len(calls) == 1
    with SessionLocal() as db:
        assert db.scalar(select(ModelCallRecord)).status == "SUCCEEDED"
        assert not db.scalars(select(WorkflowTask).where(WorkflowTask.task_type == "group_buying_image_generation")).all()

def test_ai_unverifiable_output_and_timeout_do_not_retry(client, monkeypatch):
    from app.services import intake_understanding
    monkeypatch.setattr(settings, "dashscope_api_key", "offline-test")
    calls = []
    def model(*args):
        calls.append(1)
        return '{"facts":{"hero_item":{"value":"杜撰菜品","quote":"杜撰菜品"}}}', {}, 1
    monkeypatch.setattr(intake_understanding, "_post_chat", model)
    _, asset, base = setup_creation(client)
    kwargs = dict(use_ai=True, accepted_understanding_policy="text-understanding-paid-v1")
    assert submit(client, base, asset, **kwargs).status_code == 409
    assert submit(client, base, asset, **kwargs).status_code == 409
    assert len(calls) == 1
    _, asset2, base2 = setup_creation(client)
    def timeout(*args):
        calls.append(1)
        raise ModelGatewayError("MODEL_TIMEOUT", "timeout")
    monkeypatch.setattr(intake_understanding, "_post_chat", timeout)
    assert submit(client, base2, asset2, **kwargs).status_code == 409
    assert submit(client, base2, asset2, **kwargs).status_code == 409
    assert len(calls) == 2
