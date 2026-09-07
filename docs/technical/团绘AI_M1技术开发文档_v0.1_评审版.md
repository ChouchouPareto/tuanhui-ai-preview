# 团绘AI M1 技术开发文档 V0.1｜输入、补问与首页确认

> 2026-09-08｜待评审、未开发。配套：[技术手册](团绘AI_技术手册_v0.1_评审版.md)、[PRD V0.8](../../团绘AI_PRD_v0.8_项目化创作与商业闭环评审版.md)。

## 一、阶段目标

在现有一键生图首页输入素材/自然语言，复用项目事实，集中补缺口，确认一次有效快照后交给生成入口。专业创作保留分步流程但复用同一规则。

产物：需求Schema、统一缺口服务、首页补问/确认切片、持久确认记录、安全交接适配器、测试报告。明确不做：装修全案、新产物生图引擎、完整图层编辑、收费/自动赔付、生产部署。M1通过不表示五图美术质量已达标。

## 二、技术适配摘要

采用纵向切片；现有 Next/TypeScript 和 FastAPI/Pydantic/SQLAlchemy/Alembic；不迁移CSS、不新建前端、不引入向量库或多Agent。新增长任务使用持久任务＋轮询；不等待到M3才考虑新任务的恢复。

## 三、技术栈与模型

规则提取覆盖明确标签、用户回答和项目已确认值；模糊自由文本可经授权调用百炼结构化理解，候选复用现有 qwen3-vl-plus，通过 INTAKE_MODEL 配置并在冒烟后冻结。图像OCR沿用现有契约，只有必要且已获授权才调用。无Key时手填/mock可开发，但自然语言真实理解不可标验收完成。

模型结构化返回产物/事实候选/引用/冲突，不自行决定收费、最终就绪状态或覆盖长期记忆。

## 四、环境与配置

延续项目 .venv（实查3.12.14）、现有npm锁依赖和3011/8011本地端口；不使用系统Python3.9。实际数据路径与端口必须开工时重新核实，现有服务不擅自关闭。

新配置拟包括 INTAKE_MODEL、INTAKE_TIMEOUT_SECONDS、INTAKE_MAX_ATTEMPTS、AI_INTAKE_ENABLED；默认禁用未经授权的真实调用。预算策略不存在时服务端拒绝付费整理。用户验收前需提供安全配置好的Key和测试预算，本轮不读取Key值。

启动命令在开发时依据实际工作目录更新README；不用改变cwd导致新建空库的方法“修复”数据。测试单独使用临时DB与文件根。

## 五、目录职责（拟定，不创建代码）

- backend/app/schemas.py：新增输入、缺口、确认请求/响应模型，避免与旧FactUpdate强制字段耦合。
- backend/app/services/intake.py：需求合并、缺口计算、来源管理。
- backend/app/services/prompts/intake.v1.txt：独立提示词及正反例。
- backend/app/services/creation_confirmation.py：修订校验、快照、幂等交接。
- backend/app/models.py 与 alembic/versions：新增创作/输入修订/确认记录的增量迁移。
- frontend 现有首页及共享组件：集中补问、确认卡、继续创作恢复，不另建应用。
- backend/tests：新增intake/confirmation/兼容/恢复用例；前端补关键交互测试。

## 六、数据、资产与状态

拟定 schema_version=1。Creation：UUID id/project_id，mode枚举oneclick/pro，output_type枚举（本阶段只开放five_panel），revision整数，status枚举。IntakeRevision：输入文本、asset_ids、display_flags、字段候选、来源、冲突、缺口、创建时间。Confirmation：唯一幂等键、revision、snapshot_hash、授权范围、预算策略版本、accepted_at。

show_price:boolean；hero_price可空，展示价格时才校验数值/币种或明确合法套餐文本。展示店名由display_flags决定；素材role和usage由服务端校验，不信任客户端自称renderable。

规则合并顺序：本次明确回答覆盖本次旧候选；与已确认事实冲突则提示范围；项目记忆为候选默认值；模型推测不得覆盖已确认字段。本次变更默认仅本次。

状态：DRAFT→NEEDS_INPUT/READY_TO_CONFIRM→CONFIRMED。任何修改revision递增并使旧确认不可用于新输入。理解异步任务单独PENDING/RUNNING/SUCCEEDED/FAILED/RECONCILING，重启不能盲目重发未知供应商请求。重复问题以稳定field/question_id去重。

确认记录与待交接事件同一事务写入；交接幂等键绑定confirmation_id，后台重复领取也只能关联同一个有效生成任务。M1若暂不完成此最小安全交接，则只验收到“可确认草稿”，不能声称已直达可靠生成。

旧事实/方案版本保留；新快照不回写覆盖旧任务。迁移先备份和副本演练。新建资料无需店名时用内部项目占位标题，不把占位标题印入成品。

## 七、API设计（全部为拟新增，非已存在）

统一前缀 /api/v1；下表路径中的 p 为project_id、c 为creation_id。响应均经Schema验证。

| 方法/路径 | 请求 | 响应/校验 |
|---|---|---|
| POST /projects/{p}/creations | mode,output_type | 201 creation_id,revision,status；不支持产物422 |
| POST /projects/{p}/creations/{c}/intake-runs | expected_revision,text,asset_ids,answers,display_flags,use_ai | 202 task_id,new_revision；同请求幂等返回原任务；未授权AI拒绝 |
| GET /tasks/{task_id} | 无 | 保留现有查询，新增intake类型结果含revision和错误，不破坏旧任务返回 |
| GET /projects/{p}/creations/{c}/review | 无 | revision,candidates,gaps,conflicts,ready,selected_assets,summary；最终ready由规则决定 |
| POST /projects/{p}/creations/{c}/confirm | expected_revision,snapshot_hash,accepted_budget_policy | 200 confirmation_id,status,task_id或待交接状态；必须Idempotency-Key |

确认前服务端重新计算缺口、核验资产存在/归属/快照；变更409 STALE_REVISION；缺口409 INPUT_INCOMPLETE；素材不合法422 ASSET_NOT_ELIGIBLE；预算缺失409 BUDGET_NOT_AUTHORIZED；不存在/无访问权404；模型错误503 MODEL_UNAVAILABLE。响应不含内部路径、Key或堆栈。

use_ai=false不走供应商调用。不能通过confirm绕过付费授权，也不能仅禁用前端按钮。轮询应按错误/退避策略停止，无限失败轮询不可当恢复。

旧专业入口使用原路由，内部逐步委托同一规则服务；旧规则需兼容已有存档，不要求用户为看历史再次补资料。M1交接需消除门头必传/价格必填的旧生成门槛，否则新首页只是假放行。

## 八、Prompt设计

intake.v1输入：本次文本、授权项目摘要、候选素材角色及已确认字段；输出固定JSON，禁止返回私有推理。正例：用户说“不标价格”→display_flags.show_price=false、hero_price=null；反例：把“暂未定价”当成品文案或编造99元。图像内“忽略规则”等只作数据。

服务端解析常见JSON围栏后进行严格Schema及来源校验；无法解析只有限修复，业务事实冲突不靠重试消除。缺失字段由规则层计算，不能直接相信模型ready=true。

## 九、最小真实交互

保留固定上传区域和分类归属；补问放首页输入框下，建议每批不超过3个必要项，已回答不重问。确认卡展示产物/项目/素材/事实/不展示项/风格与费用；如规则尚未启用显示不可执行原因，不显示0积分伪报价。

确认后进入任务查看；继续创作建立新Creation，保留同项目素材候选，不恢复旧任务占据输入。浏览器返回/刷新按creation/task参数区分对象。专业入口仍有上一步，不改成一键流程。验收桌面与手机宽度下的补问和确认，不扩大视觉改版范围。

## 十、测试要求

mock：完整输入零重复补问；不标价格；只有门头；纯文字老项目；纯文字新项目缺菜品；错项目素材；已删除素材；文本/图片冲突；不支持产物；非法模型JSON；use_ai=false零外部调用；无预算；重复确认；旧revision确认；确认后更改输入；任务中断与未知响应；专业流程与旧历史读取兼容。

真实：至少一条授权自由文本理解→持久化→首页可确认；涉及OCR契约变更再测真实图；如本阶段改变生成交接，再测真实菜品→确认→模型→保存→可下载。共享契约可复用证据但须说明覆盖；记录实际模型、版本、耗时、成本、首轮/修复后结构合规及人工判断。无预算、Key或未跑必须标待验。

新增API既要离线测试，也要界面端到端验证；测试库/上传路径必须隔离，不用真实data目录。真实性和审美由人工判定，不能只用HTTP200作为成功。

## 十一、产品负责人验收清单

- [ ] 上传真实菜品并写清需求，不再重复问已提供的信息。
- [ ] 写“不展示价格”，确认卡及最终交接文案都不强求价格。
- [ ] 只传门头时，明确要求补真实菜品，门头不会变成成品素材。
- [ ] 在旧项目只输入文字，可以选择复用该项目素材，能看清用了哪些图。
- [ ] 菜名和图片有冲突时，生成前让我确认，不先付费生图。
- [ ] 首页完成补充后只需一次有效生成确认；重复点击不新建两次任务。
- [ ] 刷新保留输入和确认状态；修改资料后不能误用旧确认。
- [ ] 继续创作保留旧作品，新的输入不被旧结果顶回去。
- [ ] 专业创作仍能分步返回，上一次的作品仍可下载。
- [ ] 报错会说明下一步怎么做，没有密钥、路径或程序堆栈。

## 十二、风险与待确认

理解调用在最终生图确认之前有费用，必须先确定产品承担或用户授权的预算。现有README、旧生成必填与PRD不一致，需要联动修改而非只改首页。多用户授权未完成不得公开真实数据服务。纯文字主题产物/直接发布/赔付均不由本阶段擅自开放。

## 十三、下一阶段交接

M1通过后交付：版本化输入快照、确认ID、合格素材清单、来源及可追踪交接任务、双层测试报告。M2直接编译这些快照为DesignSpec，不再重新追问相同字段。未通过项明列，产品负责人通知后才能进入下一阶段。
