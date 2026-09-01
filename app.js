const prompts = {
  1: ["先告诉我门店叫什么", "创建项目不消耗 Token，后面的素材和信息会自动归入这家店。", "例如：山城酸菜鱼", "创建项目"],
  2: ["接着把门店图片发给我", "可以一次选择多张门头、环境和 Logo，确认保存后直接继续。", "可选：补充门店环境或品牌要求", "保存，继续"],
  3: ["再补充菜单和菜品图", "菜单、招牌菜和普通菜品可以一起选择，系统会统一归类。", "可选：告诉我本次最想主推什么", "保存，确认事实"],
  4: ["最后只确认生成必需的事实", "展示版模拟一个追问：本次团购首页最想主推哪道菜或哪个套餐？", "输入准确的主推内容", "确认并锁定"],
};
let step = 1;
const views = document.querySelectorAll(".view");
const navItems = document.querySelectorAll("[data-view]");
const stepButtons = document.querySelectorAll("[data-step]");
const title = document.querySelector("#assistant-title");
const copy = document.querySelector("#assistant-copy");
const input = document.querySelector("#main-input");
const sendLabel = document.querySelector("#send-label");
const uploadTrigger = document.querySelector("#upload-trigger");
const fileInput = document.querySelector("#file-input");
const preview = document.querySelector("#attachment-preview");
const status = document.querySelector("#status");
const projectLabel = document.querySelector("#project-label");

function setView(name) {
  views.forEach((view) => view.classList.toggle("active", view.id === `${name}-view`));
  navItems.forEach((button) => button.classList.toggle("active", button.dataset.view === name));
  document.querySelector(".sidebar").classList.remove("open");
  document.querySelector(".scrim").classList.remove("open");
}
navItems.forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));

function renderStep() {
  const prompt = prompts[step];
  title.textContent = prompt[0]; copy.textContent = prompt[1]; input.placeholder = prompt[2]; sendLabel.textContent = prompt[3];
  document.querySelector(".step-count").textContent = `${step} / 4`;
  stepButtons.forEach((button) => { const value = Number(button.dataset.step); button.disabled = value > step; button.classList.toggle("active", value === step); });
  uploadTrigger.hidden = step === 1 || step === 4;
  input.value = ""; preview.innerHTML = "";
}
stepButtons.forEach((button) => button.addEventListener("click", () => { if (Number(button.dataset.step) <= step) { step = Number(button.dataset.step); renderStep(); } }));
uploadTrigger.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  preview.innerHTML = "";
  Array.from(fileInput.files).slice(0, 8).forEach((file) => { const image = document.createElement("img"); image.src = URL.createObjectURL(file); image.alt = file.name; preview.appendChild(image); });
  status.textContent = `已选择 ${fileInput.files.length} 张图片，确认后保存。`;
});
document.querySelector("#composer").addEventListener("submit", (event) => {
  event.preventDefault();
  if (step === 1 && !input.value.trim()) { input.focus(); status.textContent = "请先填写门店名称。"; return; }
  if ((step === 2 || step === 3) && fileInput.files.length === 0) { uploadTrigger.focus(); status.textContent = "请先选择图片。"; return; }
  if (step === 4 && !input.value.trim()) { input.focus(); status.textContent = "请先确认主推内容。"; return; }
  if (step === 1) projectLabel.textContent = input.value.trim();
  if (step < 4) { step += 1; fileInput.value = ""; renderStep(); status.className = "status success"; status.textContent = "已保存，继续下一步。"; }
  else { status.className = "status success"; status.textContent = "事实已锁定。展示版不连接生图 API。"; sendLabel.textContent = "已完成展示"; document.querySelector(".send-button").disabled = true; }
});

const menu = document.querySelector(".mobile-menu");
const scrim = document.querySelector(".scrim");
menu.addEventListener("click", () => { const open = document.querySelector(".sidebar").classList.toggle("open"); scrim.classList.toggle("open", open); menu.setAttribute("aria-expanded", String(open)); });
scrim.addEventListener("click", () => { document.querySelector(".sidebar").classList.remove("open"); scrim.classList.remove("open"); menu.setAttribute("aria-expanded", "false"); });
