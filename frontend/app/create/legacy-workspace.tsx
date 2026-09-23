// Preserved implementation reference, not a separate merchant route.
"use client";
import { Suspense, useEffect, useState, useRef } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { apiRequest, jsonRequest } from "../../lib/api-client";
import { GenerationGallery, type DeliveryResult } from "../generation-gallery";
import { WorkflowTiming } from "../workflow-timing";
import "../workbench/workbench.css";

const outputs: Record<string,string> = {five_panel:"五连图",three_panel:"三连图",store_decoration:"首页装修图",logo:"Logo 图",package_main:"套餐主图",voucher_main:"代金券主图",dish:"菜品单品图",detail:"详情页",promotion:"团购宣传图"};
type Review = {creation_id:string;revision:number;snapshot_hash:string;snapshot:{ready:boolean;facts:Record<string,string>;gaps:unknown[];output_type:string;delivery_types:string[];creative_draft?:Record<string,string>}};
type Run = {id:string;task_id:string;entry_mode:string;text:string;state:string;error?:string;created_at:string;generation_task_id?:string;result:{kind?:string;reply?:string;review?:Review}};
type Task = {id:string;status:string;error?:{message:string};result:{long_image?:string;slices?:string[];clean_long_image?:string;clean_slices?:string[];deliverables?:DeliveryResult[]}};
type Asset = {id:string;original_name:string;semantic_role:string};

export default function CreationPage() {
  return <Suspense fallback={<p>正在加载创作…</p>}><CreationWorkspace /></Suspense>;
}
function CreationWorkspace() {
  const params=useSearchParams(), router=useRouter();
  const initialEntry=params.get("entry");
  const actionLock=useRef(false);
  const [projects,setProjects]=useState<{id:string;name:string}[]>([]),[project,setProject]=useState(params.get("project")||"");
  const [entry,setEntry]=useState(initialEntry==="professional"||initialEntry==="fullplan"?initialEntry:"oneclick"),[output,setOutput]=useState("five_panel"),[deliveries,setDeliveries]=useState(["voucher_main","five_panel","logo"]),[count,setCount]=useState(1);
  const [text,setText]=useState(""),[facts,setFacts]=useState<Record<string,string>>({}),[style,setStyle]=useState("minimal"),[calls,setCalls]=useState(0),[consent,setConsent]=useState(false),[materials,setMaterials]=useState(false),[illustration,setIllustration]=useState(true);
  const [assets,setAssets]=useState<Asset[]>([]),[selected,setSelected]=useState<string[]>([]),[assetRole,setAssetRole]=useState("product");
  const [history,setHistory]=useState<Run[]>([]),[run,setRun]=useState<Run|null>(null),[task,setTask]=useState<Task|null>(null),[target,setTarget]=useState(params.get("task")||"");
  const [error,setError]=useState(""),[busy,setBusy]=useState(false);
  const [connected,setConnected]=useState(false);
  const pending=!!run && ["QUEUED","RUNNING"].includes(run.state);
  const rememberRun=(next:Run)=>{setRun(next);setEntry(next.entry_mode);router.replace(`/create?entry=${next.entry_mode}&project=${encodeURIComponent(project)}&run=${encodeURIComponent(next.id)}`);};
  async function reloadProjects() {setProjects(await apiRequest("/projects"));}
  useEffect(()=>{let live=true;apiRequest<{id:string;name:string}[]>("/projects").then(p=>{if(live){setProjects(p);setConnected(true);}}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[]);
  useEffect(()=>{
    let live=true;
    if(project) Promise.all([apiRequest<Run[]>(`/projects/${project}/agent-runs`),apiRequest<Asset[]>(`/projects/${project}/assets`)]).then(([h,a])=>{if(live){setHistory(h);setAssets(a);const saved=h.find(r=>r.id===params.get("run"));if(saved)setRun(saved);}}).catch(e=>{if(live)setError(e.message);});
    return ()=>{live=false;};
  },[project,params]);
  useEffect(()=>{
    if(!run||!project||!pending)return;
    let live=true;
    const poll=async()=>{try {const next=await apiRequest<Run>(`/projects/${project}/agent-runs/${run.id}`);if(live){setRun(next);if(!["QUEUED","RUNNING"].includes(next.state))setHistory(h=>[next,...h.filter(x=>x.id!==next.id)]);}}catch(e){if(live)setError((e as Error).message);}};
    const timer=setInterval(poll,1500);return ()=>{live=false;clearInterval(timer);};
  },[run,project,pending]);
  useEffect(()=>{
    const id=run?.generation_task_id;
    if(!id)return;
    let live=true;let timer:ReturnType<typeof setTimeout>;
    async function poll(){try {const next=await apiRequest<Task>(`/tasks/${id}`);if(!live)return;setTask(next);if(["PENDING","RUNNING"].includes(next.status))timer=setTimeout(poll,1800);}catch(e){if(live)setError((e as Error).message);}}
    poll();return ()=>{live=false;clearTimeout(timer);};
  },[run?.generation_task_id]);
  async function action(fn:()=>Promise<void>){if(actionLock.current)return;actionLock.current=true;setBusy(true);setError("");try{await fn();}catch(e){setError((e as Error).message);}finally{setBusy(false);actionLock.current=false;}}
  const review=run?.result.review;
  const inProgress=task && ["PENDING","RUNNING"].includes(task.status);
  const switchProject=(id:string)=>{setProject(id);setRun(null);setTask(null);setHistory([]);setAssets([]);setSelected([]);setFacts({});setTarget("");setMaterials(false);setConsent(false);setError("");router.replace(`/create?entry=${entry}&project=${encodeURIComponent(id)}`);};
  return <main className="functional-workbench" data-connected={connected}>
    <header><h1>团绘 · 创作</h1><Link href="/">返回团绘首页</Link>{project&&<Link href={`/editor?project=${encodeURIComponent(project)}`}>编辑项目画板</Link>}</header>
    <p>先整理需求、核对方案，再确认生成。作品与历史保存在原项目中。</p>
    <section className="wb-row"><label>项目<select disabled={busy} value={project} onChange={e=>switchProject(e.target.value)}><option value="">选择项目</option>{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <button disabled={busy||!connected} onClick={()=>action(async()=>{const p=await apiRequest<{project_id:string}>("/projects",jsonRequest("POST",{name:"新的创作项目"}));await reloadProjects();switchProject(p.project_id);})}>新建项目</button>
    </section>
    <nav className="wb-row" aria-label="创作入口">{Object.entries({oneclick:"一键生图",professional:"专业创作",fullplan:"全案设计"}).map(([id,label])=><button key={id} disabled={busy||pending||!!inProgress} aria-pressed={entry===id} onClick={()=>{setEntry(id);setRun(null);setTask(null);setMaterials(false);setConsent(false);router.replace(`/create?entry=${id}&project=${encodeURIComponent(project)}`);}}>{label}</button>)}</nav>
    <div className="wb-columns"><section>
      <h2>本轮需求</h2>
      {entry!=="fullplan" ? <label>单项类型<select value={output} onChange={e=>setOutput(e.target.value)}>{Object.entries(outputs).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>:<fieldset><legend>全案交付项</legend>{Object.entries(outputs).map(([id,label])=><label className="wb-check" key={id}><input type="checkbox" checked={deliveries.includes(id)} onChange={e=>setDeliveries(v=>e.target.checked?[...v,id]:v.filter(x=>x!==id))}/>{label}</label>)}</fieldset>}
      {entry!=="fullplan"&&output==="detail"&&<label>详情页张数<input type="number" min="1" max="9" value={count} onChange={e=>setCount(Number(e.target.value))}/></label>}
      <label>风格<select value={style} onChange={e=>setStyle(e.target.value)}><option value="minimal">简约</option><option value="appetite">食欲冲击</option><option value="brand">品牌质感</option><option value="street">烟火气</option></select></label>
      <label>需求或问题<textarea rows={4} value={text} onChange={e=>setText(e.target.value)} placeholder="说想做什么；如果作品有问题，先告诉我哪里不对。"/></label>
      <label>目标作品（指出问题时使用）<input value={target} onChange={e=>setTarget(e.target.value)} placeholder="任务 ID；可从下方作品选定"/></label>
      <details><summary>已确认的门店资料（未知可留空）</summary>{Object.entries({store_name:"店名",hero_item:"本次重点",positioning:"门店特色",selling_points:"真实卖点",hero_price:"价格"}).map(([key,label])=><label key={key}>{label}<input value={facts[key]||""} onChange={e=>setFacts({...facts,[key]:e.target.value})}/></label>)}</details>
      <fieldset><legend>素材</legend><label>上传用途<select value={assetRole} onChange={e=>setAssetRole(e.target.value)}><option value="product">菜品照片（可入画）</option><option value="storefront">门头（只识别）</option><option value="menu">菜单（只识别）</option><option value="environment">店内环境（只识别）</option></select></label>
        <label>添加照片<input type="file" accept="image/*" disabled={!project||busy} onChange={e=>{const file=e.target.files?.[0];if(!file)return;action(async()=>{const form=new FormData();form.set("file",file);form.set("asset_type",assetRole);const a=await apiRequest<{asset_id:string}>(`/projects/${project}/assets`,{method:"POST",body:form});setAssets(await apiRequest(`/projects/${project}/assets`));setSelected(v=>[...v,a.asset_id]);});e.target.value="";}}/></label>
        {assets.map(a=><label className="wb-check" key={a.id}><input type="checkbox" checked={selected.includes(a.id)} onChange={e=>setSelected(v=>e.target.checked?[...v,a.id]:v.filter(x=>x!==a.id))}/>{a.original_name} · {a.semantic_role}</label>)}
        <p>本入口上传不会自动付费识别。门头/菜单不可当成菜品入画；识别所得资料请先核对。</p>
      </fieldset>
      <label className="wb-check"><input type="checkbox" checked={illustration} onChange={e=>setIllustration(e.target.checked)}/>无实拍时允许 AI 示意</label>
      <label>本轮语言调用上限<select value={calls} onChange={e=>{setCalls(Number(e.target.value));setConsent(false);}}><option value={0}>0 次 · 本地解析</option><option value={1}>1 次 · 千问父 Agent</option><option value={2}>2 次 · 父 Agent ＋文案子任务</option></select></label>
      {calls>0&&<label className="wb-check"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>同意本轮最多 {calls} 次语言调用，按供应商计费，不自动重试</label>}
      <button disabled={busy||pending||!project||!text.trim()||calls>0&&!consent||entry==="fullplan"&&!deliveries.length} onClick={()=>action(async()=>{
        const next=await apiRequest<Run>(`/projects/${project}/agent-runs`,jsonRequest("POST",{request_key:crypto.randomUUID(),text,entry_mode:entry,output_type:output,delivery_types:deliveries,detail_count:count,facts:Object.fromEntries(Object.entries(facts).filter(([,v])=>v.trim())),style,asset_ids:selected,allow_illustration:illustration,show_store_name:!!facts.store_name,show_price:!!facts.hero_price,task_id:target||null,approved_text_calls:calls,accepted_policy:calls?"qwen-agent-text-v1":null}));rememberRun(next);setTask(null);setMaterials(false);setHistory(h=>[next,...h]);
      })}>整理需求 / 检查问题</button>
    </section><section>
      <h2>对话与执行</h2>{error&&<p role="alert" className="wb-error">{error}</p>}
      {run&&<article><p>{run.text}</p><p>{run.state} · {run.result.reply||run.error||"任务已保存，等待执行器"}</p>
        <WorkflowTiming path={`/projects/${project}/tasks/${run.task_id}/activity`} active={pending}/>
        {pending&&<button disabled={busy} onClick={()=>action(async()=>setRun(await apiRequest(`/projects/${project}/agent-runs/${run.id}/cancel`,{method:"POST"})))}>停止后续处理</button>}
        {review&&<><h3>生成前核对</h3><p>{outputs[review.snapshot.output_type]||"全案设计"} · {review.snapshot.delivery_types.length} 次图片调用上限</p><pre>{JSON.stringify({事实:review.snapshot.facts,文案:review.snapshot.creative_draft,待补充:review.snapshot.gaps},null,2)}</pre>
          {!run.generation_task_id&&<><label className="wb-check"><input type="checkbox" checked={materials} onChange={e=>setMaterials(e.target.checked)}/>已核对信息和素材使用权，并同意上述图片调用费用</label><button disabled={busy||!materials||!review.snapshot.ready} onClick={()=>action(async()=>{const result=await apiRequest<{task_id:string}>(`/projects/${project}/agent-runs/${run.id}/execute`,jsonRequest("POST",{snapshot_hash:review.snapshot_hash,approved_image_calls:review.snapshot.delivery_types.length,materials_confirmed:materials,accepted_policy:"local-paid-generation-v1"}));setRun({...run,generation_task_id:result.task_id});})}>确认方案并生成</button></>}
          {!review.snapshot.ready&&<p>请在左侧补充必要资料后重新整理。旧对话与作品会保留。</p>}
        </>}
      </article>}
      {task&&<article><h3>作品任务 · {task.status}</h3><WorkflowTiming path={`/projects/${project}/tasks/${task.id}/activity`} active={!!inProgress}/>{task.error&&<p role="alert">{task.error.message}</p>}
        <GenerationGallery projectId={project} taskId={task.id} longImage={task.result.long_image} slices={task.result.slices} cleanLongImage={task.result.clean_long_image} cleanSlices={task.result.clean_slices} deliverables={task.result.deliverables}/>
        <button onClick={()=>setTarget(task.id)}>将这版设为问题检查目标</button>
        {inProgress&&<button disabled={busy} onClick={()=>action(async()=>{await apiRequest(`/tasks/${task.id}/pause`,{method:"POST"});setTask(await apiRequest(`/tasks/${task.id}`));})}>停止生成</button>}
        {task.status==="SUCCEEDED"&&<Link href={`/editor?project=${project}&task=${task.id}`}>导入结构编辑器</Link>}
      </article>}
      <h3>历史对话（最近 100 条）</h3>{history.map(h=><button className="wb-history" key={h.id} disabled={busy} onClick={()=>action(async()=>{rememberRun(await apiRequest(`/projects/${project}/agent-runs/${h.id}`));setTask(null);setMaterials(false);})}>{h.text} · {h.state}</button>)}
    </section></div>
  </main>;
}
