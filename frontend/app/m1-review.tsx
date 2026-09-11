"use client";

import { Ref, useEffect, useImperativeHandle, useRef, useState } from "react";
import Image from "next/image";
import { apiRequest, apiUrl, jsonRequest } from "../lib/api-client";
import { canConfirmDraft, draftKey, DraftInput } from "../lib/intake-state";

export type IntakeSeed = { text: string; assetIds: string[]; nonce: string };
export type Snapshot = { schema_version?: number; text: string; facts: Record<string, string | string[]>; sources: Record<string, string>; assets: { id: string; name: string; usage: string }[]; show_price: boolean; show_store_name: boolean; style: string; provider: string; gaps: { field: string; question: string; kind: string }[]; ready: boolean; project_changes: string[] };
type Review = { creation_id: string; revision: number; status: string; snapshot_hash: string; snapshot: Snapshot | null; task_id?: string };
type Task = { id: string; status: string; progress: number; result: { long_image?: string; slices?: string[] }; error?: { code: string; message: string } };
export type IntakeController = { revise: () => Promise<void> };
type Props = { controller: Ref<IntakeController>; projectId: string; seed: IntakeSeed | null; draft: DraftInput; prepare: () => Promise<DraftInput>; onRestore: (snapshot: Snapshot) => void; onReply: (field?: string) => void; onAssets: () => void; onBusy: (busy: boolean) => void };

export function M1Review({ controller, projectId, seed, draft, prepare, onRestore, onReply, onAssets, onBusy }: Props) {
  const [review, setReview] = useState<Review | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [acceptedKey, setAcceptedKey] = useState("");
  const callbacks = useRef({ onRestore, onBusy, prepare });
  useEffect(() => { callbacks.current = { onRestore, onBusy, prepare }; }, [onRestore, onBusy, prepare]);
  const sending = useRef(false);
  const reviewRef = useRef<Review | null>(null);
  const processed = useRef("");
  const saveRequest = useRef({ body: "", key: "" });
  const errorRef = useRef<HTMLDivElement>(null);
  const base = `/projects/${projectId}/creations`;
  function apply(next: Review, restore = false) {
    reviewRef.current = next; setReview(next); setAcceptedKey("");
    if (restore && next.snapshot) callbacks.current.onRestore(next.snapshot);
  }
  function report(e: unknown) { setError(e instanceof Error ? e.message : "未能保存，请重试"); setTimeout(() => errorRef.current?.focus(), 0); }

  useEffect(() => {
    let stopped = false;
    const saved = new URLSearchParams(window.location.search).get("creation");
    if (saved && !seed) void apiRequest<Review>(`${base}/${saved}/review`).then(next => { if (!stopped) apply(next, true); }).catch(report);
    return () => { stopped = true; };
  }, [base, seed]);

  async function revise() {
    if (sending.current) return;
    sending.current = true; setBusy(true); callbacks.current.onBusy(true); setError("");
    try {
      let current = reviewRef.current;
      if (!current) {
        const id = new URLSearchParams(window.location.search).get("creation");
        if (id) current = await apiRequest<Review>(`${base}/${id}/review`);
      }
      if (!current || current.status === "CONFIRMED") current = await apiRequest<Review>(base, jsonRequest("POST", {}));
      reviewRef.current = current;
      window.history.replaceState({}, "", `?project=${projectId}&creation=${current.creation_id}`);
      const input = await callbacks.current.prepare();
      const body = JSON.stringify({ expected_revision: current.revision, text: input.text, asset_ids: input.assetIds, style: input.style, provider: input.provider,
        input_mode: input.replyField ? "reply" : "replace", reply_field: input.replyField ?? null,
        use_ai: Boolean(input.useAi), accepted_understanding_policy: input.useAi ? "text-understanding-paid-v1" : null });
      if (saveRequest.current.body !== body) saveRequest.current = { body, key: crypto.randomUUID() };
      const next = await apiRequest<Review>(`${base}/${current.creation_id}/intake-runs`, {
        method: "POST", body, headers: { "content-type": "application/json", "Idempotency-Key": saveRequest.current.key },
      });
      apply(next, true); setTask(null);
    } catch (e) { report(e); } finally { sending.current = false; setBusy(false); callbacks.current.onBusy(false); }
  }
  useImperativeHandle(controller, () => ({ revise }));
  useEffect(() => {
    if (!seed || processed.current === seed.nonce) return;
    processed.current = seed.nonce;
    void revise();
    // A seed represents one explicit first submission, never a render-triggered reparse.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed]);

  const taskId = review?.task_id;
  useEffect(() => {
    if (!taskId) return;
    let stopped = false; let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await apiRequest<Task>(`/tasks/${taskId}`);
        if (stopped) return;
        setTask(next);
        if (["PENDING", "RUNNING"].includes(next.status)) timer = setTimeout(poll, 1500);
      } catch (e) { if (!stopped) report(e); }
    }
    void poll(); return () => { stopped = true; clearTimeout(timer); };
  }, [taskId]);

  const snapshot = review?.snapshot;
  const reviewed = snapshot ? { text: snapshot.text, assetIds: snapshot.assets.map(a => a.id), style: snapshot.style, provider: snapshot.provider } : null;
  const clean = (snapshot?.schema_version ?? 1) >= 2 && !!reviewed && draftKey(draft) === draftKey(reviewed);
  const allowed = clean && !!snapshot && !!reviewed && canConfirmDraft(draft, reviewed, snapshot.ready);
  const authorization = review ? `${review.snapshot_hash}:${draftKey(draft)}` : "";
  async function confirm() {
    if (!review || !allowed || acceptedKey !== authorization || sending.current) return;
    sending.current = true; setBusy(true); callbacks.current.onBusy(true); setError("");
    try {
      const latest = await apiRequest<Review>(`${base}/${review.creation_id}/review`);
      if (latest.status === "CONFIRMED") { apply(latest); return; }
      if (latest.snapshot_hash !== review.snapshot_hash) { apply(latest, true); throw new Error("资料在其他页面更新，请核对最新摘要后再确认"); }
      // Confirm only the already displayed snapshot. Never reinterpret or mutate input here.
      const result = await apiRequest<{ task_id: string }>(`${base}/${review.creation_id}/confirm`, {
        ...jsonRequest("POST", { expected_revision: review.revision, snapshot_hash: review.snapshot_hash, accepted_budget_policy: "local-paid-generation-v1", materials_confirmed: true }),
        headers: { "content-type": "application/json", "Idempotency-Key": `confirm-${review.creation_id}-${review.revision}` },
      });
      apply({ ...review, status: "CONFIRMED", task_id: result.task_id });
    } catch (e) { report(e); } finally { sending.current = false; setBusy(false); callbacks.current.onBusy(false); }
  }
  async function pause() {
    if (!task) return;
    setBusy(true);
    try { setTask(await apiRequest<Task>(`/tasks/${task.id}/pause`, jsonRequest("POST", {}))); }
    catch (e) { report(e); } finally { setBusy(false); }
  }
  if (!review && !seed && !error) return null;
  return <section id="inline-confirmation" tabIndex={-1} className="inlineReview inlineFeedback" aria-label="本次生成摘要" aria-busy={busy}>
    {error && <div role="alert" tabIndex={-1} ref={errorRef} className="inlineReviewError">{error}<button type="button" disabled={busy} onClick={() => onReply()}>查看原始需求</button></div>}
    {busy && <p role="status">正在整理本次需求…</p>}
    {snapshot && review?.status !== "CONFIRMED" && <>
      {!clean && <p className="inlineFeedbackHint" role="status">需求有修改，发送后更新确认内容。</p>}
      {clean && snapshot.gaps.length > 0 && <div className="inlineMissing" role="alert" id="creation-missing">
        {snapshot.gaps.filter(g => g.field !== "assets").length > 0 && <p>请补充：{snapshot.gaps.filter(g => g.field !== "assets").map(g => g.kind === "conflict" ? g.question : ({store_name:"店名",hero_item:"本次重点（菜品、套餐、卖点或特色）",hero_price:"真实价格"} as Record<string,string>)[g.field] || g.question).join("、")}。<button type="button" onClick={() => onReply()}>继续填写</button></p>}
        {snapshot.gaps.some(g => g.field === "assets") && <p>请添加真实菜品图，门头不能用于成品。<button type="button" onClick={onAssets}>添加素材</button></p>}
      </div>}
      {allowed && <div className="inlineReady">
        <p className="inlineReadySummary"><strong>本次生成</strong> 首页五连图 · {snapshot.show_store_name ? String(snapshot.facts.store_name) : "不展示店名"} · {String(snapshot.facts.hero_item || snapshot.facts.selling_points || snapshot.facts.positioning || "展示所选菜品")}{snapshot.show_price ? ` · ${snapshot.facts.hero_price}` : ""}</p>
        <div className="inlineReadyActions"><label className="inlineConsent"><input type="checkbox" disabled={busy} checked={acceptedKey === authorization} onChange={e => setAcceptedKey(e.target.checked ? authorization : "")} /><span>确认内容与素材授权，同意本次生图费用</span></label><button type="button" className="inlineGenerate" disabled={busy || acceptedKey !== authorization} onClick={confirm}>确认生成</button></div>
      </div>}
    </>}
    {task && ["PENDING","RUNNING"].includes(task.status) && <button type="button" onClick={pause} disabled={busy}>暂停后续处理（已发送请求可能仍计费）</button>}
    {review?.status === "CONFIRMED" && <div role="status"><p>{task?.error?.message || (task?.status === "SUCCEEDED" ? "作品已生成，可以下载。" : task?.status === "RUNNING" ? "正在生成，离开页面不会取消任务。" : "任务已保存，等待后台执行。")}</p>{task?.result.long_image && <a href={apiUrl(`/projects/${projectId}/generations/${task.id}/assets/${task.result.long_image}`)} download><Image width={4000} height={600} unoptimized className="m1Result" src={apiUrl(`/projects/${projectId}/generations/${task.id}/assets/${task.result.long_image}`)} alt="完整五连图，点击下载" /></a>}{task?.result.slices && <div className="m1Options">{task.result.slices.map((file, i) => <a key={file} href={apiUrl(`/projects/${projectId}/generations/${task.id}/assets/${file}`)} download>下载第{i + 1}张</a>)}</div>}<a className="primaryButton" href={`/?project=${projectId}&compose=1`}>继续下一次创作</a></div>}
  </section>;
}
