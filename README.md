# 团绘AI

资料总入口：[全部资料导航](../00-团绘AI资料导航/README.md) · [按任务找资料](../00-团绘AI资料导航/任务与资料调用地图.md)。原件按原路径保留；同级 `团绘AI_GitHub展示版` 是独立静态演示，不是本工程。

产品唯一主线：[主 PRD](PRD.md) · [产品文档中心](docs/product/README.md) · [需求与实现状态](docs/product/requirements.json)。主 PRD 在同一路径持续迭代，旧版文档留作历史对比；文档修订不等于软件发布或模型验收。

后续项目协作先读 [AGENTS.md](AGENTS.md)。文档检查：`node scripts/product_docs.mjs check`；不可覆盖快照：`node scripts/product_docs.mjs snapshot 标签`。

当前文档依据：主 PRD R8（2026-09-21）。[功能工作台与真实验收](docs/technical/千问受控编排与功能工作台_2026-09-21.md)记录千问受控编排、基础编辑与三入口功能预览；旧阶段报告保留。真实验收使用3次语言+1次图片，专业/全案过度澄清问题修复后待复验。正式构图库、完整无限画布、视觉质量及生产上线尚未整体交付。

R9 入口拆分：前台 `http://127.0.0.1:3011/create`，专业编辑 `/editor`；内部后台 `http://127.0.0.1:3021/workbench`，不向商家开放。端口空闲时 `.venv/bin/python scripts/start_local.py` 启动 API/worker/前台/后台；不会自动停止其他服务。后台用户名 `admin`，密码读取本机 `runtime_logs/local-admin.key`，不提交或分享此文件。临时功能页不代表正式 Figma 审核完成，详见[拆分及安全边界](docs/technical/前台创作与内部后台拆分_2026-09-21.md)。

以下功能基线与启动说明最初整理于内部 v0.11.1：对话式一键生图、续作、区域化本地排字、五/三连图与 4:3 单图导出、全案批量授权及分项保存。最新实现状态按需求追踪及实际验证核对，不以该旧版本清单代替当前进度。

完整规则与验收边界见 [Input–Output PE 核对](docs/pe/Input-Output完整PE工程与交付核对_v0.11.1.md)。历史文档与 PE 快照不覆盖。

## v0.11.1 功能基线与历史边界

- 已实现：餐饮项目、菜单/门头及补充素材上传、素材角色/优先级/唯一主推图、图片基础校验、持久化分析任务、核心信息覆盖报告、最多3个问题、事实版本和确认。
- 已接入：百炼 OpenAI 兼容接口，包含图片 OCR、经营事实提炼、结构化校验、错误码和调用记录。
- 当前支持：20:3 五连图、12:3 三连图、Logo/套餐/券/菜品/宣传/装修/详情页 4:3 输出；全案默认券、五图、Logo。真实模型质量与延迟须另行验收。
- 当时暂缓：父子 Agent、构图模板库新建/扩充、无限画布。此排期已被主 PRD R3/R4 后续纳入要求更新，不再作为当前暂缓依据；平台发布、趋势采集、小程序不能据此视为已实现。
- 旧专业流程“开始整理门店信息”不会默认调用分析器；一键生图按界面的明确授权执行理解及生图，不能用旧分析器规则判断一键生图是否收费。
- `ANALYZER_MODE=mock`用于无密钥AI流程验收；切换为`bailian`后，用户主动选择AI辅助时才调用真实模型。

## 环境配置

复制`.env.example`为`.env`，密钥只填写在`.env`：

```bash
cp .env.example .env
```

真实模型验收至少需要：

```dotenv
ANALYZER_MODE=bailian
DASHSCOPE_API_KEY=你的百炼API Key
```

未配置 Key 时系统会返回`MODEL_CONFIG_MISSING`，不会自动伪造分析结果。

## 本地启动

### 一键生图（v0.11.1）

请从本仓库根目录分别启动 API、worker、前端三个进程，避免不同工作目录连接到不同 SQLite 数据库：

```bash
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8011
PYTHONPATH=backend .venv/bin/python -m app.worker
```

另一个终端进入 `frontend` 执行 `npm run dev -- --port 3011`，前端 API 地址为 `http://127.0.0.1:8011/api/v1`。
worker 会领取已经授权、尚未执行的队列任务，不会重试已停止或结果待核对的任务。新确认在 worker 不在线时返回 `WORKER_UNAVAILABLE`，不锁定创作也不入队。
以下 Stage 2B 说明属于早期流程；一键生图的当前实现包含长图生成与五图裁切。

历史 Stage 2B 的默认端口与当前一键生图不同。请勿同时从 `backend` 子目录再启动另一套数据库；统一使用上面的仓库根目录命令。后端接口文档：`http://127.0.0.1:8011/docs`。

本地回归（不调用真实付费模型）：

```bash
.venv/bin/python -m pytest backend/tests -q
```

前端：

```bash
cd frontend
npm run dev
```

访问 `http://127.0.0.1:3011`。API 与 worker 必须连接同一数据库；后台执行中断的未知调用不会自动重试。

## 测试

```bash
source .venv/bin/activate
cd backend
pytest -q
cd ../frontend
npm run typecheck
npm run build
```

本地默认使用SQLite便于验收；生产环境必须配置PostgreSQL `DATABASE_URL`。密钥只写入未提交的`.env`，仓库仅保留`.env.example`。
