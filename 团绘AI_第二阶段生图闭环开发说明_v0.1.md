# 团绘AI 第二阶段生图闭环开发说明 v0.1

## 1. 本版结果

本版已经把第一阶段的资料采集路径向后延伸为：

`确认事实 → 生成五图设计方案 → 用户确认方案 → 发起付费生图 → 本地文字排版 → 裁切五图 → 预览与下载`

测试页面：`http://127.0.0.1:3011/`

## 2. 产品约束

- 总画布固定为 20:3，成品尺寸 4000×600。
- 总画布从左到右精确裁为 5 张 800×600，即每张 4:3。
- 生图前必须先锁定经营事实，再确认设计方案。
- 店名、价格、主推内容和卖点只允许来自已确认事实。
- AI 只生成不含文字的连续视觉底图；中文、价格和品牌文案由本地排版层写入，避免乱码和事实改写。
- 点击“开始生成”前必须二次确认费用，不允许页面自动调用付费模型。

## 3. 模型策略

- 默认供应商：千问。
- 默认模型：`qwen-image-3.0`。
- 单次生成只调用一个供应商。
- 默认调用失败时，可尝试豆包兜底；未配置 `ARK_API_KEY` 时会明确记录为未配置，不会产生伪成功。
- 豆包预留模型：`doubao-seedream-5-0-260128`。

## 4. 新增后端能力

### 4.1 设计方案

- `POST /api/v1/projects/{project_id}/design-plans`
- `GET /api/v1/projects/{project_id}/design-plans/latest`
- `PATCH /api/v1/projects/{project_id}/design-plans/{plan_id}`
- `POST /api/v1/projects/{project_id}/design-plans/{plan_id}/confirm`

设计方案包含画布规格、风格、锁定文案、五屏分工和事实保护规则。

### 4.2 生图与下载

- `POST /api/v1/projects/{project_id}/generation-runs`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/projects/{project_id}/generations/{task_id}/assets/{filename}`

生成任务会保存：

- `long.png`：4000×600 完整长图。
- `01.png` 至 `05.png`：五张 800×600 图片。

## 5. 前端交互

- 资料采集仍然只显示原有四步。
- 事实锁定后，顶部自动切换为两步创作流程：`确认设计方案`、`生成与下载`。
- 设计方案页只保留一个核心操作，可选择食欲冲击、品牌质感、烟火市井、清爽简约四种方向。
- 生图页显示任务进度、错误原因、完整长图、五张裁切图和下载入口。

## 6. 环境变量

现有 `.env` 已配置百炼 Key。豆包需要后续补充：

```env
QWEN_IMAGE_MODEL=qwen-image-3.0
QWEN_IMAGE_BASE_URL=https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation
ARK_API_KEY=
ARK_IMAGE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3/images/generations
DOUBAO_IMAGE_MODEL=doubao-seedream-5-0-260128
GENERATED_DIR=./data/generated
```

## 7. 验证记录

- 后端自动化测试：20 项通过。
- 前端 TypeScript：通过。
- 前端 ESLint：通过。
- Next.js 生产构建：通过。
- 本地前端：HTTP 200。
- 本地后端健康检查：HTTP 200。
- 未自动发起付费生图调用；需要测试人员在页面明确确认后触发。

## 8. 当前限制

- 当前本机未配置豆包 `ARK_API_KEY`，因此豆包兜底尚不能真实调用。
- Qwen 图片生成模型是否已在当前百炼账号开通，需要第一次人工确认付费测试验证。
- MVP 生图采用同步供应商调用加后台任务，后续生产部署应改为独立任务队列。
