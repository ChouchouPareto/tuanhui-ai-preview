# 团绘AI Stage 1技术开发文档｜素材到事实确认

> 版本：V0.1  
> 日期：2026-08-28  
> 实现状态：Mock纵向链路已完成，真实模型冒烟待验  
> 配套：PRD V0.6、技术适配声明V0.1、技术架构方案V0.1  

## 一、阶段目标

打通“创建项目→上传菜单/门头→异步分析→覆盖报告→最多3个缺口问题→事实版本→人工确认”的纵向闭环，并确保任务和确认状态可恢复。

本阶段不做真实OCR/多模态效果、生图、Logo、20:3画布、裁切、导出、平台发布、趋势采集和小程序。

## 二、技术适配摘要

- 开发路径：纵向切片；
- 后端：Python 3.12本地运行，代码目标兼容3.11+；FastAPI、Pydantic、SQLAlchemy、Alembic、pytest；
- 前端：Next.js 16.3.3、React 19、TypeScript；
- 生产数据库：PostgreSQL；本地与自动化测试因本机无PostgreSQL暂用SQLite；
- 长任务：持久化任务记录+FastAPI后台执行，启动时恢复PENDING/RUNNING分析任务；
- 模型：`ANALYZER_MODE=mock`，真实模型尚未选型和验收。

## 三、环境与配置

`.env.example`包含：`DATABASE_URL`、`UPLOAD_DIR`、`ANALYZER_MODE`、`MAX_UPLOAD_MB`、`ALLOWED_ORIGINS`。密钥未进入前端、仓库或日志。

后端默认端口8000；本次验收因8000已被其他服务占用，使用8010。前端默认3000。

## 四、项目结构

```text
backend/app/
  api.py                 Stage 1 API
  main.py                FastAPI入口与任务恢复
  models.py              项目、素材、事实、追问、任务模型
  schemas.py             Pydantic请求结构
  core/                  配置与数据库
  services/analysis.py   Mock分析、覆盖判断、恢复
  services/storage.py    上传与图片校验
backend/alembic/          数据库迁移
backend/tests/            Stage 1自动化测试
frontend/app/             统一Web/WAP纵向页面
```

## 五、数据与状态

已实现表：`store_projects`、`source_assets`、`business_fact_versions`、`clarification_rounds`、`workflow_tasks`。初始迁移位于`backend/alembic/versions/`。

Stage 1项目状态：`DRAFT → ASSETS_UPLOADED → ANALYZING → NEEDS_CLARIFICATION → NEEDS_FACT_CONFIRMATION → FACTS_CONFIRMED`。

事实修改创建新版本；只能确认当前最新版本；店名、定位、主推内容未齐时禁止确认。

## 六、API

- `POST /api/v1/projects`
- `GET /api/v1/projects/{id}`
- `POST /api/v1/projects/{id}/assets`
- `POST /api/v1/projects/{id}/analysis-runs`
- `GET /api/v1/tasks/{id}`
- `GET /api/v1/projects/{id}/coverage`
- `POST /api/v1/projects/{id}/clarifications`
- `POST /api/v1/projects/{id}/fact-versions`
- `POST /api/v1/projects/{id}/fact-versions/{version}/confirm`

## 七、Mock分析契约

Mock不会伪造OCR结果。项目创建时填写的门店名作为`project_input`证据；门店定位和主推内容保持缺失，由覆盖判断生成最多3个问题。用户回答作为`user_clarification`证据写入新事实版本。

真实模型接入前需要新增：图片输入契约、证据区域、置信度、模型版本、费用和结构校验；不得把Mock测试标记为真实效果验收。

## 八、上传安全

- 仅接受JPEG、PNG、WEBP MIME；
- 限制单文件大小；
- Pillow验证真实图片内容；
- 对象路径由服务端项目ID/资产ID生成，不使用用户文件名拼路径；
- 保存SHA-256、真实尺寸、字节数和清晰度警告。

## 九、测试结果

后端pytest：5项通过，覆盖完整闭环、必传素材、非法上传、未补齐禁止确认、任务恢复。

前端：TypeScript检查通过；Next.js生产构建通过；npm审计0漏洞。

真实模型冒烟：待验，原因是尚未确定模型厂商、Key、数据边界及授权样本。

PostgreSQL迁移验证：迁移文件已生成；本机无PostgreSQL服务，真实PostgreSQL升级/回滚测试待验。

## 十、当前已知限制

1. 尚无账户登录、租户权限和审计事件；当前只能本地单环境验收；
2. FastAPI BackgroundTasks适合Stage 1小规模验证，不是最终生产队列；
3. 启动恢复能处理未完成分析任务，但尚无多Worker租约和抢占锁；
4. 前端轮询使用短延迟后读取覆盖报告，后续需按任务状态持续轮询；
5. 没有真实OCR、模型效果、费用与时延数据；
6. 本地使用SQLite与Python 3.12，生产目标仍为PostgreSQL和Python 3.11+兼容。

## 十一、产品验收步骤

- [ ] 打开统一Web/WAP页面并创建餐饮门店项目；
- [ ] 分别上传菜单图和门头图，低分辨率图片能看到警告；
- [ ] 未上传两类必传素材时，系统不允许分析；
- [ ] 分析后只出现缺失问题，每轮不超过3个；
- [ ] 补充定位和主推内容后，系统显示可以确认；
- [ ] 信息未补齐时不能确认；
- [ ] 确认后显示`FACTS_CONFIRMED`；
- [ ] 刷新页面或重启后端后，数据库中的事实和任务仍存在。

## 十二、进入真实模型接入前需要确认

1. Stage 1是否锁定餐饮；
2. 允许上传至哪家中国大陆可用模型服务；
3. 提供模型Key和至少10组授权样本；
4. 原始图片与事实数据保存期限；
5. 是否接受当前页面作为Stage 1正式纵向切片继续迭代。
