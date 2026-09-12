"use client";
import { useRef, useState } from "react";
import { apiRequest, jsonRequest } from "../../lib/api-client";

export function ProjectMenu({id, name, visibility, onChange}: {id:string; name:string; visibility:string; onChange:()=>void}) {
  const menu = useRef<HTMLDetailsElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const [action,setAction] = useState("");
  const [title,setTitle] = useState(name);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  function open(value:string) { setAction(value); setTitle(name); setError(""); if(menu.current) menu.current.open=false; dialog.current?.showModal(); }
  async function save() {
    setBusy(true); setError("");
    try {
      if(action === "复制") await apiRequest(`/projects/${id}/duplicate`,jsonRequest("POST",{}));
      else await apiRequest(`/projects/${id}`,jsonRequest("PATCH", action === "编辑" ? {name:title.trim()} : {visibility:action === "删除" ? "deleted" : action === "隐藏" ? "hidden" : "visible"}));
      dialog.current?.close(); onChange();
    } catch(e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  return <div className="projectMenu">
    <details ref={menu} onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget)) e.currentTarget.open=false;}} onKeyDown={e=>{if(e.key === "Escape" && menu.current) menu.current.open=false;}}>
      <summary aria-label={`管理项目：${name}`}>⋯</summary>
      <div className="projectMenuItems">{(visibility === "deleted" ? ["恢复"] : ["编辑","复制",visibility === "hidden" ? "取消隐藏" : "隐藏","删除"]).map(value=><button type="button" key={value} onClick={()=>open(value)}>{value}</button>)}</div>
    </details>
    <dialog ref={dialog} className="projectEditDialog" onCancel={e=>{if(busy)e.preventDefault();}}>
      <h2>{action}项目</h2>
      {action === "编辑" ? <label>项目名称<input value={title} maxLength={120} onChange={e=>setTitle(e.target.value)} autoFocus /></label> : <p>{action === "删除" ? "移入回收站后可恢复，素材和结果不会被清除。" : action === "复制" ? "复制项目资料与素材，不复制历史生成任务，也不会调用模型。" : action === "隐藏" ? "从默认列表隐藏，之后可在“已隐藏”中找回。" : "将项目恢复到默认列表。"}</p>}
      {error && <p role="alert">{error}</p>}
      <footer><button disabled={busy} onClick={()=>dialog.current?.close()}>取消</button><button disabled={busy || (action === "编辑" && !title.trim())} onClick={()=>void save()}>{busy ? "处理中…" : `确认${action}`}</button></footer>
    </dialog>
  </div>;
}
