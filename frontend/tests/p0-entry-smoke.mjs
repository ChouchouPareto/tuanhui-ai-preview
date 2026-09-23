// Real Chrome + entirely mocked API. No application writes or model requests.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtemp, readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
const profile = await mkdtemp(path.join(tmpdir(), 'tuanhui-p0-browser-'));
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ['--headless=new', '--no-first-run', '--disable-background-networking', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], {stdio:'ignore'});
const sleep = ms => new Promise(r => setTimeout(r, ms));
const origin = process.env.TEST_ORIGIN || 'http://127.0.0.1:3011';
let socket;
try {
  let port;
  for (let i=0;i<60;i++) {
    try {port = (await readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]; break;} catch {await sleep(200);}
  }
  assert.ok(port, 'Chrome did not start');
  const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket = new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);
  await new Promise(r=>socket.addEventListener('open',r,{once:true}));
  let sequence=0, mode='oneclick', fresh=false, revision=0, creationState='DRAFT';
  const pending=new Map(), requests=[], errors=[];
  function send(method, params={}) {
    const id=++sequence;
    return new Promise((resolve,reject)=>{
      const timeout=setTimeout(()=>{pending.delete(id);reject(new Error(`Timeout ${method}`));},15000);
      pending.set(id,{resolve:v=>{clearTimeout(timeout);resolve(v);},reject:e=>{clearTimeout(timeout);reject(e);}});
      socket.send(JSON.stringify({id,method,params}));
    });
  }
  const snapshot = () => ({schema_version:2,text:'验收面馆',facts:{store_name:'验收面馆'},sources:{},assets:[],
    show_price:false,show_store_name:true,style:'minimal',provider:'qwen',gaps:[],ready:true,project_changes:[],
    render_mode:'illustration',output_type:mode==='fullplan'?'full_plan':'five_panel',delivery_types:mode==='fullplan'?['store_decoration']:['five_panel'],messages:[]});
  const task = () => ({id:'t',project_id:'p',creation_id:mode==='professional'&&!fresh?null:'c',status:mode==='professional'&&!fresh?'FAILED_FINAL':'SUCCEEDED',progress:100,
    result:{design_plan_id:'plan-old',entry_mode:mode,output_type:mode==='fullplan'?'store_decoration':'five_panel'},error:null});
  const plan={id:'plan-old',plan_hash:'a'.repeat(64),version:1,status:'CONFIRMED',plan:{canvas:{ratio:'20:3',slice_count:5,slice_ratio:'4:3'},style:{key:'minimal',name:'清爽简约',keywords:[]},copy:{headline:'面食',subheadline:'',store_name:'验收面馆',price:''},frames:[],guardrails:[]}};
  socket.addEventListener('message', async event=>{
    const data=JSON.parse(event.data);
    if(data.id){const item=pending.get(data.id);if(item){pending.delete(data.id);data.error?item.reject(new Error(JSON.stringify(data.error))):item.resolve(data.result);}return;}
    try {
      if(data.method==='Runtime.exceptionThrown')errors.push(data.params.exceptionDetails.exception?.description || data.params.exceptionDetails.text);
      if(data.method==='Page.javascriptDialogOpening')await send('Page.handleJavaScriptDialog',{accept:true});
      if(data.method!=='Fetch.requestPaused')return;
      const {requestId,request}=data.params, url=new URL(request.url), p=url.pathname;
      if(!p.includes('/api/v1/')) {
        if(!['127.0.0.1','localhost'].includes(url.hostname) || !['GET','HEAD'].includes(request.method)) await send('Fetch.failRequest',{requestId,errorReason:'BlockedByClient'});
        else await send('Fetch.continueRequest',{requestId});
        return;
      }
      requests.push({mode,path:p,method:request.method,body:request.postData?JSON.parse(request.postData):null});
      let body={};
      if(p.endsWith('/projects/p'))body={id:'p',name:'验收面馆',status:'GENERATED'};
      else if(p.endsWith('/projects'))body=[];
      else if(p.endsWith('/assets'))body=[];
      else if(p.endsWith('/creations')&&request.method==='POST') {creationState='DRAFT';revision=0;body={creation_id:'c',entry_mode:mode,revision,status:creationState,snapshot:null};}
      else if(p.endsWith('/intake-runs')) {revision++;creationState='READY_TO_CONFIRM';body={creation_id:'c',entry_mode:mode,revision,status:creationState,snapshot_hash:'b'.repeat(64),snapshot:snapshot()};}
      else if(p.endsWith('/confirm')) {creationState='CONFIRMED';body={task_id:'t'};}
      else if(p.endsWith('/review'))body={creation_id:'c',entry_mode:mode,revision:fresh?revision:1,status:fresh?creationState:'CONFIRMED',snapshot_hash:'b'.repeat(64),snapshot:snapshot(),task_id:!fresh||creationState==='CONFIRMED'?'t':null};
      else if(p.endsWith('/tasks/t'))body=task();
      else if(p.includes('/design-plans/'))body=plan;
      else if(p.endsWith('/workspace'))body={latest_creation_id:mode==='professional'?null:'c',tasks:[task()]};
      else if(p.endsWith('/activity'))body={current:null,spans:[],server_time:new Date().toISOString()};
      else if(p.endsWith('/dialogue/history'))body=[];
      else if(p.endsWith('/dialogue/route'))body=fresh?{schema_version:'dialogue-safety-v1',intent:'new_creation',action:'prepare',can_prepare:true,reply:'',model_calls:0}:{schema_version:'dialogue-safety-v1',intent:'report_issue',action:'answer',can_prepare:false,reply:'已检查，没有重新生成。',next_steps:[],model_calls:0};
      else if(p.endsWith('/generation-runs'))body={task_id:'t'};
      else if(!['GET','OPTIONS'].includes(request.method))throw new Error(`Unexpected write ${p}`);
      await send('Fetch.fulfillRequest',{requestId,responseCode:200,responseHeaders:[{name:'content-type',value:'application/json'},{name:'access-control-allow-origin',value:'*'},{name:'access-control-allow-headers',value:'*'},{name:'access-control-allow-methods',value:'*'}],body:Buffer.from(JSON.stringify(body)).toString('base64')});
    } catch(error){errors.push(String(error));}
  });
  await send('Page.enable');await send('Runtime.enable');
  await send('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]});
  const evaluate = async expression => (await send('Runtime.evaluate',{expression,returnByValue:true})).result.value;
  async function until(expression){for(let i=0;i<80;i++){if(await evaluate(`Boolean(document.body) && (${expression})`))return;await sleep(150);}throw new Error(`DOM condition failed: ${expression}; ${await evaluate('document.body.innerText')}; requests=${JSON.stringify(requests)}; errors=${JSON.stringify(errors)}`);}
  for(mode of ['oneclick','fullplan']) {
    await send('Page.navigate',{url:`${origin}${mode==='fullplan'?'/full-plan':'/'}?project=p&creation=c`});
    await until(`!!Array.from(document.querySelectorAll('a')).find(a=>a.textContent==='继续下一次创作')`);
    const href=await evaluate(`Array.from(document.querySelectorAll('a')).find(a=>a.textContent==='继续下一次创作').getAttribute('href')`);
    assert.equal(href,`${mode==='fullplan'?'/full-plan':'/'}?project=p&compose=1`);
    await evaluate(`(()=>{const t=document.querySelector('textarea');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(t,'文字重叠，先检查，不要生成');t.dispatchEvent(new Event('input',{bubbles:true}));})()`);
    await sleep(200);
    await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='发送').click()`);
    for(let i=0;i<30&&!requests.some(r=>r.mode===mode&&r.path.endsWith('/dialogue/route'));i++)await sleep(100);
    assert.ok(requests.some(r=>r.mode===mode&&r.path.endsWith('/dialogue/route')));
    assert.ok(!requests.some(r=>r.mode===mode&&r.method==='POST'&&!r.path.endsWith('/dialogue/route')));
    assert.equal(await evaluate(`document.querySelectorAll('.studioConsent[open]').length`),0);
  }
  mode='professional';
  await send('Page.navigate',{url:`${origin}/professional?project=p&task=t`});
  await until(`!!Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='专业创作')`);
  await sleep(700);
  await until(`!!document.querySelector('.generationButton')`);
  const readsBefore=requests.filter(r=>r.path.endsWith('/tasks/t')&&r.method==='GET').length;
  await evaluate(`document.querySelector('.generationButton').click()`);
  await sleep(600);
  assert.ok(requests.filter(r=>r.path.endsWith('/tasks/t')&&r.method==='GET').length>readsBefore);
  assert.ok(!requests.some(r=>r.method==='POST'&&r.path.endsWith('/generation-runs')), 'Viewing a legacy failed task must never reserve another generation');
  assert.ok(!requests.some(r=>r.mode==='professional'&&r.path.endsWith('/design-plans/latest')));
  // A fresh reviewed plan still sends its explicit ID and fingerprint.
  await send('Page.navigate',{url:`${origin}/professional?project=p`});
  await until(`!!Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='专业创作')`);
  await sleep(700);
  await until(`!!document.querySelector('.generationButton')`);
  await evaluate(`document.querySelector('.generationButton').click()`);
  for(let i=0;i<40&&!requests.some(r=>r.method==='POST'&&r.path.endsWith('/generation-runs'));i++)await sleep(100);
  const generated=requests.find(r=>r.method==='POST'&&r.path.endsWith('/generation-runs'));
  assert.ok(generated,'Professional generation request missing');
  assert.equal(generated.body.plan_id,'plan-old');assert.equal(generated.body.plan_hash,plan.plan_hash);
  assert.equal(generated.body.allow_fallback,false);
  assert.match(generated.body.request_id,/^[A-Za-z0-9_-]{1,128}$/);
  fresh=true;
  const start=requests.length;
  await send('Page.navigate',{url:`${origin}/professional?project=p&compose=1`});
  await until(`!!document.querySelector('.quickComposer textarea') && !document.querySelector('.quickSubmit').disabled`);
  await sleep(500);
  await evaluate(`(()=>{const t=document.querySelector('textarea');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(t,'主推：面食，不放价格，用AI示意图');t.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await sleep(150);
  await evaluate(`document.querySelector('.quickSubmit').click()`);
  await until(`!!document.querySelector('.studioConsent[open]')`);
  await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='同意并开始').click()`);
  await until(`!!document.querySelector('.inlineGenerate')`);
  const submitted=requests.slice(start);
  assert.equal(submitted.find(r=>r.method==='POST'&&r.path.endsWith('/creations')).body.mode,'pro');
  assert.ok(submitted.some(r=>r.path.endsWith('/intake-runs')));
  assert.ok(!submitted.some(r=>r.path.endsWith('/analysis-runs')||r.path.endsWith('/confirm')));
  assert.equal(await evaluate(`document.querySelector('.quickAssetRail') !== null`),true,'Original professional reference rail retained');
  assert.equal(await evaluate(`document.body.innerText.includes('新版创作')`),false);
  await evaluate(`document.querySelector('.inlineGenerate').click()`);
  await until(`!!Array.from(document.querySelectorAll('a')).find(a=>a.textContent==='继续下一次创作')`);
  assert.equal(await evaluate(`Array.from(document.querySelectorAll('a')).find(a=>a.textContent==='继续下一次创作').getAttribute('href')`),'/professional?project=p&compose=1');
  const beforeReload=requests.length;
  await send('Page.reload');
  await until(`!!document.querySelector('.quickComposer') && !!Array.from(document.querySelectorAll('a')).find(a=>a.textContent==='继续下一次创作')`);
  assert.ok(!requests.slice(beforeReload).some(r=>r.method==='POST'),'Reload is read-only');
  assert.deepEqual(errors,[]);
  console.log('PASS Chrome mocked API: original three modules, professional no mandatory name/photos, explicit review, continuation/reload, complaint safety and legacy plan binding. No real API writes.');
} finally {socket?.close();chrome.kill('SIGTERM');}
