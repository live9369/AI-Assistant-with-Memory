# 第二阶段工程架构设计基线

| 属性 | 内容 |
| --- | --- |
| 版本 | V1.0 |
| 状态 | 架构与接口设计已补全 / 待实现和验证 |
| 目的 | 给出系统工程设计的统一入口与边界 |
| 执行限制 | 本轮只形成设计文档，不开始运行框架编码 |

## 1 文档组成

最新复审见[第二阶段工程架构一致性复审](phase-2-architecture-consistency-review.md)。发现的版本、租约、休眠、运行世代和结果语义缺口已在设计层修正；SQL 尚未同步，不以旧测试代表新设计已通过。

| 层级 | 权威文档 | 负责内容 |
| --- | --- | --- |
| 生命定义 | [第一阶段完整报告](phase-1-complete-report.md) | 生命特征和功能验收原则 |
| 功能边界 | [模块架构](phase-2-modular-architecture.md) | M01—M17 与 E01 的职责和状态所有权 |
| 计算机实现架构 | [实现层架构](phase-2-implementation-architecture.md) | 进程、技术栈、部署与存储边界 |
| 跨模块运行 | [系统运行契约](phase-2-system-contracts.md) | 独立思考、执行、取消、唤醒和恢复 |
| 既有数据库 | [数据库逻辑架构](phase-2-database-architecture.md)、[已生成定义](../../database/README.md) | 各生命模块状态、版本和证据 |
| 数据库设计增量 | [增量字段字典](phase-2-database-increments.md) | 新运行协议所需表、字段、约束和事务 |
| 模块交互 | [接口字段字典](phase-2-module-interface-dictionary.md) | 请求、响应、错误、事件与控制接口 |

运行契约及其字段字典补充较早设计。数据库增量尚未同步至 SQL；实施时必须一起更新，不能用旧物理结构承载新协议后声称已完整。

## 2 端到端责任闭合

| 步骤 | 接口／所有者 | 持久落点 | 中断后处理 |
| --- | --- | --- | --- |
| 接收输入 | E01 SubmitInbound／M01 ReceiveSignal | inbound_requests → perception_signals + runtime_events | 原 source_event_id 去重转交 |
| 创建与恢复活动 | M02 StartActivity／SaveCheckpoint | activities、activity_steps、checkpoints | 校验身份与未完成步骤 |
| 组装当前信息 | M04 RetrieveMemory、M05 ActivatePersonality、M08 GetRelationship、M10 GetStateSnapshot | 精确版本引用与工作记忆 | 缺失或过期返回明确状态 |
| 独立思考 | M03 PrepareThought → Generate | thought_requests、inputs、attempts、预算预留 | 同一请求新尝试，不能暗带历史 |
| 接受思考 | M03 AcceptThoughtResult | 唯一 accepted 结果与认知输出 | 版本过期则 stale，重新提出请求 |
| 目标与行为 | M06 AcceptGoals、M11 FinalizeDecision | 目标、动机、候选、决策与提案 | 读当前状态，不重复接受旧结果 |
| 审批 | M12 RequestApproval／DecideApproval | 审批、授权快照、动作状态 | 参数变更重新审批 |
| 实际行动 | M13 DispatchAction、M12 BeginExecution | outbox、attempt、回执与结果 | 未知效果先核验；不盲重试 |
| 学习与维护 | M14 CommitUpdate、M16 VerifyRecovery | 所有者新版本、学习提交、健康证据 | CAS、补偿修订与独立核验 |
| 等待与唤醒 | E01 SetWake／ClearWake | jobs → supervisor_commands → wake_schedules | 代次和确认对账，失败保持逻辑等待 |
| 升级与恢复 | E01 SwitchDeploy／Rollback | 控制库部署阶段与业务连续性事件 | 单活动实例、schema 兼容、外部效果核对 |

端到端链路的每次外部等待都有持久身份；每次结果提交有幂等或版本条件；每项权威状态有单一所有者；每个不可跨库原子完成的过程有明确交接协议。

## 3 数据一致性决定

Runtime 仍使用模块化单体和单写入器。业务服务允许异步等待，但状态提交串行并使用 CAS。控制平面独立存储，不直接改业务库。执行租约包含 token 和 generation，过期执行者不能提交旧结果。

原始信号、认知解释、回忆重构、模型响应、工具回执和真实环境结果分别记录。相同事件被不同模块引用，而不复制成多个无关联事实。输入版本与请求工件明确保留，满足独立调用与可追溯要求。

预算按操作预留与结算。未知远端用量不自动释放。授权在提案、审批和实际开始时分别检查；用户停止与撤权优先，已发生副作用必须核实和披露。

## 4 设计中的可配置项

供应商 URL、模型名称、密钥位置、具体工具插件、实际超时与资源限额、评分权重和保留期限由配置给出。它们可在实现或部署阶段确定，但配置结构、有限预算、失败状态和错误接口已在架构中定义。

规则解释器采用版本化声明式条件，不执行任意模型生成代码。行为选择策略与学习机制可替换，实际参数是否有效留给设计后的实验。中文检索方案、性能索引优化和可选向量后端属于实现验证课题。

## 5 当前完成与尚未完成

已完成：功能模块边界、进程部署、数据所有权、原数据库逻辑设计、新增运行字段设计、模块接口字段、状态转换、独立思考、权限、唤醒、取消、恢复和版本交接设计。

尚未执行：新字段 DDL 同步与迁移、Python 接口模型、Runtime／Supervisor／Runner 框架、真实 LLM 和工具对接、集成及性能验证。已有21项数据库测试只覆盖旧 SQL，不能外推为新架构已通过。

第一阶段保持完成；第二阶段的“系统架构设计”子任务可标记为设计基线已形成。第二阶段整体包含后续实现准备和可实现性验证，不能因此整体标记完成。

## 6 后续顺序

先审阅并冻结这套设计基线；获准进入实现后，同步数据库增量与类型定义，建立 Repository 和初始化，再实现控制面、协调器及执行链，接入模型和工具，最后执行契约与生命指标验证。用户尚未要求开始框架编码，因此本轮停留在文档设计产物。
