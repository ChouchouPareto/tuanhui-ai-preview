from types import SimpleNamespace
from app.services.project_naming import update_project_name, five_image_name
from test_m1_creations import setup_creation, submit


def test_default_and_correction():
    project = SimpleNamespace(name="未命名门店项目")
    first = {"facts": {"store_name": "袁记云饺"}}
    update_project_name(project, first)
    assert project.name == "袁记云饺店铺五图项目"
    update_project_name(project, {"facts": {"store_name": "山城酸菜鱼"}}, first)
    assert project.name == "山城酸菜鱼店铺五图项目"


def test_custom_and_missing_names():
    project = SimpleNamespace(name="秋季新品活动")
    update_project_name(project, {"facts": {"store_name": "测试店"}})
    assert project.name == "秋季新品活动"
    assert five_image_name("") is None
    assert len(five_image_name("长" * 150)) <= 120


def test_intake_persists_project_title(client):
    project, asset, base = setup_creation(client)
    result = submit(client, base, asset).json()
    assert result["project_name"] == "测试店店铺五图项目"
    assert client.get(f"/api/v1/projects/{project}").json()["name"] == result["project_name"]
