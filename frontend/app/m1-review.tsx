"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { runConfirmationFlow } from "../lib/confirmation-flow";
import { apiRequest, apiUrl, jsonRequest } from "../lib/api-client";


export type IntakeSeed = { text: string; assetIds: string[]; nonce: string };
export type Snapshot = { text: string; facts: Record<string, string | string[]>; sources: Record<string, string>; assets: { id: string; name: string; usage: string }[]; show_price: boolean; show_store_name: boolean; style: string; provider: string; gaps: { field: string; question: string; kind: string }[]; ready: boolean; project_changes: string[] };
type Review = { creation_id: string; revision: number; status: string; snapshot_hash: string; snapshot: Snapshot | null; task_id?: string };
type Task = { id: string; status: string; progress: number; result: { long_image?: string; slices?: string[] }; error?: { code: string; message: string } };
type Prepared = { text: string; assetIds: string[]; style: string; provider: string };
type Props = { hasDish: boolean; projectId: string; seed: IntakeSeed | null; contextKey: string; prepare: () => Promise<Prepared>; onRestore: (snapshot: Snapshot) => void; onAssets: () => void; onBusy: (busy: boolean) => void };

export function M1Review({ hasDish, projectId, seed, prepare, contextKey, onRestore, onAssets, onBusy }: Props) {
  const [review, setReview] = useState<Review | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const callbacks = useRef({ onRestore, onBusy });
  useEffect(() => { callbacks.current = { onRestore, onBusy }; }, [onRestore, onBusy]);
  const sending = useRef(false);
  const saveRequest = useRef({ body: "", key: "" });
  const errorRef = useRef<HTMLDivElement>(null);
  const sequence = useRef(Promise.resolve());
  const reviewRef = useRef<Review | null>(null);
  const processed = useRef("");

  function applyReview(next: Review) { reviewRef.current = next; setReview(next);  }
  function report(e: unknown) { setError(e instanceof Error ? e.message : "请求失败，请重试"); setTimeout(() => errorRef.current?.focus(), 0); }
  const base = `/projects/${projectId}/creations`;
  const polledTaskId = review?.task_id;
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    const saved = new URLSearchParams(window.location.search).get("creation");
    if (saved && !seed) void apiRequest<Review>(`${base}/${saved}/review`).then(value => { if (!cancelled) { applyReview(value); if (value.snapshot) callbacks.current.onRestore(value.snapshot); } }).catch(report);
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

  async function confirm(answers: Record<string, string>, showPrice: boolean, showStore: boolean) {
    if (!review || sending.current) return;
    sending.current = true; setBusy(true); callbacks.current.onBusy(true); setError("");
    try {
      const result = await runConfirmationFlow<Review>({
        read: () => apiRequest<Review>(`${base}/${review.creation_id}/review`),
        save: async () => {
          const input = await prepare();
          const body = JSON.stringify({ expected_revision: review.revision, text: input.text, asset_ids: input.assetIds, answers, show_price: showPrice, show_store_name: showStore, style: input.style, provider: input.provider });
          if (saveRequest.current.body !== body) saveRequest.current = { body, key: crypto.randomUUID() };
          return apiRequest<Review>(`${base}/${review.creation_id}/intake-runs`, {
            method: "POST", body, headers: { "content-type": "application/json", "Idempotency-Key": saveRequest.current.key },
          });
        },
        confirm: async next => {
          // Keep the saved revision even if the confirmation response is lost.
          applyReview(next);
          const result = await apiRequest<{ task_id: string }>(`${base}/${next.creation_id}/confirm`, {
            ...jsonRequest("POST", { expected_revision: next.revision, snapshot_hash: next.snapshot_hash, accepted_budget_policy: "local-paid-generation-v1", materials_confirmed: true }),
            headers: { "content-type": "application/json", "Idempotency-Key": `confirm-${next.creation_id}-${next.revision}` },
          });
          return { ...next, status: "CONFIRMED", task_id: result.task_id };
        },
      });
      applyReview(result);
      if (!result.snapshot?.ready) setTimeout(() => document.querySelector<HTMLInputElement>(".inlineReview [aria-invalid=true]")?.focus(), 0);
    } catch (e) { report(e); } finally { sending.current = false; setBusy(false); callbacks.current.onBusy(false); }
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
  return <section id="inline-confirmation" tabIndex={-1} className="inlineReview" aria-label="本次生成确认" aria-busy={busy}>
    {error && <div role="alert" tabIndex={-1} ref={errorRef} className="inlineReviewError">{error}</div>}
    {busy && <p role="status">正在保存并核对资料…</p>}
    {task && ["PENDING", "RUNNING"].includes(task.status) && <div className="inlineReviewActions"><button type="button" disabled={busy} onClick={pause}>暂停后续处理</button><small>已发送的模型请求可能仍会计费。</small></div>}
    {snapshot && review?.status !== "CONFIRMED" && <InlineFields hasDish={hasDish} key={review!.revision} snapshot={snapshot} busy={busy} contextKey={contextKey} onConfirm={confirm} onAssets={onAssets} />}
    {review?.status === "CONFIRMED" && <div role="status"><p>{task?.error?.message || (task?.status === "SUCCEEDED" ? "作品已生成，可以下载。" : task?.status === "RUNNING" ? "正在生成，离开页面不会取消任务。" : "任务已保存，等待后台执行。")}</p>{task?.result.long_image && <a href={apiUrl(`/projects/${projectId}/generations/${task.id}/assets/${task.result.long_image}`)} download><Image width={4000} height={600} unoptimized className="m1Result" src={apiUrl(`/projects/${projectId}/generations/${task.id}/assets/${task.result.long_image}`)} alt="完整五连图，点击下载" /></a>}{task?.result.slices && <div className="m1Options">{task.result.slices.map((file, i) => <a key={file} href={apiUrl(`/projects/${projectId}/generations/${task.id}/assets/${file}`)} download>下载第{i + 1}张</a>)}</div>}<a className="primaryButton" href={`/?project=${projectId}&compose=1`}>继续下一次创作</a></div>}
  </section>;
}

function InlineFields({ hasDish, snapshot, busy, contextKey, onConfirm, onAssets }: { hasDish: boolean; snapshot: Snapshot; busy: boolean; contextKey: string; onConfirm: (answers: Record<string, string>, showPrice: boolean, showStore: boolean) => Promise<void>; onAssets: () => void }) {
  const [values, setValues] = useState<Record<string, string>>(() => ({
    store_name: String(snapshot.facts.store_name ?? ""), hero_item: String(snapshot.facts.hero_item ?? ""),
    selling_points: [snapshot.facts.positioning, snapshot.facts.selling_points].flat().filter(Boolean).join("；"), hero_price: String(snapshot.facts.hero_price ?? ""),
  }));
  const [showPrice, setShowPrice] = useState(snapshot.show_price);
  const [showStore, setShowStore] = useState(snapshot.show_store_name);
  const [editing, setEditing] = useState<string[]>([]);
  const [acceptedKey, setAcceptedKey] = useState("");
  const fingerprint = JSON.stringify([contextKey, values, showPrice, showStore]);
  const accepted = acceptedKey === fingerprint;
  const missing = [!hasDish ? "菜品图" : "", showStore && !values.store_name.trim() ? "店名" : "", !values.hero_item.trim() ? "主推菜品" : "", showPrice && !values.hero_price.trim() ? "价格" : ""].filter(Boolean);
  const field = (key: string, label: string) => {
    const open = !String(snapshot.facts[key] ?? "").trim() || editing.includes(key);
    const gap = snapshot.gaps.find(g => g.field === key);
    return <div className="inlineFact" key={key}>
      <label htmlFor={`inline-${key}`}>{label}</label>
      {open ? <input id={`inline-${key}`} value={values[key]} maxLength={500} placeholder={`填写${label}`} aria-invalid={!!gap && !values[key].trim()} onChange={e => setValues(v => ({ ...v, [key]: e.target.value }))} /> :
        <button type="button" className="inlineFactValue" onClick={() => setEditing(v => [...v, key])}>{values[key]}<span>修改</span></button>}
    </div>;
  };
  async function submit(event: FormEvent) { event.preventDefault(); if (!accepted || busy) return; await onConfirm({ ...values, positioning: "" }, showPrice, showStore); }
  return <form className="inlineReviewForm" onSubmit={submit}>
    <div className="inlineReviewHeading"><strong>首页五连图</strong><span>{missing.length ? `补充 ${missing.length} 项后即可生成` : "核对信息，即可生成"}</span></div>
    <fieldset disabled={busy} className="inlineReviewBody">
      <div className="inlineFacts">{showStore && field("store_name", "店名")}{field("hero_item", "主推菜品")}</div>
      <div className="inlineChips">
        <label className="inlineToggle"><input type="checkbox" checked={showStore} onChange={e => setShowStore(e.target.checked)} />展示店名</label>
        <label className="inlineToggle"><input type="checkbox" checked={showPrice} onChange={e => setShowPrice(e.target.checked)} />展示价格</label>
        <button type="button" onClick={onAssets}>查看本次素材</button>
      </div>
      {showPrice && field("hero_price", "价格")}
      {!hasDish && <p className="inlineAssetHint">请在上方添加真实菜品图；门头仅作参考。<button type="button" onClick={onAssets}>添加素材</button></p>}
      <details className="inlineMore"><summary>特色与卖点（选填）{values.selling_points && <span> · 已填写</span>}</summary><label htmlFor="inline-selling">特色与卖点</label><input id="inline-selling" maxLength={500} value={values.selling_points} placeholder="例如：现点现做、酸香开胃" onChange={e => setValues(v => ({ ...v, selling_points: e.target.value }))} /></details>
      <div className="inlineReviewFooter"><div><small>一张长图＋五张切片 · 修改仅用于本次创作</small><label className="inlineConsent"><input type="checkbox" checked={accepted} onChange={e => setAcceptedKey(e.target.checked ? fingerprint : "")} />确认资料和素材使用权，同意本次模型费用</label></div><button className="inlineGenerate" type="submit" disabled={!accepted || busy}>{busy ? "正在提交…" : "确认并生成五图"}</button></div>
      <details className="inlineDisclosure"><summary>费用与处理说明</summary><p>按首页所选模型调用，费用由供应商计收；不自动切换模型。当前为规则整理，请核对未识别的信息。门头和菜单不进入成品。素材的移除仅取消本次引用。</p></details>
    </fieldset>
  </form>;
}
