import {createRequire} from "node:module";
import assert from "node:assert/strict";
const require = createRequire(import.meta.url);
const {chromium} = require(process.env.PLAYWRIGHT_PATH || "playwright");
const browser = await chromium.launch({headless:true,channel:"chrome"});
const page = await browser.newPage({viewport:{width:1440,height:960},reducedMotion:"reduce"});
let status="SUCCEEDED", writes=[], history=[];
const snapshot={schema_version:2,text:"山西面馆五图",facts:{store_name:"山西面馆"},sources:{},assets:[],show_price:false,show_store_name:true,style:"appetite",provider:"qwen",gaps:[],ready:true,project_changes:[],render_mode:"illustration",output_type:"five_panel",messages:[]};
const saved={creation_id:"c-old",revision:1,status:"CONFIRMED",snapshot_hash:"a".repeat(64),snapshot,task_id:"t-old"};
await page.route("**/api/v1/**",async route=>{
  const request=route.request(), p=new URL(request.url()).pathname;
  let body={};
  if(request.method()!=="GET")writes.push(p);
  if(p.endsWith("/dialogue/route")){
    const input=request.postDataJSON();
    const prepare=input.text.startsWith("重新生成");
    body={schema_version:"dialogue-safety-v1",intent:prepare?"new_creation":"report_issue",action:prepare?"prepare":"answer",can_prepare:prepare,reply:prepare?"":"这条先查看记录，没有重新生成。",next_steps:[],duration_ms:1,model_calls:0};
    if(!prepare)history.push({id:String(history.length),text:input.text,response:body});
  }else if(p.endsWith("/dialogue/history"))body=history;
  else if(p.endsWith("/projects/p"))body={id:"p",name:"山西面馆店铺五图项目"};
  else if(p.endsWith("/projects"))body=[];
  else if(p.endsWith("/assets"))body=[];
  else if(p.endsWith("/review"))body=saved;
  else if(p.endsWith("/activity"))body={current:null,spans:[],server_time:new Date().toISOString()};
  else if(p.endsWith("/pause")){status="NEEDS_USER";body={id:"t-old",project_id:"p",status,progress:20,result:{}};}
  else if(p.endsWith("/tasks/t-old"))body={id:"t-old",project_id:"p",creation_id:"c-old",status,progress:20,result:{}};
  else if(request.method()!=="GET")throw new Error(`Unexpected mutation during feedback: ${p}`);
  await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(body)});
});
try {
  for(const pathname of ["/","/full-plan"]){
    history=[];writes=[];
    await page.goto(`http://127.0.0.1:3011${pathname}?project=p&creation=c-old`);
    const input=page.getByRole("textbox",{name:"创作需求",exact:true});
    await input.waitFor();
    await page.getByRole("link",{name:"返回项目",exact:true}).waitFor();
    await page.evaluate(()=>document.fonts.ready);
    await page.getByRole("button",{name:"发送",exact:true}).waitFor();
    const before=await page.locator(".studioComposer").boundingBox();
    for (const text of ["文字又重叠了","不要重新生成，解释原因","还要多久？"]) {
      await input.fill(text);
      await page.getByRole("button",{name:"发送",exact:true}).click();
      await page.waitForFunction(()=>document.querySelector('textarea')?.value === "");
      await page.getByRole("button",{name:"发送",exact:true}).waitFor();
      assert.equal(await page.locator(".studioConsent[open]").count(),0);
    }
    assert(writes.every(p=>p.endsWith("/dialogue/route")));
    const after=await page.locator(".studioComposer").boundingBox();
    assert.equal(after.height,before.height,"conversation must not stretch composer");
    await page.reload();
    await page.getByLabel("问题与回复").getByText("文字又重叠了",{exact:true}).waitFor();
    await input.fill("重新生成一版清爽的");
    await page.getByRole("button",{name:"发送",exact:true}).click();
    await page.locator(".studioConsent[open]").waitFor();
    await page.getByRole("button",{name:"先不生成",exact:true}).click();
    assert(writes.every(p=>p.endsWith("/dialogue/route")),"cancelled consent must not submit intake/confirm");
  }
  status="RUNNING";writes=[];history=[];
  await page.goto("http://127.0.0.1:3011/?project=p&creation=c-old");
  await page.getByRole("button",{name:"停止生成",exact:true}).waitFor();
  await page.getByRole("textbox",{name:"创作需求",exact:true}).fill("还要多久？");
  await page.getByRole("button",{name:"发送",exact:true}).click();
  await page.getByLabel("问题与回复").getByText("这条先查看记录，没有重新生成。",{exact:true}).waitFor();
  assert(!writes.some(p=>p.endsWith("/pause")),"sending a query must not pause task");
  await page.setViewportSize({width:375,height:812});
  const closeMenu=page.locator(".sidebar.isOpen .brandRow button");
  if(await closeMenu.isVisible())await closeMenu.click();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.getByRole("button",{name:"停止生成",exact:true}).click();
  await page.waitForFunction(()=>!Array.from(document.querySelectorAll("button")).some(b=>b.textContent==="停止生成"));
  assert.equal(writes.filter(p=>p.endsWith("/pause")).length,1);
  await page.screenshot({path:"/tmp/tuanhui-dialogue-mobile.png"});
  await page.setViewportSize({width:1440,height:960});
  await page.screenshot({path:"/tmp/tuanhui-dialogue-desktop.png"});
  console.log("PASS mocked UI: oneclick/fullplan feedback, history, consent cancellation, running query, explicit stop, mobile layout; no model calls");
}finally{await browser.close();}
