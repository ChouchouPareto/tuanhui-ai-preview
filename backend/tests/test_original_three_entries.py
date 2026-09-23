"""Original UI protocol -> real queue/render/export, with an offline image provider.

This verifies deterministic delivery, not model image quality or native OCR accuracy.
"""
import io
import json

import pytest
from PIL import Image, ImageChops

from app.core.config import settings
from app.services.canvas_render import validate_geometry
from app.canvas_schemas import Scene
from app.worker import run_once


@pytest.mark.parametrize("mode,output,entry", [
    ("oneclick", "five_panel", "oneclick"),
    ("pro", "five_panel", "professional"),
    ("oneclick", "full_plan", "fullplan"),
])
def test_original_entry_to_five_exact_uploads(client, monkeypatch, mode, output, entry):
    calls = []
    def image_provider(prompt, references):
        calls.append(prompt)
        assert references == []
        raw = io.BytesIO()
        Image.new("RGB", (2000, 300), "#d9cab5").save(raw, "PNG")
        return raw.getvalue()
    monkeypatch.setattr("app.services.image_generation.call_qwen", image_provider)
    monkeypatch.setattr("app.services.image_generation.call_doubao", lambda *args: pytest.fail("No fallback provider"))
    project = client.post("/api/v1/projects", json={"name": "离线链路验收"}).json()["project_id"]
    base = f"/api/v1/projects/{project}/creations"
    creation = client.post(base, json={"mode": mode}).json()["creation_id"]
    base += "/" + creation
    saved = client.post(base + "/intake-runs", headers={"Idempotency-Key": "offline-input"}, json={
        "expected_revision": 0, "text": "店名：验收面馆，主推：面食，不放价格", "input_mode": "chat",
        "allow_illustration": True, "output_type": output, "delivery_types": ["five_panel"],
    })
    assert saved.status_code == 200, saved.text
    review = saved.json()
    assert review["snapshot"]["ready"]
    assert review["entry_mode"] == entry
    confirmation = dict(expected_revision=review["revision"], snapshot_hash=review["snapshot_hash"],
                        accepted_budget_policy="local-paid-generation-v1", materials_confirmed=True, approved_image_calls=1)
    response = client.post(base + "/confirm", headers={"Idempotency-Key": "offline-confirm"}, json=confirmation)
    assert response.status_code == 200, response.text
    task_id = response.json()["task_id"]
    assert run_once()
    result = client.get(f"/api/v1/tasks/{task_id}").json()
    assert result["status"] == "SUCCEEDED", result
    assert result["result"]["entry_mode"] == entry
    delivery = result["result"]
    if output == "full_plan":
        delivery = delivery["deliverables"][0]
    directory = settings.generated_dir / project / delivery.get("task_id", task_id)
    assert len(delivery["slices"]) == 5
    with Image.open(directory / delivery["long_image"]) as master:
        assert master.size == (4000, 600)
        for index, filename in enumerate(delivery["slices"]):
            with Image.open(directory / filename) as tile:
                assert tile.size == (800, 600)
                assert ImageChops.difference(tile, master.crop((800*index, 0, 800*(index+1), 600))).getbbox() is None
    editable = json.loads((directory / "editable-scene.json").read_text())
    validate_geometry(Scene.model_validate(editable["scene"]))
    assert client.get(base + "/review").json()["task_id"] == task_id
    assert client.post(base + "/confirm", headers={"Idempotency-Key": "offline-confirm"}, json=confirmation).json()["task_id"] == task_id
    assert len(calls) == 1  # Refresh/reconfirmation cannot repeat the provider.
