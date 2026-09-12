# 团绘AI

当前实现范围：Stage 2B“素材语义标注 → 对话优先收集 → 按需百炼识别 → 缺口追问 → 事实确认”纵向切片。

## 当前边界

- 已实现：餐饮项目、菜单/门头及补充素材上传、素材角色/优先级/唯一主推图、图片基础校验、持久化分析任务、核心信息覆盖报告、最多3个问题、事实版本和确认。
- 已接入：百炼 OpenAI 兼容接口，包含图片 OCR、经营事实提炼、结构化校验、错误码和调用记录。
- 未实现：成图、Logo、品牌介绍图、20:3画布、五图裁切、平台发布、趋势采集、小程序。
- 默认“开始整理门店信息”不会调用模型；只有用户明确选择“AI辅助识别”才读取`ANALYZER_MODE`并调用分析器。
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

### 一键生图（v0.9.3）

请从本仓库根目录分别启动 API、worker、前端三个进程，避免不同工作目录连接到不同 SQLite 数据库：

```bash
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8011
PYTHONPATH=backend .venv/bin/python -m app.worker
```

另一个终端进入 `frontend` 执行 `npm run dev -- --port 3011`，前端 API 地址为 `http://127.0.0.1:8011/api/v1`。
worker 会领取已经授权、尚未执行的队列任务，不会重试已停止或结果待核对的任务。新确认在 worker 不在线时返回 `WORKER_UNAVAILABLE`，不锁定创作也不入队。
以下 Stage 2B 说明属于早期流程；一键生图的当前实现包含长图生成与五图裁切。

后端（Python 3.11+）：

```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --port 8000
```

前端：

```bash
cd frontend
npm run dev
```

访问 `http://localhost:3000`，后端接口文档位于 `http://localhost:8000/docs`。若端口被占用，可将后端改为`8011`并以`NEXT_PUBLIC_API_BASE=http://localhost:8011/api/v1`启动前端。

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
