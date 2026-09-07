from app.core.database import SessionLocal
from app.models import WorkflowTask, TaskStatus


def test_project_list_and_scoped_history(client):
    ids = [client.post('/api/v1/projects', json={'name': name, 'industry': '餐饮', 'platforms': ['meituan']}).json()['project_id'] for name in ['甲店', '乙店']]
    with SessionLocal() as db:
        task = WorkflowTask(project_id=ids[0], task_type='group_buying_image_generation', status=TaskStatus.SUCCEEDED, result={'long_image': 'long.png'})
        db.add(task)
        db.commit()
    listing = client.get('/api/v1/projects').json()
    assert len(listing) == 2
    assert next(p for p in listing if p['id'] == ids[0])['task_count'] == 1
    assert len(client.get(f'/api/v1/projects/{ids[0]}/workspace').json()['tasks']) == 1
    assert client.get(f'/api/v1/projects/{ids[1]}/workspace').json()['tasks'] == []
    assert client.get('/api/v1/projects/missing/workspace').status_code == 404
