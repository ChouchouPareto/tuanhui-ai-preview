# 团绘AI · PE工程备份与审核入口

## 当前收尾版本 v0.11.1

- [完整 Input–Output PE、输出标准及逐项边界](Input-Output完整PE工程与交付核对_v0.11.1.md)
- [当前源码 PE 只增不覆盖快照](backups/20260912T174056.385597Z_v0.11.1-output-continuation-closeout_ffe04193.md)
- [最终批量防重与取消回归后的快照](backups/20260912T174503.832592Z_v0.11.1-final-batch-guard_83044c78.md)

父子 Agent、构图模板库扩充与无限画布按本轮要求暂缓。离线测试通过不代表真实模型视觉质量或耗时已通过人工验收。

## 阶段实现 v0.10.2

- [续聊、计时、文字检查与未完成项](续聊计时与文字检测_阶段记录_v0.10.2.md)
- [本阶段运行 PE 快照](backups/20260912T155856.048440Z_v0.10.2-continuation-timing-text-guard_b12ee846.md)
- [Figma 案例构图拆解审核文件](https://www.figma.com/design/3NScJVMCFE33Ec7lI5iVyW)

素材拆解以「素材案例/来源：稿定设计」为指定来源。目前第一张案例拆解稿，不代表全量构图库已经审核启用；近五次模板去重、创意文案路由和真实提速验收尚未完成。

## 完整工作流审核 v0.10.1

- [Input—Output完整PE工程、行业分类与实现差距](Input-Output完整PE工程与类目架构审核_v0.10.1.md)
- [本次核对的运行PE快照](backups/20260912T144108.700545Z_v0.10.1-workflow-audit_32510519.md)

v0.10.1为审核文档版本：运行PE没有改动。明确区分一级/二级行业、输出类型、构图、风格与案例；附现行提示词原文。后续模板可视化整理必须进入独立Figma文件，本轮未创建模板或Figma文件。历史文件与备份保留。

## 本轮版本

- [优化前 v0.9.8 源码约束快照](backups/1789215067014_v0.9.8_优化前.md)
- [优化后 v0.10.0 完整PE与约束快照](backups/20260912T123304.675466Z_v0.10.0-after_475c7d20.md)
- [12套构图区与实际组装PE示例](构图模板与PE审核_v0.10.0.md)
- [本轮变更与未完成项](变更说明_v0.10.0.md)

历史快照只增加、不覆盖、不参与运行。优化后的快照包含逐文件SHA256，便于对比。
实际运行入口位于 backend/app/services/prompts 的Markdown PE、layout_catalog.py，以及调用它们的服务。

## 后续每次修改

修改前与修改后分别执行：

    .venv/bin/python scripts/backup_pe.py --label 版本号-before
    .venv/bin/python scripts/backup_pe.py --label 版本号-after

脚本使用UTC时间戳、版本标签、唯一编号和排他创建模式，即使标签相同也不会覆盖旧文件。
每轮另建版本化变更说明，列出规则变化、调用位置、测试结果和剩余限制；不得把计划事项写成已实现。
