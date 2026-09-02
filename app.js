const views = document.querySelectorAll(".view");
const navItems = document.querySelectorAll("[data-view]");
const composer = document.querySelector("#composer");
const nameInput = document.querySelector("#store-name");
const briefInput = document.querySelector("#main-input");
const storeFiles = document.querySelector("#store-files");
const dishFiles = document.querySelector("#dish-files");
const preview = document.querySelector("#attachment-preview");
const status = document.querySelector("#status");
const projectLabel = document.querySelector("#project-label");
const projectState = document.querySelector("#project-state");
const stateBadge = document.querySelector(".collection-state");
const assistantTitle = document.querySelector("#assistant-title");
const assistantCopy = document.querySelector("#assistant-copy");
const sendLabel = document.querySelector("#send-label");
let confirming = false;

function setView(name) {
  views.forEach((view) => view.classList.toggle("active", view.id === `${name}-view`));
  navItems.forEach((button) => button.classList.toggle("active", button.dataset.view === name));
  document.querySelector(".sidebar").classList.remove("open");
  document.querySelector(".scrim").classList.remove("open");
}
navItems.forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));

function renderAttachments() {
  preview.replaceChildren();
  [["门店", storeFiles.files], ["菜品", dishFiles.files]].forEach(([kind, files]) => {
    Array.from(files).slice(0, 10).forEach((file, index) => {
      const item = document.createElement("span");
      const image = document.createElement("img");
      image.src = URL.createObjectURL(file);
      image.alt = `${kind}素材 ${index + 1}：${file.name}`;
      item.appendChild(image);
      preview.appendChild(item);
    });
  });
  document.querySelector("#store-count").textContent = storeFiles.files.length || "+";
  document.querySelector("#dish-count").textContent = dishFiles.files.length || "+";
  if (storeFiles.files.length || dishFiles.files.length) status.textContent = `已选择 ${storeFiles.files.length} 张门店素材、${dishFiles.files.length} 张菜品素材。`;
}
document.querySelectorAll("[data-upload]").forEach((button) => button.addEventListener("click", () => (button.dataset.upload === "store" ? storeFiles : dishFiles).click()));
document.querySelector(".category-select > div button:not(:disabled)").addEventListener("click", () => document.querySelector(".category-select").removeAttribute("open"));
storeFiles.addEventListener("change", renderAttachments);
dishFiles.addEventListener("change", renderAttachments);

composer.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!confirming) {
    if (!nameInput.value.trim()) { nameInput.focus(); status.textContent = "请填写门店名称。"; return; }
    if (!briefInput.value.trim()) { briefInput.focus(); status.textContent = "请写明门店定位、主推内容、价格和真实卖点。"; return; }
    if (!storeFiles.files.length) { document.querySelector('[data-upload="store"]').focus(); status.textContent = "请添加至少一张门店素材。"; return; }
    if (!dishFiles.files.length) { document.querySelector('[data-upload="dish"]').focus(); status.textContent = "请添加至少一张菜品或菜单素材。"; return; }
    confirming = true;
    projectLabel.textContent = nameInput.value.trim();
    projectState.textContent = "资料已提交·正在确认事实";
    stateBadge.classList.add("active");
    stateBadge.querySelector("b").textContent = "事实确认中";
    assistantTitle.textContent = "资料已经收到了，再确认最后一项";
    assistantCopy.textContent = "所有信息仍在同一个对话框中处理，不会跳转页面。";
    nameInput.disabled = true;
    briefInput.value = "";
    briefInput.placeholder = "本次团购首页最想主推哪道菜或哪个套餐？";
    preview.replaceChildren();
    document.querySelector(".composer-options").hidden = true;
    sendLabel.textContent = "确认并锁定";
    status.className = "status success";
    status.textContent = "资料已一次性收集完成；仅在必要时继续补问事实。";
    briefInput.focus();
    return;
  }
  if (!briefInput.value.trim()) { briefInput.focus(); status.textContent = "请先补充这项真实信息。"; return; }
  sendLabel.textContent = "已完成展示";
  document.querySelector(".send-button").disabled = true;
  briefInput.disabled = true;
  stateBadge.querySelector("b").textContent = "资料已确认";
  status.className = "status success";
  status.textContent = "事实已锁定。展示版不连接任何 API，也不会上传文件。";
});

const menu = document.querySelector(".mobile-menu");
const scrim = document.querySelector(".scrim");
menu.addEventListener("click", () => { const open = document.querySelector(".sidebar").classList.toggle("open"); scrim.classList.toggle("open", open); menu.setAttribute("aria-expanded", String(open)); });
scrim.addEventListener("click", () => { document.querySelector(".sidebar").classList.remove("open"); scrim.classList.remove("open"); menu.setAttribute("aria-expanded", "false"); });
