# 第二阶段各模块接口字段字典

| 属性 | 内容 |
| --- | --- |
| 版本 | V1.0 |
| 状态 | 接口设计基线 / 尚未生成 Python 类型或框架代码 |
| 范围 | M01—M17、E01、模型适配器、工具后端、HTTP 控制面 |
| 配套 | 系统运行契约、数据库增量字段设计 |

## 1 通用类型、执行和事务规则

本字典经[一致性复审](phase-2-architecture-consistency-review.md)修正：思考使用 input_epoch 与当前提交 revision；动作审批使用 proposal_revision；异步交接新增 runtime_epoch 和 process_run_id。旧文中的 intent_revision 在提案绑定场景统一读作 proposal_revision，动作状态 CAS 则用 lifecycle_revision。

Id=稳定字符串标识；Utc=固定毫秒UTC；Revision=非负整数；Probability=[0,1]有限数；Json=有 schema_version 的结构化值；ObjectRef={instance_id,id,kind,revision_id?,content_hash?}。表格中的 ? 表示可空；List<T> 可以为空但不能假装未知，未知用显式 available=false、reason_code 和可空 value 表达。

所有修改请求携带 CommandHeader：request_id、idempotency_key、schema_version、instance_id、actor_ref、activity_id?、correlation_id、causation_event_id?、expected_revision?、deadline?。除明确的系统调用外，actor_ref 必填且来自认证上下文，不直接信任请求体中的身份。

所有读取请求携带 ReadScope：instance_id、actor_ref、activity_id?、as_of?、allowed_purpose、read_snapshot_id?。返回记录明确实际 revision 和有效时间。UI 无权自行声明 allowed_purpose 获得更高访问范围。

CommandResult={request_id,status,object_refs,event_ids,revision?,error?}；status=accepted/applied/duplicate/rejected。accepted 只表示异步工作已持久化；applied 表示本地事务已提交，仍不保证外部动作已成功。

Error={code,message,retryable,details_ref?,current_revision?,retry_after?}。统一错误码：INVALID_SCHEMA、NOT_FOUND、FORBIDDEN、APPROVAL_REQUIRED、VERSION_CONFLICT、STALE_INPUT、DEADLINE_EXCEEDED、BUDGET_EXCEEDED、UNAVAILABLE、INVALID_TRANSITION、RESULT_UNKNOWN、DUPLICATE_PAYLOAD_CONFLICT、INTEGRITY_FAILURE。错误元数据不得泄露无权访问对象的内容。

模块只产生自己的对象和变更；跨模块读取使用只读接口。CommandHandler 在 UnitOfWork 内调用多个所有者 Repository，原子提交；模块不能隐藏提交事务。LLM／工具适配器只作外部调用，不能直接持久化业务事实。

## 2 M01 输入与感知

| 接口 | 请求字段（除通用头） | 响应字段 | 写入／事件 |
| --- | --- | --- | --- |
| ReceiveSignal | channel_id、source_event_id、source_actor_ref?、occurred_at?、artifact_ref、payload_hash、media_type | signal_ref、event_ref、activity_ref?、deduplicated | perception_signals、runtime_events；signal.received |
| ExtractObservations | signal_ref、context_ref、extractor_config_ref、quality_policy_ref | observation_revision_refs、quality_checks、unresolved_entities、uncertainty | 观察修订、质量检查；observation.created |
| ReviseObservation | observation_ref、expected_revision、new_content、locator、evidence_refs、reason | new_revision_ref、superseded_ref | 不覆盖原信号；observation.revised |

ObservationPayload={content,entity_refs,locator,extractor_version,uncertainty,source_refs,context_ref}。提取可能需要一次独立思考，但不能直接执行动作。

## 3 M02 生命活动协调器

| 接口 | 请求字段 | 响应字段 | 语义 |
| --- | --- | --- | --- |
| StartActivity | trigger_event_ref、purpose、budget、deadline?、predecessor_ref? | activity_ref、state、revision、job_ref | 创建 pending 和持久任务 |
| AdvanceActivity | activity_ref、expected_revision、step_kind、accepted_input_refs | step_ref、next_state、new_revision、scheduled_work_refs | CAS；事务内不调用网络 |
| CancelActivity | activity_ref、reason、expected_revision? | cancel_requested_at、state、inflight_action_refs | 记录请求；外部效果另核验 |
| ResumeActivity | activity_ref、reason_event_ref、expected_revision | new_revision、ready_job_refs | 只恢复非终态；终态另建活动 |
| SaveCheckpoint | activity_ref、expected_revision、state_manifest、pending_refs、release_ref | checkpoint_ref、continuity_summary | 记录实际版本，不保存虚构休眠经历 |

ActivityContext={activity_ref,revision,input_epoch,context_ref,goal_refs,commitment_refs,personality_profile_ref,value_profile_ref,state_refs,memory_scope,policy_epoch,budget,deadline}。

Budget={remaining_tokens,remaining_tool_calls,remaining_attempts,remaining_time_ms,remaining_cost_minor?,currency?}；成本未知不能记零。协调器保留 reserve 和 settle 操作，网络调用前预留预算，返回后结算，超时调用按 unknown_usage 处理。

ReserveBudget 请求={activity_ref,expected_account_revision,operation_ref,reservation_key,requested_usage}，响应={reservation_ref,new_account_revision,remaining_budget}；SettleBudget 请求={reservation_ref,actual_usage?,usage_state,receipt_ref?}，响应={settlement_state,remaining_budget}。重复结算幂等，未知远端用量保守占用额度，避免网络重试无限超支。

## 4 M03 认知与独立推理

| 接口 | 请求字段 | 响应字段 | 权责 |
| --- | --- | --- | --- |
| PrepareThought | ActivityContext、purpose、question、observation_refs、memory_refs、constraints、output_schema_ref | thought_request_ref、request_hash、input_manifest、dispatch_job_ref | 固定输入和模型配置 |
| AcceptThoughtResult | request_ref、attempt_ref、raw_response_ref、parsed_ref?、validation_report、observed_current_activity_revision、expected_input_epoch、runtime_epoch | accepted、reason_code、cognition_output_refs、new_activity_revision? | 核对语义有效性后按当前版本CAS；stale/duplicate 不产生业务更新 |
| ReviseBelief | belief_ref、expected_revision、new_statement、acceptance_state、uncertainty、evidence_links | belief_revision_ref、affected_dependency_refs | 修订依据可回溯 |
| EvaluatePrediction | prediction_ref、observed_outcome_ref、scoring_method | assessment_outcome_ref、score、sample_ref | 实际结果独立于原预测 |

CognitionOutput={episode_ref?,interpretations:List<Hypothesis>,belief_proposals:List<BeliefProposal>,predictions:List<PredictionProposal>,plans:List<PlanProposal>,information_gaps,conflicts,control_recommendation,evidence_refs}。每个 Proposal 有 schema_version、local_id 和支持／反对证据，不允许包含可直接执行的任意命令。

模型适配器接口：Generate(PreparedRequest,AttemptContext) → ModelTransportResult。

PreparedRequest={thought_id,model_config_ref,fresh_messages,output_schema,generation_config,deadline,request_hash}；fresh_messages 由 RequestBuilder 新建，没有 history、thread_id、previous_response_id 参数。供应商适配器不得内部补历史。

PreparedRequest 另带 model_version_ref、runtime_epoch、process_run_id。重试保持请求和模型固定；带纠错材料或切换模型的新推理创建新 thought_id，并显式引用旧结果。

AttemptContext={attempt_id,attempt_no,dispatch_token,credential_handle}；credential_handle 只在适配器可见。ModelTransportResult={attempt_id,transport_state,provider_request_id?,response_artifact?,usage?,timing,error?}。流式片段是临时进度，完成后才允许正式校验和接受。

### 当前实现补充：M03认知—经验与M14学习

以下为2026-11-08实际实现的影子接口补充，其余泛化接口仍按原设计状态。物理记录位于既有事件／制品层，经验版本只由M03保存。见[版本和来源约定](../architecture/cognitive-experience-ownership-v0.2.md)。

| 接口 | 所有者 | 输入 | 输出／约束 |
| --- | --- | --- | --- |
| assess_experience | Learning/M14 | opportunity_ref | 学习评估事件；当前gain=null、unknown |
| propose_experience | Learning/M14 | assessment_ref、expected_revision | 经验更新提案，不产生经验版本 |
| propose_experience_invalidation | Learning/M14 | opportunity_ref、reason、expected_revision、actor | controller授权的失效提案，可冲突后重提 |
| save_experience | Cognition/M03 | proposal_ref、expected_revision | 检查提案并保存不可变经验版本；幂等和CAS |
| experience_revision | Cognition/M03 | cell | 当前修订号 |
| experience_snapshot | Cognition/M03 | actor | 经验版本、来源有效性、影子投影；不参与选择 |

M14不得直接写cognition.experience_saved；M03不把学习自述当作已测量收益或已确认事实。旧shadow_interest只委托M03，旧事件只读或显式承接，不产生第二份所有者。

### 当前数值测量补充

[测量实现与约定](../architecture/experience-measurement-v0.1.md)新增ExperienceMeasurement.register/run_predictions/reveal_labels/evaluate；Learning.assess_measured_experience与validate_measured_experience只接受可重算的封存报告；Cognition保存v0.3影子经验版本，兼容0.2。标签、预测、预算和报告保留独立事件引用，仍不接入目标／行为选择。模型端口经领域PredictionPort和基础设施适配器调用，应用服务不在SQLite写事务内做模型I/O。

## 5 M04 记忆

| 接口 | 请求字段 | 响应字段 | 语义 |
| --- | --- | --- | --- |
| EncodeMemory | content、classification_axes、source_refs、entity_refs、valid_time、retention_policy_ref、access_policy_ref、type_details | memory_ref、revision_ref、publication_state | 分类可重叠 |
| RetrieveMemory | ReadScope、query、context_ref、filters、limit、retriever_ref | retrieval_run_ref、items[{revision_ref,rank,score,reason}]、coverage_status | 先过滤权限，不能召回后再向模型泄露 |
| BuildRecall | retrieval_run_ref、selected_revision_refs、purpose、reconstruction_method | recall_ref、content_ref、source_map、uncertainty | 产物不覆盖原记忆 |
| CorrectMemory | memory_ref、expected_revision、corrected_content、evidence_refs、reason | new_revision_ref、dependent_refs | 更新和传播记录 |
| RecordMemoryUse | memory_revision_ref、activity_ref、used_in_ref、operation、outcome_ref? | access_record_ref | retrieved、read、used 分开 |
| MaintainWorkingMemory | activity_ref、items[{temporary_content?/revision_ref?,expires_at?,activation}] | item_refs、expired_refs | 每条内容／引用二选一 |
| RequestDeletion | subject_scope、reason、authority_ref、retention_constraints | deletion_request_ref、blocked_scopes、work_refs | 完成要跨模块验证，不能立即承诺全部删除 |

## 6 M05 人格

| 接口 | 请求字段 | 响应字段 |
| --- | --- | --- |
| GetPersonality | ReadScope、profile_revision_ref? | profile_ref、traits[{dimension_ref,value,uncertainty}] |
| ActivatePersonality | profile_ref、context_ref、state_refs、activity_ref、effect_model_ref | state_refs、cognitive_modifiers、behavior_direct_modifiers、effect_paths |
| ProposePersonalityChange | current_profile_ref、evidence_refs、proposed_traits、trial_ref | update_proposal_ref、required_gates |
| MeasurePersonality | evaluation_run_ref、behavior_refs、measurement_method | measurement_refs、scores、uncertainty |

effect_paths 标记已经通过注意、目标等中介发挥的作用；行为层不得把同一路径重新完整计分。人格配置和行为测量分别返回，不能混作一个真实性分数。

## 7 M06 价值、目标与动机

| 接口 | 请求字段 | 响应字段 |
| --- | --- | --- |
| ActivateValues | value_profile_ref、context_ref、task_ref、evidence_refs | activations、compatibility_relations、conflicts |
| ProposeGoals | cognition_output_ref、external_task_refs、commitment_refs、maintenance_refs、value_activations | candidate_goal_refs、blocked_goals及理由 |
| EvaluateGoals | goal_refs、context_ref、prediction_refs、state_refs、relation_refs、strategy_ref | batch_ref、scores、probabilities、factor_paths |
| AcceptGoals | batch_ref、selected_goal_refs、expected_activity_revision | active_goal_refs、transition_refs、conflict_refs |
| SetGoalState | goal_ref、expected_state_revision、target_state、evidence_refs、reason | transition_ref、新状态与序号 |
| DeriveMotivation | active_goal_ref、state_refs、progress、source、regulation_type | motivation_ref、intensity、persistence、satiation、budget、stop_conditions |

价值是相对优先关系，规则是外部边界。目标成功判定需要证据与规则结果，不由“模型说完成”单独触发。

## 8 M07 习惯

| 接口 | 请求字段 | 响应字段 |
| --- | --- | --- |
| MatchHabitCues | context_ref、activity_ref、habit_scope、rule_engine_ref | opportunities[{cue_ref,match_result,match_score,habit_ref}] |
| SuggestHabitResponses | opportunity_refs、active_goal_refs、inhibition_rules | response_candidates、association_refs、inhibited及理由 |
| RecordHabitOpportunity | opportunity_ref、action_taken、control_mode、candidate_ref?、outcome_ref? | opportunity_record_ref、activation_ref |
| ProposeHabitUpdate | association_ref、opportunity_refs、feedback_refs、mechanism_ref | proposal_ref、before_strength、proposed_strength |

即使未执行，也保存线索机会；重复行为与习惯触发不是同一标签。习惯只提出候选，执行由决策和门禁负责。

## 9 M08 关系

| 接口 | 请求字段 | 响应字段 |
| --- | --- | --- |
| ResolveActor | observed_identifiers、evidence_refs、resolution_policy | actor_ref?、candidate_refs、identity_status |
| GetRelationship | ReadScope、actor_ref、domain、context_ref | relationship_ref、dimension_values、trust_assessments、expectations、commitment_refs |
| RecordInteraction | actor_ref、event_ref、activity_ref、interaction_role | interaction_ref |
| ProposeRelationshipChange | relationship_ref、expected_revision、dimension、evidence_refs、attribution_ref、proposed_value | proposal_ref、change_scope |
| CorrectRelationshipAttribution | change_ref、counter_evidence_refs、reason | correction_ref、dependent_update_refs |

身份未解析时不强行合并同名对象。信任输出包含领域、条件和证据；授权必须另查权限服务。

## 10 M09 社会承诺

| 接口 | 请求字段 | 响应字段 |
| --- | --- | --- |
| ProposeCommitment | debtor_ref、creditor_ref、kind、antecedent_rule、consequent_rule、due_at?、source_refs | proposed_commitment_ref、confirmation_requirements |
| ConfirmCommitment | commitment_ref、actor_ref、confirmation_event_ref、grant_ref?、expected_state_revision | confirmation_ref、transition_ref |
| LinkFulfillmentGoal | commitment_ref、goal_ref、role | link_ref |
| AssessCompliance | commitment_ref、observed_interval、evidence_refs、rule_engine_ref | check_ref、result、missing_evidence |
| TransitionCommitment | commitment_ref、expected_state_revision、target_state、evidence_refs、reason、related_actor_notification | transition_ref、new_state、notification_work_refs |

达成型和维持型分别判定；解除、违约与无法履行保留事实。自己的行动意图通过目标模块管理，不能自动变成对他者的承诺。

## 11 M10 内部状态

| 接口 | 请求字段 | 响应字段 |
| --- | --- | --- |
| ObserveState | definition_ref、value、unit、observed_at、source_ref、quality | observation_ref、expires_at |
| EstimateState | definition_ref、input_refs、method_ref、uncertainty | estimate_ref、estimate、valid_until |
| GetStateSnapshot | ReadScope、required_dimensions、at_time、freshness_policy | snapshot_refs、values、unknown_dimensions、stale_dimensions |

估计可引用关系模块的条件信任，不另学一套关系。资源不足、不确定性和冲突产生不同响应建议，不映射为一个统一“情绪值”。

## 12 M11 行为决策

| 接口 | 请求字段 | 响应字段 |
| --- | --- | --- |
| GenerateCandidates | ActivityContext、plan_refs、habit_suggestions、tool_catalog、information_gaps | candidates[{local_id,action_type,tool_ref?,arguments,expected_effect,source_paths}] |
| EvaluateCandidates | candidates、policy_assessments、predictions、goal_evaluation_ref、direct_modifiers、strategy_ref | candidate_scores、blocked_reasons、selection_distribution、factor_paths |
| FinalizeDecision | activity_ref、candidate_set、selection_strategy、seed?、expected_revision | decision_ref、selected_candidate_ref、action_proposal_ref? |

候选包含等待、核验、求助、拒绝和不行动。没有外部副作用的内部决定可只返回 decision_ref，不为每次思考虚构工具执行。任何 action_proposal 都尚未自动获得执行权限。

## 13 M12 边界与权限

| 接口 | 请求字段 | 响应字段 |
| --- | --- | --- |
| AssessAction | actor_ref、tool_ref、capability_ref、resource_scope、arguments_hash、context_ref | allow/deny/approval_required/unknown、reason、matching_grant_refs、policy_epoch |
| RequestApproval | action_ref、proposal_revision、tool_ref、arguments_hash、scope、expiry | approval_request_ref、state |
| DecideApproval | approval_ref、decision、actor_ref、expected_revision、evidence_event_ref | approval_ref、authorization_ref?、event_refs |
| AuthorizeDispatch | action_ref、proposal_revision、current_arguments_hash、deadline | authorization_record_ref、capability_token、expiry、policy_epoch |
| RevokeGrant | grant_ref、actor_ref、reason | grant_change_ref、new_policy_epoch、affected_action_refs |
| BeginExecution | action_ref、attempt_ref、capability_token、arguments_hash | start_gate_ref、permit／denial、policy_epoch |

capability_token 是短期运行秘密，不进入 LLM 请求和普通日志；数据库只保存摘要与关联。PolicyService 和 Dispatcher 的执行开始门禁必须串行裁决撤销与开始操作。

## 14 M13 工具执行与结果

| 接口 | 请求字段 | 响应字段 |
| --- | --- | --- |
| EnqueueAction | authorized_action_ref、authorization_record_ref | outbox_ref、state |
| DispatchAction | action_ref、attempt_no、capability_token、parameters、deadline、idempotency_key | attempt_ref、backend_operation_id?、receipt_ref?、state |
| PollAction | attempt_ref、backend_operation_id | running／succeeded／failed／partial／unknown、result_ref? |
| CancelAction | action_ref、reason | cancellation_ack、actual_state、verification_required |
| VerifyAction | action_ref、expected_effect、receipt_refs、environment_observations | verification_ref、actual_effects、outcome、uncertainty |
| IngestActionResult | action_ref、attempt_ref、source_event_id、receipt_artifact_ref、result_state、evidence_refs | event_ref、persisted_result_ref、deduplicated |

ToolDescriptor={tool_id,version,input_schema,output_schema,required_capability,scope_schema,reversibility,idempotency_support,query_support,cancellation_support,timeout_policy}。参考框架的能力通过该契约适配，不能把对方会话内的自动思考当成我们的直接工具结果。

工具返回统一另含 transport_state、execution_state、verification_state；进程退出成功只属于 execution_state，不直接完成目标。unknown 效果阻断依赖该成功条件的计划步骤，不阻断核验、求助或无依赖任务。

## 15 M14 学习反馈与受控更新

| 接口 | 请求字段 | 响应字段 |
| --- | --- | --- |
| RecordFeedback | prediction_ref?、result_ref、signal_type、error_value?、description?、evidence_refs | feedback_ref |
| AttributeOutcome | feedback_ref、candidate_cause_refs、method_ref、evidence_level | attribution_refs、uncertainty、unresolved_causes |
| ProposeUpdate | owner_module、target_ref、expected_revision、mechanism_ref、proposed_change、evidence_refs、risk | proposal_ref、required_gates |
| RegisterTrial | proposal_ref、baseline_run_ref、scope、candidate_version | trial_ref、evaluation_requirements |
| EvaluateTrial | trial_ref、evaluation_run_refs、independent_standard_ref | benefit、regression、accept/reject/continue、evaluation_ref |
| CommitUpdate | proposal_ref、expected_target_revision、evaluation_refs、authority_ref | new_revision_ref、commit_ref、dependent_refresh_refs |
| RevertUpdate | commit_ref、reason_evidence、expected_current_revision | compensating_proposal_ref | 

正式写入由目标模块所有者执行；学习服务组织证据和流程。撤销通常生成新的补偿版本，不改写过去。

## 16 M15 身份、自我与连续性

| 接口 | 请求字段 | 响应字段 |
| --- | --- | --- |
| BootstrapInstance | bootstrap_key、controller_ref、configuration_ref、initial_identity_manifest | instance_ref、initialization_run_ref、phase |
| CheckContinuity | instance_ref、checkpoint_ref、expected_lineage、required_dimensions | per_dimension_results、incident_refs、restrictions |
| PrepareMigration | instance_ref、target_environment、checkpoint_ref、authority_ref | migration_manifest、freeze_requirements |
| RegisterCopyOrFork | source_instance_ref、checkpoint_ref、operation、authority_ref | new_instance_refs、lineage_refs、inheritance_decisions |
| EvaluateSelfCapability | capability_model_ref、evaluation_run_ref、actual_performance | calibration_ref、correction_proposal_ref? |

数据库注册谱系不能代替 Supervisor 的单活动实例锁。复制不自动继承授权；迁移交接必须有源冻结和目标确认。

## 17 M16 数字健康

| 接口 | 请求字段 | 响应字段 |
| --- | --- | --- |
| CollectHealth | requirement_refs、observed_at、freshness_policy | observation_refs、missing_checks |
| AssessHealth | observation_refs、criticality_rules、capability_dependencies | assessments、incidents、available_capabilities、restrictions |
| PlanMaintenance | incident_ref、allowed_capabilities、recovery_options、authority_ref | plan_ref、repair/degrade/rollback/help/stop、approval_requirements |
| VerifyRecovery | maintenance_attempt_ref、independent_check_refs、expected_functionality | verification_ref、recovered/degraded/unresolved、residual_damage |

健康模块提出维护动作，仍经过行为与权限层。无法维持正常思考时由外部检测和恢复机制接管，不假设受损系统可以证明自己恢复。

## 18 M17 存储、发布与观测

| 接口 | 请求字段 | 响应字段 |
| --- | --- | --- |
| ExecuteUnitOfWork | command_key、expected_versions、typed_operations | committed_refs、event_refs、new_versions |
| PublishObject | object_ref、owner_module、expected_revision、validation_schema、evidence_refs | publication_ref、ready／quarantined、errors |
| AppendEvent | event_type、source、source_event_id、causation_ref?、payload_ref、payload_hash、lane | event_ref、event_seq、deduplicated |
| ClaimJob | worker_ref、supported_kinds、lease_duration、now | job_ref?、lease_token?、deadline? |
| CompleteJob | job_ref、lease_token、result_refs、next_work | completion_state、event_refs |
| ReadEvents | instance_ref、after_seq、limit、authorized_filter | events、next_cursor、has_more、gap_notice? |
| RecordMetric | definition_ref、run_ref、source_refs、numerator?、denominator?、value?、uncertainty | sample_ref、computable |
| BackupState | checkpoint_ref、consistency_manifest、authority_ref | snapshot_ref、hashes、restore_scope |

typed_operations 是封闭的命令类型集合，不接受外部调用者传任意 SQL。claim/complete 都校验租约，失效 worker 不能提交旧结果。事件过滤后的 cursor 仍按已扫描序号推进，不能误报跳号为丢失；保留期裁剪造成缺口时返回 gap_notice 并重新读取状态快照。

ClaimJob 返回 lease_generation、lease_expires_at；CompleteJob 和续租接口 RenewLease 都必须携带 job_ref、lease_token、lease_generation。消费事件和 outbox 投递使用相同规则。任务接管后旧执行者的迟到结果只能作为待核验外部证据输入，不能绕过新的活动版本直接提交业务结果。

## 19 E01 Supervisor 控制接口

控制面以本机固定入口和 Unix socket 提供服务。ControlHeader={request_id,idempotency_key,instance_ref,authenticated_principal,expected_control_revision?,deadline?}；Runtime service 身份仅有受限 set_wake、clear_wake、maintenance/deploy request 能力，不能自行授权部署或覆盖用户停止。

| 接口 | 请求字段 | 响应字段 |
| --- | --- | --- |
| Start／Resume | instance_ref、release_ref?、reason、user_authority | command_ref、process_run_ref?、control_state |
| Stop | instance_ref、reason、grace_period | command_ref、user_stopped=true、pending_effects |
| SetWake／ClearWake | generation、next_due_at?、schedule_hash | command_ref、applied_generation、state、stale_generation |
| SubmitInbound | source、source_event_id、payload_ref、payload_hash、authority、expiry | inbound_ref、received/waking/delivered/rejected |
| AckInbound | inbound_ref、runtime_event_ref、payload_hash | delivered_state |
| Heartbeat | process_run_ref、runtime_state、release_ref、schema_version、last_progress_at、health_summary | accepted、control_directives |
| PrepareDeploy | candidate_release、build_manifest、schema_compatibility、authority | deployment_ref、required_checks |
| SwitchDeploy | deployment_ref、expected_active_release、authority | switch_ref、phase、recovery_plan |
| Rollback | failed_deployment_ref、target_release、data_compatibility_plan、authority | rollback_ref、phase、continuity_restrictions |

WakeNotification={firing_id,instance_ref,generation,scheduled_due_at,fired_at,source_event_id,late_by_ms}。Runtime 以 source_event_id 幂等接收，对账实际 jobs 后给出计划新代次。用户停止优先于定时唤醒；主机断电期间不承诺准点执行。

新增 PrepareSleep={instance_ref,runtime_epoch,process_run_id,sleep_generation,wake_generation,state_manifest_hash,last_runtime_event_seq} → {handoff_ref,acknowledged,control_revision}；CommitSleep={handoff_ref,expected_control_revision,final_manifest_hash} → {sleeping/aborted,reason}。准备期间冻结新业务调度，新增工作或控制变更时取消交接重算。user_stopped 时普通消息不得自动唤醒。

## 20 API、默认运行参数和错误收口

浏览器连接 Supervisor 的固定控制入口；在线业务请求反向转交 Runtime，离线输入由 SubmitInbound 持久接收。REST 保留 /v1/events、/v1/activities/{id}、取消、审批、健康、承诺与指标接口；/v1/events/stream 在休眠时推送控制事件，在恢复后接续业务事件，游标带 plane=control/runtime，不能混用两库序号。

HTTP 202=持久接收；200=同步完成或重复请求的原结果；409=版本或幂等摘要冲突；422=结构错误；403=无授权；503=关键依赖不可用。审批要求是可跟踪的业务状态，不只返回一次403后丢失原动作。

部署配置必须显式提供：队列容量、请求大小、模型总期限与尝试上限、工具期限、租约长度和续租间隔、心跳间隔与失联窗口、日志保留、工件保留、单活动预算。配置提供有限默认值并在启动校验，例如续租间隔小于租约长度；具体生产数值由后续环境和实验确定。

模型暂未对接时用 not_configured 能力状态，不自动回退到未知供应商。预算耗尽、规则 unknown、存储提交失败、关键身份校验失败都终止当前推进或降级并保留原因，不无限重试。

## 21 设计完整性与后续工作

M01—M17、E01 已有输入、输出、状态归属和写入协议；跨库使用持久命令、去重、代次和确认；独立思考有请求边界和唯一接受；动作有提案到实际核验的完整链路。主流程不存在必须依赖未定义会话历史才能执行的步骤。

下一步先把数据库增量与接口模型同步为可执行定义，再实现框架，最后进行接口、恢复、权限与生命指标验证。本轮没有生成类型代码、迁移 SQL 或运行服务。具体供应商、工具插件、界面样式和阈值调优不影响当前架构的职责闭合。
