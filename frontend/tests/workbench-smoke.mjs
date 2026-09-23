// Chrome UI + isolated real API, zero model calls. No old project writes.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtemp,readFile,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
const origin=process.env.WORKBENCH_ORIGIN||'http://127.0.0.1:3011';
const api=process.env.WORKBENCH_API||'http://127.0.0.1:8021';
const profile=await mkdtemp(path.join(tmpdir(),'tuanhui-workbench-browser-'));
const chrome=spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',['--headless=new','--no-first-run','--disable-background-networking','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{stdio:'ignore'});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let socket;
try{
 let port;
 for(let i=0;i<60;i++){try{port=(await readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break;}catch{await sleep(200);}}
 const pages=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
 socket=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);
 await new Promise(r=>socket.addEventListener('open',r,{once:true}));
 const pending=new Map(),errors=[];let sequence=0;
 function send(method,params={}){const id=++sequence;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error(`CDP timeout: ${method}`)),15000);pending.set(id,{resolve:r=>{clearTimeout(timer);resolve(r);},reject:e=>{clearTimeout(timer);reject(e);}});socket.send(JSON.stringify({id,method,params}));});}
 socket.addEventListener('message',async event=>{const data=JSON.parse(event.data);if(data.id){const p=pending.get(data.id);if(p){pending.delete(data.id);data.error?p.reject(Error(JSON.stringify(data.error))):p.resolve(data.result);}return;}
  if(data.method==='Runtime.exceptionThrown')errors.push(data.params.exceptionDetails.exception?.description||data.params.exceptionDetails.text);
  if(data.method!=='Fetch.requestPaused')return;
  const {requestId,request}=data.params,u=new URL(request.url);
  try{
   if(!u.pathname.startsWith('/api/v1/')){await send('Fetch.continueRequest',{requestId});return;}
   if(request.method==='OPTIONS'){await send('Fetch.fulfillRequest',{requestId,responseCode:204,responseHeaders:[{name:'Access-Control-Allow-Origin',value:origin},{name:'Access-Control-Allow-Methods',value:'GET,POST,PATCH,OPTIONS'},{name:'Access-Control-Allow-Headers',value:'content-type'}]});return;}
   if(/\/execute$|\/confirm$|generation-runs|analysis-runs/.test(u.pathname))throw Error('Blocked paid operation');
   const body=request.postData?JSON.parse(request.postData):undefined;
   if(body?.approved_text_calls>0)throw Error('Blocked paid language operation');
   const r=await fetch(api+u.pathname+u.search,{method:request.method,headers:body?{'content-type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined});
   await send('Fetch.fulfillRequest',{requestId,responseCode:r.status,responseHeaders:[{name:'Content-Type',value:r.headers.get('content-type')||'application/json'},{name:'Access-Control-Allow-Origin',value:origin}],body:Buffer.from(await r.arrayBuffer()).toString('base64')});
  }catch(e){errors.push(e.message);await send('Fetch.failRequest',{requestId,errorReason:'BlockedByClient'});}
 });
 await send('Runtime.enable');await send('Page.enable');await send('Fetch.enable',{patterns:[{urlPattern:'*api/v1/*'}]});
 async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value;}
 async function waitFor(expression){for(let i=0;i<120;i++){if(await evaluate(`Boolean(document.body) && (${expression})`))return;await sleep(250);}throw Error(`UI timeout ${expression}: ${await evaluate('document.body?.innerText.slice(-2000)')}`);}
 async function click(label){await evaluate(`(()=>{const el=[...document.querySelectorAll('button')].find(e=>e.textContent===${JSON.stringify(label)});if(!el||el.disabled)throw Error('button missing/disabled');el.click();})()`);}
 async function fill(selector,value){await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});const proto=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:e.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event(e.tagName==='SELECT'?'change':'input',{bubbles:true}));})()`);}
 await send('Page.navigate',{url:origin+'/create'});await waitFor("document.querySelector('main')?.dataset.connected==='true'");await click('新建项目');await waitFor("document.querySelector('select').value!==''");
 const project=await evaluate("document.querySelector('select').value");
 await fill('textarea','给面馆制作五连图，主推牛肉面');await click('整理需求 / 检查问题');await waitFor("document.body.innerText.includes('生成前核对')");
 assert.equal(await evaluate("[...document.querySelectorAll('button')].find(e=>e.textContent==='确认方案并生成').disabled"),true);
 await fill('textarea','为什么文字重叠了？');await click('整理需求 / 检查问题');await waitFor("document.querySelector('article')?.innerText.includes('不会') || document.querySelector('article')?.innerText.includes('没有')");
 await send('Page.navigate',{url:origin+`/editor?project=${project}`});await waitFor("document.body.innerText.includes('工作区已连接')");await click('新建画板');await waitFor("document.body.innerText.includes('对象属性')");await click('添加文字');await waitFor("[...document.querySelectorAll('option')].some(e=>e.textContent.includes('新标题'))");
 await evaluate("(()=>{const e=[...document.querySelectorAll('select')].find(s=>[...s.options].some(o=>o.textContent.includes('新标题')));e.value=[...e.options].find(o=>o.textContent.includes('新标题')).value;e.dispatchEvent(new Event('change',{bubbles:true}));})()");
 await waitFor("!!document.querySelector('textarea')");await fill('textarea','今晚吃面');await click('保存本地修改');await waitFor("[...document.querySelectorAll('option')].some(e=>e.textContent.includes('今晚吃面'))");
 await click('保存工作区布局');await sleep(300);
 await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:origin+'/create'});await waitFor("document.body.innerText.includes('团绘 · 创作')");
 assert.equal(await evaluate("document.body.innerText.includes('模板审核')"),false);
 assert.equal(await evaluate('document.documentElement.scrollWidth<=window.innerWidth+1'),true,'mobile layout overflow');
 const screenshot=await send('Page.captureScreenshot',{format:'png'});await writeFile(path.join(profile,'workbench-mobile.png'),Buffer.from(screenshot.data,'base64'));
 assert.equal((await fetch(origin+'/workbench/templates')).status,503,'product port must not enable admin');
 if(process.env.ADMIN_TEST_ORIGIN){
   const admin=process.env.ADMIN_TEST_ORIGIN;
   assert.equal((await fetch(admin+'/workbench')).status,401);
   assert.equal((await fetch(admin+'/api/internal/templates')).status,401);
   assert.equal((await fetch(api+'/api/v1/templates/reviews')).status,401);
   const key=(await readFile(process.env.ADMIN_TEST_KEY_FILE,'utf8')).trim();
   const authorization='Basic '+Buffer.from('admin:'+key).toString('base64');
   assert.equal((await fetch(admin+'/api/internal/templates/L01/review',{method:'POST',headers:{authorization,Origin:'https://invalid.example','content-type':'application/json'},body:'{}'})).status,403);
   assert.equal((await fetch(admin+'/api/internal/projects',{headers:{authorization}})).status,404);
   await send('Network.enable');await send('Network.setExtraHTTPHeaders',{headers:{Authorization:authorization}});
   await send('Page.navigate',{url:admin+'/workbench'});await waitFor("document.body.innerText.includes('qwen-plus')");
   assert.equal(await evaluate("document.body.innerText.includes('新建项目')"),false);
   await send('Page.navigate',{url:admin+'/workbench/templates'});await waitFor("document.body.innerText.includes('L01')");
   assert.ok(await evaluate('document.querySelectorAll("svg rect").length>0'));
   await send('Network.setExtraHTTPHeaders',{headers:{}});
 }
 assert.deepEqual(errors,[]);
 const usage=await(await fetch(`${api}/api/v1/projects/${project}/usage`)).json();
 console.log(JSON.stringify({status:'passed',project,checks:['zero-call prepare','complaint','create canvas','local text edit','workspace save','mobile layout','admin separated'],usage,screenshot:path.join(profile,'workbench-mobile.png')},null,2));
}finally{socket?.close();chrome.kill('SIGTERM');}
