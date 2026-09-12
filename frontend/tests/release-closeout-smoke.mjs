import { createRequire } from "node:module";
import assert from "node:assert/strict";
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_PATH || "playwright");
const browser=await chromium.launch({headless:true,channel:"chrome"});
const page=await browser.newPage({viewport:{width:1440,height:960}});
const image=Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aE6kAAAAASUVORK5CYII=","base64");
let confirms=0, polls=0;
const snapshot={schema_version:2,text:"给测试面馆做全案",output_type:"full_plan",delivery_types:["voucher_main","five_panel","logo"],facts:{store_name:"测试面馆"},sources:{},assets:[],show_price:false,show_store_name:true,style:"appetite",provider:"qwen",gaps:[],ready:true,project_changes:[],render_mode:"illustration",messages:[{role:"user",content:"给测试面馆做全案"},{role:"assistant",content:"好，先做代金券、五连图和Logo。"}]};
const review={creation_id:"batch-creation",revision:1,status:"READY_TO_CONFIRM",snapshot_hash:"a".repeat(64),snapshot};
const result={execution_kind:"bundle",output_type:"full_plan",deliverables:[1,5,1].map((n,i)=>({task_id:`part-${i}`,label:["代金券主图","五连图","Logo图"][i],status:"SUCCEEDED",long_image:"long.png",slices:Array.from({length:n},(_,j)=>`${j+1}.png`),clean_long_image:"long-clean.png",clean_slices:Array.from({length:n},(_,j)=>`${j+1}-clean.png`)}))};
await page.route("**/api/v1/**",async route=>{
  const p=new URL(route.request().url()).pathname,method=route.request().method();
  if(p.includes("/assets/"))return route.fulfill({status:200,contentType:"image/png",body:image});
  let body={};
  if(p.endsWith("/projects"))body=method==="POST"?{project_id:"batch-project"}:[{id:"batch-project",name:"测试面馆店铺全案项目",status:"GENERATED"}];
  else if(p.endsWith("/projects/batch-project"))body={id:"batch-project",name:"测试面馆店铺全案项目",status:"GENERATED"};
  else if(p.endsWith("/assets"))body=[];
  else if(p.endsWith("/creations")&&method==="POST")body={creation_id:"batch-creation",revision:0,status:"DRAFT",snapshot:null,snapshot_hash:""};
  else if(p.endsWith("/intake-runs")||p.endsWith("/review"))body=review;
  else if(p.endsWith("/confirm")){
    confirms++;assert.equal(route.request().postDataJSON().approved_image_calls,3);
    review.status="CONFIRMED";review.task_id="batch-task";body={task_id:"batch-task"};
  }else if(p.endsWith("/activity"))body={server_time:new Date().toISOString(),current:null,spans:[]};
  else if(p.includes("/tasks/")){
    if(++polls===1)return route.fulfill({status:503,contentType:"application/json",body:JSON.stringify({detail:"临时断线"})});
    body={id:"batch-task",project_id:"batch-project",creation_id:"batch-creation",status:"SUCCEEDED",progress:100,result};
  }else if(p.endsWith("/workspace"))body={id:"batch-project",name:"测试面馆店铺全案项目",latest_creation_id:"batch-creation",creations:[],tasks:[]};
  await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(body)});
});
try{
  await page.goto("http://127.0.0.1:3011/");
  await page.getByRole("heading",{name:"今天，想为门店做什么图？"}).waitFor();
  await page.getByRole("button",{name:"全案设计",exact:true}).click();
  await page.getByRole("textbox",{name:"创作需求"}).fill("给测试面馆做全案");
  await page.getByRole("button",{name:"开始生成",exact:true}).click();
  await page.getByRole("button",{name:"同意并开始",exact:true}).click();
  await page.getByRole("button",{name:"同意费用并生成以上作品",exact:true}).waitFor();
  assert.equal(confirms,0,"multi-output must not auto-consume three image calls");
  await page.getByRole("button",{name:"同意费用并生成以上作品",exact:true}).click();
  await page.getByText("连接暂时中断，正在恢复进度。不会重新提交生成任务。").waitFor();
  await page.getByRole("heading",{name:"1. 代金券主图",exact:true}).waitFor();
  assert.equal(confirms,1);assert(polls>=2);
  assert.equal(await page.getByRole("button",{name:"预览完整作品",exact:true}).count(),2);
  await page.getByRole("button",{name:"预览完整作品",exact:true}).first().click();
  await page.getByRole("dialog",{name:"作品预览"}).waitFor();
  assert.equal(await page.locator("dialog[open]").count(),1);
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("dialog[open]").count(),0);
  await page.getByRole("button",{name:"无水印",exact:true}).first().click();
  assert((await page.getByRole("button",{name:"预览完整作品",exact:true}).first().locator("img").getAttribute("src")).includes("long-clean"));
  await page.reload();
  await page.getByRole("heading",{name:"1. 代金券主图",exact:true}).waitFor();
  assert.equal(confirms,1,"refresh must not generate again");
  await page.setViewportSize({width:375,height:812});
  await page.screenshot({path:"/tmp/tuanhui-closeout-batch-mobile.png"});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  console.log("PASS: batch explicit call-count consent / read-only reconnect / grouped results / preview / watermark / refresh / mobile");
}finally{await browser.close();}
