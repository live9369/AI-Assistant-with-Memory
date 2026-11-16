# IM05 预算账本详细设计

日期：2026-11-09；状态：隔离实现设计；依据 TL-LOOP-0.1。仅实现新学习工作的预算端口，不接模型、Runtime 或当前实例。

## 原账户与持久化

`make_work_budget(budget, source_budget=None)` 生成 `TL-WORK-BUDGET-1` 文档：`budget` 为绑定新学习账户的完整子 Budget，`source_budget` 保留原准入预算，`ledger` 初始为 `{reservations:{},halted:false,violations:[],last_seen_at:null}`。C0 同事务将该文档存入学习 activity.budget_json，并将相同 budget/source_budget 及原 time_limit_ms 放入 tl_work.conditions 工件。每次读写核对不可变工件中的原值，不能因请求、恢复、重开服务或表示版本变化替换上限。

输入/输出 token、工具、尝试、scan/items/bytes，以及账户 time_limit_ms 的 elapsed_ms，全部在同一原工作账本累计。模型/工具预留同时保存既有 budget_reservations 技术记录；纯本地读取在命名账本保存 retrieval 类型，不伪装成模型或工具尝试。token_limit 另核 input+output 总额。预留文档明确区分 reserved、entry 与 actual，预留存在不表示已进入回调或产生消费。

独立连接通过 BEGIN IMMEDIATE 串行化。同一事务更新 budget_json 账本与 activity_budget_accounts.revision CAS；不改变 activity.revision/input_epoch，避免准备后的请求因预算记账而自行失效。原 work/account/activity 的绑定、conditions 字节、上限与技术账户不符则拒绝；旧预算服务不接入新工作。

父账户的 C0 分配由工作装配服务原子登记，不能仅复制父上限制造新额度。本模块只管理已经完成分配的唯一子账户，不回收父分配；后续释放/重新分配须另有具名协议。

## 接口与授权

`ToolLearningBudget(store, authority=None, clock=utc)` 只使用可信组合根提供的连接。独立 `BudgetAuthority` 默认拒绝 `verify_budget`、`verify_entry` 和 `verify_settlement`。三者分别接收完整工作/原预算/请求预算/操作阶段、可信实际入口见证，以及待结算的完整预留和 actual；无独立确认不释放预留。JSON 中的 module、sent、entered 或 authorized 标记都不能授予权限。

`check_work(work_id, request_budget=None)` 是只读快照：返回原账户、各维剩余量和阻断原因。它检查本地工作终态/暂停、活动取消、原期限、未知用量、已知超额、账户与原 caps。本地 WAKE_DISABLED、user_stopped 通过 Store.assert_execution_allowed 只读核对并报告 instance_stopped；权限、源屏障与真正派发边界由后续可信权威核对；未接线时默认拒绝所有修改与入口见证，不把合成测试授权当成生产许可。

`reserve(entry, work_id, operation_ref, kind, amounts, request_budget=None, reservation_key=None)` 原子检查原额度与本次阶段上限。kind 为 thought_attempt/tool_attempt/retrieval；前两种分别明确预留一次模型尝试/一次工具，读取类型不增加模型或工具计数。相同键同义返回原预留，同键异义拒绝；同一个真实模型/工具 attempt 的稳定身份只能绑定一个预留，改键不能重复计调用。操作必须是真实技术行并属于 learning activity，伪造精确 revision 拒绝。预留和实际入口提交前重核权威与最新本地状态；未知用量不允许通过新键绕过。

`record_entry(entry, work_id, reservation_id, witness)` 需要独立可信权威确认实际进入，不能从预留或 sent 推断；不会调用 callback。生产见证接线留 IM06/IM11，合成测试只验证账本。

`settle(entry, work_id, reservation_id, actual)` 中 actual=None 表示用量未知，保留原预留并阻断新派发。实际结算必须提供全部八维明确值，缺项不按零填充；无真实入口不能报非零消费。已知超额仍保存事实与违规并停止后续预留，不把超额改为零或丢弃。原未进入预留仅可经独立权威确认后释放；已进入不能“释放未消费”。重复结算同义幂等、异义拒绝；已知事实不可被未知覆盖。停止/取消/到期后的在途事实仍可登记；时钟倒退不回写 last_seen_at，保留已知消费、记录违规并阻断。

## 隔离验收

全新 schema3 合成夹具加载 IM03 增量，仅使用明确标注的机械授权器；正例只在此新目录临时解除停止/唤醒锁，未启动任何生命周期进程或回调，退出时夹具停止并重锁。负例分别检查 user_stopped 与 WAKE_DISABLED。覆盖独立维度耗尽、共享总额、并发最后额度、相同/异义重放、真实入口与预留区别、unknown 保守保留、已知超额落盘、取消/期限/终态、重开服务、caps 篡改与账户错配。无网络、模型、真实工具、部署、唤醒或当前实例读取。

## 旧路径与嵌套边界

C0 在普通父 activity.budget_json 增加 `tl_work_allocations={contract:"TL-WORK-ALLOCATIONS-1",caps:父Budget,allocations:{work_id:{activity_id,account_id,budget:子Budget}}}`。旧 scheduling.Budget.reserve 在原事务中保守扣除所有永久子分配的 token/tools/attempts；带分配文档的共享父账户若任一旧预留为 usage_unknown，则阻断新的旧路径预留，直到有明确核对；不能只保守扣原预留后继续消费。无分配文档的既有活动行为不变。旧 reserve/settle 遇 TL-WORK-BUDGET-1 子活动则拒绝，不能绕过统一账本。旧路径不声称支持 scan/items/bytes。

本轮不支持学习活动继续作为父账户分配孙工作；C0 与子预算读取均拒绝该嵌套情况，避免遗漏祖先占用。纯本地读取记录只在统一账本，模型/工具记录同时与技术预留逐字段核对；任意缺失/多余旧记录都会阻断。

## 隔离自检结果

`PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest tests.test_tool_learning_budget -q`：31 项通过。包括实际入口与预留区别、全维消费与未知、commit 撤权/停止回滚、时钟倒退保留、独立连接竞争最后额度、工具实际决策链归属、旧路径双花封口及正常旧活动保持。合成 technical attempt 与 witness 均只是账本夹具，不表示发生了真实模型或工具回调。统一证据由 root 生成，本文件不修改任务状态。
