# IM05 工作、预算与协调状态实施报告

日期：2026-11-09；版本：V0.1；状态：本项完成，隔离验收通过。冻结契约 TL-LOOP-0.1 不变。

本轮先补详细设计，再将工作/协调与预算账本分给两个子 agent 实现，另由独立子 agent 只读复核。只使用全新合成实例，未读取或操作当前实例，未部署、迁移或启用数据库版本4。

## 已交付

- 主设计：docs/architecture/tool-learning-im05-design.md。
- 预算设计与字段映射：docs/architecture/tool-learning-im05-budget-design.md。
- 工作与协调：digital_life/application/tool_learning_work.py。
- 八维预算：digital_life/application/tool_learning_budget.py。
- IM04具名C0扩展：digital_life/infrastructure/persistence/tool_learning_store.py。
- 旧路径防双花：digital_life/application/scheduling.py，仅识别新增命名账本时收紧。
- 专项测试：tests/test_tool_learning_work.py、tests/test_tool_learning_budget.py。

## 实现结果

C0在同一个主库事务内完成父额度分配、内部信号、独立学习活动、预算账户、工作、命令及结果；任何必要写点失败全部回滚。内部信号保留认证入口的生产者及原来源，不走用户输入路径，不创建思考队列或记忆编码。

相同来源/加工身份跨命令键复用原工作，不再分配账户；请求说明文字或自报来源修订不能充当新的观察。原账户、期限和完整上限持久绑定，恢复或新请求不能刷新它们。不同真实来源即使字节相同也不自动合并。

TL-WORK-BUDGET-1在现有activity.budget_json保存input_tokens、output_tokens、attempts、tool_calls、scan、items、bytes、elapsed_ms账本；原caps及time_limit_ms与不可变conditions工件核对。模型/工具项同时映射既有budget_reservations；本地检索只记资源，不伪造成模型/工具尝试。独立连接通过主库事务和账户revision进行原子竞争，预算记账不改语义activity.revision/input_epoch。

父TL-WORK-ALLOCATIONS-1记录永久子分配。可信权威返回的分项向量是首次封存的TL子分配池，不是从旧总token记录自动重建的历史分项实耗。父物理tokens/tools/attempts另扣旧预留和全部子分配；旧预算入口也尊重该分配。共享父未知消费时拒绝新增分配/预留，旧入口不能绕过新学习账户账本。没有这些命名账本的普通旧活动保持原行为。

预留、可信入口见证、已知实耗与未知消费分别记录。缺失实耗字段不能补零；未知保留占用并阻断。释放需要完整结算上下文及可信核验，不能仅凭未记录entry就断言零消费。已知超额仍保存实际值并阻断；时钟倒退不抹掉已知事实或刷新边界。

状态变更通过固定意图工件进入幂等指纹，执行CAS并核状态/阶段配对，不能普通重开waiting/blocked/failed/stopped或增加review_round。最后一次合法尝试耗尽后，可在不新增消费且终点证明有效时记录零成本状态事实；新派发仍被拒绝。停止、取消、期限、未知和撤权在提交前重查。

## 统一验收

**198项通过，零失败、零错误、零跳过，源文件在验收期间稳定。**

| 检查 | 通过项数 |
| --- | ---: |
| IM05工作与协调专项 | 29 |
| IM05预算专项 | 31 |
| IM04存储回归 | 31 |
| IM03 SQL回归 | 31 |
| 进度、架构与既有任务计划 | 19 |
| 既有离线系统集成 | 29 |
| 隔离故障/进程竞争 | 3 |
| 目标调节回归 | 25 |

证据：outputs/acceptance/tool-learning/im05.json，其摘要已绑定任务状态账本。工作专项包含C0各必要写点/提交故障回滚、并发一次分配、来源完成态、原子父分配、取消/停止提交重检和最后一次尝试边界；预算专项包含各维耗尽、独立连接竞争、未知/超额、完整释放证据、旧路径封口和原期限。

正例只对新合成夹具临时允许控制状态；没有启动正式实例或生命周期运行进程。合成attempt行和见证只是账本夹具，未调用真实模型/工具或网络；相关既有回归使用确定性替身。夹具退出后重新停止、加锁并关闭连接。

## 支持边界与下一步

真实来源解析、M12权限/屏障、实际调用见证和业务终点核验使用默认拒绝端口，尚未接入Runtime。当前不宣称真实派发或整个学习链已经贯通。

本项拒绝嵌套TL父账户、未经明确分配的再加工，以及外部来源的本地FK绑定；保留来源而不伪造新身份或预算。实际受控恢复、复核轮次推进仍属IM13。旧历史输入/输出/扫描分项没有被虚构成已采集结果。

任务进度已标记IM05完成。下一项为 **IM06：依赖登记、F1屏障和最终门禁基础**，本轮未展开IM06，也未执行当前实例操作。
