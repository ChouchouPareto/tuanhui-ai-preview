"use client";

import Image from "next/image";
import { GenerationGallery } from "./generation-gallery";
import { M1Review, IntakeSeed, IntakeController } from "./m1-review";
import { ReferenceCategory, ReferenceThumbnail } from "./reference-thumbnail";
import { StudioPhotoStack } from "./studio-photo-stack";
import { OUTPUT_NAMES, DEFAULT_DELIVERIES } from "../lib/output-options";
import { ChangeEvent, FormEvent, ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { apiRequest, apiUrl, jsonRequest } from "../lib/api-client";
import { Asset, Coverage, Facts, MenuProduct, StoreNameCandidate } from "../features/store-intake/types";

type Step = 1 | 2 | 3 | 4 | 5 | 6;
type CreationView = "oneclick" | "professional";
type WorkspaceView = CreationView | "library";
type LibraryTab = "store" | "dish";
type IconName = "spark" | "folder" | "image" | "book" | "history" | "menu" | "close" | "plus" | "arrow" | "check" | "store" | "upload" | "chat" | "help" | "user" | "pause" | "play" | "retry";

const STORE_ASSET_ROLES = ["storefront", "environment", "logo"];
const DISH_ASSET_ROLES = ["menu", "signature_dish", "dish"];

type DesignFrame = { index: number; role: string; headline: string; support: string; visual: string };
type DesignPlan = { id: string; version: number; status: "DRAFT" | "CONFIRMED"; plan: { canvas: { ratio: string; slice_count: number; slice_ratio: string }; style: { key: string; name: string; keywords: string[] }; copy: { headline: string; subheadline: string; store_name: string; price: string }; frames: DesignFrame[]; guardrails: string[] } };
type GenerationTask = { id: string; status: "PENDING" | "RUNNING" | "NEEDS_USER" | "SUCCEEDED" | "FAILED_FINAL"; progress: number; result: { long_image?: string; slices?: string[]; clean_long_image?: string; clean_slices?: string[]; provider?: string; model?: string }; error: { code: string; message: string } | null };
type ProjectInfo = { id: string; name: string; status: string };

const icons: Record<IconName, ReactNode> = {
  spark: <><path d="m12 3 1.2 3.8L17 8l-3.8 1.2L12 13l-1.2-3.8L7 8l3.8-1.2L12 3Z"/><path d="m5 13 .8 2.2L8 16l-2.2.8L5 19l-.8-2.2L2 16l2.2-.8L5 13Z"/></>,
  folder: <><path d="M3.5 6.5h6l1.7 2h9.3v9.5a2 2 0 0 1-2 2h-15v-13.5Z"/><path d="M3.5 9h17"/></>,
  image: <><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m5.5 18 4.5-4 3 2.5 2.5-3 3 4.5"/></>,
  book: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v16H6.5A2.5 2.5 0 0 0 4 21.5v-16Z"/><path d="M20 5.5A2.5 2.5 0 0 0 17.5 3H13v16h4.5a2.5 2.5 0 0 1 2.5 2.5v-16Z"/></>,
  history: <><path d="M4 12a8 8 0 1 0 2.3-5.7L4 8.5"/><path d="M4 4v4.5h4.5M12 8v5l3 2"/></>,
  menu: <path d="M4 7h16M4 12h16M4 17h16"/>, close: <path d="m6 6 12 12M18 6 6 18"/>, plus: <path d="M12 5v14M5 12h14"/>,
  arrow: <><path d="M5 12h14M14 7l5 5-5 5"/></>, check: <path d="m5 12 4 4L19 6"/>,
  store: <><path d="M4 10v10h16V10M3 10l2-6h14l2 6"/><path d="M8 20v-6h8v6M3 10c0 2 3 2 4.5 0 1.5 2 4.5 2 6 0 1.5 2 4.5 2 6 0 1.5 2 4.5 2 4.5 0"/></>,
  upload: <><path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 15v4h16v-4"/></>, chat: <><path d="M4 5h16v11H9l-5 4V5Z"/><path d="M8 9h8M8 12h5"/></>,
  help: <><circle cx="12" cy="12" r="9"/><path d="M9.7 9a2.4 2.4 0 1 1 3.1 2.3c-.8.3-.8 1-.8 1.7M12 17h.01"/></>, user: <><circle cx="12" cy="8" r="3"/><path d="M5 21a7 7 0 0 1 14 0"/></>,
  pause: <><path d="M9 6v12M15 6v12"/></>, play: <path d="m9 6 9 6-9 6V6Z"/>, retry: <><path d="M20 7v5h-5"/><path d="M19 12a7 7 0 1 0-2 5"/></>,
};

function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return <svg aria-hidden="true" className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{icons[name]}</svg>;
}

function BrandMark({ className = "" }: { className?: string }) {
  return <svg aria-hidden="true" className={`brandSymbol ${className}`.trim()} viewBox="0 0 92 48" fill="none">
    <path d="M2 6 18 14v6h-4v4h4v18L2 34V6Z" fill="currentColor" />
    <path d="m20 14 16-8v28l-16 8V24h4v-4h-4v-6Z" fill="currentColor" />
    <path d="m39 6 16 8v28l-16-8V6Z" fill="#7557FF" />
    <path d="m58 14 16-8v14h-4v4h4v10l-16 8V27h4v-4h-4v-9Z" fill="currentColor" />
    <path d="m76 6 14 8v28l-14-8V24h4v-4h-4V6Z" fill="currentColor" />
  </svg>;
}

function BrandLogo({ onActivate }: { onActivate: () => void }) {
  return <a className="brand" href="#workspace" aria-label="团绘AI 首页" onClick={onActivate}>
    <BrandMark />
    <span className="brandWordmark"><strong>团绘AI</strong><small>TUANHUI AI</small></span>
  </a>;
}

function Sidebar({ open, onClose, projectName, activeView, onNavigate }: { open: boolean; onClose: () => void; projectName: string; activeView: WorkspaceView; onNavigate: (view: WorkspaceView) => void }) {
  return <><button className={`sidebarScrim ${open ? "isOpen" : ""}`} aria-label="关闭导航" onClick={onClose} /><aside className={`sidebar ${open ? "isOpen" : ""}`} aria-label="主导航">
    <div className="brandRow"><BrandLogo onActivate={() => onNavigate("oneclick")} /><button className="iconButton mobileOnly" aria-label="关闭导航" onClick={onClose}><Icon name="close" /></button></div>
    <nav className="primaryNav" aria-label="主导航"><button className={`navItem ${activeView === "oneclick" ? "active" : ""}`} type="button" aria-current={activeView === "oneclick" ? "page" : undefined} onClick={() => onNavigate("oneclick")}><Icon name="image" /><span>一键生图</span><span className="navBadge">NEW</span></button><button className={`navItem ${activeView === "professional" ? "active" : ""}`} type="button" aria-current={activeView === "professional" ? "page" : undefined} onClick={() => onNavigate("professional")}><Icon name="book" /><span>专业创作</span></button><button className="navItem" type="button" disabled title="装修全案将在后续付费版本开放"><Icon name="chat" /><span>装修全案</span></button><div className="navDivider" /><a className="navItem" href="/projects"><Icon name="folder" /><span>我的项目</span></a><button className={`navItem ${activeView === "library" ? "active" : ""}`} type="button" aria-current={activeView === "library" ? "page" : undefined} onClick={() => onNavigate("library")}><Icon name="image" /><span>素材库</span></button></nav>
    <div className="navDivider" /><section className="historySection" aria-labelledby="history-title"><div className="sectionTitle"><span id="history-title">创作历史</span><Icon name="history" size={17} /></div>{projectName ? <button className="historyItem" type="button" onClick={() => { const id = new URLSearchParams(window.location.search).get("project"); window.location.assign(id ? `/projects?project=${encodeURIComponent(id)}` : "/projects"); }}><span className="historyThumb"><Icon name="store" size={18} /></span><span><b>{projectName}</b><small>查看项目与创作记录</small></span></button> : <p className="emptyHistory">创建门店后，当前项目会显示在这里。</p>}</section>
    <div className="sidebarFooter"><span className="avatar"><Icon name="user" size={17} /></span><span><b>测试用户</b><small>团绘AI 内测</small></span><a className="iconButton" aria-label="查看使用说明" href="#guide"><Icon name="help" /></a></div>
  </aside></>;
}

function StepTabs({ active, maxStep, onSelect }: { active: Step; maxStep: Step; onSelect: (step: Step) => void }) {
  const creationMode = active >= 5;
  const items = creationMode ? [{ step: 5 as Step, label: "确认设计方案" }, { step: 6 as Step, label: "生成与下载" }] : ["门店信息", "门店素材", "菜品素材", "确认事实"].map((label, index) => ({ step: (index + 1) as Step, label }));
  return <div className="modeTabs" aria-label={creationMode ? "设计生成步骤" : "资料采集步骤"}>{items.map(({ step, label }, index) => <button type="button" key={label} className={active === step ? "active" : ""} aria-current={active === step ? "step" : undefined} disabled={step > maxStep} onClick={() => onSelect(step)}><span>{index + 1}</span>{label}</button>)}</div>;
}

function WorkflowInputFrame({ label, children, action, meta, error = false, className = "" }: { label: string; children: ReactNode; action: ReactNode; meta?: ReactNode; error?: boolean; className?: string }) {
  return <div className={`workflowField ${className}`}>
    <div className="workflowFieldLabel">{label}</div>
    <div className={`workflowInputFrame ${error ? "hasError" : ""}`}>
      <div className="workflowInputContent">{children}</div>
      <div className="workflowInputAction">{action}</div>
    </div>
    {meta && <div className="workflowInputMeta">{meta}</div>}
  </div>;
}

function CreateStep({ busy, initialName = "", locked = false, onSubmit }: { busy: boolean; initialName?: string; locked?: boolean; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  const categoryMenuRef = useRef<HTMLDetailsElement>(null);
  const [storeName, setStoreName] = useState(initialName);
  const [nameError, setNameError] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    if (!storeName.trim()) {
      event.preventDefault();
      setNameError("请先填写门店名称");
      return;
    }
    setNameError("");
    onSubmit(event);
  }

  return <div className="stepBody createStep"><div className="stepIcon"><Icon name="store" size={27} /></div><div className="stepCopy"><span className="stepKicker">门店项目</span><h2>今天要为哪家店创作？</h2><p>填写门店名称并选择分类，先建立这次设计任务。</p></div><form className="projectForm" noValidate onSubmit={handleSubmit}><input type="hidden" name="industry" value="餐饮" /><WorkflowInputFrame label="门店名称" error={Boolean(nameError)} action={<div className="createActions"><details className="inlineCategory" ref={categoryMenuRef}><summary aria-label="选择门店类型"><span><small>门店类型</small><strong>餐饮美食</strong></span><i aria-hidden="true" /></summary><div className="categoryMenu" role="listbox" aria-label="门店类型"><button type="button" role="option" aria-selected="true" onClick={() => categoryMenuRef.current?.removeAttribute("open")}><span>餐饮美食<small>当前可用</small></span><Icon name="check" size={15} /></button><button type="button" role="option" aria-selected="false" disabled><span>休闲娱乐<small>暂未开放</small></span></button><button type="button" role="option" aria-selected="false" disabled><span>丽人健身<small>暂未开放</small></span></button></div></details><button className="primaryButton" disabled={busy}>{busy ? "正在处理…" : <>{locked ? "继续下一步" : "创建项目"} <Icon name="arrow" size={18} /></>}</button></div>} meta={<div className="formMeta"><span><Icon name="check" size={15} /> 抖音 + 美团</span><span><Icon name="check" size={15} /> 创建项目不消耗 Token</span></div>}><input className="workflowTextInput" id="project-name" name="name" value={storeName} maxLength={120} placeholder="例如：山城酸菜鱼" autoComplete="organization" disabled={locked} aria-invalid={Boolean(nameError)} aria-describedby={nameError ? "project-name-error" : undefined} onChange={(event) => { setStoreName(event.target.value); if (nameError) setNameError(""); }} /></WorkflowInputFrame>{nameError && <small id="project-name-error" className="fieldError" role="alert">{nameError}</small>}</form></div>;
}

type PendingUpload = { id: string; file: File; previewUrl: string; role: string; subcategory: string; priority: number; isHero: boolean; status?: "reading" | "ready" };
type ConversationIntakePayload = { name: string; brief: string; storeItems: PendingUpload[]; dishItems: PendingUpload[] };

function parseConversationBrief(brief: string): Record<string, string> {
  const patterns: Record<string, RegExp> = {
    positioning: /(?:门店定位|定位|主营)\s*[：:]\s*([^\n]+)/i,
    hero_item: /(?:主推菜品或套餐|主推菜品|主推套餐|主推内容|主推)\s*[：:]\s*([^\n]+)/i,
    hero_price: /(?:真实价格|套餐价格|价格|售价)\s*[：:]\s*([^\n]+)/i,
    selling_points: /(?:真实卖点|核心卖点|卖点|特色)\s*[：:]\s*([^\n]+)/i,
  };
  return Object.fromEntries(Object.entries(patterns).flatMap(([field, pattern]) => { const value = brief.match(pattern)?.[1]?.trim(); return value ? [[field, value]] : []; }));
}

function SavedAssetCards({ assets, mode, library = false }: { assets: Asset[]; mode: LibraryTab; library?: boolean }) {
  if (!assets.length) return <div className={`emptyState ${library ? "libraryEmpty" : ""}`}><span className="emptyIcon"><Icon name={mode === "store" ? "store" : "image"} /></span><div><strong>{mode === "store" ? "还没有店铺素材" : "还没有菜品或菜单素材"}</strong><p>{library ? "素材保存后会自动出现在这里。" : "选择图片并点击“确认保存，下一步”。"}</p></div></div>;
  return <div className={library ? "libraryGrid" : "assetGrid"}>{assets.map((asset) => <article className="assetCard" key={asset.id}>{asset.preview_path ? <div className="assetThumb"><Image src={apiUrl(asset.preview_path)} alt={`${mode === "store" ? "店铺" : "菜品或菜单"}素材：${asset.original_name}`} fill unoptimized sizes={library ? "180px" : "88px"} /></div> : <span className="assetIcon"><Icon name={mode === "store" ? "store" : "image"} /></span>}<div className="assetCardBody"><small title={asset.original_name}>{asset.original_name}</small></div></article>)}</div>;
}

function AssetLibrary({ assets, activeTab, onTabChange, onBack }: { assets: Asset[]; activeTab: LibraryTab; onTabChange: (tab: LibraryTab) => void; onBack: () => void }) {
  const storeAssets = assets.filter((item) => STORE_ASSET_ROLES.includes(item.semantic_role));
  const dishAssets = assets.filter((item) => DISH_ASSET_ROLES.includes(item.semantic_role));
  const visibleAssets = activeTab === "store" ? storeAssets : dishAssets;
  return <section className="libraryWorkbench" aria-labelledby="library-title">
    <header className="libraryHeader"><div><span className="stepKicker">素材管理</span><h1 id="library-title">素材库</h1><p>已保存的图片统一放在这里，按用途分为两个模块。</p></div><button className="secondaryButton backButton" type="button" onClick={onBack}><Icon name="arrow" size={16} />返回创作</button></header>
    <div className="libraryTabs" role="tablist" aria-label="素材分类"><button id="store-assets-tab" type="button" role="tab" aria-selected={activeTab === "store"} aria-controls="asset-library-panel" className={activeTab === "store" ? "active" : ""} onClick={() => onTabChange("store")}><Icon name="store" size={18} /><span><b>店铺素材</b><small>门头、环境、Logo</small></span><em>{storeAssets.length}</em></button><button id="dish-assets-tab" type="button" role="tab" aria-selected={activeTab === "dish"} aria-controls="asset-library-panel" className={activeTab === "dish" ? "active" : ""} onClick={() => onTabChange("dish")}><Icon name="image" size={18} /><span><b>菜品、菜单</b><small>菜单、招牌菜、普通菜品</small></span><em>{dishAssets.length}</em></button></div>
    <section className="libraryPanel" id="asset-library-panel" role="tabpanel" aria-labelledby={activeTab === "store" ? "store-assets-tab" : "dish-assets-tab"}><div className="libraryPanelHeader"><div><h2>{activeTab === "store" ? "店铺素材" : "菜品、菜单"}</h2><p>{activeTab === "store" ? "用于识别门店名称、品牌和空间风格。" : "用于整理菜单信息、招牌菜与视觉卖点。"}</p></div><span>{visibleAssets.length} 项</span></div><SavedAssetCards assets={visibleAssets} mode={activeTab} library /></section>
  </section>;
}

function UploadStep({ mode, assets, busy, onUploadBatch, onAnalyze, onContinue, onOpenLibrary }: { mode: "store" | "dish"; assets: Asset[]; busy: boolean; onUploadBatch: (items: PendingUpload[]) => Promise<boolean>; onAnalyze: (useAI: boolean) => void; onContinue: () => void; onOpenLibrary: () => void }) {
  const defaultRole = mode === "store" ? "storefront" : "dish";
  const storeAssets = assets.filter((item) => STORE_ASSET_ROLES.includes(item.semantic_role));
  const dishAssets = assets.filter((item) => DISH_ASSET_ROLES.includes(item.semantic_role));
  const visibleAssets = mode === "store" ? storeAssets : dishAssets;
  const currentReady = visibleAssets.length > 0;
  const [pendingUploads, setPendingUploads] = useState<PendingUpload[]>([]);
  const pendingRef = useRef<PendingUpload[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { pendingRef.current = pendingUploads; }, [pendingUploads]);
  useEffect(() => () => { pendingRef.current.forEach((item) => URL.revokeObjectURL(item.previewUrl)); }, []);

  function chooseFiles(event: ChangeEvent<HTMLInputElement>) {
    const remaining = Math.max(0, 20 - pendingUploads.length);
    const files = Array.from(event.target.files ?? []).slice(0, remaining);
    const additions = files.map((file, index) => {
      return { id: `${Date.now()}-${index}-${file.name}`, file, previewUrl: URL.createObjectURL(file), role: defaultRole, subcategory: "", priority: 100, isHero: false };
    });
    setPendingUploads((current) => [...current, ...additions]);
    event.target.value = "";
  }

  function removePending(id: string) {
    setPendingUploads((current) => { const removed = current.find((item) => item.id === id); if (removed) URL.revokeObjectURL(removed.previewUrl); return current.filter((item) => item.id !== id); });
  }

  async function saveAndContinue() {
    if (pendingUploads.length) {
      if (!await onUploadBatch(pendingUploads)) return;
      pendingUploads.forEach((item) => URL.revokeObjectURL(item.previewUrl));
      setPendingUploads([]);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } else if (!currentReady) {
      return;
    }
    if (mode === "store") onContinue(); else onAnalyze(false);
  }

  return <div className="stepBody uploadStep">
    <div className="uploadHeader"><div><span className="stepKicker">{mode === "store" ? "门店素材" : "菜品素材"}</span><h2>{mode === "store" ? "上传门店相关图片" : "上传菜单与菜品图片"}</h2><p>{mode === "store" ? "门头、环境和 Logo 可以一起上传，系统统一归入门店素材。" : "菜单、招牌菜和普通菜品可以一起上传，系统统一归入菜品素材。"}</p></div></div>
    <section className="uploadComposer unifiedComposer" aria-busy={busy}>
      <WorkflowInputFrame label={mode === "store" ? "门店素材" : "菜品素材"} action={<button type="button" className="primaryButton composerSaveButton" disabled={(!pendingUploads.length && !currentReady) || busy} onClick={saveAndContinue}>{busy ? "正在保存…" : <>{currentReady && !pendingUploads.length ? "进入下一步" : mode === "store" ? "确认保存，下一步" : "确认保存，进入确认事实"}<Icon name="arrow" size={17} /></>}</button>} meta={<><div className="composerStatus" aria-live="polite"><span className={currentReady ? "saved" : "waiting"}><Icon name={currentReady ? "check" : mode === "store" ? "store" : "image"} size={16} /></span><div><strong>{mode === "store" ? currentReady ? `门店素材已上传 ${visibleAssets.length} 张` : "门店素材待上传" : currentReady ? `菜品素材已上传 ${visibleAssets.length} 张` : "菜品素材待上传"}</strong><small>{pendingUploads.length ? `另有 ${pendingUploads.length} 张已选择，确认保存后计入已上传` : mode === "store" ? visibleAssets.length < 3 ? "建议补充到 3 张以上左、中、右角度的门头图片" : "门头素材已较完整，可继续补充环境或 Logo" : "建议包含菜单、招牌菜和菜品近景图片"}</small></div></div><button type="button" className="libraryMiniButton" onClick={onOpenLibrary} aria-label="打开素材库"><Icon name="folder" size={15} />素材库</button></>}>
        <div className="inlineUploadContent">
          {pendingUploads.map((item, index) => <article className="inlineAsset" key={item.id}><div className="inlineAssetThumb"><Image src={item.previewUrl} alt={`待上传图片 ${index + 1}：${item.file.name}`} fill unoptimized sizes="64px" /><button type="button" aria-label={`移除 ${item.file.name}`} onClick={() => removePending(item.id)}><Icon name="close" size={11} /></button></div></article>)}
          <label className={`inlineChooseButton ${pendingUploads.length ? "compact" : ""}`} htmlFor={`asset-files-${mode}`}><span className="inlineChooseIcon"><Icon name="plus" size={18} /></span><span><strong>{pendingUploads.length ? "继续添加" : "选择图片"}</strong><small>{pendingUploads.length ? `已选 ${pendingUploads.length} 张` : mode === "store" ? "门头、环境、Logo" : "菜单、招牌菜、普通菜品"}</small></span></label>
        </div>
      </WorkflowInputFrame><input ref={fileInputRef} className="visuallyHiddenFile" id={`asset-files-${mode}`} type="file" accept="image/png,image/jpeg,image/webp" multiple onChange={chooseFiles} />
    </section>
    <div className="assetSection"><div className="subheading"><div><strong>已上传{mode === "store" ? "门店" : "菜品"}素材</strong><small>这里出现图片即代表已保存</small></div><span>{visibleAssets.length} 项</span></div><SavedAssetCards assets={visibleAssets} mode={mode} /></div>
  </div>;
}

function FactsStep({ coverage, busy, onSubmit, onConfirm, onSelectStore, factText }: { coverage: Coverage | null; busy: boolean; onSubmit: (event: FormEvent<HTMLFormElement>) => void; onConfirm: () => void; onSelectStore: (name: string) => void; factText: (key: string) => string }) {
  const [questionIndex, setQuestionIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [answerError, setAnswerError] = useState("");

  if (!coverage) return <div className="stepBody waitingStep"><span className="loadingOrb"><Icon name="chat" size={25} /></span><h2>正在准备需要确认的信息</h2><p>系统会先整理缺失项，不会把不确定内容写成事实。</p></div>;
  const storeCandidates = (coverage.facts.detected_store_name_candidates as StoreNameCandidate[] | undefined) ?? []; const storeNeedsConfirmation = Boolean(coverage.facts.detected_store_name_needs_confirmation); const menuProducts = (coverage.facts.products as MenuProduct[] | undefined) ?? [];
  const questionCount = coverage.questions.length;
  const currentQuestion = coverage.questions[Math.min(questionIndex, Math.max(questionCount - 1, 0))];

  function handleQuestionSubmit(event: FormEvent<HTMLFormElement>) {
    if (!currentQuestion) return;
    if (!String(answers[currentQuestion.field] ?? "").trim()) {
      event.preventDefault();
      setAnswerError("请先填写这一项");
      return;
    }
    setAnswerError("");
    if (questionIndex < questionCount - 1) {
      event.preventDefault();
      setQuestionIndex((current) => current + 1);
      return;
    }
    onSubmit(event);
  }

  const factSummary = <div className="inlineFactSummary"><span><small>门店名称</small><b>{factText("store_name")}</b></span><span><small>门店定位</small><b>{factText("positioning")}</b></span><span><small>主推内容</small><b>{factText("hero_item")}</b></span><span><small>核心卖点</small><b>{factText("selling_points")}</b></span></div>;

  return <div className="stepBody factsStep">
    <div className="uploadHeader"><div><span className="stepKicker">事实确认</span><h2>只确认生成必须使用的信息</h2><p>每次只处理一个问题；确认后的店名、价格和卖点才会进入设计。</p></div></div>
    {storeNeedsConfirmation && storeCandidates.length > 1 && <div className="dialogueBlock"><p>门头图片中出现多家店，请先选择本次要制作的门店。</p><div className="candidateList">{storeCandidates.map((candidate) => <button key={`${candidate.name}-${candidate.region}`} type="button" disabled={busy} onClick={() => onSelectStore(candidate.name)}><span><b>{candidate.name}</b><small>{candidate.region || "区域未识别"} · {candidate.evidence}</small></span><span>{Math.round(candidate.confidence * 100)}%</span></button>)}</div></div>}
    {coverage.questions.length > 0 && currentQuestion ? <form className="questionFlow unifiedQuestionFlow" noValidate onSubmit={handleQuestionSubmit}>
      {coverage.questions.map((question, index) => index === questionIndex ? null : <input key={question.field} type="hidden" name={question.field} value={answers[question.field] ?? ""} />)}
      <WorkflowInputFrame label="确认事实" error={Boolean(answerError)} action={<button className="primaryButton factActionButton" disabled={busy}>{busy ? "正在保存…" : <>{questionIndex === coverage.questions.length - 1 ? "完成确认" : "保存并继续"}<Icon name="arrow" size={17} /></>}</button>} meta={<><div className="questionProgress"><span>问题 {questionIndex + 1} / {coverage.questions.length}</span><div aria-hidden="true">{coverage.questions.map((question, index) => <i key={question.field} className={index <= questionIndex ? "active" : ""} />)}</div></div>{questionIndex > 0 && <button className="questionBack" type="button" onClick={() => { setQuestionIndex((current) => current - 1); setAnswerError(""); }}>返回上一项</button>}</>}>
        <div className="workflowQuestion"><label htmlFor={`fact-answer-${currentQuestion.field}`}>{currentQuestion.question}</label><input id={`fact-answer-${currentQuestion.field}`} name={currentQuestion.field} value={answers[currentQuestion.field] ?? ""} placeholder="输入准确答案" aria-invalid={Boolean(answerError)} onChange={(event) => { setAnswers((current) => ({ ...current, [currentQuestion.field]: event.target.value })); if (answerError) setAnswerError(""); }} />{answerError && <small className="fieldError" role="alert">{answerError}</small>}</div>
      </WorkflowInputFrame>
    </form> : <WorkflowInputFrame label="确认事实" action={<button className="primaryButton factActionButton" type="button" disabled={!coverage.ready_for_confirmation || busy} onClick={onConfirm}><Icon name="check" size={16} />确认并锁定</button>} meta={<span className="factReadyHint">V{coverage.fact_version} · 信息已齐，可以锁定</span>}><div className="workflowReady"><Icon name="check" size={20} /><div><strong>核心信息已补齐</strong><p>请在下方快速核对事实摘要。</p></div></div></WorkflowInputFrame>}
    <details className="factSummaryDisclosure" open><summary>事实摘要</summary>{factSummary}{menuProducts.length > 0 && <details className="menuDisclosure"><summary>已识别 {menuProducts.length} 项菜单内容</summary><div className="menuPreview">{menuProducts.slice(0, 5).map((product, index) => <div key={`${product.name}-${index}`}><span>{product.name}</span><b>{product.price_original ?? "未识别"}</b></div>)}{menuProducts.length > 5 && <small>另有 {menuProducts.length - 5} 项</small>}</div></details>}</details>
  </div>;
}

function ConversationIntake({ projectName, assets, busy, onSubmit }: { projectName: string; assets: Asset[]; busy: boolean; onSubmit: (payload: ConversationIntakePayload) => Promise<boolean> }) {
  const [name, setName] = useState(projectName);
  const [brief, setBrief] = useState("");
  const [storeItems, setStoreItems] = useState<PendingUpload[]>([]);
  const [dishItems, setDishItems] = useState<PendingUpload[]>([]);
  const [error, setError] = useState("");
  const storeInputRef = useRef<HTMLInputElement>(null);
  const dishInputRef = useRef<HTMLInputElement>(null);
  const categoryMenuRef = useRef<HTMLDetailsElement>(null);
  const pendingRef = useRef<PendingUpload[]>([]);
  const allPending = [...storeItems, ...dishItems];
  const savedStoreCount = assets.filter((asset) => STORE_ASSET_ROLES.includes(asset.semantic_role)).length;
  const savedDishCount = assets.filter((asset) => DISH_ASSET_ROLES.includes(asset.semantic_role)).length;

  useEffect(() => { pendingRef.current = allPending; });
  useEffect(() => () => { pendingRef.current.forEach((item) => URL.revokeObjectURL(item.previewUrl)); }, []);

  function chooseFiles(event: ChangeEvent<HTMLInputElement>, kind: "store" | "dish") {
    const current = kind === "store" ? storeItems : dishItems;
    const files = Array.from(event.target.files ?? []).slice(0, Math.max(0, 20 - current.length));
    const additions = files.map((file, index) => ({ id: `${kind}-${Date.now()}-${index}-${file.name}`, file, previewUrl: URL.createObjectURL(file), role: kind === "store" ? "storefront" : "dish", subcategory: "", priority: 100, isHero: false }));
    if (kind === "store") setStoreItems((items) => [...items, ...additions]); else setDishItems((items) => [...items, ...additions]);
    event.target.value = "";
  }

  function removeFile(id: string, kind: "store" | "dish") {
    const update = (items: PendingUpload[]) => { const removed = items.find((item) => item.id === id); if (removed) URL.revokeObjectURL(removed.previewUrl); return items.filter((item) => item.id !== id); };
    if (kind === "store") setStoreItems(update); else setDishItems(update);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) { setError("请填写门店名称"); return; }
    if (!brief.trim()) { setError("请在输入框里写明门店定位、主推内容、价格和真实卖点"); return; }
    if (!savedStoreCount && !storeItems.length) { setError("请添加至少一张门店素材"); return; }
    if (!savedDishCount && !dishItems.length) { setError("请添加至少一张菜品或菜单素材"); return; }
    setError("");
    const saved = await onSubmit({ name: name.trim(), brief: brief.trim(), storeItems, dishItems });
    if (saved) { allPending.forEach((item) => URL.revokeObjectURL(item.previewUrl)); setStoreItems([]); setDishItems([]); }
  }

  const attachmentGroup = (kind: "store" | "dish", items: PendingUpload[], savedCount: number) => <div className="conversationAttachmentGroup"><button className="conversationAttachmentButton" type="button" disabled={busy} onClick={() => (kind === "store" ? storeInputRef : dishInputRef).current?.click()}><Icon name={kind === "store" ? "store" : "image"} size={17} /><span>{kind === "store" ? "门店素材" : "菜品素材"}</span><em>{savedCount + items.length || "+"}</em></button>{items.map((item, index) => <span className="conversationThumb" key={item.id}><Image src={item.previewUrl} alt={`${kind === "store" ? "门店" : "菜品"}待上传图片 ${index + 1}`} fill unoptimized sizes="42px" /><button type="button" aria-label={`移除 ${item.file.name}`} onClick={() => removeFile(item.id, kind)}><Icon name="close" size={10} /></button></span>)}</div>;

  return <form className="singleConversationComposer" noValidate onSubmit={submit}>
    <label className="conversationNameField"><span>门店名称</span><input value={name} maxLength={120} autoComplete="organization" placeholder="例如：山城酸菜鱼" disabled={Boolean(projectName) || busy} onChange={(event) => setName(event.target.value)} /></label>
    <label className="conversationBriefField"><span className="srOnly">本次创作需求</span><textarea value={brief} maxLength={800} disabled={busy} placeholder="描述你想要的团购设计，并补充真实信息。例如：门店定位是川渝江湖菜；主推酸菜鱼双人餐；真实价格 99 元；真实卖点是活鱼现做、酸香开胃。" onChange={(event) => setBrief(event.target.value)} /></label>
    {allPending.length > 0 && <div className="conversationPreviewStrip" aria-label="已选择素材预览">{attachmentGroup("store", storeItems, savedStoreCount)}{attachmentGroup("dish", dishItems, savedDishCount)}</div>}
    <div className="conversationComposerFooter"><div className="conversationTools">{!allPending.length && <>{attachmentGroup("store", storeItems, savedStoreCount)}{attachmentGroup("dish", dishItems, savedDishCount)}</>}<details className="conversationCategory" ref={categoryMenuRef}><summary aria-label="选择门店类型"><span><small>门店类型</small><b>餐饮美食</b></span><i aria-hidden="true" /></summary><div className="conversationCategoryMenu" role="listbox" aria-label="门店类型"><button type="button" role="option" aria-selected="true" onClick={() => categoryMenuRef.current?.removeAttribute("open")}><span><b>餐饮美食</b><small>当前可用</small></span><Icon name="check" size={15} /></button><button type="button" role="option" aria-selected="false" disabled><span><b>休闲娱乐</b><small>暂未开放</small></span></button><button type="button" role="option" aria-selected="false" disabled><span><b>丽人健身</b><small>暂未开放</small></span></button></div></details></div><button className="conversationSubmit" type="submit" aria-label={busy ? "正在整理资料" : "提交全部资料"} title={busy ? "正在整理资料" : "提交全部资料"} disabled={busy}>{busy ? <span className="submitBusy">整理中</span> : <Icon name="arrow" size={19} />}</button></div>
    <input ref={storeInputRef} className="visuallyHiddenFile" type="file" accept="image/png,image/jpeg,image/webp" multiple onChange={(event) => chooseFiles(event, "store")} />
    <input ref={dishInputRef} className="visuallyHiddenFile" type="file" accept="image/png,image/jpeg,image/webp" multiple onChange={(event) => chooseFiles(event, "dish")} />
    {error && <p className="conversationFormError" role="alert"><Icon name="close" size={15} />{error}</p>}
  </form>;
}

function CreationDiscovery() {
  return <><section className="creationSuggestions" aria-labelledby="suggestion-title"><header><h2 id="suggestion-title">推荐能力</h2><span>全部</span></header><div><article><span className="suggestionIcon"><Icon name="image" size={16} /></span><b>团购首页五图</b><small>20:3 长图排版</small><Icon name="arrow" size={14} /></article><article><span className="suggestionIcon"><Icon name="spark" size={16} /></span><b>Logo 设计</b><small>品牌标识与单体图形</small><Icon name="arrow" size={14} /></article><article><span className="suggestionIcon"><Icon name="book" size={16} /></span><b>品牌介绍图</b><small>门店故事与品牌卖点</small><Icon name="arrow" size={14} /></article></div></section><section className="creationHighlights" aria-labelledby="highlight-title"><h2 id="highlight-title">亮点功能</h2><div><article className="highlightFive"><span>20:3</span><div className="fiveStrip">{[1,2,3,4,5].map((item) => <i key={item} />)}</div><h3>团购首页五图</h3><p>一张长画布设计，自动裁切五张 4:3 图片</p></article><article className="highlightLogo"><span className="logoSketch"><i /><i /><i /></span><h3>Logo 设计</h3><p>根据门店名称与定位生成品牌标识</p></article><article className="highlightBrand"><span className="brandPoster"><i /><b>BRAND</b></span><h3>品牌介绍图</h3><p>整合品牌故事、特色菜品和真实卖点</p></article><article className="highlightPlan"><span className="planSketch"><i /><i /><i /></span><h3>营销方案</h3><p>围绕团购卖点规划内容与活动表达</p></article></div></section></>;
}

const QUICK_OPTIONS = {
  model: ["千问（默认）", "豆包（失败兜底）"],
  style: ["智能匹配", "食欲冲击", "品牌质感", "烟火市井", "清爽简约"],
  layout: ["内容均衡", "爆款主图", "品牌叙事", "套餐对比", "单品聚焦", "场景沉浸"],
  template: ["经典五图", "主菜聚焦", "门店故事", "到店转化", "套餐促销", "新品上市", "节日营销", "品牌升级"],
};

type QuickMenuKey = "add" | "model" | "style" | "layout" | "template" | "preference";

function QuickSelectMenu({ menuKey, label, value, options, openMenu, onOpenMenu, onSelect }: { menuKey: QuickMenuKey; label: string; value: string; options: string[]; openMenu: QuickMenuKey | null; onOpenMenu: (key: QuickMenuKey | null) => void; onSelect: (value: string) => void }) {
  const open = openMenu === menuKey;
  return <div className={`quickDropdown ${open ? "isOpen" : ""}`}>
    <button type="button" className="quickDropdownTrigger" aria-haspopup="listbox" aria-expanded={open} onClick={() => onOpenMenu(open ? null : menuKey)}><span><small>{label}</small><b>{value}</b></span><i aria-hidden="true" /></button>
    {open && <div className="quickDropdownMenu" role="listbox" aria-label={label}>{options.map((option) => <button key={option} type="button" role="option" aria-selected={option === value} className={option === value ? "active" : ""} onClick={() => { onSelect(option); onOpenMenu(null); }}><span>{option}</span>{option === value && <Icon name="check" size={15} />}</button>)}</div>}
  </div>;
}

function QuickCreationHome({ mode, projectId, projectName, assets, coverage, generationTask, busy, message, messageTone, onSubmit, onOpenOneClick, onOpenProfessional, onOpenLibrary, intakeSeed, onPrepareAssets }: { mode: CreationView; projectId: string; projectName: string; assets: Asset[]; coverage: Coverage | null; generationTask: GenerationTask | null; designPlan: DesignPlan | null; busy: boolean; message: string; messageTone: "info" | "success" | "error"; onSubmit: (payload: ConversationIntakePayload) => Promise<boolean>; onSubmitFacts: (event: FormEvent<HTMLFormElement>) => void; onConfirmAndGenerate: (style: string, model: string) => void; onGenerateExisting: () => void; onOpenOneClick: () => void; onOpenProfessional: () => void; onOpenLibrary: (tab: LibraryTab) => void; onPause: () => void; intakeSeed?: IntakeSeed | null; onPrepareAssets?: (items: PendingUpload[]) => Promise<Asset[]> }) {
  const [brief, setBrief] = useState("");
  const [outputType, setOutputType] = useState("five_panel");
  const [deliveryTypes, setDeliveryTypes] = useState<string[]>(DEFAULT_DELIVERIES);
  const [sessionStarted, setSessionStarted] = useState(false);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (projectId && params.get("compose") !== "1") setSessionStarted(true);
  }, [projectId]);
  const [generationActive, setGenerationActive] = useState(false);
  const authorized = useRef(false);
  const canAutoGenerate = useCallback(() => authorized.current, []);
  const handleGenerationActive = useCallback((active: boolean) => { setGenerationActive(active); if (!active) authorized.current = false; }, []);
  const consentRef = useRef<HTMLDialogElement>(null);
  const simpleFormRef = useRef<HTMLFormElement>(null);
  const [storeItems, setStoreItems] = useState<PendingUpload[]>([]);
  const [dishItems, setDishItems] = useState<PendingUpload[]>([]);
  const intakeController = useRef<IntakeController>(null);
  const promptRef = useRef<HTMLTextAreaElement>(null);
  const [replyField, setReplyField] = useState<string | null>(null);
  const [replyBackup, setReplyBackup] = useState("");
  const [conversationText, setConversationText] = useState("");
  const [conversationTarget, setConversationTarget] = useState<HTMLDivElement | null>(null);
  const [assetDialog, setAssetDialog] = useState<"all" | "store" | "dish" | null>(null);
  const [excluded, setExcluded] = useState<string[]>([]);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [restoredSelection, setRestoredSelection] = useState<string[] | null>(null);
  const [model, setModel] = useState(QUICK_OPTIONS.model[0]);
  const [style, setStyle] = useState(QUICK_OPTIONS.style[0]);
  const [layout, setLayout] = useState(QUICK_OPTIONS.layout[0]);
  const [template, setTemplate] = useState(QUICK_OPTIONS.template[0]);
  const [canvasMode, setCanvasMode] = useState(true);
  const [openMenu, setOpenMenu] = useState<QuickMenuKey | null>(null);
  const [error, setError] = useState("");
  const toolbarRef = useRef<HTMLDivElement>(null);
  const storeInputRef = useRef<HTMLInputElement>(null);
  const dishInputRef = useRef<HTMLInputElement>(null);
  const pendingRef = useRef<PendingUpload[]>([]);
  const readingTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const savedDishCount = assets.filter((asset) => DISH_ASSET_ROLES.includes(asset.semantic_role)).length;

  useEffect(() => { pendingRef.current = [...storeItems, ...dishItems]; });
  useEffect(() => () => {
    pendingRef.current.forEach((item) => URL.revokeObjectURL(item.previewUrl));
    readingTimersRef.current.forEach((timer) => clearTimeout(timer));
  }, []);
  useEffect(() => {
    function closeMenus(event: PointerEvent) { if (toolbarRef.current && !toolbarRef.current.contains(event.target as Node)) setOpenMenu(null); }
    function closeOnEscape(event: KeyboardEvent) { if (event.key === "Escape" && !document.querySelector(".referenceImageDialog[open]")) { setOpenMenu(null); setAssetDialog(null); } }
    document.addEventListener("pointerdown", closeMenus);
    document.addEventListener("keydown", closeOnEscape);
    return () => { document.removeEventListener("pointerdown", closeMenus); document.removeEventListener("keydown", closeOnEscape); };
  }, []);

  function chooseFiles(event: ChangeEvent<HTMLInputElement>, kind: "store" | "dish") {
    const current = kind === "store" ? storeItems : dishItems;
    const files = Array.from(event.target.files ?? []).slice(0, Math.max(0, 20 - current.length));
    const additions = files.map((file, index) => ({ id: `quick-${kind}-${Date.now()}-${index}-${file.name}`, file, previewUrl: URL.createObjectURL(file), role: kind === "store" ? "storefront" : "dish", subcategory: "", priority: 100, isHero: false, status: "reading" as const }));
    if (kind === "store") setStoreItems((items) => [...items, ...additions]); else setDishItems((items) => [...items, ...additions]);
    additions.forEach((addition, index) => {
      const timer = setTimeout(() => {
        const markReady = (items: PendingUpload[]) => items.map((item) => item.id === addition.id ? { ...item, status: "ready" as const } : item);
        if (kind === "store") setStoreItems(markReady); else setDishItems(markReady);
      }, 420 + index * 90);
      readingTimersRef.current.push(timer);
    });
    event.target.value = "";
  }

  function removeFile(id: string, kind: "store" | "dish") {
    const update = (items: PendingUpload[]) => { const removed = items.find((item) => item.id === id); if (removed) URL.revokeObjectURL(removed.previewUrl); return items.filter((item) => item.id !== id); };
    if (kind === "store") setStoreItems(update); else setDishItems(update);
  }

  function detectedName() {
    if (projectName.trim()) return projectName.trim();
    return brief.match(/(?:门店名称|店名|门店)\s*[：:]\s*([^；;，,。\n]+)/)?.[1]?.trim() ?? "";
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mode === "oneclick" && intakeController.current) { await intakeController.current.revise(); return; }
    const name = detectedName();
    if (!brief.trim() && (mode === "professional" || (!savedDishCount && !dishItems.length && !storeItems.length))) { setError("上传素材，或说说你想做什么"); return; }
    if (mode === "professional" && !name) { setError("请在文字中写明“门店名称：×××”"); return; }
    if (mode === "professional" && !savedDishCount && !dishItems.length) { setError("请添加至少一张菜品或菜单素材"); return; }
    setError("");
    const saved = await onSubmit({ name: name || "店铺五图项目", brief: mode === "oneclick" ? brief.trim() : `${brief.trim()}\n视觉风格：${style}\n排版布局：${layout}\n模板：${template}\n模型：${model}`, storeItems, dishItems });
    if (saved) { [...storeItems, ...dishItems].forEach((item) => URL.revokeObjectURL(item.previewUrl)); setStoreItems([]); setDishItems([]); }
  }

  const localAssets = [...storeItems.map((item) => ({ ...item, kind: "store" as const })), ...dishItems.map((item) => ({ ...item, kind: "dish" as const }))];
  const visibleDialogItems = localAssets.filter((item) => assetDialog === "all" || item.kind === assetDialog);
  const savedReferenceAssets = assets.flatMap((asset) => {
    const kind = STORE_ASSET_ROLES.includes(asset.semantic_role) ? "store" as const : DISH_ASSET_ROLES.includes(asset.semantic_role) ? "dish" as const : null;
    return kind && asset.preview_path ? [{ asset, kind }] : [];
  });
  const visibleSavedAssets = savedReferenceAssets.filter((item) => assetDialog === "all" || item.kind === assetDialog);

  const selectedSaved = savedReferenceAssets.filter(item => !excluded.includes(item.asset.id) && (!restoredSelection || restoredSelection.includes(item.asset.id)));
  const assetGroup = (kind: "store" | "dish") => {
    const pending = localAssets.filter((item) => item.kind === kind);
    const saved = savedReferenceAssets.filter((item) => item.kind === kind && !excluded.includes(item.asset.id) && (!restoredSelection || restoredSelection.includes(item.asset.id)));
    return <>
        {saved.map(({ asset }) => <ReferenceThumbnail key={asset.id} src={apiUrl(asset.preview_path!)} name={asset.original_name} onRemove={mode === "oneclick" ? () => setExcluded(ids => [...ids, asset.id]) : undefined} />)}
        {pending.map((item) => <ReferenceThumbnail key={item.id} src={item.previewUrl} name={item.file.name} reading={item.status === "reading"} onRemove={() => removeFile(item.id, kind)} />)}
    </>;
  };
  const storeGroup = <ReferenceCategory label="门店" count={storeItems.length + selectedSaved.filter((item) => item.kind === "store").length} onAdd={() => storeInputRef.current?.click()}>{assetGroup("store")}</ReferenceCategory>;
  const dishGroup = <ReferenceCategory label="菜品·菜单" count={dishItems.length + selectedSaved.filter((item) => item.kind === "dish").length} onAdd={() => dishInputRef.current?.click()}>{assetGroup("dish")}</ReferenceCategory>;


  const reviewPanel = mode === "oneclick" && projectId && <M1Review key={projectId} projectId={projectId} seed={intakeSeed ?? null}
      autoGenerate={canAutoGenerate} onGenerationActive={handleGenerationActive} controller={intakeController} target={conversationTarget}
      draft={{ outputType, deliveryTypes, text: [conversationText, brief].filter(Boolean).join("\n"), assetIds: selectedSaved.map(({asset}) => asset.id), pending: localAssets.length > 0, replyField,
        style: ({ "品牌质感": "brand", "烟火市井": "street", "清爽简约": "minimal" } as Record<string,string>)[style] ?? "appetite",
        provider: model.includes("豆包") ? "doubao" : "qwen" }}
      onReply={field => { if (field === "illustration") setBrief("使用AI示意图"); promptRef.current?.focus({ preventScroll: true }); }}
      onBusy={setReviewBusy}
      onRestore={snapshot => {
        setOutputType(snapshot.output_type || "five_panel");
        setDeliveryTypes(snapshot.delivery_types || DEFAULT_DELIVERIES);
        setConversationText(snapshot.text); setBrief("");
        setReplyField(null);
        setStyle(({ brand: "品牌质感", street: "烟火市井", minimal: "清爽简约" } as Record<string, string>)[snapshot.style] ?? QUICK_OPTIONS.style[0]);
        setModel(snapshot.provider === "doubao" ? "豆包" : QUICK_OPTIONS.model[0]);
        setRestoredSelection(snapshot.assets.map(a => a.id));
      }}
      onAssets={() => setAssetDialog("all")}
      prepare={async () => {
        const pending = [...storeItems, ...dishItems];
        const all = pending.length && onPrepareAssets ? await onPrepareAssets(pending) : assets;
        const newIds = all.filter(a => !assets.some(old => old.id === a.id)).map(a => a.id);
        pending.forEach(a => URL.revokeObjectURL(a.previewUrl)); setStoreItems([]); setDishItems([]);
        if (restoredSelection) setRestoredSelection(ids => [...(ids ?? []), ...newIds]);
        return { outputType, deliveryTypes, text: brief, replyField: null, chat: true, useAi: Boolean(brief.trim()), assetIds: all.filter(a => !excluded.includes(a.id) && (!restoredSelection || restoredSelection.includes(a.id) || newIds.includes(a.id))).map(a => a.id),
          style: ({ "品牌质感": "brand", "烟火市井": "street", "清爽简约": "minimal" } as Record<string, string>)[style] ?? "appetite",
          provider: model.includes("豆包") ? "doubao" : "qwen" };
      }} />;
  const workbench = sessionStarted || Boolean(intakeSeed || conversationText || generationTask);
  if (mode === "oneclick") return <section className={`oneclickStudio ${workbench ? "isWorking" : "isWelcome"}`} aria-label="一键生图工作区">
    <header className="studioHeader"><span title={projectId ? projectName : undefined}>{projectId ? projectName || "正在整理项目名称…" : "从一个想法，开始门店设计"}</span><div><button type="button" onClick={() => setAssetDialog(assetDialog ? null : "all")}>素材与设置</button><a href={projectId ? `/?project=${projectId}&compose=1` : "/"}>新建创作</a></div></header>
    <div className="studioWelcome" hidden={workbench}>
      <div className="creationTypeTabs" aria-label="创作模式"><button type="button" onClick={onOpenProfessional}>创作</button><button type="button" className="active" aria-current="page" onClick={onOpenOneClick}>一键生图</button><button type="button" onClick={() => { setOutputType("full_plan"); setDeliveryTypes(DEFAULT_DELIVERIES); promptRef.current?.focus(); }}>全案设计</button></div>
      <h1>今天，想为门店做什么图？</h1><p>说一句想法，或放几张照片。设计交给团绘。</p>
    </div>
    <div ref={setConversationTarget} className="studioMessages" role="region" aria-label="创作消息" tabIndex={0} hidden={!workbench}>
      {busy && !reviewBusy && <p role="status">正在保存本次资料…</p>}
    </div>
    <form ref={simpleFormRef} className="studioComposer" onSubmit={event => {
      event.preventDefault();
      if (generationActive) { void intakeController.current?.pause(); return; }
      if (!brief.trim() && !localAssets.length && !selectedSaved.length) { setError("想做什么图？说个品类，或放张照片就行。"); promptRef.current?.focus(); return; }
      if (!authorized.current) { consentRef.current?.showModal(); return; }
      setSessionStarted(true); void submit(event);
    }} aria-busy={busy || reviewBusy}>
      <div className="studioInputRow">
        <StudioPhotoStack photos={[...selectedSaved.map(({asset}) => ({id: asset.id, src: apiUrl(asset.preview_path!)})), ...localAssets.map(item => ({id: item.id, src: item.previewUrl}))]} disabled={busy || reviewBusy} onAdd={() => dishInputRef.current?.click()}>{assetGroup("store")}{assetGroup("dish")}</StudioPhotoStack>
        <label className="studioInput"><span className="srOnly">创作需求</span><textarea ref={promptRef} value={brief} disabled={busy || reviewBusy} maxLength={8000} rows={3} placeholder={workbench ? "接着说，或者告诉我哪里想改。" : "想做什么图？说一句想法，或添加几张参考照片。"} onChange={e => { setBrief(e.target.value); setError(""); }} /></label>
      </div>
      <footer className="studioToolbar"><button type="button" onClick={() => setAssetDialog(assetDialog ? null : "all")} aria-expanded={!!assetDialog}>{OUTPUT_NAMES[outputType]} · {style === "智能匹配" ? "自动风格" : style}</button><button className="studioPrimary" type="submit" disabled={busy || reviewBusy}>{generationActive ? "停止生成" : busy || reviewBusy ? "正在理解…" : workbench ? "发送" : "开始生成"}</button></footer>
      <p className="studioPolicy">无实拍可做 AI 示意图；门头仅用于识别，不放进成品。</p>
      {(error || messageTone === "error") && <p className="studioHint" role="alert">{error || message}</p>}
    </form>
    {assetDialog && <section className="studioSettings" aria-label="素材与设置"><header><h2>素材与设置</h2><button type="button" onClick={() => setAssetDialog(null)}>收起</button></header><p>门头、菜单仅用于识别；请选择真实菜品照片用于成品。</p><div className="studioSettingsActions"><button type="button" onClick={() => storeInputRef.current?.click()}>添加门头参考</button><button type="button" onClick={() => dishInputRef.current?.click()}>添加菜品照片</button><button type="button" onClick={() => onOpenLibrary("store")}>打开素材库</button></div><label>图片类型<select value={outputType} onChange={e => { setOutputType(e.target.value); if(e.target.value === "full_plan") setDeliveryTypes(DEFAULT_DELIVERIES); }}>{Object.entries(OUTPUT_NAMES).map(([key,name]) => <option key={key} value={key}>{name}</option>)}</select></label>{outputType === "full_plan" && <fieldset><legend>全案包含的作品</legend>{Object.entries(OUTPUT_NAMES).filter(([key]) => key !== "full_plan").map(([key,name]) => <label key={key}><input type="checkbox" checked={deliveryTypes.includes(key)} onChange={e => setDeliveryTypes(items => e.target.checked ? [...items,key] : items.length > 1 ? items.filter(v => v !== key) : items)} />{name}</label>)}</fieldset>}<label>风格<select value={style} onChange={e => setStyle(e.target.value)}>{QUICK_OPTIONS.style.map(v => <option key={v}>{v}</option>)}</select></label><label>生图模型<select value={model} onChange={e => setModel(e.target.value)}>{QUICK_OPTIONS.model.map(v => <option key={v}>{v}</option>)}</select></label></section>}
    <input ref={storeInputRef} className="visuallyHiddenFile" type="file" accept="image/png,image/jpeg,image/webp" multiple onChange={e => chooseFiles(e,"store")} />
    <input ref={dishInputRef} className="visuallyHiddenFile" type="file" accept="image/png,image/jpeg,image/webp" multiple onChange={e => chooseFiles(e,"dish")} />
    <dialog ref={consentRef} className="studioConsent"><h2>开始前，先让你知道费用</h2><p>本地内测使用你配置的模型账号，文字理解和图片生成按服务商实际用量计费。当前还没有接入积分报价，无法提前给出准确金额。</p><p>同意后，本次需求清楚即可生成所选图片；全案或多张详情页会先列出项目及调用次数，确认后才生成。不自动重试失败任务。</p><p>请确认拥有上传素材的使用权。没有照片时使用带标识的 AI 示意图。</p><div><button type="button" onClick={() => consentRef.current?.close()}>先不生成</button><button className="studioPrimary" type="button" onClick={() => { authorized.current = true; consentRef.current?.close(); simpleFormRef.current?.requestSubmit(); }}>同意并开始</button></div></dialog>
    {reviewPanel}
  </section>;

  return <section className="quickCreationHome" aria-labelledby="quick-creation-title">
    <header className="creationAgentHeader"><div className="creationTypeTabs" role="tablist" aria-label="创作模式"><button type="button" className={mode === "professional" ? "active" : ""} role="tab" aria-selected={mode === "professional"} onClick={onOpenProfessional}>创作</button><button type="button" className={false ? "active" : ""} role="tab" aria-selected={false} onClick={onOpenOneClick}>一键生图</button><button type="button" role="tab" aria-selected="false" disabled>全案设计</button></div><h1 id="quick-creation-title">让每家门店，都有一套会成交的设计</h1></header>
    <form className="quickComposer" noValidate onSubmit={submit} aria-busy={reviewBusy} inert={reviewBusy}>
      <div className="quickComposerBody hasReferences">
        <div className="quickAssetRail" aria-label="本次参考素材">
          {storeGroup}
          {dishGroup}
          <button type="button" className="quickAssetExpand" aria-label="展开参考素材" data-tooltip="展开参考素材" onClick={() => setAssetDialog("all")}><Icon name="arrow" size={14} /></button>
        </div>
        <div className="quickPrompt"><label htmlFor="creation-prompt" className="srOnly">创作需求</label>{replyField && <span className="intakeReplyLabel">正在补充：{({store_name:"店名",hero_item:"本次重点",hero_price:"价格"} as Record<string,string>)[replyField] ?? "信息"}<button type="button" onClick={() => { setBrief(replyBackup); setReplyField(null); }}>取消补充</button></span>}<textarea id="creation-prompt" ref={promptRef} value={brief} maxLength={8000} disabled={busy} placeholder={replyField ? "直接输入补充内容，发送后合并到本次需求" : "想做什么图？说一句，或者上传照片。"} onChange={(event) => setBrief(event.target.value)} /></div>
      </div>
      <div className="quickComposerToolbar" ref={toolbarRef}>
        <div className="quickToolbarStart">
          <div className={`quickAddMenu ${openMenu === "add" ? "isOpen" : ""}`}>
            <button type="button" className="quickIconButton" aria-label="快捷添加" aria-haspopup="menu" aria-expanded={openMenu === "add"} onClick={() => setOpenMenu(openMenu === "add" ? null : "add")}><Icon name="plus" size={22} /></button>
            {openMenu === "add" && <div className="quickAddPopover" role="menu">
              <button type="button" role="menuitem" onClick={() => { setOpenMenu(null); storeInputRef.current?.click(); }}><Icon name="upload" size={17} /><span><b>本地上传</b><small>添加门头、环境或 Logo 图片</small></span></button>
              <button type="button" role="menuitem" onClick={() => { setOpenMenu(null); onOpenLibrary("store"); }}><Icon name="folder" size={17} /><span><b>素材库</b><small>引用项目中已经保存的图片</small></span></button>
              <button type="button" role="menuitem" onClick={() => { setOpenMenu(null); dishInputRef.current?.click(); }}><Icon name="image" size={17} /><span><b>菜单与菜品</b><small>批量选择菜单、套餐和菜品图</small></span></button>
            </div>}
          </div>
          <button type="button" className="quickIconButton quickMentionButton" aria-label="管理参考素材" aria-haspopup="dialog" onClick={() => { setOpenMenu(null); setAssetDialog("all"); }}><span>@</span></button>
        </div>
        <div className="quickToolbarMenus"><QuickSelectMenu menuKey="model" label="模型" value={model} options={QUICK_OPTIONS.model} openMenu={openMenu} onOpenMenu={setOpenMenu} onSelect={setModel} /><QuickSelectMenu menuKey="style" label="风格" value={style} options={QUICK_OPTIONS.style} openMenu={openMenu} onOpenMenu={setOpenMenu} onSelect={setStyle} /><QuickSelectMenu menuKey="layout" label="布局" value={layout} options={QUICK_OPTIONS.layout} openMenu={openMenu} onOpenMenu={setOpenMenu} onSelect={setLayout} /><QuickSelectMenu menuKey="template" label="模板" value={template} options={QUICK_OPTIONS.template} openMenu={openMenu} onOpenMenu={setOpenMenu} onSelect={setTemplate} /><div className={`quickPreference ${openMenu === "preference" ? "isOpen" : ""}`}><button type="button" className="quickPreferenceTrigger" aria-haspopup="dialog" aria-expanded={openMenu === "preference"} onClick={() => setOpenMenu(openMenu === "preference" ? null : "preference")}><Icon name="spark" size={16} /><b>智能匹配</b><span>创作偏好</span><i aria-hidden="true" /></button>{openMenu === "preference" && <div className="quickPreferencePanel"><div className="preferenceTabs"><button className="active" type="button">图片偏好</button><button type="button">推理模型</button></div><section><div><small>输出画布</small><strong>20:3 团购五联长图</strong><p>生成后自动裁切为五张 4:3 图片</p></div><div className="ratioChoices"><button className="active" type="button">20:3</button><button type="button" disabled>1:1</button><button type="button" disabled>3:4</button></div></section></div>}</div></div>
        <div className="quickToolbarEnd"><button className={`canvasToggle ${canvasMode ? "active" : ""}`} type="button" aria-pressed={canvasMode} onClick={() => setCanvasMode((value) => !value)}><span aria-hidden="true" />画布</button><button className="quickSubmit" type="submit" disabled={busy} aria-label={busy ? "正在整理资料" : "提交创作需求"}>{busy ? <span>整理中</span> : <Icon name="arrow" size={20} />}</button></div>
      </div>
      {(error || messageTone === "error") && <p className="quickComposerError" role="alert"><Icon name="close" size={15} />{error || message}</p>}

    </form>
    {<div className={`conversationInlineStatus ${messageTone}`} role="status" aria-live="polite"><span>{messageTone === "success" ? <Icon name="check" size={15} /> : <Icon name="spark" size={15} />}</span><p>{message}</p></div>}
    {!(false && projectId) && !coverage && !generationTask && <CreationDiscovery />}
    <input ref={storeInputRef} className="visuallyHiddenFile" type="file" accept="image/png,image/jpeg,image/webp" multiple onChange={(event) => chooseFiles(event, "store")} /><input ref={dishInputRef} className="visuallyHiddenFile" type="file" accept="image/png,image/jpeg,image/webp" multiple onChange={(event) => chooseFiles(event, "dish")} />
    {assetDialog && <div className="referenceWorkspaceBackdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setAssetDialog(null); }}>
      <button className="referenceWorkspaceClose" type="button" onClick={() => setAssetDialog(null)}><kbd>ESC</kbd><span>关闭</span></button>
      <section className="referenceWorkspace" role="dialog" aria-modal="true" aria-labelledby="reference-workspace-title">
        <aside className="referenceAssetPanel">
          <h2 id="reference-workspace-title">参考素材</h2>
          <div className="referenceTabs" role="tablist" aria-label="素材分类"><button type="button" className={assetDialog === "all" ? "active" : ""} onClick={() => setAssetDialog("all")}>全部</button><button type="button" className={assetDialog === "store" ? "active" : ""} onClick={() => setAssetDialog("store")}>门店</button><button type="button" className={assetDialog === "dish" ? "active" : ""} onClick={() => setAssetDialog("dish")}>菜品·菜单</button></div>
          <div className="referenceAssetGrid">{(assetDialog === "all" || assetDialog === "store") && storeGroup}{(assetDialog === "all" || assetDialog === "dish") && dishGroup}</div>
          <span className="referenceCount">共 {visibleSavedAssets.length + visibleDialogItems.length} 张素材</span>
        </aside>
        <div className="referenceWorkspacePrompt"><p>菜品图用于成品；门头和菜单仅作参考。移除仅取消本次引用，不删除项目素材。</p>{(excluded.length > 0 || restoredSelection !== null) && <button type="button" onClick={() => { setExcluded([]); setRestoredSelection(null); }}>重新选入项目素材</button>}<div><button type="button" onClick={() => setAssetDialog(null)}>完成选择</button></div></div>
      </section>
    </div>}
  </section>;
}

function ConversationWorkbench({ projectName, message, messageTone, taskId, collectingFacts, onOpenOneClick, children }: { projectName: string; message: string; messageTone: "info" | "success" | "error"; taskId: string; collectingFacts: boolean; onOpenOneClick: () => void; children: ReactNode }) {
  return <section className="conversationHome" aria-labelledby="conversation-title">
    <header className="creationAgentHeader"><div className="creationTypeTabs" role="tablist" aria-label="创作模式"><button type="button" className="active" role="tab" aria-selected="true">创作</button><button type="button" role="tab" aria-selected="false" onClick={onOpenOneClick}>一键生图</button><button type="button" role="tab" aria-selected="false" disabled title="装修全案将在后续付费版本开放">全案设计</button></div><h1 id="conversation-title">让每家门店，都有一套会成交的设计</h1></header>
    <section className="conversationWorkbench" id="guide" aria-label="团绘店长对话工作台">
      <div className="conversationThread"><div className="conversationStage">{children}</div></div>
    </section>
    <div className={`conversationInlineStatus ${messageTone}`} role="status" aria-live="polite"><span>{messageTone === "success" ? <Icon name="check" size={15} /> : messageTone === "error" ? <Icon name="close" size={15} /> : <Icon name="spark" size={15} />}</span><p>{collectingFacts ? `${projectName || "当前门店"} · 资料留在当前对话中继续确认` : message}</p>{taskId && <small>任务 {taskId.slice(0, 8)}</small>}</div>
    {!collectingFacts && <CreationDiscovery />}
  </section>;
}

const DESIGN_STYLES = [
  { key: "appetite", name: "食欲冲击", hint: "菜品近景 · 鲜明色彩" },
  { key: "brand", name: "品牌质感", hint: "品牌主色 · 克制留白" },
  { key: "street", name: "烟火市井", hint: "真实门店 · 暖色氛围" },
  { key: "minimal", name: "清爽简约", hint: "信息聚焦 · 轻量排版" },
];

function DesignPlanStep({ designPlan, busy, onUpdate, onConfirm }: { designPlan: DesignPlan | null; busy: boolean; onUpdate: (style: string) => void; onConfirm: () => void }) {
  const styleMenuRef = useRef<HTMLDetailsElement>(null);
  const layoutMenuRef = useRef<HTMLDetailsElement>(null);
  const [selectedFrameIndex, setSelectedFrameIndex] = useState(1);
  if (!designPlan) return <div className="stepBody waitingStep"><span className="loadingOrb"><Icon name="spark" size={25} /></span><h2>正在整理五图设计方案</h2><p>这里只组合已确认的店名、价格、主推内容与卖点。</p></div>;
  const selectedFrame = designPlan.plan.frames.find((frame) => frame.index === selectedFrameIndex) ?? designPlan.plan.frames[0];
  return <div className="stepBody designPlanStep"><header className="designPlanHeader"><div><span className="stepKicker">五图设计方案</span><h2>先确认怎么画，再开始生图</h2><p>五屏在同一张 20:3 长图上设计，输出时准确裁成五张 4:3 图片。</p></div><span className="planVersion">方案 V{designPlan.version}</span></header>
    <section className="planCanvasSection" aria-labelledby="canvas-title"><div className="planCanvasToolbar"><div className="panelMiniTitle"><strong id="canvas-title">五屏内容</strong><small>20:3 长画布 · 虚线为 4:3 裁切位置</small></div><div className="canvasControls"><details className="planDropdown compact" ref={layoutMenuRef}><summary><span><small>排版</small><b>内容均衡</b></span><i aria-hidden="true" /></summary><div className="planDropdownMenu"><button type="button" className="active" onClick={() => layoutMenuRef.current?.removeAttribute("open")}><span><b>内容均衡</b><small>五屏信息均匀分配</small></span><Icon name="check" size={15} /></button><button type="button" disabled><span><b>爆款主图</b><small>模板库接入后开放</small></span></button><button type="button" disabled><span><b>品牌叙事</b><small>模板库接入后开放</small></span></button></div></details><details className="planDropdown compact" ref={styleMenuRef}><summary><span><small>风格</small><b>{designPlan.plan.style.name}</b></span><i aria-hidden="true" /></summary><div className="planDropdownMenu">{DESIGN_STYLES.map((style) => <button key={style.key} type="button" className={designPlan.plan.style.key === style.key ? "active" : ""} disabled={busy} onClick={() => { styleMenuRef.current?.removeAttribute("open"); onUpdate(style.key); }}><span><b>{style.name}</b><small>{style.hint}</small></span>{designPlan.plan.style.key === style.key && <Icon name="check" size={15} />}</button>)}</div></details></div></div><div className="planCanvasViewport"><div className={`planCanvas style-${designPlan.plan.style.key}`} aria-label="五屏排版方案画布">{designPlan.plan.frames.map((frame) => <button key={frame.index} type="button" className={selectedFrame?.index === frame.index ? "active" : ""} aria-pressed={selectedFrame?.index === frame.index} onClick={() => setSelectedFrameIndex(frame.index)}><span className="canvasFrameNumber">{String(frame.index).padStart(2, "0")}</span><span className="canvasFrameRole">{frame.role}</span><strong>{frame.headline}</strong><small>{frame.support}</small></button>)}</div></div><div className="canvasInspector"><span><small>当前查看</small><b>{String(selectedFrame?.index ?? 1).padStart(2, "0")} · {selectedFrame?.role}</b></span><p>{selectedFrame?.headline}<small>{selectedFrame?.support}</small></p><span className="canvasRatio">单屏 4:3</span></div></section>
    <details className="guardrailDisclosure"><summary>查看事实保护规则</summary><ul>{designPlan.plan.guardrails.map((item) => <li key={item}>{item}</li>)}</ul></details>
    <footer className="designPlanActions"><p><Icon name="check" size={16} />切换方案只更新预览；确认后才会解锁付费生图。</p><button className="primaryButton" type="button" disabled={busy} onClick={onConfirm}>{busy ? "正在确认…" : <>确认方案 <Icon name="arrow" size={17} /></>}</button></footer>
  </div>;
}

function GenerateStep({ projectId, designPlan, task, busy, onGenerate, onPause }: { projectId: string; designPlan: DesignPlan | null; task: GenerationTask | null; busy: boolean; onGenerate: () => void; onPause: () => void }) {
  const completed = task?.status === "SUCCEEDED" && task.result.long_image && task.result.slices?.length === 5;
  const generating = task?.status === "RUNNING" || task?.status === "PENDING";
  const paused = task?.status === "NEEDS_USER";
  const failed = task?.status === "FAILED_FINAL";
  return <div className="stepBody generateStep"><div className="generationIntro"><span className="generationIcon"><Icon name="image" size={25} /></span><div><span className="stepKicker">生成团购首页五图</span><h2>{completed ? "五图已经生成完成" : paused ? "本次生成已经暂停" : generating ? "正在生成五图" : "方案已锁定，准备生成长图"}</h2><p>{generating ? `正在处理视觉底图 · ${task.progress}%` : paused ? "已停止后续排版、裁切和备用模型调用。" : completed ? "作品已保留在项目中。可以下载，或继续下一次创作。" : "确认后开始生成，作品将保存在当前项目中。"}</p></div>{!completed && <button className={`primaryButton generationButton ${generating ? "pauseState" : ""}`} type="button" disabled={!generating && busy} onClick={generating ? onPause : onGenerate}>{generating ? <><Icon name="pause" size={17} />暂停</> : paused ? <><Icon name="play" size={17} />继续生成</> : failed ? <><Icon name="retry" size={17} />重新生成</> : <>开始生成 <Icon name="arrow" size={17} /></>}</button>}</div>
    {completed ? <div className="generationResults"><div className="resultActions"><a className="primaryButton" href={`/?project=${projectId}&compose=1`}>继续创作 <Icon name="arrow" size={16} /></a><a href={`/projects?project=${projectId}`}>返回项目</a><button type="button" onClick={() => window.location.assign(window.location.origin)}>新建项目</button></div><GenerationGallery projectId={projectId} taskId={task.id} longImage={task.result.long_image} slices={task.result.slices} cleanLongImage={task.result.clean_long_image} cleanSlices={task.result.clean_slices} /><p className="resultProvider">由 {task.result.provider === "qwen" ? "千问" : "豆包"} · {task.result.model} 生成视觉底图，文字由本地排版层写入。</p></div> : <><div className="generationCanvas"><div className="canvasPreview" aria-label="五联图画布预览">{designPlan?.plan.frames.map((frame) => <div key={frame.index}><span>{frame.index}</span><b>{frame.role}</b></div>)}</div><div className="generationMeta"><span>总图 20:3</span><span>五张 4:3</span><span>文字后置排版</span></div></div>{paused ? <div className="generationNotice paused"><Icon name="pause" size={18} /><div><strong>已暂停</strong><p>继续生成会重新调用模型，并在开始前再次确认费用。</p></div></div> : failed ? <div className="generationNotice error"><Icon name="close" size={18} /><div><strong>本次生成失败</strong><p>{task.error?.message || "请检查模型配置后重试。"}</p></div></div> : <div className="generationNotice"><Icon name="spark" size={18} /><div><strong>{generating ? "生成中可以随时暂停" : "生成前会再次确认"}</strong><p>{generating ? "暂停后不会继续排版、裁切或调用备用模型。" : "点击后才调用付费模型；生成完成会自动保存一张长图和五张裁切图。"}</p></div></div>}</>}
  </div>;
}

export default function Home() {
  const [intakeSeed, setIntakeSeed] = useState<IntakeSeed | null>(null);
  const [projectId, setProjectId] = useState(""); const [projectName, setProjectName] = useState(""); const [taskId, setTaskId] = useState(""); const [assets, setAssets] = useState<Asset[]>([]); const [coverage, setCoverage] = useState<Coverage | null>(null); const [designPlan, setDesignPlan] = useState<DesignPlan | null>(null); const [generationTask, setGenerationTask] = useState<GenerationTask | null>(null); const [message, setMessage] = useState("把门店资料和创作要求一次发给我。"); const [messageTone, setMessageTone] = useState<"info" | "success" | "error">("info"); const [busy, setBusy] = useState(false); const [activeStep, setActiveStep] = useState<Step>(1); const [activeView, setActiveView] = useState<WorkspaceView>("oneclick"); const [libraryTab, setLibraryTab] = useState<LibraryTab>("store"); const [sidebarOpen, setSidebarOpen] = useState(false); const libraryReturnView = useRef<CreationView>("oneclick");
  useEffect(() => { window.scrollTo({ top: 0, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); }, [activeStep, activeView]);
  useEffect(() => {
    const renamed = (event: Event) => {
      const detail = (event as CustomEvent<{projectId: string; name: string}>).detail;
      if (detail?.projectId === projectId && detail.name) setProjectName(detail.name);
    };
    window.addEventListener("tuanhui:project-renamed", renamed);
    return () => window.removeEventListener("tuanhui:project-renamed", renamed);
  }, [projectId]);
  useEffect(() => { const params = new URLSearchParams(window.location.search); const savedProjectId = params.get("project"); const savedTaskId = params.get("task"); if (!savedProjectId) return; void (async () => { setBusy(true); try { const [project, savedAssets] = await Promise.all([apiRequest<ProjectInfo>(`/projects/${savedProjectId}`), apiRequest<Asset[]>(`/projects/${savedProjectId}/assets`)]); setProjectId(project.id); setProjectName(project.name); setAssets(savedAssets); if (params.get("compose") === "1") { setActiveStep(1); setActiveView("oneclick"); notify("已保留项目素材，请填写这一次的新需求。", "success"); return; } if (params.get("creation")) { setActiveView("oneclick"); setActiveStep(1); return; } try { const plan = await apiRequest<DesignPlan>(`/projects/${savedProjectId}/design-plans/latest`); setDesignPlan(plan); setActiveStep(plan.status === "CONFIRMED" ? 6 : 5); } catch { setActiveStep(savedAssets.some((asset) => STORE_ASSET_ROLES.includes(asset.semantic_role)) ? 3 : 2); } if (savedTaskId) { const task = await apiRequest<GenerationTask>(`/tasks/${savedTaskId}`); setTaskId(task.id); setGenerationTask(task); setActiveStep(6); if (task.status === "PENDING" || task.status === "RUNNING") window.setTimeout(() => void pollGeneration(task.id), 700); } notify("已恢复上次的项目和生成状态。", "success"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(false); } })(); }, []);
  const hasStoreAssets = assets.some((asset) => STORE_ASSET_ROLES.includes(asset.semantic_role)); const maxStep: Step = designPlan?.status === "CONFIRMED" ? 6 : designPlan ? 5 : coverage || taskId ? 4 : hasStoreAssets ? 3 : projectId ? 2 : 1; const factText = (key: string) => Array.isArray(coverage?.facts[key]) ? (coverage?.facts[key] as string[]).join("、") : String(coverage?.facts[key] ?? "待确认");
  function notify(text: string, tone: "info" | "success" | "error" = "info") { setMessage(text); setMessageTone(tone); }
  async function createProject(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (projectId) { setActiveStep(2); notify("门店信息已保留，请继续上传门店素材。", "success"); return; } setBusy(true); const fd = new FormData(event.currentTarget); const name = String(fd.get("name") ?? "").trim(); const industry = String(fd.get("industry") ?? "餐饮"); try { const result = await apiRequest<{ project_id: string }>("/projects", jsonRequest("POST", { name, industry, platforms: ["douyin", "meituan"] })); window.history.replaceState({}, "", `?project=${result.project_id}`); setProjectId(result.project_id); setProjectName(name); setAssets([]); setCoverage(null); setDesignPlan(null); setGenerationTask(null); setActiveStep(2); notify("项目已创建，请先上传门店素材。", "success"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(false); } }
  async function refreshAssets(targetProjectId = projectId) { const latest = await apiRequest<Asset[]>(`/projects/${targetProjectId}/assets`); setAssets(latest); return latest; }
  async function persistUploads(items: PendingUpload[], targetProjectId: string) { let completed = 0; for (const item of items) { const fd = new FormData(); const assetType = item.role === "storefront" ? "storefront" : item.role === "menu" ? "menu" : DISH_ASSET_ROLES.includes(item.role) ? "product" : "other"; fd.append("file", item.file); fd.append("asset_type", assetType); fd.append("semantic_role", item.role); if (item.subcategory.trim()) fd.append("subcategory", item.subcategory.trim()); fd.append("priority", String(item.priority)); if (item.isHero) fd.append("is_hero", "true"); await apiRequest(`/projects/${targetProjectId}/assets`, { method: "POST", body: fd }); completed += 1; } return completed; }
  async function uploadBatch(items: PendingUpload[]): Promise<boolean> { if (!projectId || !items.length) return false; setBusy(true); let completed = 0; const groupName = items[0].role === "storefront" ? "门店" : "菜品"; try { completed = await persistUploads(items, projectId); await refreshAssets(projectId); notify(`已成功上传 ${completed} 张${groupName}素材。`, "success"); return true; } catch (error) { if (completed) await refreshAssets(projectId); notify(`${completed ? `已完成 ${completed} 张；` : ""}${(error as Error).message}`, "error"); return false; } finally { setBusy(false); } }
  async function analyze(useAI = false) { if (!projectId) return; if (useAI && !window.confirm("AI 将识别已上传图片并产生模型费用。确认继续吗？")) return; setBusy(true); try { const task = await apiRequest<{ task_id: string }>(`/projects/${projectId}/analysis-runs`, jsonRequest("POST", { use_ai: useAI })); setTaskId(task.task_id); setActiveStep(4); notify(useAI ? "正在调用 AI 识别素材，请稍候。" : "正在整理需要你确认的门店信息。", "info"); window.setTimeout(() => void loadCoverage(0), useAI ? 1000 : 150); } catch (error) { notify((error as Error).message, "error"); setBusy(false); } }
  async function loadCoverage(attempt = 0, targetProjectId = projectId) { try { const result = await apiRequest<Coverage>(`/projects/${targetProjectId}/coverage`); setCoverage(result); notify(result.ready_for_confirmation ? "核心信息已齐，请核对后锁定。" : "请补充下面的缺失信息，系统不会替你猜。", result.ready_for_confirmation ? "success" : "info"); setBusy(false); } catch (error) { if ((error as { code?: string }).code === "HTTP_409" && attempt < 8) { window.setTimeout(() => void loadCoverage(attempt + 1, targetProjectId), 250); return; } notify((error as Error).message, "error"); setBusy(false); } }
  async function loadConversationCoverage(targetProjectId: string, answers: Record<string, string>, attempt = 0) { try { let result = await apiRequest<Coverage>(`/projects/${targetProjectId}/coverage`); if (Object.keys(answers).length) { const clarified = await apiRequest<{ fact_version: number; facts: Facts; coverage: Coverage }>(`/projects/${targetProjectId}/clarifications`, jsonRequest("POST", { answers })); result = { ...clarified.coverage, fact_version: clarified.fact_version, facts: clarified.facts }; } setCoverage(result); setActiveStep(4); notify(result.ready_for_confirmation ? "资料已经整理完成，请核对后锁定事实。" : "资料已整理好，只需在当前对话补充缺失事实。", result.ready_for_confirmation ? "success" : "info"); setBusy(false); } catch (error) { if ((error as { code?: string }).code === "HTTP_409" && attempt < 8) { window.setTimeout(() => void loadConversationCoverage(targetProjectId, answers, attempt + 1), 250); return; } notify((error as Error).message, "error"); setBusy(false); } }
  async function submitAnswers(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setBusy(true); const fd = new FormData(event.currentTarget); const answers: Record<string, string> = {}; coverage?.questions.forEach((question) => { const value = String(fd.get(question.field) ?? "").trim(); if (value) answers[question.field] = value; }); try { const result = await apiRequest<{ fact_version: number; facts: Facts; coverage: Coverage }>(`/projects/${projectId}/clarifications`, jsonRequest("POST", { answers })); setCoverage({ ...result.coverage, fact_version: result.fact_version, facts: result.facts }); notify(result.coverage.ready_for_confirmation ? "信息已补齐，请核对并确认。" : "已保存，仍有少量信息需要补充。", result.coverage.ready_for_confirmation ? "success" : "info"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(false); } }
  async function confirm() { if (!coverage) return; setBusy(true); try { await apiRequest(`/projects/${projectId}/fact-versions/${coverage.fact_version}/confirm`, jsonRequest("POST", { confirmed: true })); const plan = await apiRequest<DesignPlan>(`/projects/${projectId}/design-plans`, jsonRequest("POST", { style: "appetite" })); setDesignPlan(plan); setActiveStep(5); notify("事实已锁定，五图方案已整理好，请确认风格与每屏内容。", "success"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(false); } }
  async function updatePlanStyle(style: string) { if (!designPlan) return; setBusy(true); try { const plan = await apiRequest<DesignPlan>(`/projects/${projectId}/design-plans/${designPlan.id}`, jsonRequest("PATCH", { style })); setDesignPlan(plan); notify(`已切换为${plan.plan.style.name}风格。`, "success"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(false); } }
  async function confirmPlan() { if (!designPlan) return; setBusy(true); try { const plan = await apiRequest<DesignPlan>(`/projects/${projectId}/design-plans/${designPlan.id}/confirm`, jsonRequest("POST", { confirmed: true })); setDesignPlan(plan); setActiveStep(6); notify("设计方案已锁定，生图任务已就绪。", "success"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(false); } }
  async function pollGeneration(id: string) { try { const task = await apiRequest<GenerationTask>(`/tasks/${id}`); setGenerationTask(task); if (task.status === "PENDING" || task.status === "RUNNING") { window.setTimeout(() => void pollGeneration(id), 1200); return; } setBusy(false); if (task.status === "SUCCEEDED") notify("长图与五张裁切图已生成，可以下载。", "success"); else if (task.status === "NEEDS_USER") notify("本次生成已经暂停，可以稍后继续。", "info"); else notify(task.error?.message || "本次生成失败，请检查模型配置。", "error"); } catch (error) { setBusy(false); notify((error as Error).message, "error"); } }
  async function startGeneration() { const restarting = generationTask?.status === "NEEDS_USER" || generationTask?.status === "FAILED_FINAL"; const confirmText = restarting ? "继续或重新生成会再次调用千问并产生一笔新的费用。确认继续吗？" : "即将调用千问图片生成模型并产生费用。确认开始生成吗？"; if (!designPlan || !window.confirm(confirmText)) return; setBusy(true); setGenerationTask(null); try { const result = await apiRequest<{ task_id: string }>(`/projects/${projectId}/generation-runs`, jsonRequest("POST", { provider: "qwen", allow_fallback: true })); window.history.replaceState({}, "", `?project=${projectId}&task=${result.task_id}`); setTaskId(result.task_id); setGenerationTask({ id: result.task_id, status: "PENDING", progress: 0, result: {}, error: null }); notify("千问正在生成无文字视觉底图，完成后会自动排版与裁切。", "info"); window.setTimeout(() => void pollGeneration(result.task_id), 700); } catch (error) { setBusy(false); notify((error as Error).message, "error"); } }
  async function confirmQuickAndGenerate(styleLabel: string, modelLabel: string) { if (!coverage?.ready_for_confirmation || !projectId) return; const provider = modelLabel.startsWith("豆包") ? "doubao" : "qwen"; if (!window.confirm(`确认门店事实并调用${provider === "qwen" ? "千问" : "豆包"}图片模型？本次操作会产生生成费用。`)) return; const styleMap: Record<string, string> = { "智能匹配": "appetite", "食欲冲击": "appetite", "品牌质感": "brand", "烟火市井": "street", "清爽简约": "minimal" }; setBusy(true); setGenerationTask(null); try { await apiRequest(`/projects/${projectId}/fact-versions/${coverage.fact_version}/confirm`, jsonRequest("POST", { confirmed: true })); const draft = await apiRequest<DesignPlan>(`/projects/${projectId}/design-plans`, jsonRequest("POST", { style: styleMap[styleLabel] || "appetite" })); const plan = await apiRequest<DesignPlan>(`/projects/${projectId}/design-plans/${draft.id}/confirm`, jsonRequest("POST", { confirmed: true })); setDesignPlan(plan); setActiveStep(6); const result = await apiRequest<{ task_id: string }>(`/projects/${projectId}/generation-runs`, jsonRequest("POST", { provider, allow_fallback: true })); window.history.replaceState({}, "", `?project=${projectId}&task=${result.task_id}`); setTaskId(result.task_id); setGenerationTask({ id: result.task_id, status: "PENDING", progress: 0, result: {}, error: null }); notify(`${provider === "qwen" ? "千问" : "豆包"}正在生成视觉底图，完成后会自动排版与裁切。`, "info"); window.setTimeout(() => void pollGeneration(result.task_id), 700); } catch (error) { setBusy(false); notify((error as Error).message, "error"); } }
  async function pauseGeneration() { if (!generationTask || !["PENDING", "RUNNING"].includes(generationTask.status)) return; try { const task = await apiRequest<GenerationTask>(`/tasks/${generationTask.id}/pause`, jsonRequest("POST", {})); setGenerationTask(task); setBusy(false); notify("已暂停；不会继续排版、裁切或调用备用模型。", "info"); } catch (error) { notify((error as Error).message, "error"); } }
  async function selectStoreName(name: string) { setBusy(true); try { await apiRequest(`/projects/${projectId}/fact-versions`, jsonRequest("POST", { store_name: name })); await loadCoverage(); notify(`已确认目标门店：${name}`, "success"); } catch (error) { notify((error as Error).message, "error"); setBusy(false); } }
  function navigate(view: WorkspaceView) { if (view === "oneclick" || view === "professional") libraryReturnView.current = view; setActiveView(view); setSidebarOpen(false); }
  function openLibrary(tab: LibraryTab) { if (activeView === "oneclick" || activeView === "professional") libraryReturnView.current = activeView; setLibraryTab(tab); navigate("library"); }
  async function submitConversationIntake(payload: ConversationIntakePayload): Promise<boolean> {
    setBusy(true); let targetProjectId = projectId;
    try {
      if (!targetProjectId) {
        const created = await apiRequest<{ project_id: string }>("/projects", jsonRequest("POST", { name: payload.name, industry: "餐饮", platforms: ["douyin", "meituan"] }));
        targetProjectId = created.project_id; setProjectId(targetProjectId); setProjectName(payload.name);
        window.history.replaceState({}, "", `?project=${targetProjectId}`);
      }
      if (payload.storeItems.length) await persistUploads(payload.storeItems, targetProjectId);
      if (payload.dishItems.length) await persistUploads(payload.dishItems, targetProjectId);
      const savedAssets = await apiRequest<Asset[]>(`/projects/${targetProjectId}/assets`); setAssets(savedAssets);
      if (activeView === "oneclick") {
        setCoverage(null); setDesignPlan(null); setGenerationTask(null);
        setIntakeSeed({ text: payload.brief, assetIds: savedAssets.map(a => a.id), nonce: crypto.randomUUID() });
        setBusy(false); notify("收到，我们就在这里接着聊。", "success"); return true;
      }
      const task = await apiRequest<{ task_id: string }>(`/projects/${targetProjectId}/analysis-runs`, jsonRequest("POST", { use_ai: false }));
      setTaskId(task.task_id); setActiveStep(4);
      window.setTimeout(() => void loadConversationCoverage(targetProjectId, parseConversationBrief(payload.brief)), 150);
      return true;
    } catch (error) { notify((error as Error).message, "error"); setBusy(false); return false; }
  }

  const activeStepContent = <>
    {activeStep === 1 && <CreateStep busy={busy} initialName={projectName} locked={Boolean(projectId)} onSubmit={createProject} />}
    {activeStep === 2 && <UploadStep mode="store" assets={assets} busy={busy} onUploadBatch={uploadBatch} onAnalyze={analyze} onContinue={() => setActiveStep(3)} onOpenLibrary={() => openLibrary("store")} />}
    {activeStep === 3 && <UploadStep mode="dish" assets={assets} busy={busy} onUploadBatch={uploadBatch} onAnalyze={analyze} onContinue={() => undefined} onOpenLibrary={() => openLibrary("dish")} />}
    {activeStep === 4 && <FactsStep key={coverage ? `${coverage.fact_version}-${coverage.questions.map((question) => question.field).join("|")}` : "loading"} coverage={coverage} busy={busy} onSubmit={submitAnswers} onConfirm={confirm} onSelectStore={selectStoreName} factText={factText} />}
    {activeStep === 5 && <DesignPlanStep designPlan={designPlan} busy={busy} onUpdate={updatePlanStyle} onConfirm={confirmPlan} />}
    {activeStep === 6 && <GenerateStep projectId={projectId} designPlan={designPlan} task={generationTask} busy={busy} onGenerate={startGeneration} onPause={pauseGeneration} />}
  </>;

  return <div className={`appShell ${activeView === "oneclick" ? "studioShell" : ""}`}>
    <a className="skipLink" href="#workspace">跳到主要内容</a>
    <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} projectName={projectName} activeView={activeView} onNavigate={navigate} />
    <main className="mainArea" id="workspace">
      <header className="topbar"><button className="iconButton menuButton" aria-label="打开导航" aria-expanded={sidebarOpen} onClick={() => setSidebarOpen(true)}><Icon name="menu" /></button><div className="announcement"><span>NEW</span><b>{activeView === "professional" ? "团绘AI 专业创作" : "团绘AI 一键生图首页"}</b><small>{activeView === "professional" ? "确认事实与设计方案后再生成" : "首页确认真实信息，直接成图"}</small></div><div className="topActions"><span className="tokenBadge"><i /> 内测 · 生图另计费</span><a className="helpButton" href="#guide"><Icon name="help" size={18} />帮助</a></div></header>
      <div className="contentWrap">
        {activeView === "library" ? <AssetLibrary assets={assets} activeTab={libraryTab} onTabChange={setLibraryTab} onBack={() => navigate(libraryReturnView.current)} /> : activeView === "oneclick" ? <QuickCreationHome intakeSeed={intakeSeed} onPrepareAssets={async items => { await persistUploads(items, projectId); const saved = await apiRequest<Asset[]>(`/projects/${projectId}/assets`); setAssets(saved); return saved; }} mode="oneclick" projectId={projectId} projectName={projectName} assets={assets} coverage={coverage} generationTask={generationTask} designPlan={designPlan} busy={busy} message={message} messageTone={messageTone} onSubmit={submitConversationIntake} onSubmitFacts={submitAnswers} onConfirmAndGenerate={confirmQuickAndGenerate} onGenerateExisting={startGeneration} onOpenOneClick={() => navigate("oneclick")} onOpenProfessional={() => navigate("professional")} onOpenLibrary={openLibrary} onPause={pauseGeneration} /> : activeStep <= 4 ? !coverage ? <QuickCreationHome mode="professional" projectId={projectId} projectName={projectName} assets={assets} coverage={null} generationTask={generationTask} designPlan={designPlan} busy={busy} message={message} messageTone={messageTone} onSubmit={submitConversationIntake} onSubmitFacts={submitAnswers} onConfirmAndGenerate={confirmQuickAndGenerate} onGenerateExisting={startGeneration} onOpenOneClick={() => navigate("oneclick")} onOpenProfessional={() => navigate("professional")} onOpenLibrary={openLibrary} onPause={pauseGeneration} /> : <ConversationWorkbench projectName={projectName} message={message} messageTone={messageTone} taskId={taskId} collectingFacts onOpenOneClick={() => navigate("oneclick")}><FactsStep key={`${coverage.fact_version}-${coverage.questions.map((question) => question.field).join("|")}`} coverage={coverage} busy={busy} onSubmit={submitAnswers} onConfirm={confirm} onSelectStore={selectStoreName} factText={factText} /></ConversationWorkbench> : <>
          <section className="workbench" aria-label={activeView === "professional" ? "专业门店资料采集工作台" : "五图创作工作台"}>
            <div className="workbenchTop"><div className="workflowBackSlot">{activeStep > 1 && <button className="workflowBackButton" type="button" aria-label="返回上一步" onClick={() => setActiveStep((activeStep - 1) as Step)}><Icon name="arrow" size={16} /><span>上一步</span></button>}</div><div className="workbenchLabel"><Icon name={activeStep === 1 ? "store" : activeStep === 4 ? "chat" : activeStep >= 5 ? "spark" : "upload"} size={18} /><span><b>{activeStep >= 5 ? "五图创作" : "门店视觉包"}</b><small>{projectName || "新建项目"}</small></span></div><StepTabs active={activeStep} maxStep={maxStep} onSelect={setActiveStep} /><div className="stepCounter">{activeStep >= 5 ? activeStep - 4 : activeStep} / {activeStep >= 5 ? 2 : 4}</div></div>
            {activeStepContent}
            <div className={`statusToast ${messageTone}`} role="status" aria-live="polite"><span>{messageTone === "success" ? <Icon name="check" size={17} /> : messageTone === "error" ? <Icon name="close" size={17} /> : <Icon name="spark" size={17} />}</span><p>{message}</p>{taskId && <small>任务 {taskId.slice(0, 8)}</small>}</div>
          </section>
        </>}

      </div>
    </main>
  </div>;
}
