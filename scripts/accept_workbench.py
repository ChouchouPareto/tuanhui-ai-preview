"""Opt-in live acceptance: <=3 text +3 image calls, no paid retry.

Use a fresh local isolated service. A persistent exclusive ledger prevents reruns.
"""
import argparse
import json
import time
from pathlib import Path
from uuid import uuid4
import httpx


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8021/api/v1')
    parser.add_argument('--ledger', required=True)
    parser.add_argument('--allow-paid-3-text-3-image', action='store_true')
    args=parser.parse_args()
    if not args.allow_paid_3_text_3_image:
        parser.error('Requires explicit budget authorization')
    ledger=Path(args.ledger)
    ledger.mkdir(parents=True, exist_ok=True)
    # Never silently resume paid execution after process interruption.
    with (ledger/'started.json').open('x') as f:
        json.dump({'text_limit':3,'image_limit':3,'automatic_retry':False,'started_at':time.time()},f)
    client=httpx.Client(base_url=args.base, timeout=30)
    def request(method,path,body=None):
        response=client.request(method,path,json=body)
        response.raise_for_status()
        return response.json()
    def save(name,value):
        with (ledger/name).open('x',encoding='utf8') as f:
            json.dump(value,f,ensure_ascii=False,indent=2)
    def poll(path,field):
        deadline=time.monotonic()+360
        while time.monotonic()<deadline:
            value=request('GET',path)
            if value[field] not in {'QUEUED','PENDING','RUNNING'}:
                return value
            time.sleep(2)
        raise TimeoutError('Result unknown; no retry')
    receipts=[]
    for entry,output in [('oneclick','five_panel'),('professional','three_panel'),('fullplan','store_decoration')]:
        started=time.monotonic()
        receipt={'entry':entry, 'image_submitted':False}
        try:
            project=request('POST','/projects',{'name':f'本轮千问验收-{entry}'})['project_id']
            receipt['project_id']=project
            save(f'{entry}-authorization.json',{'project_id':project,'text_calls':1,'image_calls':1})
            label={'five_panel':'五连图','three_panel':'三连图','store_decoration':'首页装修图'}[output]
            run=request('POST',f'/projects/{project}/agent-runs',{
                'request_key':str(uuid4()),'entry_mode':entry,'output_type':output,
                'delivery_types':[output], 'text':f'给山西面馆制作{label}，主推牛肉面。简约温暖，不放价格。',
                'facts':{'store_name':'山西面馆','hero_item':'牛肉面'},
                'style':'minimal','allow_illustration':True,'show_price':False,'show_store_name':True,
                'approved_text_calls':1,'accepted_policy':'qwen-agent-text-v1'})
            receipt['agent_id']=run['id']
            run=poll(f'/projects/{project}/agent-runs/{run["id"]}','state')
            save(f'{entry}-agent.json',run)
            receipt['text_calls']=run['text_calls']
            if run['state']!='SUCCEEDED' or run['result'].get('kind')!='review':
                receipt['outcome']='agent_not_ready'
            else:
                review=run['result']['review']
                if not review['snapshot']['ready'] or len(review['snapshot']['delivery_types'])!=1:
                    receipt['outcome']='review_not_ready_or_over_budget'
                else:
                    confirmed=request('POST',f'/projects/{project}/agent-runs/{run["id"]}/execute',{
                        'snapshot_hash':review['snapshot_hash'],'approved_image_calls':1,
                        'materials_confirmed':True,'accepted_policy':'local-paid-generation-v1'})
                    receipt['image_submitted']=True
                    receipt['task_id']=confirmed['task_id']
                    task=poll(f'/tasks/{confirmed["task_id"]}','status')
                    save(f'{entry}-task.json',task)
                    receipt['outcome']=task['status']
                    usage=request('GET',f'/projects/{project}/usage')
                    save(f'{entry}-usage.json',usage)
        except Exception as exc:
            # Do not print headers, keys or raw upstream HTTP bodies.
            receipt['outcome']='unknown_or_failed'
            receipt['error_type']=type(exc).__name__
        receipt['elapsed_seconds']=round(time.monotonic()-started,2)
        receipts.append(receipt)
        save(f'{entry}-receipt.json',receipt)
        print(json.dumps(receipt,ensure_ascii=False),flush=True)
    save('summary.json',receipts)


if __name__=='__main__':
    main()
