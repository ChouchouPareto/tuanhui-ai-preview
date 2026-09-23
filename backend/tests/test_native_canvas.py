import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image, ImageChops
from sqlalchemy import select, func

from app.core.database import SessionLocal
from app.core.config import settings
from app.models import (StoreProject, CanvasVersion, ModelCallRecord, WorkflowTask,
                        TaskStatus, ProjectDisplayState, WorkflowEvent)
from app.services.design_plan import build_design_plan
from app.services.image_generation import render_and_slice


def project():
    with SessionLocal() as db:
        row = StoreProject(name="测试店铺")
        db.add(row)
        db.commit()
        return row.id


def scene(**kwargs):
    return {"nodes": [
        {"id": "title", "role": "headline", "box": [.025, .10, .15, .25], "text": "午餐吃好一点", "color": "#111111"},
        {"id": "subtitle", "role": "subheadline", "box": [.025, .42, .15, .16], "text": "来一碗热面", "color": "#333333"},
    ], **kwargs}


def setup(client, body=None):
    p = project()
    base = f"/api/v1/projects/{p}/canvases"
    response = client.post(base, json={"scene": body or scene()})
    assert response.status_code == 200, response.text
    data = response.json()
    return p, base + "/" + data["document_id"], data


def change(client, url, ver, operations, key="edit-key-0001"):
    return client.post(url+"/mutations", json={"base_version_id": ver, "request_key": key, "operations": operations})


def operation(text):
    return [{"op": "update", "object_id": "title", "patch": {"text": text}}]


def test_target_resolution_requires_unique_object_and_action(client):
    _, url, doc = setup(client)
    def resolve(**kw):
        r = client.post(url+"/resolve-edit", json={"version_id": doc["version_id"], **kw})
        assert r.status_code == 200, r.text
        return r.json()
    assert resolve(message="标题改成好好吃饭")["status"] == "needs_target"
    assert resolve(message="改一下")["status"] == "needs_target"
    assert resolve(message="主标题改一下")["status"] == "needs_action"
    assert resolve(message="主标题颜色改为红色")["status"] == "needs_action"
    assert resolve(message="不要把主标题改成好好吃饭")["status"] == "needs_action"
    assert resolve(message="能不能把主标题改成好好吃饭")["status"] == "needs_action"
    assert resolve(message="主标题改成好好吃饭", selected_object_id="subtitle")["status"] == "target_conflict"
    assert resolve(quote="来一碗热面", role="headline", replacement="好好吃饭")["status"] == "target_conflict"
    assert resolve(message="把“来一碗热面”改成“今天吃点热乎的”")["status"] == "ready"
    assert len(client.get(url+"/versions").json()) == 1
    resolved = resolve(message="主标题改成好好吃饭")
    assert resolved["status"] == "ready"
    assert resolved["before"] == "午餐吃好一点"
    applied = client.post(url+f"/proposals/{resolved['proposal_id']}/apply", json={
        "base_version_id": doc["version_id"], "request_key": "apply-key-001"})
    assert applied.status_code == 200, applied.text
    updated = applied.json()
    assert updated["scene"]["nodes"][0]["text"] == "好好吃饭"
    assert updated["scene"]["nodes"][1] == doc["scene"]["nodes"][1]
    assert updated["image_model_calls"] == 0
    assert client.post(url+f"/proposals/{resolved['proposal_id']}/apply", json={
        "base_version_id": doc["version_id"], "request_key": "apply-key-002"}).json()["version_id"] == updated["version_id"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ModelCallRecord)) == 0
        assert db.scalar(select(func.count()).select_from(WorkflowEvent).where(WorkflowEvent.stage == "canvas_edit")) == 1


def test_immutable_versions_idempotency_restore_and_fork(client):
    _, url, doc = setup(client)
    body = operation("认真吃一餐")
    first = change(client, url, doc["version_id"], body).json()
    assert change(client, url, doc["version_id"], body).json()["version_id"] == first["version_id"]
    assert change(client, url, doc["version_id"], operation("另一句")).json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert change(client, url, doc["version_id"], body, "another-key").json()["detail"]["code"] == "STALE_VERSION"
    assert client.get(url+"/versions/"+doc["version_id"]).json()["scene"] == doc["scene"]
    restored = client.post(url+"/restore", json={"base_version_id": first["version_id"],
        "target_version_id": doc["version_id"], "request_key": "restore-key"}).json()
    assert restored["scene"] == doc["scene"]
    assert restored["version_id"] not in {first["version_id"], doc["version_id"]}
    assert restored["parent_version_id"] == first["version_id"]
    fork = client.post(url+"/versions/"+doc["version_id"]+"/fork").json()
    assert fork["document_id"] != doc["document_id"] and fork["scene"] == doc["scene"]
    assert client.get(url).json()["version_id"] == restored["version_id"]


def test_two_writers_never_overwrite_each_other(client):
    _, url, doc = setup(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda i: change(client, url, doc["version_id"], operation(f"午餐选择{i}"), f"parallel-{i}"), range(2)))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert len(client.get(url+"/versions").json()) == 2


def test_concurrent_same_request_returns_one_version(client):
    _, url, doc = setup(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: change(client, url, doc["version_id"], operation("午餐吃好一点")), range(2)))
    assert [r.status_code for r in results] == [200, 200]
    assert len({r.json()["version_id"] for r in results}) == 1
    assert len(client.get(url+"/versions").json()) == 2


def test_failed_persistence_rolls_back_head_and_records_rejection(client, monkeypatch):
    from app.services import canvas
    from app.services.intake import fail
    _, url, doc = setup(client)
    def fail_write(*args):
        fail("VERSION_SAVE_FAILED", "测试存储失败", 503)
    monkeypatch.setattr(canvas, "save_render", fail_write)
    response = change(client, url, doc["version_id"], operation("换一句标题"))
    assert response.status_code == 503
    assert client.get(url).json()["version_id"] == doc["version_id"]
    assert len(client.get(url+"/versions").json()) == 1
    with SessionLocal() as db:
        event = db.scalar(select(WorkflowEvent).where(WorkflowEvent.error_code == "VERSION_SAVE_FAILED"))
        assert event and event.duration_ms >= 1


def test_frozen_pixels_do_not_depend_on_later_font_or_render_code(client, monkeypatch):
    from app.services import canvas_render
    p, url, doc = setup(client)
    path = url+"/versions/"+doc["version_id"]+"/assets/long.png"
    before = client.get(path).content
    def forbidden(*a, **kw):
        raise AssertionError("Historical export must not render again")
    monkeypatch.setattr(canvas_render, "fitted_text", forbidden)
    assert client.get(path).content == before
    artifact = settings.generated_dir / p / "canvas_versions" / doc["document_id"] / doc["version_id"] / "marked.png"
    artifact.write_bytes(b"corrupted isolated test artifact")
    assert client.get(path).json()["detail"]["code"] == "VERSION_ARTIFACT_CHANGED"


def test_lock_geometry_overflow_and_scope_guards(client):
    p, url, doc = setup(client)
    for patch in ({"box": [.025, .42, .15, .16]}, {"box": [.18, .1, .1, .25]},
                  {"box": [-.1, 0, .1, .2]}, {"text": "很长的标题"*100}):
        r = change(client, url, doc["version_id"], [{"op": "update", "object_id": "title", "patch": patch}])
        assert r.status_code == 422, r.text
    assert len(client.get(url+"/versions").json()) == 1
    locked = change(client, url, doc["version_id"], [{"op": "lock", "object_id": "title"}]).json()
    r = change(client, url, locked["version_id"], operation("新标题"), "second-key")
    assert r.json()["detail"]["code"] == "OBJECT_LOCKED"
    other = project()
    assert client.get(url.replace(p, other)).status_code == 404
    with SessionLocal() as db:
        db.add(ProjectDisplayState(project_id=p, visibility="deleted"))
        db.commit()
    assert client.get(url).status_code == 404


@pytest.mark.parametrize("output_type", ["logo", "package_main", "voucher_main"])
def test_square_safe_zone(output_type, client):
    body = scene(output_type=output_type, width=800, height=600, slice_count=1)
    base = f"/api/v1/projects/{project()}/canvases"
    assert client.post(base, json={"scene": body}).status_code == 422
    for node in body["nodes"]:
        node["box"][0], node["box"][2] = .15, .70
    assert client.post(base, json={"scene": body}).status_code == 200


@pytest.mark.parametrize("output_type,width,count", [("five_panel", 4000, 5), ("three_panel", 2400, 3), ("detail", 800, 1)])
def test_real_png_export_and_inline_preview(output_type, width, count, client):
    _, url, doc = setup(client, scene(output_type=output_type, width=width, slice_count=count, height=600, ai_generated=True))
    path = url+"/versions/"+doc["version_id"]
    marked = client.get(path+"/assets/long.png")
    assert marked.status_code == 200 and marked.headers["content-disposition"].startswith("inline")
    clean = client.get(path+"/assets/long.png?watermark=false")
    a, b = Image.open(io.BytesIO(marked.content)), Image.open(io.BytesIO(clean.content))
    assert a.size == (width, 600) and ImageChops.difference(a, b).getbbox()
    assert client.get(path+"/assets/01.png?download=true").headers["content-disposition"].startswith("attachment")
    archive = client.post(path+"/export?watermark=false")
    assert archive.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
        assert len(z.namelist()) == count+1
        for name in z.namelist():
            assert Image.open(z.open(name)).size == ((width, 600) if name == "long.png" else (800, 600))
    assert client.get(path+"/assets/secret.png").status_code == 404


def test_native_generation_import_edit_pixel_preservation(client, monkeypatch):
    from app.services import image_generation
    def forbidden(*a, **kw):
        raise AssertionError("local edit must not call image model")
    monkeypatch.setattr(image_generation, "call_qwen", forbidden)
    monkeypatch.setattr(image_generation, "call_doubao", forbidden)
    p = project()
    plan = build_design_plan({"store_name": "测试面馆", "copy_headline": "今天吃点热乎的"})
    with SessionLocal() as db:
        task = WorkflowTask(project_id=p, task_type="generate", status=TaskStatus.SUCCEEDED)
        db.add(task); db.commit()
        task_id = task.id
    folder = settings.generated_dir / p / task_id
    raw = io.BytesIO()
    Image.new("RGB", (4000, 600), "#384738").save(raw, format="PNG")
    render_and_slice(raw.getvalue(), plan, folder)
    assert (folder / "editable-scene.json").is_file()
    base = f"/api/v1/projects/{p}/canvases"
    response = client.post(base+"/import", json={"task_id": task_id})
    assert response.status_code == 200, response.text
    doc = response.json(); url = base+"/"+doc["document_id"]
    original = client.get(url+"/versions/"+doc["version_id"]+"/assets/long.png?watermark=false")
    title = next(n for n in doc["scene"]["nodes"] if n["role"] == "headline")
    updated = change(client, url, doc["version_id"], [{"op": "update", "object_id": title["id"], "patch": {"text": "认真吃一餐"}}]).json()
    latest = client.get(url+"/versions/"+updated["version_id"]+"/assets/long.png?watermark=false")
    diff = ImageChops.difference(Image.open(io.BytesIO(original.content)), Image.open(io.BytesIO(latest.content))).getbbox()
    assert diff
    x,y,w,h = title["box"]
    assert diff[0] >= int(x*4000)-1 and diff[2] <= int((x+w)*4000)+1
    assert diff[1] >= int(y*600)-1 and diff[3] <= int((y+h)*600)+1
    assert (folder / "long-clean.png").read_bytes()  # old task remains intact
    with SessionLocal() as db:
        assert db.get(WorkflowTask, task_id).status == TaskStatus.SUCCEEDED
        assert db.scalar(select(func.count()).select_from(ModelCallRecord)) == 0
    (folder / "typography-base.png").unlink()  # isolated test artifact only
    # Delivered versions remain readable even if an old generation source goes missing.
    assert client.get(url+"/versions/"+updated["version_id"]+"/assets/long.png").status_code == 200
    denied = change(client, url, updated["version_id"], [{"op": "update", "object_id": title["id"], "patch": {"text": "换一句"}}], "source-missing")
    assert denied.json()["detail"]["code"] == "SOURCE_CHANGED"


def test_flat_history_is_not_falsely_editable(client):
    p = project()
    with SessionLocal() as db:
        task = WorkflowTask(project_id=p, task_type="generate", status=TaskStatus.SUCCEEDED)
        db.add(task); db.commit(); tid = task.id
    r = client.post(f"/api/v1/projects/{p}/canvases/import", json={"task_id": tid})
    assert r.json()["detail"]["code"] == "NO_EDITABLE_SOURCE"


def test_asset_roles_and_project_binding_are_enforced(client):
    from test_m1_creations import setup_creation
    from app.models import SourceAsset
    p, asset_id, _ = setup_creation(client)
    body = scene()
    body["nodes"].append({"id": "photo", "kind": "image", "role": "photo", "asset_id": asset_id,
                          "box": [.3, .1, .15, .5]})
    path = f"/api/v1/projects/{p}/canvases"
    with SessionLocal() as db:
        asset = db.get(SourceAsset, asset_id)
        asset.semantic_role = "storefront"
        db.commit()
    denied = client.post(path, json={"scene": body})
    assert denied.json()["detail"]["code"] == "ASSET_ROLE_FORBIDDEN"
    with SessionLocal() as db:
        asset = db.get(SourceAsset, asset_id)
        asset.semantic_role = "dish"
        db.commit()
    assert client.post(path, json={"scene": body}).status_code == 200
    assert client.post(f"/api/v1/projects/{project()}/canvases", json={"scene": body}).status_code == 404


def test_additive_migration_fresh_and_bootstrapped(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect
    from app.core.database import Base
    from pathlib import Path
    cfg = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    database = tmp_path / "migration.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database}")
    command.upgrade(cfg, "head")
    engine = create_engine(settings.database_url)
    assert {"canvas_documents", "canvas_versions", "canvas_mutations", "canvas_proposals"} <= set(inspect(engine).get_table_names())
    engine.dispose()
    bootstrap = tmp_path / "bootstrap.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{bootstrap}")
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    command.stamp(cfg, "d8a1b2c3d4e5")
    command.upgrade(cfg, "head")
    assert len(inspect(engine).get_columns("canvas_versions")) == 8
    engine.dispose()
