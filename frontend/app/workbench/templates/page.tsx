"use client";
import {useEffect,useState} from "react";
import Link from "next/link";
import {jsonRequest} from "../../../lib/api-client";
import {adminRequest as apiRequest} from "../../../lib/admin-client";
import "../workbench.css";
type Template={id:string;name:string;template_hash:string;review_state:string;notes:string;regions:{role:string;box?:number[];rect?:number[]}[]};
export default function Templates(){
 const [rows,setRows]=useState<Template[]>([]),[error,setError]=useState("");
 useEffect(()=>{apiRequest<Template[]>("/templates").then(setRows).catch(e=>setError(e.message));},[]);
 async function review(row:Template,state:string){setError("");try{await apiRequest(`/templates/${row.id}/review`,jsonRequest("POST",{template_hash:row.template_hash,state,notes:row.notes}));setRows(await apiRequest("/templates"));}catch(e){setError((e as Error).message);}}
 return <main className="functional-workbench"><header><h1>构图结构审核 · 功能版</h1><Link href="/workbench">返回工作台</Link></header><p>这是已有坐标模板的结构预览，不是稿定案例拆解完成稿，也不是 Figma 审核稿。审核按内容指纹记录；模板变动需要重新审核。当前生成仍属内部预览。</p>{error&&<p role="alert">{error}</p>}<div className="wb-template">{rows.map(row=><section key={row.id}><h2>{row.id} · {row.name}</h2><svg viewBox="0 0 600 180" aria-label={`${row.name}区域示意`} role="img">{row.regions.map((r,i)=>{const b=r.box||r.rect;return b?<g key={i}><rect x={b[0]*600} y={b[1]*180} width={b[2]*600} height={b[3]*180} fill={r.role==="copy"?"#e0d3fa":"#d8e9df"} stroke="#555"/><text x={b[0]*600+4} y={b[1]*180+16} fontSize="12">{r.role}</text></g>:null;})}</svg><p>状态：{row.review_state}</p><details><summary>查看坐标合同</summary><pre>{JSON.stringify(row.regions,null,2)}</pre></details><label>审核备注<textarea value={row.notes} onChange={e=>setRows(rows.map(r=>r.id===row.id?{...r,notes:e.target.value}:r))}/></label><div className="wb-row"><button onClick={()=>review(row,"approved")}>审核通过</button><button onClick={()=>review(row,"rejected")}>需修改</button><button onClick={()=>review(row,"draft")}>保留草稿</button></div></section>)}</div></main>;
}
