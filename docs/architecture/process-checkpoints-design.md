# 自身进程管理与应用检查点 V0.1

2026-11-15，实施设计。

## 目标与恢复含义

将源码Git版本、部署manifest、运行进程和持久化工作状态绑定。新部署失败或已部署进程失去健康时，重启上一兼容、已核准版本，并以当前持久化账本恢复安全队列。不是操作系统线程寄存器/堆内存快照；不保证从任意Python指令续跑。

每次版本切换前，必须没有旧运行进程登记。使用既有 registered backup_bundle 保存SQLite一致快照和引用工件，附绑定元数据（旧deployment、release hash、对应Git提交、schema/config、任务/队列/未确认动作概况、历史process id）。检查点只在完成备份和元数据写入后登记可用。

默认回退旧代码，保留当前身份、记忆、权限、预算和工具结果。不会拿旧数据库覆盖新数据库来“抹掉”外部副作用。未知动作/未确认模型调用暂停核对，不重放，不恢复已用预算。全库历史恢复沿用已有显式恢复流程，本版不自动把它等同线程恢复。

## 控制面

新增CLI：process-manager enable/disable/status/checkpoint/list/rollback。

- 设置与checkpoint要求进程已停止；启动授权仍按现有CLI。
- rollback指定checkpoint只验证并说明目标；显式 --start 才启动并监督目标程序，尊重禁止唤醒锁。
- 正常启用后，Deployment在更新前自动保存旧版本checkpoint，并绑定目标版本的Git提交。watchdog回退日志关联checkpoint；所有原有schema4兼容与来源保护继续执行。
- 版本绑定从验证过的release目录读取，存入私有Git对象库；不盲信工作目录当前head。完整发布manifest hash单独保留。大于文件编辑上限的发布工件只由宿主发布流程归档，不扩大模型读取权限。
- 旧版本不兼容当前数据库时停止并报告，禁止自动降库。

备份位于实例目录外的受管 work/process-snapshots 中，经 backup.created 登记，沿用已有隐私清理路径。检查点控制元数据放在实例 process-checkpoints，用户文件工具不可访问。

## 最小验收

临时实例验证checkpoint持久化、Git/manifest绑定、部署失败自动回退、未知动作不重放和预算不重置、用户停止不重启、快照篡改/错误实例拒绝。尽量复用既有实际进程失败测试，所有故障注入只在临时目录，不故意弄坏正式实例。完成后在原实例启用并创建一个实际检查点。

SQLite一致快照参考：[SQLite Backup API](https://www.sqlite.org/backup.html)。备份完整性不等于外部世界也能倒退。
