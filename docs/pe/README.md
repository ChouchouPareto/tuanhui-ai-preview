# 团绘AI · PE工程备份与审核入口

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
