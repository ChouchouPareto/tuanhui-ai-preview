"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { apiRequest, apiUrl, jsonRequest } from "../lib/api-client";
import { Asset } from "../features/store-intake/types";

export type IntakeSeed = { text: string; assetIds: string[]; nonce: string };
type Snapshot = { text: string; facts: Record<string, string | string[]>; sources: Record<string, string>; assets: { id: string; name: string; usage: string }[]; show_price: boolean; show_store_name: boolean; style: string; provider: string; gaps: { field: string; question: string; kind: string }[]; ready: boolean; project_changes: string[] };
type Review = { creation_id: string; revision: number; status: string; snapshot_hash: string; snapshot: Snapshot | null; task_id?: string };
type Task = { id: string; status: string; progress: number; result: { long_image?: string; slices?: string[] }; error?: { code: string; message: string } };
const fields: Record<string, string> = { store_name: "展示店名", hero_item: "主推菜品 / 套餐", positioning: "门店特色（可选）", selling_points: "真实卖点（可选）", hero_price: "已确认价格" };

export function M1Review({ projectId, assets, seed }: { projectId: string; assets: Asset[]; seed: IntakeSeed | null }) {
  const [review, setReview] = useState<Review | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [dirty, setDirty] = useState(false);
  const errorRef = useRef<HTMLDivElement>(null);
  const sequence = useRef(Promise.resolve());
  const reviewRef = useRef<Review | null>(null);
  const processed = useRef("");

  function applyReview(next: Review) { reviewRef.current = next; setReview(next); setAccepted(false); setDirty(false); }
  function report(e: unknown) { setError(e instanceof Error ? e.message : "请求失败，请重试"); setTimeout(() => errorRef.current?.focus(), 0); }
  const base = `/projects/${projectId}/creations`;
  const polledTaskId = review?.task_id;
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    const saved = new URLSearchParams(window.location.search).get("creation");
    if (saved && !seed) void apiRequest<Review>(`${base}/${saved}/review`).then(value => { if (!cancelled) applyReview(value); }).catch(report);
    return () => { cancelled = true; };
  }, [base, projectId, seed]);

  useEffect(() => {
    if (!projectId || !seed || processed.current === seed.nonce) return;
    processed.current = seed.nonce;
    sequence.current = sequence.current.then(async () => {
      setBusy(true); setError(""); setTask(null);
      try {
        let current = reviewRef.current;
        if (!current || current.status === "CONFIRMED") current = await apiRequest<Review>(base, jsonRequest("POST", {}));
        // Write the identity before intake so a lost response can be recovered by refresh.
        window.history.replaceState({}, "", `?project=${projectId}&creation=${current.creation_id}`);
        const styleMap: Record<string, string> = { "品牌质感": "brand", "烟火市井": "street", "清爽简约": "minimal" };
        const style = Object.keys(styleMap).find(label => seed.text.includes(`视觉风格：${label}`));
        const result = await apiRequest<Review>(`${base}/${current.creation_id}/intake-runs`, {
          ...jsonRequest("POST", { expected_revision: current.revision, text: seed.text, asset_ids: seed.assetIds, show_price: /(?:价格|售价)[:：]\s*\d/.test(seed.text), style: style ? styleMap[style] : "appetite", provider: seed.text.includes("模型：豆包") ? "doubao" : "qwen" }),
          headers: { "content-type": "application/json", "Idempotency-Key": seed.nonce },
        });
        applyReview(result);
      } catch (e) { report(e); } finally { setBusy(false); }
    });
  }, [base, projectId, seed]);

  useEffect(() => {
    if (!polledTaskId) return;
    let stopped = false; let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const value = await apiRequest<Task>(`/tasks/${polledTaskId}`);
        if (stopped) return;
        setTask(value);
        if (["PENDING", "RUNNING"].includes(value.status)) timer = setTimeout(poll, 1500);
      } catch (e) { if (!stopped) report(e); }
    }
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [polledTaskId]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!review?.snapshot) return;
    const data = new FormData(event.currentTarget); setBusy(true); setError("");
    try {
      const answers = Object.fromEntries(Object.keys(fields).map(key => [key, String(data.get(key) ?? "")]));
      const next = await apiRequest<Review>(`${base}/${review.creation_id}/intake-runs`, {
        ...jsonRequest("POST", { expected_revision: review.revision, text: review.snapshot.text, asset_ids: data.getAll("asset_id"), answers, show_price: data.get("show_price") === "on", show_store_name: data.get("show_store_name") === "on", style: data.get("style"), provider: data.get("provider") }),
        headers: { "content-type": "application/json", "Idempotency-Key": crypto.randomUUID() },
      });
      applyReview(next);
    } catch (e) { report(e); } finally { setBusy(false); }
  }
  async function confirm() {
    if (!review || !accepted || dirty) return;
    setBusy(true); setError("");
    try {
      const result = await apiRequest<{ task_id: string }>(`${base}/${review.creation_id}/confirm`, {
        ...jsonRequest("POST", { expected_revision: review.revision, snapshot_hash: review.snapshot_hash, accepted_budget_policy: "local-paid-generation-v1", materials_confirmed: accepted }),
        headers: { "content-type": "application/json", "Idempotency-Key": `confirm-${review.creation_id}-${review.revision}` },
      });
      applyReview({ ...review, status: "CONFIRMED", task_id: result.task_id });
    } catch (e) { report(e); } finally { setBusy(false); }
  }
  async function pause() {
    if (!task) return;
    setBusy(true);
    try {
      setTask(await apiRequest<Task>(`/tasks/${task.id}/pause`, jsonRequest("POST", {})));
    } catch (e) { report(e); } finally { setBusy(false); }
  }
  if (!review && !seed && !error) return null;
  const snapshot = review?.snapshot;
  return <section className="m1Review" aria-labelledby="m1-title" aria-busy={busy}>
    <header><div><span className="stepKicker">本次创作 · M1 内测</span><h2 id="m1-title">{review?.status === "CONFIRMED" ? "已确认，作品会保留在当前项目" : "把必要信息一次确认清楚"}</h2></div><a href={`/projects?project=${projectId}`}>返回项目</a></header>
    {error && <div role="alert" tabIndex={-1} ref={errorRef} className="m1Error">{error}</div>}
    {busy && <p role="status">正在保存，请稍候…</p>}
    {snapshot && <details><summary>查看已保存的原始需求</summary><p style={{ whiteSpace: "pre-wrap" }}>{snapshot.text}</p></details>}
    {task && ["PENDING", "RUNNING"].includes(task.status) && <div className="m1Options"><button type="button" disabled={busy} onClick={pause}>暂停后续处理</button><small>已发送的模型请求可能仍会计费；暂停不会撤销供应商请求。</small></div>}
    {snapshot && review?.status !== "CONFIRMED" && <>
      <p>当前使用规则整理，不调用付费理解模型。自由描述没有识别出的信息，请在下方填写；不会猜测菜品和价格。</p>
      {!!snapshot.gaps.length && <ul className="m1Gaps">{snapshot.gaps.map(gap => <li key={gap.field}><a href={`#m1-${gap.field}`}>{gap.question}</a></li>)}</ul>}
      <form key={review!.revision} onSubmit={save} onChange={() => { setDirty(true); setAccepted(false); }}>
        <div className="m1Fields">{Object.entries(fields).map(([key, label]) => <label key={key} htmlFor={`m1-${key}`}>{label}<input id={`m1-${key}`} name={key} maxLength={500} defaultValue={String(snapshot.facts[key] ?? "")} aria-invalid={snapshot.gaps.some(g => g.field === key)} aria-describedby={snapshot.gaps.some(g => g.field === key) ? `m1-error-${key}` : undefined} />{snapshot.gaps.filter(g => g.field === key).map(g => <small id={`m1-error-${key}`} key={g.field}>{g.question}</small>)}</label>)}</div>
        <div className="m1Options"><label><input type="checkbox" name="show_price" defaultChecked={snapshot.show_price} />展示价格</label><label><input type="checkbox" name="show_store_name" defaultChecked={snapshot.show_store_name} />展示店名</label><label>风格<select name="style" defaultValue={snapshot.style}><option value="appetite">食欲冲击</option><option value="brand">品牌质感</option><option value="street">烟火市井</option><option value="minimal">清爽简约</option></select></label><label>模型<select name="provider" defaultValue={snapshot.provider}><option value="qwen">千问</option><option value="doubao">豆包</option></select></label></div>
        <fieldset id="m1-assets"><legend>本次使用素材（可取消勾选）</legend>{assets.map(a => <label key={a.id}><input type="checkbox" name="asset_id" value={a.id} defaultChecked={snapshot.assets.some(item => item.id === a.id)} />{a.original_name}<small>{["dish", "signature_dish"].includes(a.semantic_role) ? "菜品候选 · 请核对内容" : "仅识别，不进入成品"}</small></label>)}</fieldset>
        <button className="primaryButton" disabled={busy}>保存补充，更新确认卡</button>
      </form>
      {snapshot.ready && <div className="m1Confirm"><h3>生成确认</h3><p>交付：一张完整长图＋五张切片。{snapshot.show_price ? `价格：${snapshot.facts.hero_price}` : "不展示价格"}；{snapshot.show_store_name ? `店名：${snapshot.facts.store_name}` : "不展示店名"}。所选菜品将合成到同一母版。</p><p>本次修改仅用于当前创作，不覆盖项目长期资料。修改上方信息后，请先保存再确认。</p><p>本地内测：调用 {snapshot.provider === "qwen" ? "千问" : "豆包"} 将产生供应商模型费用，最多提交一次、不自动切换模型。订阅积分尚未启用，不代表免费。</p><label><input type="checkbox" checked={accepted} onChange={e => setAccepted(e.target.checked)} />我确认已保存的信息和菜品一致、拥有素材使用权，并同意本次模型费用</label><button type="button" className="primaryButton" disabled={busy || !accepted || dirty} onClick={confirm}>确认并开始生成</button></div>}
    </>}
    {review?.status === "CONFIRMED" && <div role="status"><p>{task?.error?.message || (task?.status === "SUCCEEDED" ? "作品已生成，可以下载。" : task?.status === "RUNNING" ? "正在生成，离开页面不会取消任务。" : "任务已保存，等待后台执行。")}</p>{task?.result.long_image && <a href={apiUrl(`/projects/${projectId}/generations/${task.id}/assets/${task.result.long_image}`)} download><Image width={4000} height={600} unoptimized className="m1Result" src={apiUrl(`/projects/${projectId}/generations/${task.id}/assets/${task.result.long_image}`)} alt="完整五连图，点击下载" /></a>}{task?.result.slices && <div className="m1Options">{task.result.slices.map((file, i) => <a key={file} href={apiUrl(`/projects/${projectId}/generations/${task.id}/assets/${file}`)} download>下载第{i + 1}张</a>)}</div>}<a className="primaryButton" href={`/?project=${projectId}&compose=1`}>继续下一次创作</a></div>}
  </section>;
}
