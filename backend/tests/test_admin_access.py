from app.core.config import settings


def test_admin_routes_fail_closed(client, monkeypatch):
    monkeypatch.setattr(settings, 'admin_api_token', '')
    for path in ['/api/v1/templates/reviews', '/api/v1/agent/contracts']:
        assert client.get(path).status_code == 503


def test_management_auth_cannot_be_bypassed_by_direct_api(client, monkeypatch):
    token = 'test-only-admin-token-with-32-characters'
    monkeypatch.setattr(settings, 'admin_api_token', token)
    for path in ['/api/v1/templates/reviews', '/api/v1/agent/contracts']:
        for headers in [{}, {'Authorization':'Bearer wrong'}, {'Authorization':token}]:
            assert client.get(path, headers=headers).status_code == 401
        response = client.get(path, headers={'Authorization':f'Bearer {token}'})
        assert response.status_code == 200
        assert token not in response.text
    assert client.post('/api/v1/templates/L01/review', json={
        'template_hash':'0'*64, 'state':'approved'}).status_code == 401
    assert client.get('/api/v1/projects').status_code == 200
