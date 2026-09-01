# 团绘AI Stage 2A技术开发文档｜素材语义化与真实分析接入

> 日期：2026-08-31  
> 配套：PRD V0.7、技术适配声明V0.2、AI产品Vibe Coding通用技术栈手册  
> 本文档只覆盖Stage 2A，不提前实现图片生成与平台发布。

## 一、阶段目标

交付“创建餐饮项目 → 上传并标记素材角色/优先级 → 异步分析 → 门店事实卡 → 最多3个缺口问题 → 人工确认”的完整纵向切片。

阶段产物：

- 可管理语义角色、优先级和主视觉的素材API与页面；
- 百炼真实分析适配器、mock适配器和模型调用审计；
- 包含主推卖点与表达视角的门店事实卡；
- 数据迁移、自动化测试、README和真实冒烟说明。

明确不做：千问/豆包生图、20:3母版、五图裁切、Logo、品牌介绍图、ZIP导出、平台发布、趋势采集、小程序。

## 二、技术适配摘要

- 开发路径：纵向切片；
- 延续现有模块化单体，不整体重构；
- 本地SQLite、生产PostgreSQL目标不变；
- 长任务采用持久化任务+轮询；
- 真实模型缺Key时不阻塞编码与mock测试，只阻塞真实冒烟验收。

## 三、技术栈与模型

- 后端：Python 3.11+目标，当前项目虚拟环境Python 3.12；FastAPI、Pydantic、SQLAlchemy、Alembic、httpx、pytest。
- 前端：Next.js 16、React 19、TypeScript；延续现有CSS。
- OCR默认模型：`qwen-vl-ocr-2025-11-20`，通过配置覆盖；不使用漂移的`latest`。
- 视觉语义模型：通过配置`BAILIAN_VISION_MODEL`指定；默认`qwen3-vl-plus`，上线前锁定可用快照。
- API：百炼华北2 OpenAI兼容`chat/completions`；Base URL与Key必须来自同一地域/计费方案。

## 四、环境与配置

新增配置：

```env
ANALYZER_MODE=mock
DASHSCOPE_API_KEY=
BAILIAN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
BAILIAN_OCR_MODEL=qwen-vl-ocr-2025-11-20
BAILIAN_VISION_MODEL=qwen3-vl-plus
MODEL_TIMEOUT_SECONDS=60
```

`ANALYZER_MODE=bailian`且缺少Key时，任务以受控错误失败，不回退到伪造的mock结果。

本轮验证端口：后端8011、前端3011，避免占用已有3000/8000服务。

## 五、项目结构

- `backend/app/services/model_gateway.py`：百炼HTTP适配、错误分类、调用元数据；
- `backend/app/services/prompts/`：OCR/门店事实提取Prompt；
- `backend/app/services/analysis.py`：mock/百炼分派与事实合并；
- `backend/alembic/versions/`：Stage 2A字段和调用记录迁移；
- `frontend/app/page.tsx`：素材角色/优先级、事实卡和表达视角；
- `backups/2026-08-31_pre_stage2/`：开发前备份，不进入应用运行路径。

## 六、数据、资产与状态

`source_assets`新增：`semantic_role`、`priority`、`is_hero`。

`model_call_records`保存：供应商、模型、契约、状态、耗时、Token数量、错误分类、任务ID和时间；不保存Key、完整Prompt、图片Base64或完整菜单正文。

事实版本新增受控字段：`selling_points: string[]`、`expression_view: brand_official|owner_recommendation|diner_seed`、`restaurant_category`、`brand_color`。

Stage 2A沿用项目状态机；真实模型失败时任务进入`FAILED_FINAL`并保留错误码，项目回到可重试的`ASSETS_UPLOADED`。

## 七、API设计

- `GET /api/v1/projects/{id}/assets`：返回素材及语义元数据；
- `POST /api/v1/projects/{id}/assets`：增加`semantic_role`、`priority`、`is_hero`表单字段；
- `PATCH /api/v1/projects/{id}/assets/{asset_id}`：修改角色、优先级和主视觉；
- 现有分析、覆盖、补问、事实版本和确认接口保持兼容；覆盖报告新增主卖点缺口。

错误码：`MODEL_CONFIG_MISSING`、`MODEL_AUTH_FAILED`、`MODEL_RATE_LIMITED`、`MODEL_TIMEOUT`、`MODEL_BAD_OUTPUT`、`MODEL_UPSTREAM_ERROR`。

## 八、Prompt设计

- OCR Prompt：只转写菜单/门头中可见文字并返回JSON，不根据常识补全；给出合法JSON正例，禁止Markdown围栏和解释文字。
- 视觉事实Prompt：只基于OCR文本和项目输入提取餐饮子类、定位、主推候选与卖点；无证据返回`null`或空数组。
- 解析器：先解析原始JSON，再兼容Markdown围栏和首尾说明中的首个JSON对象；最终使用Pydantic校验。字段超量属于质量告警，不以无限重试处理。

## 九、验收界面

在现有Web/WAP页面增加：

- 必传和可选素材统一上传；
- 可见标签、优先级和“设为主视觉”；
- 提交后的加载、成功和错误反馈；
- 门店事实卡展示主推卖点与表达视角；
- 移动端单列布局、44px以上触控目标、可见焦点与状态文字。

## 十、测试要求

mock自动化覆盖：

- 非餐饮项目拒绝；
- 素材角色/优先级/唯一主视觉；
- 模型JSON宽容解析和坏输出拒绝；
- 缺主卖点时仍阻止确认；
- 表达视角受控；
- 百炼缺Key、超时、鉴权和上游错误映射；
- 原Stage 1流程回归。

真实冒烟：用户填写`.env`后，以至少一组授权餐饮菜单和门头调用百炼，记录模型版本、耗时、Token、结构首测合规情况和事实卡结果。没有Key时明确标记待验。

## 十一、产品验收清单

- [ ] 创建项目时行业固定为餐饮；
- [ ] 上传菜单和门头时可以看到素材角色、优先级和主视觉；
- [ ] 同一项目只能有一个主视觉；
- [ ] 未上传菜单和门头不能开始分析；
- [ ] 分析后门店事实卡显示店名、定位、主推内容、主卖点和表达视角；
- [ ] 缺失问题每轮不超过3个；
- [ ] 主卖点未补齐不能确认；
- [ ] 确认后刷新页面数据仍存在；
- [ ] `ANALYZER_MODE=mock`时页面明确标注mock；
- [ ] `ANALYZER_MODE=bailian`完成至少一组真实端到端冒烟后，才可标记真实模型通过。

## 十二、风险与待确认项

- 当前缺少`.env`，真实模型冒烟待验；
- Base URL和Key不配套会返回401，必须由同一百炼地域/计费方案提供；
- 公开网络样本只用于内部PoC且需保留来源，不作为训练集或商业模板；
- 数据保留期限尚未确认，因此本阶段不实现自动删除策略，只保持可追溯与不跨项目复用。

## 十三、交接给下一阶段

完成后，下一阶段可直接复用已确认事实卡、素材语义和模型调用审计，开始五图方案/Prompt确认及千问默认、豆包失败切换的图片生成网关。

