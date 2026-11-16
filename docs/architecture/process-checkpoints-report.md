# 原初00自身进程管理与应用检查点 V0.1

2026-11-15。状态：已部署、原实例已启用、实际检查点及备份校验通过。

## 实现范围

进程管理器位于外部 CLI/Deployment/watchdog 控制面。旧程序已经停止后，新部署启动前保存一致应用备份，并将以下对象关联：源码 Git 提交、发布 manifest hash、deployment id、历史进程登记、配置及数据库 schema、事件序号、队列概况和未确认动作数。

采用 SQLite Backup API 和已有 backup_bundle 保存数据库与所引用工件，通过 backup.created 登记，沿用既有受管备份的隐私清理路径。检查点不保存 Codex 凭据、账号认证数据库或任意 OS 线程内存。当前为原实例 native schema2/3 路径；受保护来源/学习存储需要专用检查点适配器，不以本功能绕过原 schema4 保护。

源码版本从已验证的 release 目录归档进私有 Git，不盲信工作目录当前 head。发布大工件由宿主内部归档，不扩大模型文件读取上限。Git提交和完整发布manifest共同标识发布内容，Git树还可含非发布文件。

## 自动回退

- 新进程准备失败、激活后启动失败、后续进程退出或原有健康心跳检查失败时，沿原 Deployment 回退到上一已核准且兼容当前数据库的版本。
- 自动回退关联更新前的 checkpoint id，记录失败部署、恢复部署、是否重启、状态恢复策略。
- 保留当前身份、记忆、权限、预算、已接受结果和工具回执，不用旧数据库覆盖新账本。
- 在途动作标记未确认，运行中任务暂停、租约清理；不重放可能已经发生的副作用，不把预算恢复成未使用。
- 用户明确停止、禁止唤醒锁仍优先；不因健康恢复擅自解除。
- 数据库版本不兼容时停止并报告，不自动降库或降低保护。

健康诊断现在能显示进程恢复功能及最近检查点；模型仍不能直接启停自身。部署、启动和手动回退维持 CLI 权限边界。

## 这与“线程快照”的区别

本版是应用状态检查点与旧版程序重启，不是把 Python 线程堆栈、寄存器或网络连接恢复到某条指令。OS级方案如 [CRIU](https://github.com/checkpoint-restore/criu)面向 Linux；本项目当前 macOS 实现采用持久化任务状态。参考 [SQLite Backup API](https://www.sqlite.org/backup.html)。

检查点中保留实际旧数据库及工件备份，但自动回退不将它写回正式库；需要全库历史恢复时，仍走已有显式恢复与外部副作用核对流程。不能把“创建了快照”说成已经实现任意线程原样恢复。

## 验证

- 检查点、watchdog及自我维持相关39项通过，35.724秒。
- 最终4项核心测试通过，1.574秒：Git绑定/快照持久化/篡改拒绝、候选失败回退且保留更新后记忆、任务暂停且预算不重置、外部效果已发生但回执丢失时不重放不退款。
- 两项真实子进程故障注入通过，8.283秒：仅终止临时实例自有候选，分别模拟准备前失败和实际激活后失败，均恢复旧进程并关联检查点。
- 一项真实进程显式停止测试通过，3.740秒：用户停止不触发自动重启。
- 仅使用本机模型清单替身，无真实模型调用，未向正式实例注入故障。

首次小测试发现无账号系统的实例被错误要求提供账号上下文，已改为显式区分已安装账号与原本无账号路径，最终验证通过。

## 正式实例记录

- 当前部署：`1e0af29bc0ae45d481ea26bbabaf7cc4`，PID 1665，运行中。
- 检查点：`d70b95148e8947768dc5270fdbc23bbc`。
- 对应上一部署：`64e9ac355742497a93f6c73ad1c5b4c5`。
- 上一部署 Git 版本：`119d0368c63e49c384c483881abb0ffc2cbfd39e`。
- 当前部署 Git 版本：`a014029cdc99ad9f2f977908d53ed56c63fe3636`。
- 实际备份与所有引用文件的校验通过；部署模块与当前源码一致。

检查点元数据位于实例 process-checkpoints，受管数据备份位于 work/process-snapshots 下。每次更新会产生完整应用备份，V0.1没有自动清理历史备份；列表只展示最近30项，不表示旧项已删除。不要手动删已登记备份后仍假定恢复点可用。

## CLI 操作

在项目目录执行：

```sh
# 查看状态和最近检查点，不停止实例
python3 -m digital_life --data work/primordial00-first-wake process-manager status
python3 -m digital_life --data work/primordial00-first-wake process-manager list

# 手动检查点：先正常停止并等待退出，再执行
python3 manage.py stop
python3 -m digital_life --data work/primordial00-first-wake process-manager checkpoint

# 只验证回退目标和备份，不启动，不覆盖数据库；需要已停止
python3 -m digital_life --data work/primordial00-first-wake process-manager rollback \
  --checkpoint CHECKPOINT_ID --verify-bundle

# 明确启动目标旧程序并持续监督，保留当前账本；不会解除禁止唤醒锁
python3 -m digital_life --data work/primordial00-first-wake process-manager rollback \
  --checkpoint CHECKPOINT_ID --start
```

正常 `manage.py start/wake` 部署路径已接入自动检查点，不需要每次手工创建。手动 rollback 的 --start 需要保持终端打开；Ctrl+C 停止。

## 证据

- `outputs/project-tools-review/process-checkpoint-tests.log`
- `outputs/project-tools-review/process-checkpoint-final-core.log`
- `outputs/project-tools-review/checkpoint-real-process-tests.log`
- `outputs/project-tools-review/checkpoint-user-stop-test.log`
- `outputs/project-tools-review/process-manager-formal-state.json`

## 部署验收更新（2026-11-15）

原实例已额外启用一次独立思考验收，新版本通过后才放行普通任务。回退已知可用版本时不重复调用模型。当前实现与正式证据见 `deployment-thought-gate-report.md`。此前部署号及PID是当时记录。
