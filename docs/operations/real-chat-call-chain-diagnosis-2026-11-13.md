# 真实聊天调用链耗时排查

日期：2026-11-13（Asia/Shanghai）。状态：原因已复现；业务修复尚未实施。

## 结论

验证实例 `work/real-chat-ready-20261112` 中，聊天失败发生在 LLM 调用之前。健康状态有效期为 30 秒，而刷新后的状态快照读取与来源校验耗时 50.68 秒，使刚采集的健康状态在校验时过期。`GoalRegulation.context` 因此抛出 `Forbidden`，拒绝思考。不是远端模型响应慢。

本次未提高活动预算、有效期或看门狗阈值，未削减高维特征、来源校验和权限保护，未操作旧的正式实例。诊断沿用验证实例既有身份与历史，未创建新身份。

## 实际调用链与计时

实际消息活动：`89e7ee884f98434d9d64dc68a95e8448`。

`认证聊天入口 → 入库/队列 → StrictEngine.process_one → think → prepare → _contexts → calculate → GoalRegulation.context → refresh → assess → States.snapshot → Forbidden`。

|阶段|实测耗时|
|---|---:|
|原始消息读取|0.022 秒|
|记忆召回|1.044 秒|
|会话关联|0.014 秒|
|高维特征读取与校验|14.366 秒|
|上下文计算及校验（以下子项包含在内）|150.860 秒|
|准备阶段总计|166.315 秒|
|LLM 调用|未进入，新增调用尝试数为 0|

上下文中的关键子项：

|子项|实测耗时|
|---|---:|
|计算前字段来源校验|8.908 秒|
|首次内部状态快照|38.714 秒|
|刷新检查时再次读取状态快照|39.625 秒|
|重新采集健康状态|10.472 秒|
|刷新后评估再次读取状态快照|50.680 秒|
|健康评估整体（包含上项）|52.160 秒|

嵌套阶段不能重复累加。以上为轻量函数入口/出口计时；此前详细 profiler 尝试带来较大额外开销，触发看门狗回滚，其时间不作为正常业务延迟。上一次未加诊断的账本记录为：高维特征 14.420 秒、上下文 151.800 秒，与轻量复现接近。

## 为什么会失败

`States.snapshot()` 遍历全部状态观测，对每条观测单独读取定义；在严格计算边界中，`DomainReadCollector` 同时采集与校验实际来源。一次思考里，该路径被初始状态、刷新检查、刷新后评估重复调用。当前仅有 15 条历史状态观测、8 个定义，因此不能简单归因为数据库数据量大；严格来源处理与重复读取是本次需优先处理的路径。

`StateCollector.collect()` 以 30 秒 TTL 记录健康状态。刷新后 `GoalRegulation.assess()` 再次调用 `States.snapshot()`，这次耗时 50.680 秒，超过有效期。最终拒绝原因是：

```text
goal deferred: state_missing_or_stale:R.disk_free_bytes,
state_missing_or_stale:F.sqlite_integrity,
state_missing_or_stale:F.restore_reconciliation_required,
state_missing_or_stale:W.queue_depth
```

异常位置：`digital_life/application/behavior/goal_regulation.py:135`。入口为 `tool_learning_contexts.py:153`，由 `tool_learning_engine.py:712` 调用。刷新和评估处于同一计算事务，拒绝后采集写入回滚；不能把未提交的采集当作已持久化健康记录。

## 另外两个已证实的问题

1. 队列任务失败，但活动状态仍为 `running`。严格准备失败发生在创建模型尝试之前；队列异常分支只结束 job，没有同步活动失败/延期状态。运行日志仅保存异常类型，面板无法展示实际失败理由。之前“等了十分钟仍在运行”的判断不准确；历史事件证明实际在约五分钟时已经失败，含前一任务排队时间。
2. 看门狗与长任务不协调。运行器只在 `process_one` 前后更新心跳；看门狗 180 秒未见心跳会终止进程并回滚。详细 profiler 的诊断轮发生 `heartbeat-expired`，回滚到上一版本。此行为是已存在设计在长任务中的风险，并非本次轻量复现的直接拒绝原因。

## 后续修复顺序

1. 先统一严格上下文和执行入口的实时健康证据来源，避免旧状态快照在重复来源校验后自然过期。保持原有健康阈值和有效期，不通过放宽保护解决。
2. 状态读取按每个定义选择实际最新观测；历史继续保留。一个只读检查阶段准备并核验一次来源材料，各用途仍分别检查授权；写入、撤销、边界变化后重新读取。
3. 准备失败同步记录活动可见状态和安全的失败原因，使聊天页能明确区分排队、处理、拒绝和失败。不得自动恢复已失败任务或重放模型。
4. 将进程存活心跳与业务进度区分；长任务仍受原有活动期限约束，不能用无限更新心跳掩盖卡死。
5. 上述修复后，仅重跑一条真实聊天；通过后再验证连续第二轮。本报告不声称聊天业务已通过。

## 证据

- `outputs/real-chat-attempt/health-call-chain-evidence.json`：轻量阶段计时与异常栈（不包含输入参数、令牌、密钥或模型正文）。
- `outputs/real-chat-attempt/previous-failure-timing.json`：上轮账本实际阶段耗时。
- `outputs/real-chat-attempt/health-timing.json`：实际消息及活动标识。

诊断由 `DIGITAL_LIFE_CALL_DIAGNOSTICS=1` 显式开启，默认关闭。高开销 profiler 已移除，只保留可选轻量分段记录。
