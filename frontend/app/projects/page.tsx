"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { apiRequest, apiUrl } from "../../lib/api-client";

type Project = { id: string; name: string; status: string; updated_at: string; task_count: number; cover: string | null };
type Task = { id: string; status: string; created_at: string; progress: number; result: { long_image?: string }; error: string | null };
type Workspace = { id: string; name: string; facts: Record<string, unknown>; style: { name: string } | null; tasks: Task[] };
type Asset = { id: string; original_name: string; semantic_role: string; preview_path: string };
const labels: Record<string, string> = { SUCCEEDED: "已完成", RUNNING: "生成中", PENDING: "等待中", FAILED_FINAL: "生成失败", NEEDS_USER: "已暂停" };
const roles: Record<string, string> = { storefront: "门头", menu: "菜单", dish: "菜品", signature_dish: "招牌菜", logo: "Logo", environment: "环境" };

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [tab, setTab] = useState("作品");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let disposed = false;
    const id = new URLSearchParams(window.location.search).get("project");
    queueMicrotask(() => { if (!disposed) { setLoading(true); setError(""); } });
    const request = id ? Promise.all([apiRequest<Workspace>(`/projects/${id}/workspace`), apiRequest<Asset[]>(`/projects/${id}/assets`)]).then(([w, a]) => { if (!disposed) { setWorkspace(w); setAssets(a); } }) : apiRequest<Project[]>("/projects").then(p => { if (!disposed) setProjects(p); });
    void request.catch(e => { if (!disposed) setError(e.message); }).finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [revision]);
  const compose = workspace ? `/?project=${workspace.id}&compose=1` : "/";
  const fields: Record<string, string> = { store_name: "门店名称", positioning: "门店定位", hero_item: "主推内容", hero_price: "套餐价格", selling_points: "卖点" };
  return <main className="projectHub">
    <nav className="projectBreadcrumb" aria-label="导航"><Link href="/">团绘AI · 创作首页</Link><span>/</span><a href="/projects">我的项目</a>{workspace && <><span>/</span><span>{workspace.name}</span></>}</nav>
    <header className="projectHeader"><div><small>PROJECT WORKSPACE</small><h1>{workspace?.name || "我的项目"}</h1><p>{workspace ? "素材、品牌资料与每一次创作，都保留在这个项目里。" : "从一家门店开始，让每一次创作保持一致。"}</p></div><div className="projectActions"><button onClick={() => setRevision(v => v + 1)} disabled={loading}>刷新</button><a className="projectPrimary" href={compose}>{workspace ? "继续创作" : "新建项目"}</a></div></header>
    {error && <p role="alert" className="projectError">{error} · 请确认本地后端已启动，可点击刷新重试。</p>}
    {loading ? <p role="status" className="projectEmpty">正在读取项目…</p> : !error && <>
      <div className="projectTools">{workspace ? <div className="projectTabs" role="tablist" aria-label="项目内容">{["作品", "素材", "品牌资料"].map(t => <button key={t} role="tab" aria-selected={tab === t} onClick={() => { setTab(t); setQuery(""); }}>{t}</button>)}</div> : <span>{projects.length} 个项目</span>}<input aria-label="搜索项目或素材" placeholder="搜索名称或任务编号" value={query} onChange={e => setQuery(e.target.value)} /></div>
      {!workspace ? <div className="projectGrid">{projects.filter(p => p.name.includes(query)).map(p => <a className="projectCard" key={p.id} href={`/projects?project=${p.id}`}><div className="projectCover">{p.cover ? <Image src={apiUrl(p.cover)} alt={`${p.name}最近作品`} width={800} height={120} unoptimized /> : <span>尚未生成作品</span>}</div><h2>{p.name}</h2><p>{p.task_count} 次创作 · {new Date(p.updated_at).toLocaleDateString()}</p><span>打开项目 →</span></a>)}{!projects.filter(p => p.name.includes(query)).length && <p className="projectEmpty">{query ? "没有匹配的项目" : "还没有项目，点击「新建项目」开始。"}</p>}</div> : tab === "作品" ? <div className="projectGrid">{workspace.tasks.filter(t => t.id.includes(query)).map(t => <a className="projectCard" key={t.id} href={`/?project=${workspace.id}&task=${t.id}`}><div className="projectCover">{t.result.long_image ? <Image src={apiUrl(`/projects/${workspace.id}/generations/${t.id}/assets/${t.result.long_image}`)} alt="五连图作品" width={800} height={120} unoptimized /> : <span>{labels[t.status] || t.status}</span>}</div><h2>{labels[t.status] || t.status} · 五连图</h2><p>{new Date(t.created_at).toLocaleString()} · {t.id.slice(0, 8)}</p>{t.error && <p>{t.error}</p>}<span>查看任务与作品 →</span></a>)}{!workspace.tasks.filter(t => t.id.includes(query)).length && <p className="projectEmpty">暂无匹配作品。点击「继续创作」开始，已有素材会保留。</p>}</div> : tab === "素材" ? <><p className="projectHint">按项目保存的原始上传。需要补充素材时，点击「继续创作」在首页添加。</p><div className="projectGrid">{assets.filter(a => a.original_name.includes(query)).map(a => <a className="projectCard" href={apiUrl(a.preview_path)} target="_blank" rel="noreferrer" key={a.id}><div className="projectCover assetCover"><Image src={apiUrl(a.preview_path)} alt={a.original_name} width={320} height={240} unoptimized /></div><h2>{a.original_name}</h2><p>{roles[a.semantic_role] || "其他素材"}</p></a>)}{!assets.length && <p className="projectEmpty">暂无素材</p>}</div></> : <section className="projectFacts"><h2>项目品牌记忆</h2><p>下一次创作沿用项目素材；修改资料需在创作流程中重新确认。</p><dl>{Object.entries(fields).map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{Array.isArray(workspace.facts[key]) ? (workspace.facts[key] as string[]).join("、") : String(workspace.facts[key] || "待补充")}</dd></div>)}<div><dt>最近设计风格</dt><dd>{workspace.style?.name || "尚未选择"}</dd></div></dl></section>}
    </>}
  </main>;
}
