# IM13：断点恢复与同一工作有限续处理

日期：2026-11-10。状态：详细设计／待隔离验证。依赖：IM09、IM12已完成。不改变冻结协议、DDL、正式实例、原预算或期限。

## 1. 职责与实际入口

新增 `application/tool_learning_recovery.py`。`ToolLearningRecovery.resume(entry, envelope)` 执行冻结 `resume_work`；`RecoveryAuthority` 默认拒绝。协调器通过真实进程身份、当前策略、原work/account与实际阶段创建具名入口，不能由调用者的模块字符串、布尔值或条件说明取得权限。M14仅更新原work；M04重建原handoff租约，M12维护授权仅用于本地保护性维护。

`Recovery.reconcile`仍是停止后的保守事故核对：保留未知外部动作及未知占用，绝不重发工具或模型。新增TL核对由具名服务完成，不把普通旧恢复事件当作恢复授权。`data_management`增加显式受控恢复入口；旧入口遇TL保护状态或TL备份不得绕过当前镜像外核对。

## 2. 不可变核对材料与字段

`TL-WORK-RECONCILIATION-1`工件记录：instance_id、work_id、expected_work_revision、原phase/review_round、条件Ref清单、持久命令查询（command_id/operation/idempotency_key/request_fingerprint/持久response）、C1决定及内容修订、C2handoff/receipt/representation、F1change/barrier/epoch、未知外部动作说明、核对时间与下一合法阶段。工件是事实，不能自行证明条件已解除。

请求字段严格沿冻结：payload.work、expected_work_revision、conditions、reconciliation；work_ref/expected必须指向同一个真实work。原account、budget、绝对deadline、控制版本与当前身份仍必须有效。读取及核对计入实际原账户的有限阶段；未知消费不释放。输入先深复制，存储执行同gate同事务，最后权威回调后再次核本地停止/锁/期限/CAS。

## 3. 状态与同轮幂等

仅waiting/blocked/failed/stopped可续到processing（原assess/decide阶段）或handoff_pending（原represent阶段）。completed/no_change/rejected无出边。phase=admit或complete缺少可信继续点时拒绝。不得重跑已经持久提交的assess/C1/C2，提交不明先按原命令身份与指纹查主库；不存在不能推断外部操作未执行。已发布回执保持事实；迟到worker不能恢复旧租约。

phase=decide仅在真实owner确认原条件解除或明确已授权基线变化时review_round+1；旧决定、原proposal与原content均保留。缺少条件owner、未知基线、只提交空conditions或自报review_ready均拒绝。represent只重开未完成原handoff并使用新generation；published不降级，原attempts/预算/期限不清零。组成员仍按原固定成员和每成员当前资格核验。

## 4. 原清理计划续授

扩展真实 `ControllerMaintenanceAuthority`：认证当前Bearer、当前策略、原F1来历、原plan及完整固定target集合。续授grant绑定旧planID/指纹与原work、新独立maintenance activity/account/caps/deadline；target.plan_ref不变。旧账本和unknown占用不改、不释放，旧代历史保留。续授不是跨plan替换，也不是模型/工具机会。中断后先核实际目标状态与验证证据；未知提交/副作用保守停，不以新grant盲重删。

## 5. 镜像外当前排除与恢复

恢复必须由当前可信Control定位已登记根、设备/inode身份及当前head，不能相信备份内token/配置/目录或调用者传入空目录。消费IM12完整有界排除记录与当前pending指令：pending、缺记录、旧anchor、权限无法确认、覆盖超限均RESTORE_BLOCKED。权限恢复不复活erase。

受控恢复仅复制到新隔离锁定目录，绝不覆盖当前实例；原实例身份不得并行运行。恢复候选保留WAKE_DISABLED与RESTORE_RECONCILIATION_REQUIRED。对较旧镜像不得丢弃当前已提交C1/C2/F1及排除；无法证明连续性则只生成明确blocked核对结果，不能声称已恢复。真实恢复授权与排除消费分开，读取排除记录本身不授予唤醒权。

## 6. 验收与限制

新synthetic实例验证：同work有限续处理、同键异义/CAS/期限/停止拒绝、候选新round而非新work、持久提交核对、不重发unknown动作、旧lease迟到、当前排除pending/旧目录/旧anchor拒绝、旧plan固定targets真实续授、预算unknown不释放。默认拒绝端口单测与实际可信SDK接线测试分别标注；没有真实owner的条件不得冒称已实现。专项冻结后交根协调统一门禁，与IM14不同任务并行但不同时改共享文件。

## 7. 最终实现边界与精确映射

`TL-WORK-RECONCILIATION-1`闭合字段为 `contract/instance_id/work_id/expected_work_revision/phase/review_round/conditions/facts`。facts含work技术快照、该work的tl_command/tl_product/tl_decision/tl_handoff逐行固定证据；当前正在执行的resume命令不算历史未决命令。任何历史非committed命令阻断，不猜测提交；F1另有真实M12 `reconcile_protective_commit`按原授权/准备/命令指纹/结果barrier查证，不执行F1，不释放未知消费，不清当前pending恢复栅栏。

实际SDK `StrictLearningCoordinator.resume_work(work_id,conditions)` 支持：①已持久化且当前来源合格的完整Observation material stage，恢复后仅发布原四产物，不重做produce/模型；②当前认证controller review，明确绑定下一review_round、proposal、native head及当前policy；③所有固定未完成handoff的当前accepted修订与已解除/过期租约条件。缺失material、未知模型消费、未知外部动作、其他语义域条件没有owner时仍blocked。模型失败不构成自动重试许可。

暂停work的原账户实际读取通过 `BudgetAuthority.verify_recovery_read` 与 `ToolLearningBudget.recovery_read_context`封闭能力绑定entry/work/account/operation/阶段；仅精确暂停work状态作为例外，模型/tool、halted/unknown、活动真实终态、用户stop、恢复锁、原deadline/caps均不例外。与独立IM14协作增加的`evaluation_read_context`同样仅真实M14固定terminal work的retrieval，绝非恢复或模型权限。

`reconcile_stopped_work`属于已认证的停机控制命令，固定最多1秒/1024行/1MiB，当前`recovery_control_limits`只能收紧。该scope实测并记最小控制消费/覆盖失败，不向原暂停work领取模型额度。processing/awaiting_decision/handoff_pending先核持久结果：C2确有固定receipt则完成；C1有未完成义务则原represent blocked；已有完整产物则原decide blocked；其他保持原阶段blocked。原conditions工件引用保留，不重存来源metadata。CLI实际reconcile读取所选实例已有非symlink token进入认证通道；无真实tl_work仍保留旧行为。

## 8. 清理续授与恢复的具体授权

`ContinuedErasure.authorize`仅真实ControllerMaintenanceAuthority，绑定旧plan/固定targets/原F1证明与新grant/独立维护activity/account、有限caps/deadline。旧journal的plan/used/account/unknown保持；新消费存`continuations[continuation_id]`，同键异义拒绝。旧unknown/entered不得以新grant覆盖。`run`复用原物理adapter、目标CAS和真实复核，不重写target.plan_ref，九域完成度仍不能由本域签收代替。

整库候选不能由单source清理grant推导。`configure_restore_candidate`需当前实际controller+policy owner，明确`TL-RESTORE-CANDIDATE-POLICY-1`的purpose=restore_locked_candidate、instance、精确source_bundle与新target路径、whole_current_database_and_registered_artifacts范围、保留控制metadata，external_material_use=false/wake_authorized=false。恢复仍逐当前memory/signal及work原source核所有权；不支持的原来源owner或private self-only源阻断。政策不创造来源权限。

`restore_current_bundle`保留当前权威SQLite，绝不使用旧SQLite覆盖当前历史；旧manifest只供当前登记且非排除的缺失blob校验。外部当前root/head/完整排除及pending两次核对，全部文件/隐含DB读取受同实际meter；SQLite复制按实际page_size前置限制。补回路径检查canonical父目录并以目录fd/O_NOFOLLOW打开，禁止备份blobs symlink。授权后任何manifest/目录/复制失败均记录真实failed或unknown结算；失败候选保留双锁，不盲删。当前权威库或当前可信Control丢失时RESTORE_BLOCKED；灾难恢复、正式迁移/唤醒不属于此路径。
