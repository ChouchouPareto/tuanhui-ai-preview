"use client";

import Image from "next/image";
import { ChangeEvent, FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import { apiRequest, apiUrl, jsonRequest } from "../lib/api-client";
import { Asset, Coverage, Facts, MenuProduct, StoreNameCandidate } from "../features/store-intake/types";

type Step = 1 | 2 | 3 | 4;
type WorkspaceView = "create" | "library";
type LibraryTab = "store" | "dish";
type IconName = "spark" | "folder" | "image" | "book" | "history" | "menu" | "close" | "plus" | "arrow" | "check" | "store" | "upload" | "chat" | "help" | "user";

const STORE_ASSET_ROLES = ["storefront", "environment", "logo"];
const DISH_ASSET_ROLES = ["menu", "signature_dish", "dish"];

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
    <div className="brandRow"><BrandLogo onActivate={() => onNavigate("create")} /><button className="iconButton mobileOnly" aria-label="关闭导航" onClick={onClose}><Icon name="close" /></button></div>
    <nav className="primaryNav" aria-label="主导航"><button className={`navItem ${activeView === "create" ? "active" : ""}`} type="button" aria-current={activeView === "create" ? "page" : undefined} onClick={() => onNavigate("create")}><Icon name="spark" /><span>开始创作</span></button><button className="navItem" type="button" disabled title="项目列表将在后续接口接入后开放"><Icon name="folder" /><span>我的项目</span><span className="soon">待接入</span></button><button className={`navItem ${activeView === "library" ? "active" : ""}`} type="button" aria-current={activeView === "library" ? "page" : undefined} onClick={() => onNavigate("library")}><Icon name="image" /><span>素材库</span></button><a className="navItem" href="#guide" onClick={() => onNavigate("create")}><Icon name="book" /><span>使用说明</span></a></nav>
    <div className="navDivider" /><section className="historySection" aria-labelledby="history-title"><div className="sectionTitle"><span id="history-title">创作历史</span><Icon name="history" size={17} /></div>{projectName ? <button className="historyItem" type="button"><span className="historyThumb"><Icon name="store" size={18} /></span><span><b>{projectName}</b><small>资料采集中</small></span></button> : <p className="emptyHistory">创建门店后，当前项目会显示在这里。</p>}</section>
    <div className="sidebarFooter"><span className="avatar"><Icon name="user" size={17} /></span><span><b>测试用户</b><small>团绘AI 内测</small></span><a className="iconButton" aria-label="查看使用说明" href="#guide"><Icon name="help" /></a></div>
  </aside></>;
}

function StepTabs({ active, maxStep, onSelect }: { active: Step; maxStep: Step; onSelect: (step: Step) => void }) {
  return <div className="modeTabs" aria-label="创作步骤">{["门店信息", "上传门店素材", "上传菜品素材", "确认事实"].map((label, index) => { const step = (index + 1) as Step; return <button type="button" key={label} className={active === step ? "active" : ""} aria-current={active === step ? "step" : undefined} disabled={step > maxStep} onClick={() => onSelect(step)}><span>{step}</span>{label}</button>; })}</div>;
}

function CreateStep({ busy, onSubmit }: { busy: boolean; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  return <div className="stepBody createStep"><div className="stepIcon"><Icon name="store" size={27} /></div><div className="stepCopy"><span className="stepKicker">门店项目</span><h2>今天要为哪家店创作？</h2><p>填写门店名称并选择分类，先建立这次设计任务。</p></div><form className="projectForm" onSubmit={onSubmit}><label htmlFor="project-name">门店名称</label><div className="inputAction"><input id="project-name" name="name" required maxLength={120} placeholder="例如：山城酸菜鱼" autoComplete="organization" /><label className="inlineCategory" htmlFor="project-industry"><span>门店类型</span><select id="project-industry" name="industry" defaultValue="餐饮" aria-label="门店类型"><option value="餐饮">餐饮美食</option><option value="休闲娱乐" disabled>休闲娱乐（暂未开放）</option><option value="丽人健身" disabled>丽人健身（暂未开放）</option></select></label><button className="primaryButton" disabled={busy}>{busy ? "正在创建…" : <>创建项目 <Icon name="arrow" size={18} /></>}</button></div><div className="formMeta"><span><Icon name="check" size={15} /> 抖音 + 美团</span><span><Icon name="check" size={15} /> 创建项目不消耗 Token</span></div></form></div>;
}

type PendingUpload = { id: string; file: File; previewUrl: string; role: string; subcategory: string; priority: number; isHero: boolean };

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
    <div className="uploadHeader"><div><span className="stepKicker">{mode === "store" ? "门店素材" : "菜品素材"}</span><h2>{mode === "store" ? "上传门店相关图片" : "上传菜单与菜品图片"}</h2><p>{mode === "store" ? "门头、环境和 Logo 可以一起上传，系统统一归入门店素材。" : "菜单、招牌菜和普通菜品可以一起上传，系统统一归入菜品素材。"}</p><small className="uploadCompletionHint"><Icon name="check" size={14} />图片出现在“已上传素材”且顶部显示“已完成”，即上传成功。</small></div><div className="requirementPills"><span className={currentReady ? "done" : ""}><Icon name={currentReady ? "check" : mode === "store" ? "store" : "image"} size={15} />{mode === "store" ? "门店素材" : "菜品素材"}{currentReady ? "已完成" : "待上传"}</span></div></div>
    <section className="uploadComposer" aria-busy={busy}>
      <div className="composerHeading"><div><strong>待上传{mode === "store" ? "门店" : "菜品"}素材</strong><small>{pendingUploads.length ? `已选择 ${pendingUploads.length} 张，可继续添加或移除` : currentReady ? "素材已保存，可直接进入下一步" : "选择图片后在这里核对"}</small></div><button type="button" className="libraryMiniButton" onClick={onOpenLibrary} aria-label="打开素材库"><Icon name="folder" size={15} />素材库</button></div>
      <div className="uploadInputBar">
        <div className="inlineUploadContent">
          {pendingUploads.map((item, index) => <article className="inlineAsset" key={item.id}><div className="inlineAssetThumb"><Image src={item.previewUrl} alt={`待上传图片 ${index + 1}：${item.file.name}`} fill unoptimized sizes="64px" /><button type="button" aria-label={`移除 ${item.file.name}`} onClick={() => removePending(item.id)}><Icon name="close" size={11} /></button></div></article>)}
          <label className={`inlineChooseButton ${pendingUploads.length ? "compact" : ""}`} htmlFor={`asset-files-${mode}`}><span className="inlineChooseIcon"><Icon name="plus" size={18} /></span><span><strong>{pendingUploads.length ? "继续添加" : "选择图片"}</strong><small>{pendingUploads.length ? `已选 ${pendingUploads.length} 张` : mode === "store" ? "门头、环境、Logo" : "菜单、招牌菜、普通菜品"}</small></span></label>
        </div>
        <button type="button" className="primaryButton composerSaveButton" disabled={(!pendingUploads.length && !currentReady) || busy} onClick={saveAndContinue}>{busy ? "正在保存…" : <>{currentReady && !pendingUploads.length ? "进入下一步" : mode === "store" ? "确认保存，下一步" : "确认保存，进入确认事实"}<Icon name="arrow" size={17} /></>}</button>
        <input ref={fileInputRef} className="visuallyHiddenFile" id={`asset-files-${mode}`} type="file" accept="image/png,image/jpeg,image/webp" multiple onChange={chooseFiles} />
      </div>
    </section>
    <div className="assetSection"><div className="subheading"><div><strong>已上传{mode === "store" ? "门店" : "菜品"}素材</strong><small>这里出现图片即代表已保存</small></div><span>{visibleAssets.length} 项</span></div><SavedAssetCards assets={visibleAssets} mode={mode} /></div>
  </div>;
}

function FactsStep({ coverage, busy, onSubmit, onConfirm, onSelectStore, factText }: { coverage: Coverage | null; busy: boolean; onSubmit: (event: FormEvent<HTMLFormElement>) => void; onConfirm: () => void; onSelectStore: (name: string) => void; factText: (key: string) => string }) {
  if (!coverage) return <div className="stepBody waitingStep"><span className="loadingOrb"><Icon name="chat" size={25} /></span><h2>正在准备需要确认的信息</h2><p>系统会先整理缺失项，不会把不确定内容写成事实。</p></div>;
  const storeCandidates = (coverage.facts.detected_store_name_candidates as StoreNameCandidate[] | undefined) ?? []; const storeNeedsConfirmation = Boolean(coverage.facts.detected_store_name_needs_confirmation); const menuProducts = (coverage.facts.products as MenuProduct[] | undefined) ?? [];
  return <div className="stepBody factsStep"><div className="factsLayout"><section className="conversationPanel"><div className="panelTitle"><span className="assistantAvatar"><BrandMark /></span><div><strong>团绘助手</strong><small>{coverage.questions.length ? `还需要确认 ${coverage.questions.length} 项信息` : "核心信息已经齐全"}</small></div></div>
    {storeNeedsConfirmation && storeCandidates.length > 1 && <div className="dialogueBlock"><p>我在门头图中看到了多家店，请选择你要制作的目标门店。</p><div className="candidateList">{storeCandidates.map((candidate) => <button key={`${candidate.name}-${candidate.region}`} type="button" disabled={busy} onClick={() => onSelectStore(candidate.name)}><span><b>{candidate.name}</b><small>{candidate.region || "区域未识别"} · {candidate.evidence}</small></span><span>{Math.round(candidate.confidence * 100)}%</span></button>)}</div></div>}
    {coverage.questions.length > 0 ? <form className="questionForm" onSubmit={onSubmit}>{coverage.questions.map((question, index) => <label key={question.field}><span><i>{index + 1}</i>{question.question}</span><input name={question.field} required placeholder="请直接输入准确答案" /></label>)}<button className="primaryButton" disabled={busy}>{busy ? "正在提交…" : <>提交补充信息 <Icon name="arrow" size={18} /></>}</button></form> : <div className="readyMessage"><Icon name="check" size={20} /><div><strong>核心信息已补齐</strong><p>请在右侧核对事实卡，确认后将锁定本版本。</p></div></div>}
    </section><aside className="factCard"><div className="subheading"><strong>门店事实卡</strong><span>V{coverage.fact_version}</span></div><dl><div><dt>门店名称</dt><dd>{factText("store_name")}</dd></div><div><dt>门店定位</dt><dd>{factText("positioning")}</dd></div><div><dt>主推内容</dt><dd>{factText("hero_item")}</dd></div><div><dt>核心卖点</dt><dd>{factText("selling_points")}</dd></div><div><dt>表达视角</dt><dd>品牌官方</dd></div></dl>{menuProducts.length > 0 && <div className="menuPreview"><strong>菜单识别 · 价格待确认</strong>{menuProducts.slice(0, 5).map((product, index) => <div key={`${product.name}-${index}`}><span>{product.name}</span><b>{product.price_original ?? "未识别"}</b></div>)}{menuProducts.length > 5 && <small>另有 {menuProducts.length - 5} 项已保存在事实卡</small>}</div>}<button className="primaryButton fullWidth" type="button" disabled={!coverage.ready_for_confirmation || busy} onClick={onConfirm}><Icon name="check" size={18} />确认并锁定事实</button></aside></div></div>;
}

export default function Home() {
  const [projectId, setProjectId] = useState(""); const [projectName, setProjectName] = useState(""); const [taskId, setTaskId] = useState(""); const [assets, setAssets] = useState<Asset[]>([]); const [coverage, setCoverage] = useState<Coverage | null>(null); const [message, setMessage] = useState("准备好后，从创建门店开始。"); const [messageTone, setMessageTone] = useState<"info" | "success" | "error">("info"); const [busy, setBusy] = useState(false); const [activeStep, setActiveStep] = useState<Step>(1); const [activeView, setActiveView] = useState<WorkspaceView>("create"); const [libraryTab, setLibraryTab] = useState<LibraryTab>("store"); const [sidebarOpen, setSidebarOpen] = useState(false);
  useEffect(() => { window.scrollTo({ top: 0, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); }, [activeStep, activeView]);
  const hasStoreAssets = assets.some((asset) => STORE_ASSET_ROLES.includes(asset.semantic_role)); const maxStep: Step = coverage || taskId ? 4 : hasStoreAssets ? 3 : projectId ? 2 : 1; const factText = (key: string) => Array.isArray(coverage?.facts[key]) ? (coverage?.facts[key] as string[]).join("、") : String(coverage?.facts[key] ?? "待确认");
  function notify(text: string, tone: "info" | "success" | "error" = "info") { setMessage(text); setMessageTone(tone); }
  async function createProject(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setBusy(true); const fd = new FormData(event.currentTarget); const name = String(fd.get("name") ?? "").trim(); const industry = String(fd.get("industry") ?? "餐饮"); try { const result = await apiRequest<{ project_id: string }>("/projects", jsonRequest("POST", { name, industry, platforms: ["douyin", "meituan"] })); setProjectId(result.project_id); setProjectName(name); setAssets([]); setCoverage(null); setActiveView("create"); setActiveStep(2); notify("项目已创建，请先上传门店素材。", "success"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(false); } }
  async function refreshAssets() { setAssets(await apiRequest<Asset[]>(`/projects/${projectId}/assets`)); }
  async function uploadBatch(items: PendingUpload[]): Promise<boolean> { if (!projectId || !items.length) return false; setBusy(true); let completed = 0; const groupName = items[0].role === "storefront" ? "门店" : "菜品"; try { for (const item of items) { const fd = new FormData(); const assetType = item.role === "storefront" ? "storefront" : item.role === "menu" ? "menu" : DISH_ASSET_ROLES.includes(item.role) ? "product" : "other"; fd.append("file", item.file); fd.append("asset_type", assetType); fd.append("semantic_role", item.role); if (item.subcategory.trim()) fd.append("subcategory", item.subcategory.trim()); fd.append("priority", String(item.priority)); if (item.isHero) fd.append("is_hero", "true"); await apiRequest(`/projects/${projectId}/assets`, { method: "POST", body: fd }); completed += 1; } await refreshAssets(); notify(`已成功上传 ${completed} 张${groupName}素材。`, "success"); return true; } catch (error) { if (completed) await refreshAssets(); notify(`${completed ? `已完成 ${completed} 张；` : ""}${(error as Error).message}`, "error"); return false; } finally { setBusy(false); } }
  async function analyze(useAI = false) { if (!projectId) return; if (useAI && !window.confirm("AI 将识别已上传图片并产生模型费用。确认继续吗？")) return; setBusy(true); try { const task = await apiRequest<{ task_id: string }>(`/projects/${projectId}/analysis-runs`, jsonRequest("POST", { use_ai: useAI })); setTaskId(task.task_id); setActiveStep(4); notify(useAI ? "正在调用 AI 识别素材，请稍候。" : "正在整理需要你确认的门店信息。", "info"); window.setTimeout(() => void loadCoverage(0), useAI ? 1000 : 150); } catch (error) { notify((error as Error).message, "error"); setBusy(false); } }
  async function loadCoverage(attempt = 0) { try { const result = await apiRequest<Coverage>(`/projects/${projectId}/coverage`); setCoverage(result); notify(result.ready_for_confirmation ? "核心信息已齐，请核对后锁定。" : "请补充下面的缺失信息，系统不会替你猜。", result.ready_for_confirmation ? "success" : "info"); setBusy(false); } catch (error) { if ((error as { code?: string }).code === "HTTP_409" && attempt < 8) { window.setTimeout(() => void loadCoverage(attempt + 1), 250); return; } notify((error as Error).message, "error"); setBusy(false); } }
  async function submitAnswers(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setBusy(true); const fd = new FormData(event.currentTarget); const answers: Record<string, string> = {}; coverage?.questions.forEach((question) => { const value = String(fd.get(question.field) ?? "").trim(); if (value) answers[question.field] = value; }); try { const result = await apiRequest<{ fact_version: number; facts: Facts; coverage: Coverage }>(`/projects/${projectId}/clarifications`, jsonRequest("POST", { answers })); setCoverage({ ...result.coverage, fact_version: result.fact_version, facts: result.facts }); notify(result.coverage.ready_for_confirmation ? "信息已补齐，请核对并确认。" : "已保存，仍有少量信息需要补充。", result.coverage.ready_for_confirmation ? "success" : "info"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(false); } }
  async function confirm() { if (!coverage) return; setBusy(true); try { await apiRequest(`/projects/${projectId}/fact-versions/${coverage.fact_version}/confirm`, jsonRequest("POST", { confirmed: true })); notify("经营事实已锁定，可以进入后续版式与成图阶段。", "success"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(false); } }
  async function selectStoreName(name: string) { setBusy(true); try { await apiRequest(`/projects/${projectId}/fact-versions`, jsonRequest("POST", { store_name: name })); await loadCoverage(); notify(`已确认目标门店：${name}`, "success"); } catch (error) { notify((error as Error).message, "error"); setBusy(false); } }
  function navigate(view: WorkspaceView) { setActiveView(view); setSidebarOpen(false); }
  function openLibrary(tab: LibraryTab) { setLibraryTab(tab); navigate("library"); }

  return <div className="appShell">
    <a className="skipLink" href="#workspace">跳到主要内容</a>
    <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} projectName={projectName} activeView={activeView} onNavigate={navigate} />
    <main className="mainArea" id="workspace">
      <header className="topbar"><button className="iconButton menuButton" aria-label="打开导航" aria-expanded={sidebarOpen} onClick={() => setSidebarOpen(true)}><Icon name="menu" /></button><div className="announcement"><span>NEW</span><b>团绘AI 对话优先测试版</b><small>先确认事实，再进入成图</small></div><div className="topActions"><span className="tokenBadge"><i /> 默认 0 Token</span><a className="helpButton" href="#guide"><Icon name="help" size={18} />帮助</a></div></header>
      <div className="contentWrap">
        {activeView === "library" ? <AssetLibrary assets={assets} activeTab={libraryTab} onTabChange={setLibraryTab} onBack={() => navigate("create")} /> : <>
          <section className="workbench" aria-label="门店资料采集工作台">
            <div className="workbenchTop"><div className="workbenchLabel"><Icon name={activeStep === 1 ? "store" : activeStep === 4 ? "chat" : "upload"} size={18} /><span><b>门店视觉包</b><small>{projectName || "新建项目"}</small></span></div><StepTabs active={activeStep} maxStep={maxStep} onSelect={setActiveStep} /><div className="stepCounter">{activeStep} / 4</div></div>
            {activeStep === 1 && <CreateStep busy={busy} onSubmit={createProject} />}
            {activeStep === 2 && <UploadStep mode="store" assets={assets} busy={busy} onUploadBatch={uploadBatch} onAnalyze={analyze} onContinue={() => setActiveStep(3)} onOpenLibrary={() => openLibrary("store")} />}
            {activeStep === 3 && <UploadStep mode="dish" assets={assets} busy={busy} onUploadBatch={uploadBatch} onAnalyze={analyze} onContinue={() => undefined} onOpenLibrary={() => openLibrary("dish")} />}
            {activeStep === 4 && <FactsStep coverage={coverage} busy={busy} onSubmit={submitAnswers} onConfirm={confirm} onSelectStore={selectStoreName} factText={factText} />}
            <div className={`statusToast ${messageTone}`} role="status" aria-live="polite"><span>{messageTone === "success" ? <Icon name="check" size={17} /> : messageTone === "error" ? <Icon name="close" size={17} /> : <Icon name="spark" size={17} />}</span><p>{message}</p>{taskId && <small>任务 {taskId.slice(0, 8)}</small>}</div>
          </section>
          {activeStep === 1 && <section className="guideSection" id="guide"><div className="sectionHeading"><div><span className="stepKicker">创作流程</span><h2>从门店资料到团购首页</h2></div><p>按四个步骤补齐门店和菜品信息，确认无误后即可进入五图设计。</p></div><div className="guideGrid"><article><span>01</span><Icon name="store" /><h3>建立门店项目</h3><p>选择门店类型并填写名称，建立一份独立的设计任务。</p></article><article><span>02</span><Icon name="upload" /><h3>上传真实素材</h3><p>依次添加门头、环境、菜单和菜品图片，系统统一保存整理。</p></article><article><span>03</span><Icon name="check" /><h3>核对后开始设计</h3><p>确认店名、主推菜、价格和卖点，再生成团购首页五图。</p></article></div></section>}
        </>}
      </div>
    </main>
  </div>;
}
