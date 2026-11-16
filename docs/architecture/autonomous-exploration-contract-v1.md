# 自主探索首版运行契约 AE-RUNTIME-1.0

冻结日期：2026-11-08（Asia/Shanghai）。作者：Codex 主 agent（/root）。  
状态：描述性首版基线冻结，不代表所有状态均有数据库强制约束。  
关联：[实现报告](autonomous-exploration-implementation.md)、[量化指标](../research/autonomous-exploration-metrics-v1.md)、[正式评测契约](../research/autonomous-exploration-evaluation-v1.md)。

## 1 冻结范围和变更规则

冻结当前状态语义、服务接口、模型 V2、事件 payload V1、调度和停止行为；源码及文档摘要见 [机器基线](autonomous-exploration-baseline-v1.json)。当前普通任务继续用模型 V1，SQL schema 仍为 2／3。本契约版本与工程发布版本、输出 schema 版本、事件 payload 版本互不等同。

冻结后，状态名、迁移语义、必需字段、请求身份、选择策略或停止规则的行为变动必须新建版本、列兼容影响并增加对应验证；不得只重算摘要掩盖差异。仅解释性修订应记录勘误，不自动表示旧评测仍适用。冻结不禁止修复缺陷；修复后的源码须形成新基线，旧结果留作历史。

优先顺序：当前用户指令与实例控制 → 本版本冻结行为及明确限制 → 实现报告 → 修改前提案。评测中的规范要求独立记录，不能倒推为运行代码已经具备。

## 2 对象、身份与连续性

| 对象 | 身份与关系 |
| --- | --- |
| 配置世代 | 每条 exploration.configured 的事件 ID；显式重新配置产生新世代、重置该世代活动额度并取消旧探索活动 |
| 问题 | SHA-256(' '.join(question.casefold().split()))；无 Unicode 归一化及语义去重；可跨活动保存 |
| 活动 | 既有 activities ID；绑定 discover 或 investigate；调查绑定一个问题 |
| 轮次 | 当前活动 exploration.observed 数量 + 1，属于逻辑派生值 |
| 思考请求 | thought:<activity>:<round>；后轮用 request_parent_id 指向前轮；请求包不可变 |
| 尝试 | 同一请求的独立 thought_attempt；失败重试不生成新轮次 |
| 工具观察 | action_results ID 去重，关联 evidence 和原始 receipt artifact |

问题可派生子问题，但不把系统产生的问题存为用户事实。internal 通道、self_actor 和 internal-trigger 标记必须保留。持久化以 runtime_events 及 artifact 为源，按 event_seq 取问题最后快照；不依赖供应商会话或模型隐藏历史。

## 3 三种状态必须分开

### 3.1 问题状态

| 当前状态 | 触发与条件 | 下一状态 |
| --- | --- | --- |
| 不存在 | 接受的模型候选通过引用校验、文本 ID 不重复、问题总量和父深度许可 | candidate（visits=0，立即到期） |
| candidate／dormant | 到期、visits<2、证据仍可读、调度选择 | investigating（visits+1，绑定新活动） |
| investigating | 模型 resolved + wait，至少引用上下文中的一条工具观察 | resolved（仅模型评估） |
| investigating | 模型 dormant + wait，visits<2 | dormant（300 秒后可再选择） |
| investigating | 模型 dormant + wait，visits>=2 | abandoned |
| investigating | 轮次耗尽、模型作业失败、观察失败／未知，经 pause | dormant 或 abandoned，取决于 visits 是否达到 2 |
| investigating | 后续 tick 发现关联活动 cancelled／failed／paused | dormant 或 abandoned；惰性同步，重新设 due_at=当前时间+300 秒 |
| investigating | configure 取消旧活动 | dormant、立即到期；即使 visits=2 也可能留下 dormant 标签，但选择条件仍会排除它 |
| resolved／abandoned | 文本相同的候选再次出现 | 不覆盖，不重置次数 |

没有 selected 独立状态，也没有自动重开 resolved 的路径。`record()` 是内部快照写入方法，没有集中式状态迁移校验器；上表描述公共流程产生的迁移，不声明数据库阻止所有非法状态写入。

### 3.2 活动状态

沿用 Engine.transition：pending → running／cancelled；running → waiting_input／waiting_tool／paused／completed／failed／cancelled；waiting_input、waiting_tool、paused 可回 running 或转 paused（原状态允许时）、failed、cancelled。终态 completed、failed、cancelled 不自动重开。

探索主路径：pending → running → waiting_input（审批）→ running（执行）→ 观察后新轮次 → completed 或 paused。`waiting_input` 仍兼有审批语义，不是独立探索休眠状态。discover 结束只表示问题发现活动完成，不表示生成的问题已解决。

### 3.3 调度显示状态

`status.scheduler_state` 仅为 disabled、budget-exhausted、enabled。enabled 不表示此刻可运行；用户工作、审批等待、实例锁、间隔、证据权限均可能阻塞。总活动额度耗尽只阻止创建新活动，不取消已创建的活动。

## 4 接口冻结

| 方法签名 | 输入／返回语义 | 副作用和限制 |
| --- | --- | --- |
| configure(actor, enabled, max_activities=12, max_rounds=3, interval_seconds=300) | 返回 status；非法类型／范围 ContractError，非控制者 Forbidden | 取消旧探索工作并写配置；不解锁、不启动模型 |
| config() | 未配置返回 enabled=False；已配置返回字段及 generation | 只读 |
| status() | configuration、activities_used、remaining_activities、scheduler_state、questions、inference_started=False | 只读；不是时间点一致性快照保证 |
| tick(engine) | 返回新 activity ID 或 None；锁定时可 Forbidden | 原子检查并创建活动；只能由已获授权运行的进程调用 |
| context(activity) | 非探索返回 None；否则 kind、round、max_rounds、question、recent_memories、observations、allowed_evidence_refs、instructions | 写记忆访问记录；由请求构造事务调用 |
| check_inputs(activity, payload) | 成功无返回；来源不可读或配置过期 Forbidden | 不调用模型 |
| validate_output(activity, payload, output) | 成功无返回；非法引用、动作组合或版本 ContractError | 只检查提案，不执行行动 |
| accept(engine, activity, payload, output, request_id) | 已处理返回结果字典；需进入工具授权链返回 None | 必须在结果接受事务内；不是外部可调用的授权入口 |
| observed(engine, activity, outcome) | 同 result 已记录则无操作 | 事务内记录观察、问题证据、input_epoch 和后续 think；失败则暂停 |
| pause(engine, activity, reason) | 无返回 | 记录问题休眠／放弃，适用活动转 paused |

辅助方法 events、payloads、questions、record、binding、round、observations、readable_refs 是内部投影接口，不是管理 API。CLI 冻结为 `exploration status|enable|disable` 及三个预算参数，复用 --data；本版无新增 HTTP／面板接口。

## 5 数据与输出契约

模型 V2 必须且只能有 schema_version=2、action、explanation、exploration。exploration 必须且只能有 candidates、disposition、assessment、evidence_refs；disposition 为 continue／resolved／dormant。assessment 非空且最多 2000 字符，explanation 最多 16000 字符。

候选必须含 question（非空，最多1000字符）、verification（非空，最多1000字符）、expected_gain 和 cost（有限数值0–1，拒绝布尔）、evidence_refs（1–4个不重复引用）。每次至多4个候选；评估引用0–8个。每个引用必须出现在 allowed_evidence_refs，不能仅凭“数据库存在”获得引用资格。

发现只允许 wait+dormant；调查 continue 只允许 read_file／list_files；调查 resolved／dormant 只允许 wait。V2 通用 schema 仍含其他工具变体，但探索语义校验会拒绝它们。不能把 schema 检查替代上下文语义校验。

事件 payload V1 的必需字段：

| 事件 | 必需字段（均另含 version=1） |
| --- | --- |
| exploration.configured | enabled、max_activities、max_rounds、interval_seconds |
| exploration.bound | activity、generation、kind、question_id（discover为null）、max_rounds、next_due |
| exploration.question | id、question、verification、expected_gain、cost、evidence_refs、state、parent_id、depth、visits、due_at、created_by、activity；后续可附assessment、stop_reason |
| exploration.assessed | request、assessment（完整exploration对象）、verification_status=model-assessed-not-independently-verified |
| exploration.observed | state、evidence、receipt、result；正常路径另有event，补齐已提交回执的路径可没有event |

注意 discover 返回的 questions 数量是提案数量，可能包含被去重或容量过滤的项；统计入库问题数必须比较问题事件，不能直接用该返回值。

## 6 调度与数值边界

顺序：启用与实例执行许可 → 无非终态且未暂停活动 → 本世代额度未满 → 最新绑定 next_due 已到 → 惰性同步问题 → 筛选问题并排序 → 新建调查或发现。候选 score=expected_gain-cost，同分按问题 ID 升序。分数是模型估计，不是实测知识增益。

| 参数／边界 | 冻结值 |
| --- | --- |
| max_activities | 默认12，整数1–100；本世代 discover、investigate 都计数，失败和取消不退还 |
| max_rounds | 默认3，整数2–3；达到末轮仍请求 continue 时暂停、不再观察 |
| interval_seconds | 默认300，整数60–86400；从创建活动时设 next_due，不是完成后冷却 |
| 问题再调查 | visits<2，due_at已到，证据可读；休眠通常300秒 |
| 候选容量／父深度 | 全实例最多256个问题；父深度>=3不再派生，根深度0 |
| 每活动预算账户 | token_limit=rounds×3×4096，attempt_limit=rounds×4，tool_call_limit=rounds |
| 每请求尝试／预留 | 最多3次，每次预留4096 tokens； settled及usage_unknown仍计入额度 |
| 近期记忆 | 最多4条；先从最近24条、每条<=1200字符且active的记录中过滤权限 |

token 预留不代表实际输入／输出或计费。预算表 time_limit_ms、活动 deadline 字段的存在不等于已实现整个探索活动的硬墙钟截止；本版不能据此宣称“600秒必停”。请求本身有接受期限，工具和模型适配器各有超时。

## 7 停止、等待和恢复条件

| 条件 | 作用范围与实际行为 | 恢复条件 |
| --- | --- | --- |
| 已评估解决 | 问题resolved、活动completed | 不自动恢复 |
| 模型休眠／轮次耗尽／观察失败或未知／模型作业失败 | 活动paused，问题dormant或abandoned | 新活动重新调查，需到期、次数、总额及权限许可 |
| 本世代额度耗尽 | 不再创建活动；现有工作可结束 | 控制者显式新配置，不自动重置 |
| 未到期、存在等待审批／用户工作 | 不新建活动，属于等待 | 条件解除 |
| 引用来源撤权或修订 | 调度排除问题；请求发送及接受时检查，失败可暂停 | 明确恢复可读来源或新问题，不自动替换旧证据 |
| 用户取消活动 | activity取消，相关think工作取消；问题标签可能暂留investigating | 后续调度可同步，但不取消整个探索配置 |
| disable／重新configure | 旧探索活动取消；拒绝旧世代新推理／执行，返回结果可标stale | 显式enable形成新世代 |
| 用户停止／WAKE_DISABLED／恢复待协调锁 | 阻止新的运行步骤；不删除历史 | 遵循已有控制面恢复流程 |
| 工具已发出后停止 | 不保证撤回在途动作，保留回执或unknown，不自动重放未知副作用 | 人工／证据协调 |

停用探索不等于终止 Runtime；用户停止 Runtime 不等于清空问题。跨运行世代：已提交观察可用于新请求；旧世代已准备请求须经原有保守恢复流程处理。Executor成功回执已提交而Engine未消费时，可补齐观察而不重放工具。

## 8 已知限制登记（不是通过声明）

- K01：问题迁移未集中强制校验，外部调用内部record可绕过状态机；本契约不授权这种调用。
- K02：取消后的问题投影惰性同步；tick先遇到额度或活动阻塞可能不立即清理。判断停止应先看活动／配置，而非只看问题state。
- K03：现有时间记录不能证明每种并发竞态都在停止提交后阻止新派发；需要评测器时间边界和竞争测试。已在途调用不算新派发。
- K04：没有完整活动墙钟硬截止；不能承诺固定停止延迟；时间限额属于后续工程项。
- K05：resolved仅模型评估；没有独立验证器、长期兴趣学习或实测信息收益评分。
- K06：事件投影读历史、文本去重及工作区感知的规模与能力有限；完整回执超过上下文上限会拒绝，不自动截断。
- K07：SQL版本兼容不等于旧二进制能理解探索；回退须停止并协调，未完成旧二进制接管验收。

冻结检查验证摘要、接口和文档完整性，不会把这些限制变成已修复项。发现实际行为与本文不同应登记缺陷并版本化修订。
