# 第二阶段系统架构：运行契约与工程闭环

| 属性 | 内容 |
| --- | --- |
| 版本 | V1.0 |
| 状态 | 系统架构设计基线 / 增量和接口字段已展开，SQL同步与实现待开展 |
| 依据 | 第一阶段 V1.0、模块架构、实现层架构、数据库设计 |
| 本次范围 | 补齐跨模块协议、运行状态、独立思考、唤醒、授权、初始化与恢复 |
| 参考定位 | OpenClaw、Hermes 可供工具实现参考；不承担本项目架构定义 |

## 1 设计基线与文档优先关系

本报告已由[数据库增量字段设计](phase-2-database-increments.md)和[模块接口字段字典](phase-2-module-interface-dictionary.md)展开；总体入口为[工程架构设计基线](phase-2-architecture-design-baseline.md)。

最新[一致性复审](phase-2-architecture-consistency-review.md)补充运行世代、语义输入版本、不可变提案版本、完整租约及两阶段休眠交接；这些是本契约的组成部分。

第一阶段定义功能与边界；模块架构定义责任；实现层架构定义进程、技术栈和部署；本报告统一跨模块契约。涉及本报告明确修订的行为时，以本报告为准；SQL 的当前物理结构仍由 database/ 目录表示。

本报告列出的数据库增量是待落实的设计，不表示当前 SQL 已经具备这些字段。实施前须同步生成器、SQL、字段字典与迁移。本轮不修改 SQL，不开始运行框架编码，不执行新的功能验证。已有数据库测试作为既有证据保留，不能代替新契约验证。

验证不再作为继续设计的前置条件。先形成完整架构和数据契约，随后实现，再按本文验收计划验证。具体模型供应商、密钥、负载阈值和环境配置可在部署前填写，不阻塞抽象契约设计。

## 2 核心分工与依赖方向

```text
用户控制端 → Supervisor：启动、停止、恢复、部署
输入通道 → Runtime API → 持久事件 → 活动协调器
活动协调器 → 生命业务服务 → Repository／模型适配器
行为决策 → 权限服务 → 执行调度器 → 工具后端
结果输入 → 活动协调器 → 反馈与状态所有者
Runtime → Supervisor：心跳、唤醒计划、维护请求
```

Runtime 只能提出维护或部署请求；Supervisor 根据用户控制和受保护部署策略决定是否执行。工具后端不直接修改生命数据库。LLM 不直接执行工具、不持有数据库连接、不决定持久化事务。

业务服务只能通过自身 Repository 写权威状态，跨模块以命令和版本化读取协作。协调器组织多个 Repository 参与同一短事务；不允许各模块在一次逻辑提交内自行提交半套数据。

## 3 独立、无会话上下文的思考契约

一次 ThoughtRequest 是完整、不可变的请求包。每次调用重新创建消息，不从上次调用继承聊天历史、服务端线程、前次响应标识或隐藏会话状态。HTTP 连接池可复用，它不等于认知会话。

| 请求字段 | 含义 |
| --- | --- |
| thought_id、activity_id、step_id | 本次思考、所属活动和步骤 |
| purpose、task | 推断、计划、核验等用途与明确任务 |
| instruction_version、output_schema_version | 本次指令与输出结构版本 |
| input_manifest | 观察、记忆、目标、承诺、人格、价值、情境的精确版本引用 |
| request_artifact_id、request_hash | 实际提交的完整请求及摘要；敏感内容按保留策略处理 |
| model_config_id、generation_config | 模型路由和采样配置，不包含密钥 |
| prepared_activity_revision、input_epoch、policy_version、runtime_epoch | 构造版本及接受条件；提交时使用当前业务 revision 做 CAS |
| deadline、token_budget、retry_policy | 调用期限和预算 |

RequestBuilder 按任务选取必要信息，而非每次加载完整生命数据库。稳定系统规则和本次角色边界允许重复包含；历史输出只有被显式选作当前证据或状态时才重新进入请求，并标明来源。工具结果也以当前观察重新输入，不自动追加整段工具聊天轨迹。

如果模型建议调用工具，返回结构化候选给行为层；行为层选择并授权执行。结果返回后，需要继续推理时创建新的 ThoughtRequest。一次生命活动可以包含多次独立思考。

PromptCache 如果仅缓存本次显式请求的相同前缀，可以作为传输优化；任何会自动合并历史内容的能力不用于本契约。供应商是否保留数据是另一项部署配置，不由“无会话”自动保证。

## 4 模型调用状态、重试和结果接受

ThoughtRequest 状态：prepared → running → succeeded／failed／cancelled／superseded。每次网络尝试单独记录 queued、sent、received、timeout、failed、cancelled；请求与网络尝试不能共用一个状态。

网络超时可能已经发生远程计算。重试使用同一个不可变请求包和新的 attempt_id，不以供应商恰好一次执行为前提。一个 thought_id 最多允许一个 accepted_result_id，采用带预期版本的条件写入；多个有效响应只接受一次，其余记录为 duplicate 或 stale。

接受前依次检查：结构有效、证据引用合法、活动仍有效、语义输入及依赖版本未过期、运行世代有效、相关授权未失效、预算和期限未超出；再读取当前活动 revision 做 CAS。发送、租约与预算等运行元数据变化不单独使语义输入过期。需增加纠错材料或切换模型时创建新 thought_id，不能把新输入偷换成同请求重试。

流式文本可以展示为临时输出，但不得把未完成流式结果提交为正式决定。取消网络请求不保证供应商未继续计算；晚到结果仍须经过接受条件。

## 5 活动状态机与并发模型

协调器只串行提交同一实例的权威业务状态。网络等待释放执行器和数据库事务，其他活动可在安全步骤推进；因此每个结果都带状态版本，不能依赖“只有一个进程”消除逻辑并发。

| 当前状态 | 允许去向 | 触发条件 |
| --- | --- | --- |
| pending | running、cancelled | 被领取或用户取消 |
| running | waiting_input、waiting_tool、paused、completed、failed、cancelled | 需要外部信息、等待工具、暂停、完成或终止 |
| waiting_input | running、paused、failed、cancelled | 有效输入、时限或控制指令 |
| waiting_tool | running、paused、failed、cancelled | 结果已核实、需人工处理或取消 |
| paused | running、failed、cancelled | 明确恢复或终止 |
| completed／failed／cancelled | 无 | 后续重做创建新活动，保留 predecessor_activity_id |

pending/running 等表示活动调度状态，不表示人格或情绪。单次模型网络等待保持 running，并以步骤和 attempt 状态反映阻塞；waiting_tool 专用于外部工具。

活动增加 revision、input_epoch、cancel_requested_at、cancel_reason、deadline。所有状态提交采用 compare-and-swap：WHERE id=? AND revision=?，成功后 revision+1。影响事实、任务和权限的新输入提升 input_epoch；不相关的观测不必让所有思考失效，关联规则由协调器按任务定义。

取消接口先持久化请求，再停止后续新行动；对在途工具请求尽力取消并核实实际效果。被取消活动仍可以接收执行结果用于记账和披露，但不能因此恢复自动推进。

## 6 待授权动作与执行门槛

动作生命周期：proposed → awaiting_approval／authorized → queued → dispatching → running → succeeded／failed／partial／unknown；未执行前可取消。结果核验可以将 unknown 变为核实状态，但需追加核验历史。

动作提案拥有完整参数和参数摘要，但 grant_ref 初始可空。approval_requests 引用提案，包含确切工具、对象范围、参数摘要、有效期。审批通过后创建或绑定授权；用户批准的是该动作范围，不是任意未来参数。

同一事务检查提案版本和审批决定，写入授权引用并创建 outbox。待授权提案不得进入可投递队列，也不得创建实际执行尝试。参数改变后形成新提案或重新审批，旧批准不可复用。

Dispatcher 在领取动作时再次检查当前授权、期限、撤销、工具所需能力和参数范围；成功后生成绑定 action_id、arguments_hash、expiry、policy_epoch 的短期执行凭据。Runner 验证凭据并在执行前核对当前有效性。授权撤销持久化与执行开始之间以单一执行门禁串行裁决；已经开始的动作尽力停止并核验结果，不能保证撤回已经发生的外部作用。

开放模式由 PolicyService 在用户指定范围内授予广泛能力，而非绕过执行记录、范围校验和用户停止控制。

## 7 执行后端契约与框架参考

第一版以自有 ToolBackend 接口定义行为能力：

```text
describe(tool_id) → 参数结构、能力、范围、幂等／查询／取消能力
execute(action_id, arguments, capability, deadline) → receipt / handle
poll(handle) → running / result / unknown
cancel(handle) → cancellation acknowledgement
verify(action_id, expected_effect) → evidence + outcome
```

工具后端可以是本地受控程序、浏览器、远程 API，也可以是经过适配的现有执行组件。OpenClaw、Hermes 的工具注册和进程控制仅提供实现参考；其 Agent 会话、自动记忆、模型循环与权限语义不成为本系统的隐含依赖。

工具 session 或 handle 是执行资源句柄，与 LLM 思考会话不同。每个句柄绑定实例、动作、尝试和权限范围。后端无法支持某能力时明确报告，不以猜测补齐。

## 8 无法跨系统原子提交时的处理

本地持久提交保证内部状态原子性，外部调用使用 outbox、幂等键、句柄、回执和核验。动作记录、投递状态和结果状态不可混为一项。

| 中断位置 | 恢复处理 |
| --- | --- |
| 提案尚未提交 | 没有可执行动作 |
| outbox 已提交、未开始调用 | 可重新领取，仍需权限检查 |
| 已发出、是否执行不明 | unknown，查询或按后端幂等协议恢复 |
| 外部成功、本地结果未提交 | 核实原操作，禁止默认重新执行 |
| 本地结果已提交、目标尚未推进 | 幂等处理结果事件，再更新目标／承诺 |
| 用户取消后收到结果 | 保存实际结果，保持活动取消，不发起下一行动 |

控制事件、工具结果和用户输入共用持久事件信封，但各自有明确 payload 类型。业务对象和事件信封通过引用关联；事件信封只保存最小路由元数据，内容按原模块保留和删除。

## 9 休眠、唤醒和用户输入路由

区分两种模式：Runtime 存活但无活动时为逻辑等待，模型无调用；Runtime 进程停止但保留实例状态时为进程休眠。Supervisor 始终由操作系统管理并保持最小控制能力。

浏览器控制入口由 Supervisor 的轻量控制服务提供固定地址；用户输入在 Runtime 休眠时先进入控制库 inbound_requests，经认证、限额和去重后登记，在 user_stopped=false 时唤醒 Runtime。用户停止时仅接收并展示待处理，不自动启动。转交得到 Runtime 持久接收确认后才标记 delivered；重复转交使用同一个 source_event_id，Runtime 按实例与来源去重。只有用户显式 start/resume 清除 user_stopped。

Runtime 内部任务的完整状态仍在 jobs。外部管理器只保存下一唤醒摘要，不读取或修改业务表：

1. Runtime 在提交 job 变更时，同事务写 supervisor_commands 类型的 set_wake 指令。
2. 指令含 instance_id、schedule_generation、next_due_at；无下一期限用 clear_wake。
3. Supervisor 幂等接收后更新 wake_schedules，返回确认；旧 generation 不覆盖新计划。
4. 计划未确认时，不允许自动进入进程休眠；可以保持逻辑等待并报告降级。
5. Runtime 重启先重新汇总 jobs 并对账唤醒计划。
6. 到期只产生一次可去重唤醒事件；Runtime 自己判断具体哪些 job 到期。

取得计划确认不是立即退出的充分条件；还必须完成一致性复审第4节的 PrepareSleep／CommitSleep 交接，冻结新业务调度并核对新增工作，避免交接后的任务失去唤醒。

主机整体睡眠或关机时，软件不能保证准点运行；主机恢复后追赶检查，按任务 late_policy 决定补做、过期、重谈或求助。

## 10 初始化与对象发布

初始化由 Supervisor 获取单实例锁，核验数据库能力和 schema，再由 Runtime 在受控事务中建立身份、控制主体、最低策略、模型路由占位、能力与规则字典、初始人格／价值版本和必要恢复状态。LLM 尚未配置时运行态为 degraded，可进行控制和存储活动，但不伪造真实推理结果。

对象区分事务内 constructing 与业务可见 ready；当前修订允许为空只用于创建过程。Repository 的 publish 操作必须检查当前版本归属、来源、必需字段和业务状态，再将对象标记 ready。读服务默认只取 ready 对象；历史和故障诊断可以显式读取未完成对象。

目标与意图从初始状态创建；社会承诺从 proposed 创建，之后依据确认记录生效。禁止通过直接插入 fulfilled 承诺绕过履行证据。受控导入／恢复使用独立接口，必须提供历史来源和连续性标记。

全局对象引用不能仅凭 registry 里存在就认定有效：Repository 同时核对类型、所属实例、当前发布状态和调用方允许的对象种类。

## 11 事件、重放与审计

新增 runtime_events 保存 event_id、instance_id、event_seq、type、source_event_id、correlation_id、causation_id、payload_ref、recorded_at 和处理状态。event_seq 在实例内单调递增，支撑 SSE 断线补读；source_event_id 在来源作用域内唯一。perception_signals 仍拥有原始感知载荷，不再复制成第二套观察真值。

事件重放分为两种：重建派生视图可以重放；实际工具执行禁止通过通用重放触发。消费者保存处理位置和幂等键，业务更新与消费确认同事务提交。事件只证明记录发生过，不自动证明其内容真实。

审计关联活动、思考、决策、动作、部署与授权版本。事件路由、思考请求工件、日志和索引均纳入删除传播，不能只清理 memory_revisions。

## 12 最小规则解释器与决策确定性

第一版规则采用带 engine_version 的声明式 JSON AST，只允许已定义的比较、集合、布尔和时间操作，禁止 eval 或任意代码执行。结果为 true、false、unknown；前置条件 unknown 时不能当作允许执行。

规则引用变量必须注明来源、类型、单位和有效期。对健康范围、目标成功、触发线索、履行标准使用同一解释器接口，但规则命名空间和授权所有者分开。检查数据库里存在规则并不等于其语义已经合法。

决策保存策略版本、完整候选集、因素路径和随机种子。初版可采用明确的分层规则和受约束加权选择作为可替换策略；在参数未经实验校准前，其数值是工程初值，不表述为科学定律。

## 13 参数变化、学习和数据库事务

推理阶段读取固定 input_manifest，计算结束后在短事务中核对对象版本并提交。若目标版本已变化，提案不直接覆盖，进入重新评估或失效。跨模块更新需要同一事务，或者拆成有持久进度的明确工作流；不靠内存回调保证一致性。

学习与自修改都产生提案。长期人格、价值和标准变化必须经过各自门控，不因框架自动生成技能或总结而绕过生命模块所有权。模型与参数工件采用先写临时文件、校验、原子发布、再提交引用的流程；崩溃产生的未引用工件由清理任务处理。

自更新候选在隔离数据副本上运行，不能提前改变正式人格、记忆和承诺。观察失败后如何回退必须使用对应数据兼容策略。

## 14 生命周期、版本与控制平面

Supervisor 独占启动锁、部署指针、停止标记和控制库。Runtime 启动分 starting → recovering → ready／degraded；停止经 quiescing → stopped；意外退出记为 failed。Supervisor 自身异常由操作系统重启后先核对实际进程与锁，再决定恢复，避免重复启动。

部署流程按 prepare、quiesce、stop、backup、switch、start、verify、commit 分阶段持久记录。新进程未达到 ready 或明确可接受的 degraded 状态时不能把部署标成成功。用户主动停止优先于自动恢复。

代码回退优先不回退正式业务数据：迁移采用向前后兼容扩展，旧版必须能读取最新数据。破坏性迁移作为单独维护窗口，执行前冻结外部动作，提供受控快照和明确恢复范围。不得自动删除升级后已发生的外部历史；必须恢复旧数据时进入 continuity_incident 和未知行动对账。

## 15 数据库设计增量清单

| 位置 | 待落实设计 | 消除的问题 |
| --- | --- | --- |
| Runtime thought_requests | task、输入清单、请求工件、模型配置、activity_revision、input_epoch、state、accepted_result_id | 无会话思考的持久边界 |
| Runtime thought_attempts／thought_results | 请求、尝试、时间、网络状态、结果工件、校验与接受状态 | 重试、晚到响应、一次接受 |
| Runtime activities | revision、input_epoch、取消字段、期限、前置活动引用 | 并发、取消和恢复 |
| Runtime action_intents | 独立状态、参数摘要、可空授权引用 | 先提案再申请授权 |
| Runtime action_authorization_records | 动作版本、审批、授权快照、有效时间 | 审批范围可追溯 |
| Runtime outbox／action_attempts | 投递租约、执行开始门禁、policy_epoch | 撤权与重复执行 |
| Runtime runtime_events／consumer_offsets | 单调序号、来源去重、消费者进度 | SSE、结果投递和业务幂等 |
| Runtime supervisor_commands | 指令编号、generation、请求、确认与重试状态 | 跨库指令可靠交接 |
| Runtime 对象／承诺 | 发布状态与初始化状态限制 | 半成品读取与伪履行 |
| Supervisor wake_schedules | 实例、generation、next_due_at、最后触发及确认 | 进程休眠后的唤醒 |
| Supervisor inbound_requests | 去重 ID、内容引用、路由与交付状态、保留策略 | Runtime 停止时接收用户输入 |
| Supervisor control_commands | 启停、部署、授权主体、请求 ID 与执行状态 | 用户控制和控制面幂等 |

现有数据库166张业务与控制表是上次设计的物理基线。上述增量尚未生成 SQL；后续不能继续用旧的21项测试宣称新契约已验证。

## 16 架构闭合检查

| 路径 | 明确责任与落点 | 设计结论 |
| --- | --- | --- |
| 外部信息进入 | 固定入口、控制库接收、Runtime 事件与感知载荷 | 路由闭合 |
| 生命连续性 | 数据库版本、恢复点、身份与承诺、单实例启动锁 | 职责闭合 |
| 独立思考 | RequestBuilder、不可变请求、attempt、版本化接受 | 调用边界闭合 |
| 行为申请和执行 | 提案、审批、授权、投递、门禁、结果核验 | 无授权环形依赖 |
| 非同步结果 | event_id 去重、输入 epoch、消费者位置、unknown | 恢复语义明确 |
| 休眠与唤醒 | 计划交接确认、Supervisor 调度、主机恢复补偿 | 控制面闭合 |
| 健康维护 | 内部健康证据、外部检测、降级、回退与用户停止 | 责任闭合 |
| 版本交接 | 分阶段控制记录、schema 兼容与历史对账 | 回退边界明确 |

架构层没有必须依赖未定义的后台会话或未登记状态才能运行的主链。它在设计语义上可以进入实现准备，但仍需要把字段增量同步到数据库，把每个接口展开成代码契约；这些是已有决定的细化，不需要重新定义生命概念。

## 17 设计后验证顺序

先完成数据库增量和接口类型定义，再实现存储、协调器和控制平面，最后接入模型与工具。验证按契约覆盖初始化、独立请求、一次接受、晚到响应、审批、撤权、休眠唤醒、结果未知、崩溃恢复和部署回退。

目前阶段标记为“工程架构与接口字段设计已补全／待SQL同步、实现与验证”。它不表示第二阶段所有指标可实现性研究已完成，也不表示程序已经运行。具体供应商对接和性能调优在相应实现阶段完成。
