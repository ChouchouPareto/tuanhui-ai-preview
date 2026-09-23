import json
import uuid
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models import AgentRun, WorkflowTask, ModelCallRecord, DesignPlan
from app.services import agent_runtime


def project(client):
    return client.post('/api/v1/projects', json={'name':'工作台验收'}).json()['project_id']


def submit(client, p, **kwargs):
    body = {'request_key':str(uuid.uuid4()), 'text':'给山西面馆制作五连图',
            'facts':{'store_name':'山西面馆','hero_item':'牛肉面'}, **kwargs}
    response = client.post(f'/api/v1/projects/{p}/agent-runs', json=body)
    assert response.status_code == 200, response.text
    return response.json()


def finish(client, p, run):
    agent_runtime.run_job(run['id'])
    return client.get(f'/api/v1/projects/{p}/agent-runs/{run["id"]}').json()


def test_three_entries_preserve_origin_and_require_confirmation(client):
    for entry in ['oneclick','professional','fullplan']:
        p = project(client)
        run = finish(client, p, submit(client,p, entry_mode=entry, delivery_types=['five_panel']))
        assert run['state'] == 'SUCCEEDED', run
        review = run['result']['review']
        assert review['snapshot']['ready'], review
        with SessionLocal() as db:
            assert not db.scalars(select(ModelCallRecord)).all()
        response = client.post(f'/api/v1/projects/{p}/agent-runs/{run["id"]}/execute', json={
            'snapshot_hash':review['snapshot_hash'], 'approved_image_calls':1,
            'materials_confirmed':True, 'accepted_policy':'local-paid-generation-v1'})
        assert response.status_code == 200, response.text
        with SessionLocal() as db:
            task = db.get(WorkflowTask,response.json()['task_id'])
            assert task.result['entry_mode'] == entry


def test_complaint_does_not_call_model(client, monkeypatch):
    monkeypatch.setattr(agent_runtime.model_gateway, '_post_chat', lambda *a: (_ for _ in ()).throw(AssertionError('must not call')))
    p = project(client)
    run = finish(client,p,submit(client,p,text='文字重叠了，为什么？',approved_text_calls=1,accepted_policy='qwen-agent-text-v1'))
    assert run['state'] == 'SUCCEEDED', run
    assert run['result']['kind'] == 'answer'
    assert run['text_calls'] == 0


def test_language_budget_recorded_and_not_retried(client, monkeypatch):
    seen=[]
    def chat(model, messages):
        seen.append(model)
        return json.dumps({'intent':'prepare','reply':'请核对','facts':{}}), {'prompt_tokens':12,'completion_tokens':9}, 15
    monkeypatch.setattr(agent_runtime.model_gateway,'_post_chat',chat)
    p = project(client)
    initial=submit(client,p,approved_text_calls=1,accepted_policy='qwen-agent-text-v1')
    run=finish(client,p,initial)
    assert run['state']=='SUCCEEDED',run
    assert run['text_calls']==1 and len(seen)==1
    finish(client,p,initial)
    assert len(seen)==1


def test_invalid_fact_evidence_stops(client, monkeypatch):
    monkeypatch.setattr(agent_runtime.model_gateway,'_post_chat',lambda *a:(json.dumps({
        'intent':'prepare','reply':'核对','facts':{'hero_price':{'value':'9.9','quote':'只要9.9'}}}),{},4))
    p=project(client)
    run=finish(client,p,submit(client,p,approved_text_calls=1,accepted_policy='qwen-agent-text-v1'))
    assert run['state']=='NEEDS_USER'
    assert run['text_calls']==1
    assert '原文证据' in run['error']


def test_idempotency_cancel_and_cross_project(client):
    p=project(client)
    key=str(uuid.uuid4())
    first=submit(client,p,request_key=key)
    assert submit(client,p,request_key=key)['id']==first['id']
    response=client.post(f'/api/v1/projects/{p}/agent-runs',json={'request_key':key,'text':'不同的需求'})
    assert response.status_code==409
    client.post(f'/api/v1/projects/{p}/agent-runs/{first["id"]}/cancel')
    assert finish(client,p,first)['state']=='CANCELLED'
    other=project(client)
    assert client.get(f'/api/v1/projects/{other}/agent-runs/{first["id"]}').status_code==404


def test_workspace_cas_and_template_review(client, monkeypatch):
    from app.core.config import settings
    token='test-only-admin-token-with-32-characters'
    monkeypatch.setattr(settings, 'admin_api_token', token)
    headers={'Authorization':f'Bearer {token}'}
    p=project(client)
    path=f'/api/v1/projects/{p}/editor-workspace'
    assert client.get(path).json()['revision']==0
    assert client.patch(path,json={'expected_revision':0,'positions':{},'viewport':[2,3,1]}).json()['revision']==1
    assert client.patch(path,json={'expected_revision':0}).status_code==409
    templates=client.get('/api/v1/templates/reviews',headers=headers).json()
    row=templates[0]
    path=f'/api/v1/templates/{row["id"]}/review'
    assert client.post(path,headers=headers,json={'template_hash':'0'*64,'state':'approved'}).status_code==409
    assert client.post(path,headers=headers,json={'template_hash':row['template_hash'],'state':'approved'}).status_code==200
    assert client.get('/api/v1/templates/reviews',headers=headers).json()[0]['review_state']=='approved'


def test_new_creation_contract_never_supplies_empty_edit_objects():
    from app.agent_schemas import AgentInput
    for entry in ['oneclick','professional','fullplan']:
        payload=AgentInput(request_key='contract-test',text='做一张图',entry_mode=entry)
        context=agent_runtime.parent_context(payload,'new_creation',[])
        assert context['workflow_kind']=='new_creation'
        assert context['allow_illustration'] is True
        assert context['layout_owner']=='program_template_library'
        assert 'objects' not in context
        assert 'selected_object_id' not in context


def test_stopped_late_model_result_cannot_create_a_draft(client, monkeypatch):
    p=project(client)
    run=submit(client,p,approved_text_calls=1,accepted_policy='qwen-agent-text-v1')
    def chat(*args):
        client.post(f'/api/v1/projects/{p}/agent-runs/{run["id"]}/cancel')
        return json.dumps({'intent':'prepare','reply':'核对','facts':{}}),{},8
    monkeypatch.setattr(agent_runtime.model_gateway,'_post_chat',chat)
    result=finish(client,p,run)
    assert result['state']=='CANCELLED'
    assert not result['result']
    with SessionLocal() as db:
        assert db.scalar(select(ModelCallRecord)).status=='SUCCEEDED'
        assert not db.scalars(select(DesignPlan)).all()


def test_phrase_break_preserves_text():
    from PIL import Image,ImageDraw
    from app.services.master_layout import fitted_text
    from app.services.image_generation import _font
    draw=ImageDraw.Draw(Image.new('RGB',(800,600)))
    text='一碗热腾腾的山西牛肉面'
    width=draw.textlength('一碗热腾腾的山',font=_font(50))+1
    result=fitted_text(draw,text,(0,0,width,300),_font,'#222222',50)
    assert ''.join(result['lines'])==text
    assert result['lines'][0]=='一碗热腾腾的'


def test_copy_child_has_its_own_context_and_budget(client, monkeypatch):
    seen=[]
    def chat(model,messages):
        seen.append(messages)
        value={'intent':'prepare','reply':'核对','facts':{}} if len(seen)==1 else {'headline':'今晚吃碗热乎的面','subheadline':'把一餐留给自己'}
        return json.dumps(value,ensure_ascii=False),{},10
    monkeypatch.setattr(agent_runtime.model_gateway,'_post_chat',chat)
    p=project(client)
    run=finish(client,p,submit(client,p,approved_text_calls=2,accepted_policy='qwen-agent-text-v1'))
    assert run['state']=='SUCCEEDED',run
    assert run['text_calls']==2 and len(seen)==2
    assert 'objects' not in json.loads(seen[1][1]['content'])
    assert run['result']['review']['snapshot']['creative_draft']['headline']=='今晚吃碗热乎的面'
