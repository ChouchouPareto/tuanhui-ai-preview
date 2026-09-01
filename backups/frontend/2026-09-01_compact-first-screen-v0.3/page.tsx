"use client";

import Image from "next/image";
import { ChangeEvent, FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import { apiRequest, apiUrl, jsonRequest } from "../lib/api-client";
import { Asset, Coverage, Facts, MenuProduct, ROLE_NAMES, StoreNameCandidate } from "../features/store-intake/types";

type Step = 1 | 2 | 3;
type IconName = "spark" | "folder" | "image" | "book" | "history" | "menu" | "close" | "plus" | "arrow" | "check" | "store" | "upload" | "chat" | "help" | "user" | "wand";

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
  wand: <><path d="m15 4 5 5L9 20l-5-5L15 4Z"/><path d="m12 7 5 5M5 3v3M3.5 4.5h3M20 16v4M18 18h4"/></>,
};

function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return <svg aria-hidden="true" className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{icons[name]}</svg>;
}

function Sidebar({ open, onClose, projectName }: { open: boolean; onClose: () => void; projectName: string }) {
  return <><button className={`sidebarScrim ${open ? "isOpen" : ""}`} aria-label="关闭导航" onClick={onClose} /><aside className={`sidebar ${open ? "isOpen" : ""}`} aria-label="主导航">
    <div className="brandRow"><div className="brand"><span className="brandMark"><Icon name="spark" size={18} /></span><strong>团绘AI</strong></div><button className="iconButton mobileOnly" aria-label="关闭导航" onClick={onClose}><Icon name="close" /></button></div>
    <nav className="primaryNav" aria-label="主导航"><a className="navItem active" href="#workspace" aria-current="page"><Icon name="spark" /><span>开始创作</span></a><button className="navItem" type="button" disabled title="项目列表将在后续接口接入后开放"><Icon name="folder" /><span>我的项目</span><span className="soon">待接入</span></button><button className="navItem" type="button" disabled title="素材库将在后续阶段开放"><Icon name="image" /><span>素材库</span></button><a className="navItem" href="#guide"><Icon name="book" /><span>使用说明</span></a></nav>
    <div className="navDivider" /><section className="historySection" aria-labelledby="history-title"><div className="sectionTitle"><span id="history-title">创作历史</span><Icon name="history" size={17} /></div>{projectName ? <button className="historyItem" type="button"><span className="historyThumb"><Icon name="store" size={18} /></span><span><b>{projectName}</b><small>资料采集中</small></span></button> : <p className="emptyHistory">创建门店后，当前项目会显示在这里。</p>}</section>
    <div className="sidebarFooter"><span className="avatar"><Icon name="user" size={17} /></span><span><b>测试用户</b><small>团绘AI 内测</small></span><a className="iconButton" aria-label="查看使用说明" href="#guide"><Icon name="help" /></a></div>
  </aside></>;
}

function StepTabs({ active, maxStep, onSelect }: { active: Step; maxStep: Step; onSelect: (step: Step) => void }) {
  return <div className="modeTabs" aria-label="创作步骤">{["创建门店", "上传素材", "确认信息"].map((label, index) => { const step = (index + 1) as Step; return <button type="button" key={label} className={active === step ? "active" : ""} aria-current={active === step ? "step" : undefined} disabled={step > maxStep} onClick={() => onSelect(step)}><span>{step}</span>{label}</button>; })}</div>;
}

function WorkspaceIntro({ active }: { active: Step }) {
  const content = { 1: ["先创建一个真实门店项目", "只需要一个名称，行业和目标平台已经按首版范围配置好。"], 2: ["把门店素材交给我们整理", "先上传菜单和门头。其他菜品、环境和 Logo 可以随后补充。"], 3: ["把经营事实说准确", "系统只追问缺失信息；需要识图时，再由你主动开启 AI 辅助。"] }[active];
  return <div className="workspaceHeading"><div className="eyebrow"><span /> 对话优先 · 默认 0 Token</div><h1>{content[0]}</h1><p>{content[1]}</p></div>;
}

function CreateStep({ busy, onSubmit }: { busy: boolean; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  return <div className="stepBody createStep"><div className="stepIcon"><Icon name="store" size={27} /></div><div className="stepCopy"><span className="stepKicker">门店项目</span><h2>今天要为哪家店创作？</h2><p>输入门店名称即可开始。首版固定为餐饮行业，并同时适配抖音团购与美团团购。</p></div><form className="projectForm" onSubmit={onSubmit}><label htmlFor="project-name">门店名称</label><div className="inputAction"><input id="project-name" name="name" required maxLength={120} placeholder="例如：山城酸菜鱼" autoComplete="organization" /><button className="primaryButton" disabled={busy}>{busy ? "正在创建…" : <>创建项目 <Icon name="arrow" size={18} /></>}</button></div><div className="formMeta"><span><Icon name="check" size={15} /> 餐饮行业</span><span><Icon name="check" size={15} /> 抖音 + 美团</span><span><Icon name="check" size={15} /> 不调用模型</span></div></form></div>;
}

const ROLE_OPTIONS: { value: string; label: string; hint: string; icon: IconName }[] = [
  { value: "menu", label: "菜单", hint: "菜品与价格", icon: "image" },
  { value: "storefront", label: "门头", hint: "店名与门店", icon: "store" },
  { value: "signature_dish", label: "招牌菜", hint: "重点推荐", icon: "spark" },
  { value: "dish", label: "普通菜品", hint: "丰富内容", icon: "image" },
  { value: "environment", label: "环境", hint: "空间氛围", icon: "store" },
  { value: "logo", label: "Logo", hint: "品牌标识", icon: "spark" },
  { value: "credential", label: "资质", hint: "证照证明", icon: "check" },
  { value: "other", label: "其他", hint: "补充素材", icon: "plus" },
];

function formatFileSize(bytes: number) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function UploadStep({ assets, busy, requiredReady, onSubmit, onAnalyze }: { assets: Asset[]; busy: boolean; requiredReady: boolean; onSubmit: (event: FormEvent<HTMLFormElement>) => Promise<boolean>; onAnalyze: (useAI: boolean) => void }) {
  const hasMenu = assets.some((item) => item.semantic_role === "menu");
  const hasStorefront = assets.some((item) => item.semantic_role === "storefront");
  const suggestedRole = !hasMenu ? "menu" : !hasStorefront ? "storefront" : "signature_dish";
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedRole, setSelectedRole] = useState(suggestedRole);
  const [previewUrl, setPreviewUrl] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setSelectedFile(file);
    setPreviewUrl(file ? URL.createObjectURL(file) : "");
  }

  function clearFile() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setSelectedFile(null); setPreviewUrl("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function submitUpload(event: FormEvent<HTMLFormElement>) {
    const succeeded = await onSubmit(event);
    if (succeeded) {
      clearFile();
      setSelectedRole(selectedRole === "menu" && !hasStorefront ? "storefront" : selectedRole === "storefront" && !hasMenu ? "menu" : "signature_dish");
    }
  }

  const currentRole = ROLE_OPTIONS.find((role) => role.value === selectedRole) ?? ROLE_OPTIONS[0];
  return <div className="stepBody uploadStep">
    <div className="uploadHeader"><div><span className="stepKicker">素材采集</span><h2>先放图片，再告诉我它是什么</h2><p>每次只处理一张，选中后立即预览；系统会优先推荐当前缺少的素材类型。</p></div><div className="requirementPills"><span className={hasMenu ? "done" : ""}><Icon name={hasMenu ? "check" : "image"} size={15} />菜单{hasMenu ? "已完成" : "待上传"}</span><span className={hasStorefront ? "done" : ""}><Icon name={hasStorefront ? "check" : "store"} size={15} />门头{hasStorefront ? "已完成" : "待上传"}</span></div></div>
    <form className="uploadComposer" onSubmit={submitUpload} aria-busy={busy}>
      <section className={`fileStage ${selectedFile ? "hasFile" : ""}`}>
        {selectedFile && previewUrl ? <><div className="pendingPreview"><Image src={previewUrl} alt={`待上传图片：${selectedFile.name}`} fill unoptimized sizes="(max-width: 760px) 100vw, 520px" /></div><div className="pendingFile"><span className="fileReady"><Icon name="check" size={16} /></span><div><strong>{selectedFile.name}</strong><small>{formatFileSize(selectedFile.size)} · 已选择，尚未上传</small></div><button type="button" className="textButton" onClick={clearFile}>移除</button></div><label className="replaceButton" htmlFor="asset-file"><Icon name="image" size={16} />更换图片</label></> : <label className="dropzone" htmlFor="asset-file"><span className="uploadGlyph"><Icon name="upload" size={24} /></span><strong>点击选择门店图片</strong><small>PNG、JPEG、WebP，单张不超过系统限制</small><span className="dropHint">选择后会在这里预览</span></label>}
        <input ref={fileInputRef} className="visuallyHiddenFile" id="asset-file" name="file" type="file" accept="image/png,image/jpeg,image/webp" required onChange={chooseFile} />
      </section>
      <section className="classificationPanel"><div className="classificationTitle"><div><span>这张图片是什么？</span><small>已自动推荐「{ROLE_NAMES[suggestedRole]}」</small></div><span className="selectedRole"><Icon name={currentRole.icon} size={15} />{currentRole.label}</span></div>
        <div className="roleGrid" role="radiogroup" aria-label="图片用途">{ROLE_OPTIONS.map((role) => <label key={role.value} className={`roleOption ${selectedRole === role.value ? "selected" : ""}`}><input type="radio" name="semantic_role" value={role.value} checked={selectedRole === role.value} onChange={() => setSelectedRole(role.value)} /><span className="roleIcon"><Icon name={role.icon} size={18} /></span><span><b>{role.label}</b><small>{role.hint}</small></span>{role.value === suggestedRole && <i>推荐</i>}</label>)}</div>
        <details className="advancedSettings"><summary>更多设置 <span>一般不需要修改</span></summary><div className="advancedBody"><fieldset><legend>素材重要性</legend><div className="priorityChoices"><label><input type="radio" name="priority" value="50" />重点</label><label><input type="radio" name="priority" value="100" defaultChecked />普通</label><label><input type="radio" name="priority" value="200" />备用</label></div></fieldset><label className="heroCheck"><input name="is_hero" type="checkbox" value="true" /><span><b>设为唯一主推图</b><small>适合最想突出的一张招牌菜或门店图</small></span></label></div></details>
        <input type="hidden" name="asset_type" value="other" />
        <button className="primaryButton addAssetButton" disabled={!selectedFile || busy}>{busy ? "正在加入素材…" : <>确认添加为「{currentRole.label}」 <Icon name="arrow" size={18} /></>}</button>
      </section>
    </form>
    <div className="assetSection"><div className="subheading"><div><strong>门店素材</strong><small>已成功上传并保存</small></div><span>{assets.length} 项</span></div>{assets.length ? <div className="assetGrid">{assets.map((asset) => <article className="assetCard" key={asset.id}>{asset.preview_path ? <div className="assetThumb"><Image src={apiUrl(asset.preview_path)} alt={`${ROLE_NAMES[asset.semantic_role] ?? "门店"}素材：${asset.original_name}`} fill unoptimized sizes="220px" /></div> : <span className="assetIcon"><Icon name={asset.semantic_role === "storefront" ? "store" : "image"} /></span>}<div className="assetCardBody"><div><b>{ROLE_NAMES[asset.semantic_role] ?? asset.semantic_role}</b>{asset.is_hero && <span>主推</span>}</div><small title={asset.original_name}>{asset.original_name}</small><p>{asset.width && asset.height ? `${asset.width} × ${asset.height}` : "尺寸读取中"} · {asset.priority <= 50 ? "重点素材" : asset.priority >= 200 ? "备用素材" : "普通素材"}</p></div></article>)}</div> : <div className="emptyState"><span className="emptyIcon"><Icon name="image" /></span><div><strong>还没有已上传素材</strong><p>先选择图片并确认分类，上传成功后会显示真实缩略图。</p></div></div>}</div>
    <div className="actionBar"><div><strong>{requiredReady ? "基础素材已齐，可以开始整理" : "先完成菜单和门头两类素材"}</strong><small>{requiredReady ? "默认通过对话收集事实，不调用模型。" : `下一张建议上传：${!hasMenu ? "菜单" : "门头"}。`}</small></div><div className="actionButtons"><button className="ghostButton" type="button" disabled={!requiredReady || busy} onClick={() => onAnalyze(true)}><Icon name="wand" size={17} />AI 辅助识别</button><button className="primaryButton" type="button" disabled={!requiredReady || busy} onClick={() => onAnalyze(false)}>开始整理 <Icon name="arrow" size={18} /></button></div></div>
  </div>;
}

function FactsStep({ coverage, busy, onSubmit, onConfirm, onSelectStore, factText }: { coverage: Coverage | null; busy: boolean; onSubmit: (event: FormEvent<HTMLFormElement>) => void; onConfirm: () => void; onSelectStore: (name: string) => void; factText: (key: string) => string }) {
  if (!coverage) return <div className="stepBody waitingStep"><span className="loadingOrb"><Icon name="chat" size={25} /></span><h2>正在准备需要确认的信息</h2><p>系统会先整理缺失项，不会把不确定内容写成事实。</p></div>;
  const storeCandidates = (coverage.facts.detected_store_name_candidates as StoreNameCandidate[] | undefined) ?? []; const storeNeedsConfirmation = Boolean(coverage.facts.detected_store_name_needs_confirmation); const menuProducts = (coverage.facts.products as MenuProduct[] | undefined) ?? [];
  return <div className="stepBody factsStep"><div className="factsLayout"><section className="conversationPanel"><div className="panelTitle"><span className="assistantAvatar"><Icon name="spark" size={16} /></span><div><strong>团绘助手</strong><small>{coverage.questions.length ? `还需要确认 ${coverage.questions.length} 项信息` : "核心信息已经齐全"}</small></div></div>
    {storeNeedsConfirmation && storeCandidates.length > 1 && <div className="dialogueBlock"><p>我在门头图中看到了多家店，请选择你要制作的目标门店。</p><div className="candidateList">{storeCandidates.map((candidate) => <button key={`${candidate.name}-${candidate.region}`} type="button" disabled={busy} onClick={() => onSelectStore(candidate.name)}><span><b>{candidate.name}</b><small>{candidate.region || "区域未识别"} · {candidate.evidence}</small></span><span>{Math.round(candidate.confidence * 100)}%</span></button>)}</div></div>}
    {coverage.questions.length > 0 ? <form className="questionForm" onSubmit={onSubmit}>{coverage.questions.map((question, index) => <label key={question.field}><span><i>{index + 1}</i>{question.question}</span><input name={question.field} required placeholder="请直接输入准确答案" /></label>)}<button className="primaryButton" disabled={busy}>{busy ? "正在提交…" : <>提交补充信息 <Icon name="arrow" size={18} /></>}</button></form> : <div className="readyMessage"><Icon name="check" size={20} /><div><strong>核心信息已补齐</strong><p>请在右侧核对事实卡，确认后将锁定本版本。</p></div></div>}
    </section><aside className="factCard"><div className="subheading"><strong>门店事实卡</strong><span>V{coverage.fact_version}</span></div><dl><div><dt>门店名称</dt><dd>{factText("store_name")}</dd></div><div><dt>门店定位</dt><dd>{factText("positioning")}</dd></div><div><dt>主推内容</dt><dd>{factText("hero_item")}</dd></div><div><dt>核心卖点</dt><dd>{factText("selling_points")}</dd></div><div><dt>表达视角</dt><dd>品牌官方</dd></div></dl>{menuProducts.length > 0 && <div className="menuPreview"><strong>菜单识别 · 价格待确认</strong>{menuProducts.slice(0, 5).map((product, index) => <div key={`${product.name}-${index}`}><span>{product.name}</span><b>{product.price_original ?? "未识别"}</b></div>)}{menuProducts.length > 5 && <small>另有 {menuProducts.length - 5} 项已保存在事实卡</small>}</div>}<button className="primaryButton fullWidth" type="button" disabled={!coverage.ready_for_confirmation || busy} onClick={onConfirm}><Icon name="check" size={18} />确认并锁定事实</button></aside></div></div>;
}

export default function Home() {
  const [projectId, setProjectId] = useState(""); const [projectName, setProjectName] = useState(""); const [taskId, setTaskId] = useState(""); const [assets, setAssets] = useState<Asset[]>([]); const [coverage, setCoverage] = useState<Coverage | null>(null); const [message, setMessage] = useState("准备好后，从创建门店开始。"); const [messageTone, setMessageTone] = useState<"info" | "success" | "error">("info"); const [busy, setBusy] = useState(false); const [activeStep, setActiveStep] = useState<Step>(1); const [sidebarOpen, setSidebarOpen] = useState(false);
  const maxStep: Step = coverage ? 3 : projectId ? 2 : 1; const requiredReady = assets.some((asset) => asset.semantic_role === "menu") && assets.some((asset) => asset.semantic_role === "storefront"); const factText = (key: string) => Array.isArray(coverage?.facts[key]) ? (coverage?.facts[key] as string[]).join("、") : String(coverage?.facts[key] ?? "待确认");
  function notify(text: string, tone: "info" | "success" | "error" = "info") { setMessage(text); setMessageTone(tone); }
  async function createProject(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setBusy(true); const fd = new FormData(event.currentTarget); const name = String(fd.get("name") ?? "").trim(); try { const result = await apiRequest<{ project_id: string }>("/projects", jsonRequest("POST", { name, industry: "餐饮", platforms: ["douyin", "meituan"] })); setProjectId(result.project_id); setProjectName(name); setAssets([]); setCoverage(null); setActiveStep(2); notify("项目已创建，请先上传菜单和门头图片。", "success"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(false); } }
  async function refreshAssets() { setAssets(await apiRequest<Asset[]>(`/projects/${projectId}/assets`)); }
  async function upload(event: FormEvent<HTMLFormElement>): Promise<boolean> { event.preventDefault(); if (!projectId) return false; setBusy(true); const form = event.currentTarget; const fd = new FormData(form); try { await apiRequest(`/projects/${projectId}/assets`, { method: "POST", body: fd }); await refreshAssets(); form.reset(); notify("素材上传成功，已经加入当前门店。", "success"); return true; } catch (error) { notify((error as Error).message, "error"); return false; } finally { setBusy(false); } }
  async function analyze(useAI = false) { if (!projectId) return; if (useAI && !window.confirm("AI 将识别已上传图片并产生模型费用。确认继续吗？")) return; setBusy(true); try { const task = await apiRequest<{ task_id: string }>(`/projects/${projectId}/analysis-runs`, jsonRequest("POST", { use_ai: useAI })); setTaskId(task.task_id); setActiveStep(3); notify(useAI ? "正在调用 AI 识别素材，请稍候。" : "正在整理需要你确认的门店信息。", "info"); window.setTimeout(() => void loadCoverage(), useAI ? 1200 : 300); } catch (error) { notify((error as Error).message, "error"); setBusy(false); } }
  async function loadCoverage() { try { const result = await apiRequest<Coverage>(`/projects/${projectId}/coverage`); setCoverage(result); notify(result.ready_for_confirmation ? "核心信息已齐，请核对后锁定。" : "请补充下面的缺失信息，系统不会替你猜。", result.ready_for_confirmation ? "success" : "info"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(false); } }
  async function submitAnswers(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setBusy(true); const fd = new FormData(event.currentTarget); const answers: Record<string, string> = {}; coverage?.questions.forEach((question) => { const value = String(fd.get(question.field) ?? "").trim(); if (value) answers[question.field] = value; }); try { const result = await apiRequest<{ fact_version: number; facts: Facts; coverage: Coverage }>(`/projects/${projectId}/clarifications`, jsonRequest("POST", { answers })); setCoverage({ ...result.coverage, fact_version: result.fact_version, facts: result.facts }); notify(result.coverage.ready_for_confirmation ? "信息已补齐，请核对并确认。" : "已保存，仍有少量信息需要补充。", result.coverage.ready_for_confirmation ? "success" : "info"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(false); } }
  async function confirm() { if (!coverage) return; setBusy(true); try { await apiRequest(`/projects/${projectId}/fact-versions/${coverage.fact_version}/confirm`, jsonRequest("POST", { confirmed: true })); notify("经营事实已锁定，可以进入后续版式与成图阶段。", "success"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(false); } }
  async function selectStoreName(name: string) { setBusy(true); try { await apiRequest(`/projects/${projectId}/fact-versions`, jsonRequest("POST", { store_name: name })); await loadCoverage(); notify(`已确认目标门店：${name}`, "success"); } catch (error) { notify((error as Error).message, "error"); setBusy(false); } }
  return <div className="appShell"><a className="skipLink" href="#workspace">跳到主要内容</a><Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} projectName={projectName} /><main className="mainArea" id="workspace"><header className="topbar"><button className="iconButton menuButton" aria-label="打开导航" aria-expanded={sidebarOpen} onClick={() => setSidebarOpen(true)}><Icon name="menu" /></button><div className="announcement"><span>NEW</span><b>团绘AI 对话优先测试版</b><small>先确认事实，再进入成图</small></div><div className="topActions"><span className="tokenBadge"><i /> 默认 0 Token</span><a className="helpButton" href="#guide"><Icon name="help" size={18} />帮助</a></div></header><div className="contentWrap"><StepTabs active={activeStep} maxStep={maxStep} onSelect={setActiveStep} /><WorkspaceIntro active={activeStep} /><section className="workbench" aria-label="门店资料采集工作台"><div className="workbenchTop"><div className="workbenchLabel"><Icon name={activeStep === 1 ? "store" : activeStep === 2 ? "upload" : "chat"} size={18} /><span>门店视觉包</span></div><div className="stepCounter">步骤 {activeStep} / 3</div></div>{activeStep === 1 && <CreateStep busy={busy} onSubmit={createProject} />}{activeStep === 2 && <UploadStep assets={assets} busy={busy} requiredReady={requiredReady} onSubmit={upload} onAnalyze={analyze} />}{activeStep === 3 && <FactsStep coverage={coverage} busy={busy} onSubmit={submitAnswers} onConfirm={confirm} onSelectStore={selectStoreName} factText={factText} />}</section><div className={`statusToast ${messageTone}`} role="status" aria-live="polite"><span>{messageTone === "success" ? <Icon name="check" size={17} /> : messageTone === "error" ? <Icon name="close" size={17} /> : <Icon name="spark" size={17} />}</span><p>{message}</p>{taskId && <small>任务 {taskId.slice(0, 8)}</small>}</div>{activeStep === 1 && <section className="guideSection" id="guide"><div className="sectionHeading"><div><span className="stepKicker">工作方式</span><h2>少识别一次，多确认一步</h2></div><p>把模型用在真正需要看图的地方，把店名、价格和品牌决定权留给商家。</p></div><div className="guideGrid"><article><span>01</span><Icon name="upload" /><h3>素材先分角色</h3><p>菜单、门头、招牌菜和环境图各司其职，避免图片顺序变成隐性规则。</p></article><article><span>02</span><Icon name="chat" /><h3>缺什么就问什么</h3><p>每轮最多三个问题，默认不调用模型，先让用户给出最准确信息。</p></article><article><span>03</span><Icon name="check" /><h3>事实锁定再生成</h3><p>价格、门店名、Logo 与品牌信息经确认后，才会进入后续视觉流程。</p></article></div></section>}</div></main></div>;
}
