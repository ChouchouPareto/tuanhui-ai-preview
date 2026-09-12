"use client";

import { Ref, useEffect, useImperativeHandle, useRef, useState } from "react";
import { GenerationGallery } from "./generation-gallery";
import { WorkflowTiming } from "./workflow-timing";
import { createPortal } from "react-dom";
import { apiRequest, jsonRequest } from "../lib/api-client";
import { canConfirmDraft, draftKey, DraftInput } from "../lib/intake-state";

export type IntakeSeed = { text: string; assetIds: string[]; nonce: string };
export type Snapshot = { render_mode?: string; messages?: { role: string; content: string }[]; schema_version?: number; text: string; facts: Record<string, string | string[]>; sources: Record<string, string>; assets: { id: string; name: string; usage: string }[]; show_price: boolean; show_store_name: boolean; style: string; provider: string; gaps: { field: string; question: string; kind: string }[]; ready: boolean; project_changes: string[] };
type Review = { creation_id: string; revision: number; status: string; snapshot_hash: string; snapshot: Snapshot | null; task_id?: string; previous_task_id?: string; project_name?: string };
type Task = { id: string; project_id?: string; creation_id?: string; status: string; progress: number; result: { long_image?: string; slices?: string[]; clean_long_image?: string; clean_slices?: string[] }; error?: { code: string; message: string } };
export type IntakeController = { revise: () => Promise<void>; pause: () => Promise<void> };
type Props = { autoGenerate?: () => boolean; onGenerationActive?: (active: boolean) => void; target: HTMLElement | null; controller: Ref<IntakeController>; projectId: string; seed: IntakeSeed | null; draft: DraftInput; prepare: () => Promise<DraftInput>; onRestore: (snapshot: Snapshot) => void; onReply: (field?: string) => void; onAssets: () => void; onBusy: (busy: boolean) => void };

export function M1Review({ autoGenerate, onGenerationActive, target, controller, projectId, seed, draft, prepare, onRestore, onReply, onAssets, onBusy }: Props) {
  const [review, setReview] = useState<Review | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [previousTask, setPreviousTask] = useState<Task | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const callbacks = useRef({ onRestore, onBusy, prepare });
  useEffect(() => { callbacks.current = { onRestore, onBusy, prepare }; }, [onRestore, onBusy, prepare]);
  const sending = useRef(false);
  const reviewRef = useRef<Review | null>(null);
  const processed = useRef("");
  const saveRequest = useRef({ body: "", key: "" });
  const errorRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if (task) onGenerationActive?.(["PENDING", "RUNNING"].includes(task.status)); }, [task, onGenerationActive]);
  const base = `/projects/${projectId}/creations`;
  useEffect(() => { if (target) target.scrollTop = target.scrollHeight; }, [target, review?.revision, task?.status]);
  function apply(next: Review, restore = false) {
    reviewRef.current = next; setReview(next);
    if (next.project_name) window.dispatchEvent(new CustomEvent("tuanhui:project-renamed", {detail: {projectId, name: next.project_name}}));
    if (restore && next.snapshot) callbacks.current.onRestore(next.snapshot);
  }
  function report(e: unknown) { setError(e instanceof Error ? e.message : "未能保存，请重试"); setTimeout(() => errorRef.current?.focus(), 0); }

  useEffect(() => {
    let stopped = false;
    const params = new URLSearchParams(window.location.search);
    if (!seed && params.get("compose") !== "1") void (async () => {
      let saved = params.get("creation");
      let savedTask = params.get("task");
      if (!saved && !savedTask) {
        const workspace = await apiRequest<{latest_creation_id?: string; tasks: Task[]}>(`/projects/${projectId}/workspace`);
        saved = workspace.latest_creation_id || null;
        if (!saved) savedTask = workspace.tasks[0]?.id || null;
      }
      if (!saved && savedTask) {
        const restored = await apiRequest<Task>(`/tasks/${savedTask}`);
        if (restored.project_id && restored.project_id !== projectId) throw new Error("该结果不属于当前项目");
        if (stopped) return;
        saved = restored.creation_id || null;
        setTask(restored);
        if (!saved) apply({creation_id: "", revision: 0, status: "CONFIRMED", snapshot_hash: "", snapshot: null, task_id: restored.id});
      }
      if (saved) {
        const next = await apiRequest<Review>(`${base}/${saved}/review`);
        if (!stopped) apply(next, true);
        if (next.previous_task_id) {
          const previous = await apiRequest<Task>(`/tasks/${next.previous_task_id}`);
          if (!stopped && previous.status === "SUCCEEDED" && previous.project_id === projectId) setPreviousTask(previous);
        }
      }
    })().catch(e => { if (!stopped) report(e); });
    return () => { stopped = true; };
  }, [base, projectId, seed]);

  async function revise(initial?: IntakeSeed) {
    if (sending.current || (task && ["PENDING", "RUNNING"].includes(task.status))) return;
    sending.current = true; setBusy(true); callbacks.current.onBusy(true); setError("");
    try {
      let current = reviewRef.current;
      if (!current) {
        const id = new URLSearchParams(window.location.search).get("creation");
        if (id) current = await apiRequest<Review>(`${base}/${id}/review`);
      }
      if (!current || current.status === "CONFIRMED") {
        if (task?.status === "SUCCEEDED") setPreviousTask(task);
        current = await apiRequest<Review>(base, jsonRequest("POST", current?.creation_id ? { parent_creation_id: current.creation_id } : {}));
        setTask(null);
      }
      reviewRef.current = current;
      setReview(current);
      window.history.replaceState({}, "", `?project=${projectId}&creation=${current.creation_id}`);
      const input = initial ? { ...draft, text: initial.text, assetIds: initial.assetIds, chat: true, useAi: Boolean(initial.text.trim()) } : await callbacks.current.prepare();
      const body = JSON.stringify({ expected_revision: current.revision, text: input.text, asset_ids: input.assetIds, style: input.style, provider: input.provider,
        input_mode: input.chat ? "chat" : input.replyField ? "reply" : "replace", reply_field: input.replyField ?? null,
        allow_illustration: true, use_ai: Boolean(input.useAi), accepted_understanding_policy: input.useAi ? "text-understanding-paid-v1" : null });
      if (saveRequest.current.body !== body) saveRequest.current = { body, key: crypto.randomUUID() };
      const next = await apiRequest<Review>(`${base}/${current.creation_id}/intake-runs`, {
        method: "POST", body, headers: { "content-type": "application/json", "Idempotency-Key": saveRequest.current.key },
      });
      apply(next, true); setTask(null);
      if (autoGenerate?.() && next.snapshot?.ready) await confirmSnapshot(next);
      setTimeout(() => onReply(), 0);
    } catch (e) { report(e); } finally { sending.current = false; setBusy(false); callbacks.current.onBusy(false); }
  }
  useImperativeHandle(controller, () => ({ revise, pause }));
  useEffect(() => {
    if (!seed || processed.current === seed.nonce) return;
    processed.current = seed.nonce;
    void revise(seed);
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
  async function confirmSnapshot(candidate: Review) {
    const latest = await apiRequest<Review>(`${base}/${candidate.creation_id}/review`);
    if (latest.status === "CONFIRMED") { apply(latest); return; }
    if (latest.snapshot_hash !== candidate.snapshot_hash) { apply(latest, true); throw new Error("需求在其他页面更新了，请查看最新内容后再开始。"); }
    const result = await apiRequest<{ task_id: string }>(`${base}/${candidate.creation_id}/confirm`, {
      ...jsonRequest("POST", { expected_revision: candidate.revision, snapshot_hash: candidate.snapshot_hash, accepted_budget_policy: "local-paid-generation-v1", materials_confirmed: true }),
      headers: { "content-type": "application/json", "Idempotency-Key": `confirm-${candidate.creation_id}-${candidate.revision}` },
    });
    apply({ ...candidate, status: "CONFIRMED", task_id: result.task_id });
  }
  async function confirm() {
    if (!review || !allowed || sending.current) return;
    sending.current = true; setBusy(true); callbacks.current.onBusy(true); setError("");
    try { await confirmSnapshot(review); }
    catch (e) { report(e); } finally { sending.current = false; setBusy(false); callbacks.current.onBusy(false); }
  }
  async function pause() {
    if (!task) return;
    setBusy(true);
    try { setTask(await apiRequest<Task>(`/tasks/${task.id}/pause`, jsonRequest("POST", {}))); }
    catch (e) { report(e); } finally { setBusy(false); }
  }
  if (!target || (!review && !seed && !error && !busy)) return null;
  return createPortal(<section id="inline-confirmation" tabIndex={-1} className="inlineReview inlineFeedback" aria-label="本次生成摘要" aria-busy={busy}>
    <div className="chatMessages" aria-label="创作对话">{(snapshot?.messages ?? (snapshot?.text ? [{role:"user", content:snapshot.text}] : [])).map((message, index) => <div key={index} className={`chatMessage ${message.role}`}><span className="srOnly">{message.role === "user" ? "你" : "团绘"}</span><p>{message.content}</p></div>)}</div>
    {error && <div role="alert" tabIndex={-1} ref={errorRef} className="inlineReviewError">{error}<button type="button" disabled={busy} onClick={() => onReply()}>继续修改</button></div>}
    {busy && <p role="status">我在看你的需求…</p>}
    <WorkflowTiming path={task ? `/projects/${projectId}/tasks/${task.id}/activity` : review?.creation_id ? `${base}/${review.creation_id}/activity` : null} active={busy || !!task && ["PENDING", "RUNNING"].includes(task.status)} />
    {previousTask && task?.status !== "SUCCEEDED" && <details className="previousResult"><summary>查看上一版作品（已保留）</summary><GenerationGallery projectId={projectId} taskId={previousTask.id} longImage={previousTask.result.long_image} slices={previousTask.result.slices} cleanLongImage={previousTask.result.clean_long_image} cleanSlices={previousTask.result.clean_slices} /></details>}
    {snapshot && review?.status !== "CONFIRMED" && <>
      {!clean && <p className="inlineFeedbackHint" role="status"></p>}
      {clean && !snapshot.messages?.length && snapshot.gaps.length > 0 && <div className="inlineMissing" role="status" aria-live="polite" id="creation-missing">
        {snapshot.gaps.filter(g => g.field !== "assets").length > 0 && <p>{snapshot.gaps.filter(g => g.field !== "assets").map(g => g.kind === "conflict" ? g.question : ({store_name:"图片上想展示哪个店名？",hero_item:"这次想突出什么？菜品、套餐、卖点或特色都可以。",hero_price:"想在图片上展示的价格是多少？不展示也可以。"} as Record<string,string>)[g.field] || g.question).join(" ")}<button type="button" onClick={() => onReply()}>补充一句</button></p>}
        {snapshot.gaps.some(g => g.field === "assets") && <p>还需要一张真实菜品图来制作画面，门头照片仅用于识别。<button type="button" onClick={onAssets}>上传菜品图</button></p>}
      </div>}
      {allowed && !busy && <div className="inlineReady">
        <p className="inlineReadySummary"><strong>本次生成</strong> {snapshot.render_mode === "illustration" ? "AI 示意五连图（非实拍）" : "首页五连图"} · {snapshot.show_store_name ? String(snapshot.facts.store_name) : "不展示店名"} · {String(snapshot.facts.hero_item || snapshot.facts.selling_points || snapshot.facts.positioning || "展示所选菜品")}{snapshot.show_price ? ` · ${snapshot.facts.hero_price}` : ""}</p>
        <div className="inlineReadyActions"><span className="generationConsentNote">点击即确认素材使用权并同意本次生图费用。</span><button type="button" className="inlineGenerate" disabled={busy} onClick={confirm}>生成五图</button></div>
      </div>}
    </>}
    {snapshot?.messages?.length && snapshot.gaps.some(g => g.field === "assets") && <div className="chatAssetChoices"><button type="button" className="chatUpload" onClick={onAssets}>上传菜品照片</button><button type="button" className="chatUpload" onClick={() => onReply("illustration")}>先做 AI 示意图</button><small>示意图不代表真实菜品，导出保留标识。</small></div>}
    {task && ["PENDING","RUNNING"].includes(task.status) && <div className="studioProgress" role="status"><h2>{task.status === "PENDING" ? "正在排队，尚未开始生图" : "正在生成整张长图"}</h2><p>{task.status === "PENDING" ? "后台接单后会自动开始，可以随时停止排队。" : "完成后会自动排版，再切成五张。"}</p><progress max={100} value={task.progress} /><p>已发送的模型请求可能仍会计费；停止后不再继续后续处理。</p></div>}
    {review?.status === "CONFIRMED" && <div role="status"><p>{task?.error?.message || (task?.status === "SUCCEEDED" ? "作品已生成，可以下载。" : task?.status === "RUNNING" ? "正在生成，离开页面不会取消任务。" : task?.status === "NEEDS_USER" ? "已停止，需求和素材已保留。需要重新生成时请开始下一次创作。" : task?.status === "FAILED_FINAL" ? "这次生成没有完成，需求已保留，没有自动重试。" : "任务已保存，等待后台执行。")}</p>{task && <GenerationGallery projectId={projectId} taskId={task.id} longImage={task.result.long_image} slices={task.result.slices} cleanLongImage={task.result.clean_long_image} cleanSlices={task.result.clean_slices} />}<div className="studioResultActions"><a className="primaryButton" href={`/?project=${projectId}&compose=1`}>继续下一次创作</a><a href={`/projects?project=${projectId}`}>返回项目</a></div></div>}
  </section>, target);
}
