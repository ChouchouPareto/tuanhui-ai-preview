"use client";
import {useEffect,useState,useRef,Suspense} from "react";
import {useSearchParams} from "next/navigation";
import Link from "next/link";
import {apiRequest,apiUrl,jsonRequest} from "../../lib/api-client";
import "../workbench/workbench.css";

type Node={id:string;kind:"text"|"shape"|"image";role:string;text:string;box:number[];font_size:number;color:string;locked:boolean;visible:boolean;z_index:number;asset_id?:string};
type Canvas={document_id:string;version_id:string;head_version_id:string;name:string;visual_editability:string;scene:{width:number;height:number;nodes:Node[]}};
type Board={document_id:string;name:string;head_version_id:string};
type Space={revision:number;positions:Record<string,[number,number]>;viewport:[number,number,number]};
type Proposal={status:string;proposal_id?:string;reply?:string;candidates?:unknown[];[key:string]:unknown};
export default function Editor(){return <Suspense fallback={<p>加载画板…</p>}><EditorContent/></Suspense>;}
function EditorContent(){
 const stageRef=useRef<HTMLDivElement>(null);
 const [ready,setReady]=useState(false);
 const params=useSearchParams();
 const project=params.get("project")||"";
 const [source,setSource]=useState(params.get("task")||"");
 const [boards,setBoards]=useState<Board[]>([]),[current,setCurrent]=useState<Canvas|null>(null),[node,setNode]=useState<Node|null>(null),[versions,setVersions]=useState<{version_id:string;reason:string}[]>([]);
 const [space,setSpace]=useState<Space>({revision:0,positions:{},viewport:[0,0,1]}),[error,setError]=useState(""),[busy,setBusy]=useState(false),[watermark,setWatermark]=useState(true),[message,setMessage]=useState(""),[replacement,setReplacement]=useState(""),[proposal,setProposal]=useState<Proposal|null>(null),[newType,setNewType]=useState("five_panel");
 const base=`/projects/${project}/canvases`;
 useEffect(()=>{if(!project)return;let live=true;Promise.all([apiRequest<Board[]>(`/projects/${project}/canvases`),apiRequest<Space>(`/projects/${project}/editor-workspace`)]).then(([b,s])=>{if(live){setBoards(b);setSpace(s);setReady(true);}}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[project]);
 async function action(fn:()=>Promise<void>){setBusy(true);setError("");try{await fn();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function load(doc:string){const c=await apiRequest<Canvas>(`${base}/${doc}`);setCurrent(c);setNode(null);setProposal(null);setVersions(await apiRequest(`${base}/${doc}/versions`));setBoards(await apiRequest(base));}
 async function mutate(operations:unknown[]){if(!current)return;await apiRequest(`${base}/${current.document_id}/mutations`,jsonRequest("POST",{base_version_id:current.head_version_id,request_key:crypto.randomUUID(),operations}));await load(current.document_id);}
 const readonly=current?.version_id!==current?.head_version_id;
 const preview=current?apiUrl(`${base}/${current.document_id}/versions/${current.version_id}/assets/long.png?watermark=${watermark}`):"";
 return <main className="functional-workbench"><header><h1>团绘 · 专业结构编辑</h1><Link href={`/create?entry=professional&project=${encodeURIComponent(project)}`}>返回专业创作</Link><Link href="/">团绘首页</Link></header>
 <p>文字、形状和已确认素材可本地修改；AI 底图仍是一层，不伪称已拆出所有物体。所有编辑保留版本，不调用生图模型。</p><p role="status">{ready?"工作区已连接":"正在连接工作区…"}</p>
 {!project?<p>请先从创作页面选择项目再进入。</p>:<>
 <section className="wb-row"><label>空白画布规格<select value={newType} onChange={e=>setNewType(e.target.value)}><option value="five_panel">五连图 20:3</option><option value="three_panel">三连图 12:3</option><option value="promotion">单张宣传图 4:3</option></select></label>
 <button disabled={busy} onClick={()=>action(async()=>{const slices=newType==="five_panel"?5:newType==="three_panel"?3:1;const c=await apiRequest<Canvas>(base,jsonRequest("POST",{name:"新建画板",scene:{output_type:newType,width:slices*800,height:600,slice_count:slices,nodes:[]}}));await load(c.document_id);})}>新建画板</button>
 <label>导入已生成任务<input value={source} onChange={e=>setSource(e.target.value)}/></label><button disabled={busy||!source} onClick={()=>action(async()=>{const c=await apiRequest<Canvas>(`${base}/import`,jsonRequest("POST",{task_id:source}));await load(c.document_id);})}>导入作品</button></section>
 {error&&<p role="alert" className="wb-error">{error}</p>}
 <section><h2>项目画板</h2><p>多个画板独立保存。移动布局不会改变图片内部内容。</p>
 <label>工作区缩放<input type="range" min="0.1" max="2" step="0.1" value={space.viewport[2]} onChange={e=>setSpace({...space,viewport:[space.viewport[0],space.viewport[1],Number(e.target.value)]})}/></label>
 <button disabled={busy} onClick={()=>action(async()=>setSpace(await apiRequest(`/projects/${project}/editor-workspace`,jsonRequest("PATCH",{expected_revision:space.revision,positions:space.positions,viewport:space.viewport}))))}>保存工作区布局</button>
 <button onClick={()=>stageRef.current?.scrollTo(space.viewport[0],space.viewport[1])}>恢复已保存视口</button>
 <button onClick={()=>{const s=stageRef.current;if(s)setSpace({...space,viewport:[s.scrollLeft,s.scrollTop,space.viewport[2]]});}}>记录当前视口</button>
 {current&&<div className="wb-row">{[0,1].map(i=><label key={i}>当前画板 {i===0?"X":"Y"}<input type="number" min="0" max="10000" value={space.positions[current.document_id]?.[i]||0} onChange={e=>{const xy:[number,number]=[...(space.positions[current.document_id]||[0,0])];xy[i]=Number(e.target.value);setSpace({...space,positions:{...space.positions,[current.document_id]:xy}});}}/></label>)}</div>}
 <div ref={stageRef} className="wb-stage" style={{height:300}}><div style={{position:"relative",width:2000*space.viewport[2],height:1000*space.viewport[2]}}>{boards.map((b,i)=>{const [x,y]=space.positions[b.document_id]||[(i%4)*340,Math.floor(i/4)*180];return <div key={b.document_id} style={{position:"absolute",left:x*space.viewport[2],top:y*space.viewport[2],width:320*space.viewport[2]}}>
 <button draggable onDragStart={e=>e.dataTransfer.setData("text/plain",b.document_id)} onDragEnd={e=>{if(!e.clientX&&!e.clientY)return;const el=e.currentTarget.parentElement?.parentElement;if(!el)return;const r=el.getBoundingClientRect();setSpace(s=>({...s,positions:{...s.positions,[b.document_id]:[Math.max(0,(e.clientX-r.left)/s.viewport[2]),Math.max(0,(e.clientY-r.top)/s.viewport[2])]}}));}} onClick={()=>action(()=>load(b.document_id))}>{b.name}</button>
 {/* eslint-disable-next-line @next/next/no-img-element */}
 <img alt={b.name} style={{width:"100%"}} src={apiUrl(`${base}/${b.document_id}/versions/${b.head_version_id}/assets/long.png`)}/>
 </div>;})}</div></div></section>
 {current&&<div className="wb-columns"><section><h2>{current.name}</h2>
 <label>版本<select value={current.version_id} onChange={e=>action(async()=>{setCurrent(await apiRequest(`${base}/${current.document_id}/versions/${e.target.value}`));setNode(null);setProposal(null);})}>{versions.map(v=><option key={v.version_id} value={v.version_id}>{v.reason} · {v.version_id.slice(0,8)}</option>)}</select></label>
 {readonly&&<p>正在查看历史版本，修改前请恢复为新版本。</p>}
 <div className="wb-row"><button disabled={busy||!readonly} onClick={()=>action(async()=>{await apiRequest(`${base}/${current.document_id}/restore`,jsonRequest("POST",{base_version_id:current.head_version_id,target_version_id:current.version_id,request_key:crypto.randomUUID()}));await load(current.document_id);})}>恢复此版本</button>
 <button disabled={busy} onClick={()=>action(async()=>{const c=await apiRequest<Canvas>(`${base}/${current.document_id}/versions/${current.version_id}/fork`,{method:"POST"});await load(c.document_id);})}>复制为新画板</button></div>
 <label className="wb-check"><input type="checkbox" checked={watermark} onChange={e=>setWatermark(e.target.checked)}/>导出含 AI 示意水印</label>
 <div className="wb-stage"><div style={{position:"relative",width:Math.min(1000,current.scene.width),aspectRatio:`${current.scene.width}/${current.scene.height}`}}>
 {/* eslint-disable-next-line @next/next/no-img-element */}
 <img alt="当前版本预览" src={preview} style={{width:"100%",height:"100%"}}/>
 {current.scene.nodes.filter(n=>n.visible).map(n=><button key={n.id} aria-label={`选择 ${n.role} ${n.text||n.id}`} onClick={()=>setNode({...n,box:[...n.box]})} style={{position:"absolute",left:`${n.box[0]*100}%`,top:`${n.box[1]*100}%`,width:`${n.box[2]*100}%`,height:`${n.box[3]*100}%`,minHeight:0,padding:0,border:node?.id===n.id?"2px solid #714fd3":"1px dashed #aaa",borderRadius:0,background:"transparent"}}/>)}</div></div>
 <a href={`${preview}&download=true`}>下载当前母版</a> · <button disabled={busy} onClick={()=>action(async()=>{const r=await fetch(apiUrl(`${base}/${current.document_id}/versions/${current.version_id}/export?watermark=${watermark}`),{method:"POST"});if(!r.ok)throw Error("导出失败，请检查素材或版本");const url=URL.createObjectURL(await r.blob());const a=document.createElement("a");a.href=url;a.download="artwork.zip";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);})}>导出切片 ZIP</button>
 </section><section><h2>对象属性</h2><label>选择对象<select value={node?.id||""} onChange={e=>{const n=current.scene.nodes.find(n=>n.id===e.target.value);setNode(n?{...n,box:[...n.box]}:null);}}><option value="">选择主标题、副标题或其他对象</option>{current.scene.nodes.map(n=><option key={n.id} value={n.id}>{n.role} · {n.text||n.id}</option>)}</select></label>
 {node&&<><p>{node.locked?"已锁定":"可编辑"} · {node.id}</p>{node.kind==="text"&&<><label>文字<textarea value={node.text} onChange={e=>setNode({...node,text:e.target.value})}/></label><label>字号<input type="number" min="18" max="200" value={node.font_size} onChange={e=>setNode({...node,font_size:Number(e.target.value)})}/></label></>}
 <label>颜色<input type="color" value={node.color} onChange={e=>setNode({...node,color:e.target.value})}/></label><div className="wb-inspector">{["X","Y","宽","高"].map((v,i)=><label key={v}>{v}（0–1）<input type="number" min="0" max="1" step=".01" value={node.box[i]} onChange={e=>setNode({...node,box:node.box.map((b,j)=>i===j?Number(e.target.value):b)})}/></label>)}</div>
 <label>图层顺序<input type="number" value={node.z_index} onChange={e=>setNode({...node,z_index:Number(e.target.value)})}/></label>
 <button disabled={busy||readonly||node.locked} onClick={()=>action(()=>mutate([{op:"update",object_id:node.id,patch:{...(node.kind==="text"?{text:node.text}:{}),box:node.box,color:node.color,font_size:node.font_size,z_index:node.z_index}}]))}>保存本地修改</button>
 <button disabled={busy||readonly} onClick={()=>action(()=>mutate([{op:node.locked?"unlock":"lock",object_id:node.id}]))}>{node.locked?"解锁":"锁定"}</button>
 <button disabled={busy||readonly||node.locked} onClick={()=>action(()=>mutate([{op:"remove",object_id:node.id}]))}>移除对象（可恢复）</button></>}
 <p><button disabled={busy||readonly} onClick={()=>action(async()=>{const id=`text_${crypto.randomUUID().replaceAll("-","")}`;await mutate([{op:"add",object_id:id,node:{id,kind:"text",role:"headline",text:"新标题",box:[.04,.1,.12,.3],color:"#222222",font_size:36}}]);})}>添加文字</button></p>
 <h3>对话定位（本地，不计模型费用）</h3><label>修改描述<input value={message} onChange={e=>setMessage(e.target.value)} placeholder="修改主标题；也可先点击目标对象"/></label><label>替换为<input value={replacement} onChange={e=>setReplacement(e.target.value)}/></label>
 <button disabled={busy||readonly||!replacement} onClick={()=>action(async()=>setProposal(await apiRequest(`${base}/${current.document_id}/resolve-edit`,jsonRequest("POST",{version_id:current.version_id,message,selected_object_id:node?.id||null,replacement}))))}>先确认修改目标</button>
 {proposal&&<><pre>{JSON.stringify(proposal,null,2)}</pre>{proposal.proposal_id&&<button disabled={busy||readonly} onClick={()=>action(async()=>{await apiRequest(`${base}/${current.document_id}/proposals/${proposal.proposal_id}/apply`,jsonRequest("POST",{base_version_id:current.version_id,request_key:crypto.randomUUID()}));await load(current.document_id);})}>确认并应用提案</button>}</>}
 </section></div>}
 </>}
 </main>;
}
