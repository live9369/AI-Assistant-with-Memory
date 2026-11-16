# 第二阶段工程架构一致性复审

| 属性 | 内容 |
| --- | --- |
| 版本 | V1.0 |
| 状态 | 静态设计复审完成 / 修正规则待实现 |
| 范围 | 模块接口、数据库增量、既有 SQL 与端到端运行 |
| 方法 | 对照设计文档和字段定义追踪正常、中断、重试及控制流程 |
| 限制 | 不开始框架编码；本轮不执行新功能测试或修改现有 SQL |

## 1 结论

原设计的功能分工和总体进程架构合理，但“接口字段已展开”不意味着所有交接都已经严格自洽。本次发现若干会在实现时造成冲突的字段和流程缺口，以下给出修正规则，并同步至相关设计文档。

修正后，正常活动、独立思考、审批执行、取消、恢复和休眠的主链在设计层能够闭合。当前可作为后续实现准备基线，但数据库新旧版本尚未合并，接口仍需转换为类型和服务代码，不能据此宣称实际系统已通过运行验证。

## 2 发现项与设计裁决

| 编号 | 发现 | 风险 | 修正规则 |
| --- | --- | --- | --- |
| R01 | 思考接受绑定 activity.revision，调用排队、预算和步骤状态也可能推进它 | 合法结果被自己的运行记录判为 stale | 区分业务 revision 与语义 input_epoch；结果 CAS 使用提交时当前 revision，语义有效性用不可变输入清单与 epoch 检查 |
| R02 | 审批绑定 intent_revision，而授权、排队和执行会改变动作 revision | 批准后随即版本不匹配 | 分离不可变 proposal_revision 与 lifecycle_revision；审批和参数摘要绑定前者 |
| R03 | 协议要求 owner/token/generation，jobs 和 consumer_receipts 的增量只显式加了 generation | 无法按接口校验完整租约 | 三类租约字段统一列齐；过期执行者不得修改业务状态 |
| R04 | 唤醒计划确认后到 Runtime 退出前，仍可能新增 job | 管理器持有旧期限，新任务无人唤醒 | 引入 sleep_prepare／sleep_commit 与持久接收入口；准备期间冻结业务领取和新任务提交，变更则取消休眠重新交接 |
| R05 | 用户停止、计划唤醒和新输入唤醒的优先关系不完整 | 消息到达会绕过用户停止 | user_stopped 为控制面硬门槛；输入可以接收，但默认不启动，不清除停止标记 |
| R06 | 模型调用配置只描述 model_config_id，实际模型路由及每次尝试的模型标识不足 | 重试切模型而不留证据，无法解释差异 | 请求固定 model_version_id 与配置；同请求不透明切换供应商／模型，新模型使用新 thought_id |
| R07 | 无效结构输出只提到有限重试，未说明是否能修改原请求 | 纠错提示混入重试，破坏请求不可变 | 相同请求重试不修改内容；带纠错材料的再思考必须创建新请求并引用旧结果 |
| R08 | unknown 动作有记录，但缺少阻止关联任务盲目推进的统一门槛 | 重复行动或错误完成目标 | 结果核验前保持该动作效果未知；依赖它的计划步骤不得通过成功前置条件，允许查询、求助和无依赖活动 |
| R09 | 跨库回复可能迟到，数据库恢复又会回退本地计数 | 旧 ACK／响应被恢复后的状态误接收 | 使用控制面持久 runtime_epoch 与 process_run_id 作为实例运行世代；所有交接和异步结果标记世代 |
| R10 | 不同执行后端的 stdout、退出码、完成回执未等同于真实任务效果 | 技术执行成功被记为任务成功 | 明确 transport_state、execution_state、verification_state 三层；目标完成读取核验证据 |
| R11 | 每模块接口字段已有，但依赖信息从何种版本读取未统一 | 一轮活动混用前后版本或误把无关更新判为 stale | 使用一致读快照构建 input_manifest；只监控清单依赖和相关策略失效 |
| R12 | 删除流程覆盖记忆与 FTS，但新增请求工件、队列和跨库原文也含同样内容 | 被删内容从思考记录或待转交输入重新出现 | 删除传播覆盖 thought 输入输出、工作记忆、事件载荷、控制面 inbound、日志及备份策略，先阻断访问与再注入 |

这些是原架构细化时遗漏的协议条件，不能算作已经被旧21项数据库测试验证过的能力。

## 3 字段和接口的统一修正

### 3.1 思考结果有效性

thought_requests.expected_activity_revision 更名为 prepared_activity_revision，仅记录请求构造时版本，不作为“必须始终相等”的唯一接受条件。保留 expected_input_epoch，新增 runtime_epoch、process_run_id、model_version_id、request_parent_id(可空)、supersedes_request_id(可空)。

活动纯运行元数据变化（租约、预算结算、发送状态）不提升语义 input_epoch；与本次任务有关的新事实、目标、承诺和边界变化才使相关输入失效。请求的输入清单保存来源版本，适用范围明确。不能靠无限提升全局 epoch 使系统永远无法接受结果。

AcceptThoughtResult 新增 observed_current_activity_revision、expected_input_epoch、runtime_epoch。事务内读取活动、核对状态与依赖并以当前 revision CAS 提交；冲突时重新检查语义条件，不直接接受旧判定。取消、过期、输入失效与运行世代不符都拒绝业务写入。

### 3.2 动作版本和租约

action_intents.proposal_revision 表示工具、参数、范围与核验条件的不可变版本；lifecycle_revision 表示审批、排队和执行状态的推进。approval_requests、action_authorization_records、执行凭据绑定 proposal_revision 和 arguments_hash，不绑定会随状态推进的 lifecycle_revision。

jobs、outbox、consumer_receipts 统一拥有 lease_owner、lease_token、lease_generation、lease_expires_at；可空性按 leased／processing 状态约束。接口 Claim、Renew、Complete 使用相同四元组。动作已发生但旧租约失效时，其结果仍可通过新事件入口登记与核验，不能直接完成已被新 worker 接管的 job。

### 3.3 世代、模型和执行结果

Supervisor 在每次正式启动或恢复前推进 instance_control_state.runtime_epoch；process_runs 保存对应 runtime_epoch，并保持单一活动进程。计数由控制面管理，不从 Runtime 旧备份恢复。所有模型／工具 attempt、控制命令与 ACK 记录 runtime_epoch 和 process_run_id；重启后主动恢复旧动作由新世代 recovery 命令登记原操作 ID，不直接信任旧进程提交。

thought_requests 固定 model_version_id 与 model_config_id，attempt 记录实际 provider、model、endpoint_alias 和 usage_method。实际路由与请求不符时不能作为同一请求透明接受。模型暂不可用可以失败、等待或经新请求明确切换，不隐式改变人格和策略。

工具接口返回 transport_state(received/unreachable/timeout)、execution_state(running/succeeded/failed/partial/unknown)、verification_state(pending/pass/fail/unknown)。退出码0仅支持 execution_state，verification_state 需要环境或可信回执证据；查询类工具可按工具契约指定回执本身为核验依据。

## 4 安全休眠与输入接收

1. Runtime 进入 quiescing，停止领取新 work；控制／结果事件仍可接收并持久化。
2. 在短事务里计算最早到期 job，记录 state_manifest_hash、sleep_generation 和待确认唤醒计划。
3. Supervisor 确认计划及控制状态，返回 sleep_prepare_ack；若 user_stopped 已变化，服从最新用户指令。
4. Runtime 检查没有新增可运行任务、待投递未知动作、未处理高优先结果或未确认控制命令；有则中止自动休眠，继续处理。
5. Runtime 在最终短事务写 sleep_commit 和最后接受输入边界；Supervisor 看到对应确认后才停止进程并标记 sleeping。
6. 准备期间新外部输入先进入 Supervisor inbound，不直接跳过入口写 Runtime；若需要继续运行则撤销休眠并转交，若进程已停则重新唤醒。
7. Supervisor 在休眠交接任何阶段重启，都根据持久阶段、实际进程和锁对账；无法确认则保持或启动受控恢复，不能无记录丢掉期限。

新增 control_sleep_handoffs：instance_ref、runtime_epoch、process_run_id、sleep_generation、wake_generation、state_manifest_hash、phase(prepared/acknowledged/committed/sleeping/aborted)、last_runtime_event_seq、reason、timestamps。Runtime supervisor_commands 保存同交接键。执行这套协议不承诺主机断电期间准点运行。

用户 stop 与自动休眠不同。user_stopped=true 时，定时器和普通输入都不得自行启动 Runtime；控制端展示输入待处理。只有用户显式 start/resume 清除标记。维护恢复不能覆盖用户停止。

## 5 模块、接口、数据库交叉检查

| 模块组 | 设计是否有输入与输出 | 权威数据位置 | 剩余工作性质 |
| --- | --- | --- | --- |
| 感知／记忆／认知 | 有，信号、观察、检索、推断和修订可关联 | 现有模块表＋thought 请求与结果增量 | 新字段 SQL 和 Repository 同步 |
| 人格／价值／动机／习惯／关系 | 有，配置、状态与行为测量分开 | 现有专题表与版本引用 | 参数有效性在实现后实验验证 |
| 目标／意图／承诺 | 有，来源、确认、状态和履行证据明确 | 现有表及状态历史 | 普通创建初态、发布门槛待 SQL 收紧 |
| 行为／权限／执行 | 有，提案、审批、凭据、尝试、核验明确 | action 状态／授权增量＋已有执行表 | proposal/lifecycle 版本分离与门禁实现 |
| 学习／健康／自我 | 有，提案、归因、试用、提交、损伤与恢复可关联 | 现有所有者版本和证据表 | 实际独立评估和恢复实现 |
| 活动／存储／事件 | 有，CAS、清单、事件、租约与消费者明确 | activities增量＋runtime_events等 | 事件和租约字段同步，数据原子性实现 |
| Supervisor | 有，接收、启停、交接、唤醒与部署明确 | 旧控制表＋计划、输入和休眠交接增量 | 控制面持久协议实现 |

没有发现需要把已有模块推翻或重新拆成微服务的理由。问题集中在版本边界、运行世代、交接竞态和外部效果语义，而不是生命模块数量不足。

## 6 正常与异常流程裁决

正常流程：固定入口持久接收 → 观察与一致快照 → 独立思考 → 验证并唯一接受 → 目标与决策 → 提案审批 → 当前授权门禁 → 工具执行 → 环境核验 → 更新和健康检查 → 安全等待／休眠。

异常处理：模型超时不直接当作没计算；工具超时不直接当作没执行；取消不直接当作外部效果已撤销；响应迟到不直接当作新活动结果；恢复旧数据不直接当作外部世界回退。所有异常都进入具体状态、事件或连续性损伤记录。

## 7 尚待实现和设计后的验证

- 新数据库增量、版本更名、触发器与迁移合并，现有 SQL 尚不满足新协议。
- Python 类型、Repository、RequestBuilder、协调器、权限门禁、Supervisor 与 Runner 的实现。
- 独立调用审计、重复响应、审批与状态推进、撤权、租约接管、休眠竞态、停止后输入、恢复世代和未知行动的集成验证。
- JSON 与规则解释器的具体模型校验、中文检索、性能与索引优化、删除传播和备份保留策略验证。

这些工作不要求重新定义生命概念，但不能由静态审查替代。第二阶段的工程架构设计已具有可落实的主流程；系统实际可运行和生命指标成立仍待后续实现与实验。
