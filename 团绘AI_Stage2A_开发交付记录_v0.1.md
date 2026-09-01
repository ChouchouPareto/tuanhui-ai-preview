# 团绘AI Stage 2A 开发交付记录 v0.1

日期：2026-08-31

## 1. 本次交付结论

本次按《团绘AI PRD v0.7 竞品启发优化版》和《AI产品 Vibe Coding 通用技术栈手册》实施 Stage 2A，完成“素材语义标注—素材分析—信息缺口追问—经营事实确认”的可运行版本。

本次没有进入五图生成、Logo 生成、品牌介绍图生成、20:3 长图编排和平台发布，这些仍属于后续阶段。

## 2. 已完成能力

- MVP 行业范围限定为餐饮。
- 支持菜单、门头、招牌菜、菜品、环境、Logo、资质和其他素材角色。
- 支持素材优先级和项目内唯一主推图。
- 提供素材列表接口和素材元数据修改接口。
- 核心事实增加“真实卖点”，与门店名称、定位、主推项共同构成确认门槛。
- 默认品牌官方表达视角，并为后续店主推荐、食客种草视角预留数据结构。
- 接入百炼 OpenAI 兼容接口：图片 OCR、经营事实提炼、JSON 结构校验、可控错误和模型调用记录。
- 未配置密钥时明确失败，不静默切换 Mock，不把模拟结果冒充真实 AI 结果。
- 前端完成素材用途、优先级、主推图标记、素材清单和事实卡片展示，并适配窄屏。

## 3. 数据库变更

- `source_assets`新增：`semantic_role`、`priority`、`is_hero`。
- 新增`model_call_records`，记录供应商、模型、契约、耗时、Token 和错误码。
- Alembic 版本：`9f4c8e2a1d7b (head)`。

## 4. 验证结果

| 验证项 | 结果 |
|---|---|
| Python 编译检查 | 通过 |
| 后端自动化测试 | 8 passed |
| 空数据库 Alembic 升级 | 通过，升级至 `9f4c8e2a1d7b` |
| TypeScript 类型检查 | 通过 |
| Next.js 生产构建 | 通过 |
| 后端健康检查 | `status=ok, stage=2A` |
| 前端本地 HTTP 检查 | 200 OK |
| 百炼真实图片调用 | 待填写`.env`中的`DASHSCOPE_API_KEY`后验收 |

## 5. 本地验收方式

默认 Mock 流程：

```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm run dev
```

真实百炼分析：复制`.env.example`为`.env`，填写`DASHSCOPE_API_KEY`，并设置`ANALYZER_MODE=bailian`。密钥不得写进`.env.example`、Markdown、截图或版本库。

## 6. 后续建议

下一阶段先用真实门店的菜单图、门头图做一轮百炼效果与成本验收，确认 OCR 字段稳定性、事实提炼准确率和错误恢复，再进入版式 DSL、20:3 长图及五图裁切，避免把未经确认的经营信息带入成图链路。
