// Read-only browser inspection of this run's own test projects. All write
// requests are blocked; loading/reloading a result can never authorize a model.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = path.join(root, 'data/acceptance/20260920-three-entries/browser');
await fs.mkdir(out, {recursive: true});
const pages = await (await fetch('http://127.0.0.1:9333/json/list')).json();
const target = pages.find(p => p.type === 'page' && p.url === 'about:blank');
if (!target) throw new Error('Expected our isolated blank audit tab');
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise(resolve => socket.addEventListener('open', resolve, {once: true}));
let counter = 0;
const pending = new Map();
const blockedWrites = [], failures = [];
function send(method, params = {}) {
  const id = ++counter;
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timeout: ${method}`)); }, 25000);
    pending.set(id, {resolve: value => {clearTimeout(timeout); resolve(value);}, reject: error => {clearTimeout(timeout); reject(error);}});
    socket.send(JSON.stringify({id, method, params}));
  });
}
socket.addEventListener('message', async event => {
  const value = JSON.parse(event.data);
  if (value.id) {
    const item = pending.get(value.id);
    if (item) { pending.delete(value.id); value.error ? item.reject(new Error(JSON.stringify(value.error))) : item.resolve(value.result); }
  } else if (value.method === 'Fetch.requestPaused') {
    const {requestId, request} = value.params;
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method)) {
      blockedWrites.push({method: request.method, url: request.url});
      await send('Fetch.failRequest', {requestId, errorReason: 'BlockedByClient'});
    } else await send('Fetch.continueRequest', {requestId});
  } else if (value.method === 'Runtime.exceptionThrown') failures.push(value.params.exceptionDetails);
  else if (value.method === 'Network.responseReceived' && value.params.response.status >= 400)
    failures.push({url: value.params.response.url, status: value.params.response.status});
});
await send('Page.enable');
await send('Runtime.enable');
await send('Network.enable');
await send('Fetch.enable', {patterns: [{urlPattern: '*', requestStage: 'Request'}]});
await send('Emulation.setDeviceMetricsOverride', {width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false});
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const entries = [
  ['oneclick-failed', 'http://127.0.0.1:3011/?project=ebafb66a-272a-4a01-8333-d9ea9fef32fd&creation=5d5de2fd-0417-4bac-a15f-2b93b7627883'],
  ['fullplan-success', 'http://127.0.0.1:3011/full-plan?project=632d3a8c-de65-4845-85a3-af9c0b631611&creation=3f546ae8-0ce2-4f58-a850-74139590aa20'],
  ['professional-preflight', 'http://127.0.0.1:3011/?project=88ac7674-5795-4fcd-b4d9-78de242926ce&compose=1'],
];
for (const [label, url] of entries) {
  await send('Page.navigate', {url});
  await sleep(6000);
  if (label === 'professional-preflight') {
    const found = await send('Runtime.evaluate', {expression: `Array.from(document.querySelectorAll('button')).filter(b=>b.innerText.trim()==='专业创作').map(b=>({text:b.innerText,disabled:b.disabled}))`, returnByValue: true});
    if (found.result.value?.length === 1) {
      await send('Runtime.evaluate', {expression: `Array.from(document.querySelectorAll('button')).find(b=>b.innerText.trim()==='专业创作').click()`});
      await sleep(1500);
    }
  }
  const dom = await send('Runtime.evaluate', {expression: `JSON.stringify({url:location.href,text:document.body.innerText,buttons:Array.from(document.querySelectorAll('button')).map(b=>({text:b.innerText,label:b.getAttribute('aria-label'),disabled:b.disabled})),images:Array.from(document.querySelectorAll('img')).map(i=>({src:i.src,alt:i.alt,width:i.naturalWidth,height:i.naturalHeight}))})`, returnByValue: true});
  await fs.writeFile(path.join(out, label + '.json'), JSON.stringify({dom: JSON.parse(dom.result.value), blockedWrites, failures}, null, 2), {flag:'wx'});
  const screenshot = await send('Page.captureScreenshot', {format:'png', captureBeyondViewport:false});
  await fs.writeFile(path.join(out, label+'.png'), Buffer.from(screenshot.data, 'base64'), {flag:'wx'});
  console.log(label + ': ' + dom.result.value.slice(0, 3500));
}
await send('Fetch.disable');
socket.close();
console.log(JSON.stringify({blockedWrites, failures}));
