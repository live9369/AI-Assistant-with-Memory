# 第二阶段数据库增量字段设计

| 属性 | 内容 |
| --- | --- |
| 版本 | V1.0 |
| 状态 | 增量设计完成 / 尚未同步到生成器、SQL 和迁移 |
| 依据 | 系统运行契约 V1.0；数据库逻辑架构 V1.0 |
| 范围 | 独立思考、审批、异步结果、取消、唤醒、初始化与发布 |

## 1 版本边界

本设计经[第二阶段一致性复审](phase-2-architecture-consistency-review.md)修订；其中关于版本、世代、休眠交接与执行结果的更具体规则优先。

database/ 中的 Runtime 160张业务表和 Supervisor 6张表仍是已生成的旧物理基线。本文是下一数据库版本的完整增量设计。旧测试结果仅适用于原 SQL，不用于本文新增结构。本轮不编写或执行新的 DDL。

新增 Runtime 表沿用 id:TEXT、instance_id:TEXT、recorded_at:UTC TEXT、schema_version:INTEGER>=1。id 全局唯一；每个外键除明确例外外，使用 (instance_id,target_id) 绑定目标实例。新增控制库表不使用 Runtime 外键，其 instance_ref 是协议标识。

下文“必填”表示 NOT NULL；“可空”表示存在明确未产生或不适用状态；不以空字符串代替未知。UTC 时间采用固定毫秒精度的 RFC3339 格式。JSON 列由 schema_version 对应的接口模型校验。所有新表的业务外键默认 RESTRICT、延迟到事务提交检查。

## 2 独立思考

### 2.1 thought_requests

| 字段 | 类型／可空 | 含义与约束 |
| --- | --- | --- |
| activity_id、step_id | TEXT，必填 | activities 与 activity_steps；步骤必须属于该活动 |
| request_key | TEXT，必填 | 调用方幂等键；实例内唯一，相同键不同请求哈希应冲突 |
| purpose | TEXT，必填 | infer、plan、evaluate、verify、reflect |
| task | TEXT，必填 | 本次明确思考任务 |
| instruction_version | TEXT，必填 | 请求构造规则版本 |
| output_schema_version | TEXT，必填 | 预期响应结构版本 |
| request_artifact_id | TEXT，必填 | artifacts；实际发出的完整内容工件 |
| request_hash | TEXT，必填 | 规范化请求摘要，不含密钥 |
| input_manifest_hash | TEXT，必填 | 精确输入清单摘要 |
| model_config_id | TEXT，必填 | configuration_versions；引用供应商、模型及能力配置 |
| generation_config | JSON，必填 | 本次采样、输出长度及结构化输出配置 |
| prepared_activity_revision | INTEGER>=0，必填 | 构造时的活动修订；运行元数据改变不自动使思考失效 |
| expected_input_epoch | INTEGER>=0，必填 | 相关输入代次 |
| expected_policy_epoch | INTEGER>=0，必填 | 权限边界代次 |
| deadline | UTC TEXT，必填 | 请求失效时间 |
| token_budget、attempt_limit | INTEGER>0，必填 | 本次总预算与尝试上限 |
| retry_policy | JSON，必填 | 可重试错误、退避与总时限 |
| state | TEXT，必填 | prepared、running、succeeded、failed、cancelled、superseded |
| accepted_result_id | TEXT，可空 | thought_results；只允许属于该请求的 accepted 结果 |
| state_revision | INTEGER>=0，默认0 | CAS 与状态历史 |

另增 runtime_epoch:INTEGER>=0、process_run_id:TEXT、model_version_id:FK model_versions 均必填；request_parent_id、supersedes_request_id 为可空同表外键。新输入或纠错提示产生新请求，不能修改同一请求再称重试。

task、配置、输入清单与哈希在 prepared 发布后不可改；需变更时新建请求。state、accepted_result_id 仅由协调器通过专用事务更新。succeeded 必须有 accepted_result_id；其他状态不得有。请求与结果相互引用通过延迟复合外键解决，不能引用另一请求的结果。

### 2.2 thought_request_inputs

| 字段 | 类型／可空 | 含义与约束 |
| --- | --- | --- |
| request_id | TEXT，必填 | thought_requests |
| ordinal | INTEGER>=0，必填 | UNIQUE(request_id,ordinal) |
| role | TEXT，必填 | observation、memory、goal、commitment、personality、value、context、state、tool_result、instruction |
| object_revision_id | TEXT，可空 | object_revision_registry，版本对象 |
| object_id | TEXT，可空 | object_registry，引用不可变观测或活动产物 |
| artifact_id | TEXT，可空 | artifacts，本次临时内容 |
| content_hash | TEXT，必填 | 本次实际选取内容的摘要 |
| locator | JSON，必填 | 使用原始内容的哪个范围 |
| selection_reason | TEXT，必填 | 为什么进入本次请求 |

三个来源外键恰有一个非空。可变对象必须提供版本引用或冻结内容工件；不能只保存会随时间变化的“当前对象”指针。请求工件才是发出内容的权威证据，引用清单用于来源与依赖追踪。

### 2.3 thought_attempts

| 字段 | 类型／可空 | 含义与约束 |
| --- | --- | --- |
| request_id | TEXT，必填 | 请求 |
| attempt_no | INTEGER>0，必填 | UNIQUE(request_id,attempt_no) |
| state | TEXT，必填 | queued、sent、received、timeout、failed、cancelled |
| queued_at | UTC TEXT，必填 | 入队 |
| sent_at、finished_at | UTC TEXT，可空 | 尚未发送或结束时为空 |
| provider_request_id | TEXT，可空 | 远端诊断 ID，仅用于诊断，不作会话续接 |
| error_code | TEXT，可空 | 传输、限流或供应商错误 |
| usage_json | JSON，可空 | 远端报告的 token、费用和耗时；未知不记0 |
| dispatch_token | TEXT，必填 | 本地一次尝试标识，实例内唯一 |

一次请求允许多次远端计算，但只接受一个正式结果。没有 provider_request_id 不代表请求未送达。

### 2.4 thought_results 与 thought_state_events

| 表 | 字段及类型 | 约束 |
| --- | --- | --- |
| thought_results | request_id:TEXT、attempt_id:TEXT、response_artifact_id:TEXT、response_hash:TEXT、received_at:UTC TEXT，均必填 | attempt 必须属于 request；原始响应不可由结构校验覆盖 |
| thought_results | parsed_artifact_id:可空TEXT、validation_errors:JSON、validation_state:valid/invalid/pending | 有效解析指向独立结构化结果工件 |
| thought_results | acceptance:pending/accepted/stale/duplicate/rejected、reason_code:可空TEXT、accepted_at:可空UTC TEXT | 对 request_id 建 accepted 条件唯一索引；accepted 必须 valid 且 accepted_at 非空 |
| thought_state_events | request_id:TEXT、transition_no:INTEGER>0、from_state:TEXT、to_state:TEXT、reason_code:TEXT、result_id:可空TEXT | 单调转换历史，与请求状态同事务提交 |

结果接受事务核对 input_epoch、依赖版本、运行世代、取消、期限和相关授权，并以事务读取的当前 activity revision 做 CAS。prepared_activity_revision 用于来源追踪，不要求它与接收时版本始终相等。accepted_result_id、accepted 结果及请求 succeeded 状态原子提交。

## 3 活动、取消与恢复

新增 activity_budget_accounts：activity_id 唯一、revision、token_limit、tool_call_limit、attempt_limit、time_limit_ms、cost_limit_minor(可空)、currency(可空)。上限均非负；有成本上限必须有币种。

新增 budget_reservations：activity_id、operation_ref、operation_kind(thought_attempt/tool_attempt)、reservation_key(活动内唯一)、reserved_tokens、reserved_tool_calls、reserved_attempts、reserved_cost_minor(可空)、state(reserved/settled/released/usage_unknown)、actual_usage:可空JSON、reserved_at、settled_at(可空)。所有预留在账户 CAS 事务内检查余额，网络超时但远端可能发生用量时标为 usage_unknown 并保守保留额度，不直接释放；后续按账单或明确结算政策处理。计算步骤的剩余时间从单调计时得出，不通过数据库记录假装得到精确 CPU 使用量。

activities 新增字段：revision:INTEGER>=0 默认0、input_epoch:INTEGER>=0 默认0、deadline:可空UTC TEXT、cancel_requested_at:可空UTC TEXT、cancel_reason:可空TEXT、predecessor_activity_id:可空FK activities、publication_state:constructing/ready/quarantined。predecessor 不允许自环或闭环。

新增 activity_state_events：activity_id、transition_no、from_state、to_state、cause_event_id(FK runtime_events)、expected_revision、reason_code 均必填；转换号实例活动内唯一。修改活动状态、revision 及 history 在同一事务完成；input_epoch 只在影响本活动输入的事件被正式接受后推进。

activity_steps 新增 input_manifest_hash、idempotency_key、started_at、finished_at、accepted_output_ref、expected_activity_revision。允许部分可空以表达尚未开始；幂等键活动内唯一。恢复不直接把 running 步骤视为未执行，先按步骤类型核验模型结果、外部动作或事务提交状态。

jobs、outbox 和 consumer_receipts 的租约均增加 lease_generation:非负INTEGER。领取或接管时 generation+1，结果提交和续租必须同时匹配 owner、token、generation 与未过期条件；不能仅凭任务 ID 提交。这是数据库写入的 fencing，不宣称能撤销已经发生的外部副作用。

jobs 和 consumer_receipts 同时显式新增 lease_token:可空TEXT；lease_owner、lease_expires_at 沿用或新增为可空字段。outbox 已列 lease_token。三者领取状态必须四项齐备，接口统一使用 lease_expires_at（旧 jobs.lease_expiry 迁移改名）。

取消请求先持久化，后停止后续调度。活动 cancelled 后依然允许关联实际外部结果的记账事件，但不重新推进任务。恢复终态活动必须创建新活动并引用 predecessor。

## 4 动作提案、审批与执行

### 4.1 action_intents 修改

新增 state（proposed、awaiting_approval、authorized、queued、dispatching、running、succeeded、failed、partial、unknown、cancelled）、proposal_revision:INTEGER>=0、lifecycle_revision:INTEGER>=0、arguments_hash:TEXT、required_capability_id:FK capability_definitions、resource_scope:JSON、deadline:可空UTC TEXT。

原 grant_version 字段调整为可空，并在新逻辑名称中改称 grant_id；迁移保留兼容读取映射。proposed／awaiting_approval 可以为空。candidate、工具、参数和范围形成提案后固定；参数变化创建新提案并使旧审批失效。现有“只能引用已定稿选中候选”约束保留，它不等于已经获准执行。

approval_requests 新增 proposal_revision、arguments_hash、tool_id、required_capability_id、expires_at、requested_by、decision_by、revision。其中 requested_by 必填，decision_by 在 pending 时可空。审批和授权绑定 proposal_revision；动作状态推进只改变 lifecycle_revision，不能让批准自动失效。

### 4.2 action_authorization_records

| 字段 | 类型／可空 | 含义与约束 |
| --- | --- | --- |
| intent_id、grant_id | TEXT，必填 | 动作与 grants |
| approval_request_id | TEXT，可空 | 广泛授权模式可不产生逐项审批 |
| proposal_revision | INTEGER>=0，必填 | 绑定不可变提案版本 |
| arguments_hash | TEXT，必填 | 绑定参数 |
| scope_snapshot | JSON，必填 | 本次允许的作用范围 |
| policy_epoch | INTEGER>=0，必填 | 检查时边界版本 |
| issued_at、expires_at | UTC TEXT，必填 | 执行凭据时间窗口 |
| revoked_at | UTC TEXT，可空 | 本地撤销 |
| state | TEXT，必填 | valid、revoked、expired、consumed |

时间窗口、提案版本、工具要求与 grant 能力必须一致。消费含义为一次执行开始凭据已使用，不代表长期授权失效；重试需要重新经过门禁，不能重放已消费凭据。

新增 action_state_events：intent_id、transition_no、from_state、to_state、cause_event_id、attempt_id(可空)、reason_code，保存未知到核实、取消和失败历史。attempts/results 仍分别保存物理尝试和实际结果。

### 4.3 policy_epochs、outbox 和执行尝试

policy_epochs：instance_id 唯一，epoch:INTEGER>=0、policy_version_id、last_change_event_id、updated_at 均必填。授权授予、撤销、模式切换在同一事务推进 epoch，作为失效通知；它不是替代细粒度授权检查的万能版本号。

outbox 新增 authorization_record_id:可空FK、lease_owner:可空TEXT、lease_token:可空TEXT、lease_expires_at:可空UTC TEXT、attempt_count:INTEGER>=0、last_error:可空TEXT。仅 pending 状态且拥有有效授权的动作可领取；leased 状态必须有完整租约。意图与可发送 outbox 同事务创建不再是无条件规则：先完成审批，随后绑定授权并创建投递记录。

action_attempts 新增 authorization_record_id、policy_epoch、execution_token_hash、arguments_hash、backend_operation_id(可空)、start_gate_at(可空)、cancel_requested_at(可空)。实际开始必须有门禁记录，执行令牌一次使用。grant 能力、对象范围与参数应在 Runner 接收时复验。

## 5 持久事件、消费者与界面补读

### 5.1 runtime_events

| 字段 | 类型／可空 | 含义与约束 |
| --- | --- | --- |
| event_seq | INTEGER>0，必填 | UNIQUE(instance_id,event_seq)，SSE 补读顺序 |
| event_type、source | TEXT，必填 | 事件种类和来源命名空间 |
| source_event_id | TEXT，必填 | UNIQUE(instance_id,source,source_event_id) |
| correlation_id | TEXT，必填 | 跨步骤活动关联标识 |
| causation_event_id | 可空FK runtime_events | 直接起因；只允许较早序号，避免因果环 |
| activity_id | 可空FK activities | 输入尚未建立活动时可空 |
| lane | TEXT，必填 | control、result、work、telemetry |
| payload_object_id／payload_artifact_id | 可空FK，二选一 | 模块对象或临时材料 |
| payload_hash | TEXT，必填 | 去重请求的内容校验 |
| occurred_at | 可空UTC TEXT | 来源时间未知时保留未知 |
| received_at | UTC TEXT，必填 | 系统接收时间 |
| authority_ref | 可空FK social_actors | 系统内部事件可以无外部主体，但 source 必须明确 |

source 去重只返回原接收结果，相同键不同内容拒绝。event_seq 在短写事务分配，不依赖进程内计数。payload 仅引用权威内容，感知原文仍在 perception_signals 对应工件。

### 5.2 consumer_receipts 与 consumer_offsets

consumer_receipts：consumer_name、consumer_version、event_id、state(pending/processing/processed/dead_letter)、attempt_count、lease_owner(可空)、lease_expires_at(可空)、last_error(可空)、processed_at(可空)，UNIQUE(instance_id,consumer_name,consumer_version,event_id)。业务变更和 processed 同事务提交。

consumer_offsets：consumer_name、consumer_version、lane、last_event_seq、updated_at，UNIQUE(instance_id,consumer_name,consumer_version,lane)。该位置仅表示该 lane 中已连续处理的适用事件边界；不能因为处理了高序号事件就跳过低序号未完成事件。

调度按 lane 优先级处理控制和结果事件，避免长任务阻塞取消和授权。失败事件有限重试后进入 dead_letter，推进需要明确处置记录，不能静默丢弃；重放业务计算不能重放外部副作用。

## 6 控制面交接

### 6.1 Runtime supervisor_commands

command_key:实例内唯一TEXT、kind(set_wake/clear_wake/request_maintenance/request_deploy)、schedule_generation:可空INTEGER>=0、payload:JSON、payload_hash:TEXT、state(pending/sent/acknowledged/rejected)、attempt_count:INTEGER>=0、next_attempt_at:UTC TEXT、ack_control_command_id:可空TEXT、acknowledged_at:可空UTC TEXT、last_error:可空TEXT。

set_wake/clear_wake 必须有 generation；任务变更、generation 更新、指令入库同事务。需要 instance_wake_state 表保存 instance_id 唯一、desired_generation、acknowledged_generation、desired_due_at(可空)、acknowledged_due_at(可空)。未同步时禁止自动进程休眠。

### 6.2 Supervisor control_commands

| 字段 | 类型／可空 | 约束 |
| --- | --- | --- |
| id、instance_ref、source、command_key | TEXT，必填 | UNIQUE(source,instance_ref,command_key) |
| kind | TEXT，必填 | start、stop、resume、set_wake、clear_wake、deploy、rollback、maintenance |
| payload、payload_hash | JSON／TEXT，必填 | 同幂等键不同摘要拒绝 |
| generation | 可空INTEGER>=0 | 唤醒类必填 |
| authority_kind、authority_ref | TEXT，必填 | user 或 runtime_service；只允许各自明确能力 |
| state | TEXT，必填 | received、running、succeeded、rejected、failed |
| result_json、error_code | 可空JSON／TEXT | 执行结果与失败原因 |
| received_at、finished_at | UTC TEXT，结束可空 | 可恢复工作流 |

ack 表示命令已被接受并持久化还是已完成必须分开；Runtime 只有收到 succeeded 的计划更新确认才认为唤醒交接成功。

### 6.3 Supervisor wake_schedules 与 wake_firings

wake_schedules：id、instance_ref:唯一TEXT、generation:INTEGER>=0、next_due_at:可空UTC TEXT、enabled:BOOL、last_control_command_id:FK control_commands、updated_at:UTC TEXT、last_firing_id:可空FK wake_firings。clear_wake 用更高 generation 写 enabled=false 和空期限，不删除记录，防止旧命令恢复已取消计划。

wake_firings：id、schedule_id、generation、scheduled_due_at、fired_at、source_event_id、state(pending/delivered/acknowledged/suppressed)、runtime_ack_event_id(可空TEXT)、suppression_reason(可空TEXT)。UNIQUE(schedule_id,generation,scheduled_due_at)，重复启动或请求转交均使用相同事件身份。

Supervisor 使用同库 instance_control_state 保存 instance_ref 唯一、user_stopped、control_revision、active_process_run_id(可空FK)、last_stop_command_id(可空FK)。stop 持久化后定时器只记录 suppressed，不自动清除 user_stopped。resume 需用户授权。

instance_control_state 增 runtime_epoch:INTEGER>=0，由 Supervisor 每次启动／恢复推进；process_runs、异步 attempt 与交接 ACK 标记该世代。该值不从 Runtime 快照回退。新增 control_sleep_handoffs 的完整字段和状态见一致性复审第4节；它闭合计划确认后到进程退出间的新任务竞态。

### 6.4 Supervisor inbound_requests

id、instance_ref、source、source_event_id、request_kind、payload_path、payload_hash、authority_ref、received_at、expires_at、retention_class 均必填；state=received/waking/transferring/delivered/rejected/expired，runtime_ack_event_id、delivered_at、last_error 可空，attempt_count 非负。UNIQUE(instance_ref,source,source_event_id)。

payload_path 指向控制面自己管理的加密或访问受限载体，不引用 Runtime artifacts 外键。Runtime 采用相同来源事件身份接收，确认自身持久提交后才 ack。转交完成后按策略清理控制面原文，保留最少去重元数据。审批到期、输入过期和用户停止不能被后台重试绕过。

user_stopped=true 时，普通 inbound 只接收与展示待处理，不自动启动 Runtime；start/resume 才能明确解除停止。删除传播应覆盖此处原文及思考请求／响应工件，避免删除后的内容被重试重新注入。

## 7 初始化、发布和转换历史

初始化新增 initialization_runs：id、instance_id、bootstrap_key(唯一)、schema_migration_version、configuration_id、phase、state(started/committed/failed)、error_code(可空)、completed_at(可空)。新建实例与 bootstrap 起点在同事务建立；崩溃恢复从已提交阶段继续，不重复生成身份。

object_publications：object_id(FK registry，实例内唯一)、state(constructing/ready/quarantined/redacted)、current_revision_id(可空FK revision registry)、owner_module、validation_schema、published_at(可空)、revision:INTEGER>=0、reason_ref(可空)。业务表的 current_revision_id 仍是模块权威指针；此处指针仅为发布校验快照，两者同事务一致，不允许独立修改。

仅需要作为可读取业务对象的表参与发布（认知对象、记忆、人格／价值版本、目标、承诺、计划、自我模型和规则）。事件、度量、审计和关联行不用机械重复发布。每类可发布对象的必填条件由 owner_module 对应 ValidateForPublish 明确规定。

对目标、意图、承诺的 INSERT 增加初始状态限制与 state_revision=0。恢复／导入使用具有明确控制授权的独立事务，保存导入运行和来源，不能使用普通创建入口构造终态历史。追加 import_runs：id、source_artifact_id、authority_ref、mode(restore/import)、continuity_incident_id(可空)、state、started_at、completed_at(可空)。

## 8 迁移顺序与兼容策略

1. 在新 schema 版本中创建独立新表及可空增量列。
2. 对现有数据登记 legacy_call 未追踪标记，不编造过去 LLM 请求；现有记录不能自动声称符合新的独立思考契约。
3. 初始化活动 revision／input_epoch，现有授权保留旧编号并建立 grant_id 兼容映射。
4. 待授权动作列的 NOT NULL 调整可能需要重建 action_intents；按 SQLite 受控表重建步骤迁移，保留 ID、外键、触发器与数据校验。
5. 回填发布状态，未完成或证据不足对象进入 quarantined；不能全部默认 ready。
6. 应用接口切换后再收紧约束。破坏性迁移单独安排维护窗口，不自动回退覆盖新增历史。

以上为迁移设计，尚未形成执行脚本。当前没有正式业务实例数据，未来首次部署可直接采用合并后的新 schema。

## 9 索引与事务清单

新增索引优先覆盖 request(state,deadline)、attempt(request_id,attempt_no)、result(request_id,acceptance)、event(instance_id,event_seq)、event(source,source_event_id)、receipt(consumer,lane/state)、outbox(state,next_attempt_at)、wake(next_due_at,enabled)、inbound(state,expires_at)。accepted 结果使用条件唯一索引；精确列组合在 DDL 阶段落实。

| 事务 | 必须一起提交 |
| --- | --- |
| 接收输入 | 原始引用、runtime_event、活动／job、去重结果 |
| 构造思考 | 不可变 request、input_manifest、request_artifact 引用、初始 attempt |
| 接受思考 | 活动版本核对、唯一 accepted 结果、请求状态、结构化认知输出和后续 job |
| 审批通过 | 审批决定、授权绑定、动作状态、outbox、审计事件 |
| 开始执行 | 当前授权核对、一次执行凭据消费、attempt 开始、动作状态 |
| 接收结果 | 回执、actual result、事件与下一消费者任务 |
| 变更到期任务 | jobs、desired wake generation、supervisor_command |
| 接收唤醒计划 | control_command 执行状态、wake_schedule 与代次 |
| 发布对象 | 模块版本、current 指针、发布记录、变化事件 |

调用网络和工具必须在事务之外。控制库与 Runtime 库不做跨库原子承诺，以幂等命令、确认、代次和恢复对账闭合。
