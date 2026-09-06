const views = document.querySelectorAll(".view");
const navItems = document.querySelectorAll("[data-view]");
const status = document.querySelector("#status");
const quickStoreFiles = document.querySelector("#quick-store-files");
const quickDishFiles = document.querySelector("#quick-dish-files");
const modal = document.querySelector("#asset-modal");
const modalTitle = document.querySelector("#asset-modal-title");
const modalContent = document.querySelector("#modal-content");
let activePicker = "store";

function setView(name) {
  views.forEach((view) => view.classList.toggle("active", view.id === `${name}-view`));
  navItems.forEach((button) => button.classList.toggle("active", button.dataset.view === name));
  const notice = document.querySelector(".notice");
  notice.querySelector("span").textContent = name === "professional" ? "团绘AI 专业创作" : "团绘AI 一键生图首页";
  notice.querySelector("small").textContent = name === "professional" ? "确认事实与设计方案后再生成" : "首页确认真实信息，直接成图";
  document.querySelector(".sidebar").classList.remove("open");
  document.querySelector(".scrim").classList.remove("open");
}
navItems.forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));

const selectedAssets = { store: [], dish: [] };
const hoverPreview = document.querySelector("#image-hover");
const imageDialog = document.querySelector("#image-dialog");
let previewedAsset = null;

function inputFor(kind) { return kind === "store" ? quickStoreFiles : quickDishFiles; }
function filesFor(kind) { return selectedAssets[kind]; }
function closeHoverPreview() { hoverPreview.hidden = true; }
function removeAsset(kind, id) {
  const index = selectedAssets[kind].findIndex((asset) => asset.id === id);
  if (index < 0) return;
  URL.revokeObjectURL(selectedAssets[kind][index].url);
  selectedAssets[kind].splice(index, 1);
  if (previewedAsset?.id === id) imageDialog.close();
  closeHoverPreview();
  renderQuickAsset(kind);
  if (!modal.hidden) renderModal();
}
function openImageDialog(asset) {
  closeHoverPreview();
  previewedAsset = asset;
  imageDialog.querySelector("img").src = asset.url;
  imageDialog.querySelector("img").alt = asset.file.name;
  document.querySelector("#image-dialog-name").textContent = asset.file.name;
  imageDialog.showModal();
}
function assetThumb(asset) {
  const card = document.createElement("article");
  card.className = "asset-thumb";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "asset-thumb-image";
  button.setAttribute("aria-label", `预览 ${asset.file.name}`);
  const image = document.createElement("img");
  image.src = asset.url;
  image.alt = asset.file.name;
  button.appendChild(image);
  button.addEventListener("click", () => openImageDialog(asset));
  button.addEventListener("pointerenter", (event) => {
    if (event.pointerType !== "mouse" || !matchMedia("(hover:hover)").matches) return;
    const rect = button.getBoundingClientRect();
    hoverPreview.querySelector("img").src = asset.url;
    hoverPreview.querySelector("small").textContent = asset.file.name;
    hoverPreview.style.left = `${Math.max(8, rect.right + 292 < innerWidth ? rect.right + 12 : rect.left - 292)}px`;
    hoverPreview.style.top = `${Math.max(8, Math.min(rect.top, innerHeight - 308))}px`;
    hoverPreview.hidden = false;
  });
  button.addEventListener("pointerleave", closeHoverPreview);
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "asset-remove";
  remove.setAttribute("aria-label", `移除 ${asset.file.name}`);
  remove.textContent = "×";
  remove.addEventListener("pointerenter", closeHoverPreview);
  remove.addEventListener("click", () => removeAsset(asset.kind, asset.id));
  card.append(button, remove);
  return card;
}
function renderQuickAsset(kind) {
  const assets = filesFor(kind);
  const preview = document.querySelector(`#quick-${kind}-preview`);
  const count = document.querySelector(`#quick-${kind}-count`);
  preview.replaceChildren();
  assets.forEach((asset) => preview.appendChild(assetThumb(asset)));
  const add = document.createElement("button");
  add.type = "button";
  add.className = "asset-add";
  add.setAttribute("aria-label", `添加${kind === "store" ? "门店" : "菜品·菜单"}素材`);
  add.innerHTML = assets.length ? "<b>＋</b><small>继续添加</small>" : "＋";
  add.addEventListener("click", () => inputFor(kind).click());
  preview.appendChild(add);
  preview.classList.toggle("has-assets", Boolean(assets.length));
  count.textContent = String(assets.length);
}
function renderModal() {
  const assets = filesFor(activePicker);
  modalTitle.textContent = activePicker === "store" ? "门店素材" : "菜品素材";
  modalContent.replaceChildren();
  if (!assets.length) {
    const empty = document.createElement("p");
    empty.textContent = `暂无${activePicker === "store" ? "门店" : "菜品"}素材，点击“新增”选择图片`;
    modalContent.appendChild(empty);
    return;
  }
  const grid = document.createElement("div");
  grid.className = "modal-grid";
  assets.forEach((asset) => {
    const card = assetThumb(asset);
    const label = document.createElement("span");
    label.textContent = asset.file.name;
    card.append(label);
    grid.appendChild(card);
  });
  modalContent.appendChild(grid);
}
function openPicker(kind) {
  activePicker = kind;
  renderModal();
  modal.hidden = false;
  modal.querySelector("[data-modal-close]").focus();
}
document.querySelectorAll("[data-picker]").forEach((button) => button.addEventListener("click", () => openPicker(button.dataset.picker)));
document.querySelector("#modal-add").addEventListener("click", () => inputFor(activePicker).click());
document.querySelectorAll("[data-modal-close]").forEach((button) => button.addEventListener("click", () => { modal.hidden = true; }));
modal.addEventListener("mousedown", (event) => { if (event.target === modal) modal.hidden = true; });
[quickStoreFiles, quickDishFiles].forEach((input, index) => input.addEventListener("change", () => {
  const kind = index ? "dish" : "store";
  Array.from(input.files).slice(0, Math.max(0, 20 - selectedAssets[kind].length)).forEach((file) => selectedAssets[kind].push({ id: `${kind}-${Date.now()}-${Math.random()}`, kind, file, url: URL.createObjectURL(file) }));
  input.value = "";
  renderQuickAsset(kind);
  if (!modal.hidden) renderModal();
}));
document.querySelectorAll("[data-add-files]").forEach((button) => button.addEventListener("click", () => inputFor(button.dataset.addFiles).click()));
document.querySelector("#image-dialog-close").addEventListener("click", () => imageDialog.close());
document.querySelector("#image-dialog-remove").addEventListener("click", () => previewedAsset && removeAsset(previewedAsset.kind, previewedAsset.id));
imageDialog.addEventListener("click", (event) => { if (event.target === imageDialog) imageDialog.close(); });
addEventListener("scroll", closeHoverPreview, true);
addEventListener("resize", closeHoverPreview);

document.querySelectorAll(".quick-menu > div button").forEach((button) => button.addEventListener("click", () => {
  const menu = button.closest("details");
  menu.querySelectorAll("button").forEach((item) => item.classList.toggle("active", item === button));
  menu.querySelector("summary b").textContent = button.textContent;
  menu.removeAttribute("open");
}));
const quickMenus = document.querySelectorAll(".quick-menu, .preference-menu");
quickMenus.forEach((menu) => menu.addEventListener("toggle", () => {
  if (!menu.open) return;
  quickMenus.forEach((other) => { if (other !== menu) other.removeAttribute("open"); });
}));
document.addEventListener("pointerdown", (event) => {
  if (!event.target.closest(".quick-menu, .preference-menu")) quickMenus.forEach((menu) => menu.removeAttribute("open"));
});
document.addEventListener("keydown", (event) => { if (event.key === "Escape") quickMenus.forEach((menu) => menu.removeAttribute("open")); });
document.querySelector(".canvas-switch").addEventListener("click", (event) => {
  const button = event.currentTarget;
  const active = button.classList.toggle("active");
  button.setAttribute("aria-pressed", String(active));
});
document.querySelector("#quick-composer").addEventListener("submit", (event) => {
  event.preventDefault();
  const brief = document.querySelector("#quick-input");
  const error = document.querySelector("#quick-error");
  const fail = (text, target) => { error.hidden = false; error.textContent = text; target?.focus(); };
  if (!brief.value.trim()) return fail("请先描述门店名称、主推内容、价格和真实卖点。", brief);
  if (!/(?:门店名称|店名|门店)\s*[：:]/.test(brief.value)) return fail("请在文字中写明“门店名称：×××”。", brief);
  if (!selectedAssets.store.length) return fail("请添加至少一张门店素材。", document.querySelector('[data-add-files="store"]'));
  if (!selectedAssets.dish.length) return fail("请添加至少一张菜品或菜单素材。", document.querySelector('[data-add-files="dish"]'));
  error.hidden = true;
  status.className = "status inline-status success";
  status.textContent = "资料已收集完成，请在首页确认后直接生成。";
  const storeMatch = brief.value.match(/(?:门店名称|店名|门店)\s*[：:]\s*([^；;,，。\n]+)/);
  document.querySelector("#confirm-store").textContent = storeMatch?.[1]?.trim() || "待确认";
  document.querySelector("#quick-confirm").hidden = false;
  document.querySelector("#quick-confirm").scrollIntoView({ behavior: "smooth", block: "center" });
});
document.querySelector("#preview-generate").addEventListener("click", () => {
  status.className = "status inline-status success";
  status.textContent = "已完成首页确认。GitHub 展示版不连接 API，不会产生任何费用。";
});

function renderProAttachments() {
  const preview = document.querySelector("#pro-preview");
  preview.replaceChildren();
  [["store", "门店"], ["dish", "菜品"]].forEach(([kind, label]) => {
    const input = document.querySelector(`#pro-${kind}-files`);
    document.querySelector(`#pro-${kind}-count`).textContent = input.files.length || "+";
    Array.from(input.files).slice(0, 10).forEach((file, index) => {
      const image = document.createElement("img");
      image.src = URL.createObjectURL(file);
      image.alt = `${label}素材 ${index + 1}`;
      preview.appendChild(image);
    });
  });
}
document.querySelectorAll("[data-pro-upload]").forEach((button) => button.addEventListener("click", () => document.querySelector(`#pro-${button.dataset.proUpload}-files`).click()));
document.querySelector("#pro-store-files").addEventListener("change", renderProAttachments);
document.querySelector("#pro-dish-files").addEventListener("change", renderProAttachments);
document.querySelector("#pro-composer").addEventListener("submit", (event) => {
  event.preventDefault();
  const name = document.querySelector("#pro-store-name");
  const brief = document.querySelector("#pro-main-input");
  const proStatus = document.querySelector("#pro-status");
  if (!name.value.trim()) { name.focus(); proStatus.textContent = "请填写门店名称。"; return; }
  if (!brief.value.trim()) { brief.focus(); proStatus.textContent = "请补充本次创作需求。"; return; }
  proStatus.className = "status inline-status success";
  proStatus.textContent = "资料已保存。下一步将确认事实与设计方案，确认后再开始生成；展示版不连接 API。";
});

const menu = document.querySelector(".mobile-menu");
const scrim = document.querySelector(".scrim");
menu.addEventListener("click", () => { const open = document.querySelector(".sidebar").classList.toggle("open"); scrim.classList.toggle("open", open); menu.setAttribute("aria-expanded", String(open)); });
scrim.addEventListener("click", () => { document.querySelector(".sidebar").classList.remove("open"); scrim.classList.remove("open"); menu.setAttribute("aria-expanded", "false"); });
