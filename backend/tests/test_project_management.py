from test_m1_creations import setup_creation, submit


def test_hide_delete_restore_and_edit(client):
    project, _, _ = setup_creation(client)
    url = f"/api/v1/projects/{project}"
    assert client.patch(url, json={"name":"自定义活动"}).status_code == 200
    for visibility in ["hidden", "deleted"]:
        assert client.patch(url, json={"visibility":visibility}).status_code == 200
        assert not any(p["id"] == project for p in client.get('/api/v1/projects').json())
        assert any(p["id"] == project for p in client.get(f'/api/v1/projects?visibility={visibility}').json())
        assert client.get(url+'/assets').json()
    client.patch(url, json={"visibility":"visible"})
    assert any(p["id"] == project for p in client.get('/api/v1/projects').json())


def test_duplicate_does_not_generate_and_custom_name_survives(client):
    project, asset, base = setup_creation(client)
    client.patch(f'/api/v1/projects/{project}', json={"name":"我自己的标题"})
    assert submit(client,base,asset).json()['project_name'] == '我自己的标题'
    response=client.post(f'/api/v1/projects/{project}/duplicate')
    assert response.status_code == 201, response.text
    copy=response.json()['project_id']
    assets=client.get(f'/api/v1/projects/{copy}/assets').json()
    assert len(assets) == 1 and assets[0]['id'] != asset
    assert client.get('/api/v1'+assets[0]['preview_path']).status_code == 200
    assert client.get(f'/api/v1/projects/{copy}/workspace').json()['tasks'] == []
