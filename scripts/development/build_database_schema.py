"""Generate reviewable SQLite DDL and field dictionary from explicit module specs.

This is a deterministic artifact generator, not a runtime database service.
"""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'database'
# field:type:description; ? means nullable; @table means same-instance FK.
# p=probability, b=boolean, j=JSON, n=nonnegative real, i=nonnegative integer.
SPEC = r'''
[共同基础]
object_registry|对象登记|kind:t:对象表类型
object_revision_registry|版本登记|object_id:@object_registry:所属对象 revision_no:i:修订序号 kind:t:版本类型
world_entities|世界对象|entity_type:t:对象类型 canonical_name:t:规范名称 resolution_status:e(unresolved,resolved,ambiguous):解析状态
world_entity_aliases|对象别名|entity_id:@world_entities:对象 alias:t:别名 source_ref:?@evidence_items:来源
world_entity_relations|对象关系|subject_id:@world_entities:主体 relation_type:t:关系类型 object_id:@world_entities:客体 evidence_id:@evidence_items:证据
context_snapshots|情境快照|activity_id:@activities:活动 task_ref:?@goal_items:任务 location_ref:?@world_entities:地点 context_schema:t:结构版本 attributes_json:j:情境属性
context_entity_links|情境对象|context_id:@context_snapshots:情境 entity_id:@world_entities:对象 role:t:角色
artifacts|材料载体|hash:t:内容摘要 size:i:字节数 media_type:t:媒体类型 storage_ref:t:存储位置 retention_class:t:保留分类
evidence_items|来源证据|origin_object_id:?@object_registry:来源对象 origin_revision_id:?@object_revision_registry:来源版本 artifact_id:?@artifacts:材料 source_actor_id:?@social_actors:提供者 method:t:获取方法
evidence_derivations|证据派生|derived_evidence_id:@evidence_items:派生证据 parent_evidence_id:@evidence_items:上游证据 operation:t:派生操作 version:t:方法版本
activities|生命活动|trigger_event_id:?@perception_signals:触发输入 state:e(pending,running,waiting_input,waiting_tool,paused,completed,failed,cancelled):活动状态 budget_json:j:预算 checkpoint_ref:?@checkpoints:恢复点 release_id:t:部署版本
activity_steps|活动步骤|activity_id:@activities:活动 step_no:i:步骤序号 step_type:t:步骤类型 state:e(pending,running,completed,failed,cancelled,unknown):步骤状态 input_ref:?@object_registry:输入 output_ref:?@object_registry:输出 attempt:i:尝试次数
activity_context_refs|活动读取版本|activity_id:@activities:活动 object_revision_id:@object_revision_registry:精确版本 role:t:用途
rule_definitions|规则版本|name:t:规则名称 version:i:版本 expression_json:j:声明式条件 engine_version:t:解释器版本
capability_definitions|能力定义|name:t:能力名称 description:t:能力描述
tool_definitions|工具定义|name:t:工具名称 version:i:工具版本 input_schema:j:参数结构 capability_id:@capability_definitions:所需能力 supports_idempotency:b:支持幂等可查询 supports_query:b:支持结果查询
[感知]
perception_channels|输入通道|kind:t:通道类型 capabilities:j:能力 verification_method:t:验证方式 state:e(available,unavailable,unknown):状态
perception_signals|原始输入|channel_id:@perception_channels:通道 source_actor_id:?@social_actors:来源主体 external_id:?t:外部去重标识 artifact_id:@artifacts:原始内容 received_at:t:接收时间
perception_observations|观察|signal_id:@perception_signals:主输入 context_id:@context_snapshots:情境 current_revision_id:?@perception_observation_revisions:当前修订 state:e(active,disputed,retracted):状态
perception_observation_revisions|观察修订|observation_id:@perception_observations:所属观察 revision_no:i:序号 content:t:观察内容 entity_ref:?@world_entities:对象 locator_json:j:原材料定位 uncertainty_json:j:不确定性 extractor_version:t:提取版本
perception_observation_sources|观察来源|observation_revision_id:@perception_observation_revisions:观察修订 signal_id:@perception_signals:输入 locator_json:j:来源定位
perception_quality_checks|感知质量|signal_id:?@perception_signals:输入 observation_revision_id:?@perception_observation_revisions:观察修订 check_type:t:检查类型 result:e(pass,fail,unknown):结果 evidence_id:@evidence_items:依据
[人格]
personality_dimensions|人格维度|parent_id:?@personality_dimensions:上级维度 name:t:名称 definition:t:定义 scale_min:r:下界 scale_max:r:上界 direction:t:方向 theory_version:t:理论版本
personality_profiles|人格版本|version:i:版本 effective_at:t:生效时间 previous_profile_id:?@personality_profiles:前版 update_commit_id:?@learning_update_commits:更新提交
personality_trait_values|特质值|profile_id:@personality_profiles:人格版本 dimension_id:@personality_dimensions:维度 central_value:r:中心值 uncertainty_json:j:不确定性
personality_states|人格状态|activity_id:@activities:活动 context_id:@context_snapshots:情境 dimension_id:@personality_dimensions:维度 value:r:状态值 value_origin:e(configured,derived,estimated,measured):数值来源 method_version:t:方法版本
personality_context_effects|人格情境作用|profile_id:@personality_profiles:版本 dimension_id:@personality_dimensions:维度 context_rule_id:@rule_definitions:情境规则 effect_parameters:j:调节参数
personality_behavior_measurements|人格行为测量|evaluation_run_id:@evaluation_runs:实验 dimension_id:@personality_dimensions:维度 behavior_ref:@action_results:行为结果 score:r:评分 rater_method:t:评分方法
personality_change_records|人格变化|old_profile_id:@personality_profiles:原版 new_profile_id:@personality_profiles:新版 proposal_id:@learning_update_proposals:提案 reason:t:原因 reversal_of:?@personality_change_records:撤销对象
[认知]
cognition_episodes|认知任务|activity_id:@activities:活动 question:t:问题 context_id:@context_snapshots:情境 method_version:t:方法 state:e(open,resolved,paused,failed):状态
cognition_concepts|概念|name:t:名称 definition:t:定义 current_revision_id:?@cognition_concept_revisions:当前修订
cognition_concept_revisions|概念修订|concept_id:@cognition_concepts:概念 revision_no:i:序号 definition:t:定义 evidence_id:@evidence_items:依据
cognition_concept_relations|概念关系|subject_concept_id:@cognition_concepts:主体 relation_type:t:关系 object_concept_id:@cognition_concepts:客体 evidence_id:@evidence_items:证据
cognition_beliefs|信念|subject_ref:@world_entities:主体 predicate:t:谓词 object_ref:?@world_entities:客体 literal:?j:字面值 scope:j:适用范围 current_revision_id:?@cognition_belief_revisions:当前修订
cognition_belief_revisions|信念修订|belief_id:@cognition_beliefs:信念 revision_no:i:序号 content:t:命题 acceptance_state:e(accepted,held,rejected,expired):接受状态 uncertainty_json:j:不确定性 method_version:t:方法
cognition_hypotheses|竞争解释|episode_id:@cognition_episodes:任务 content:t:解释 state:e(open,supported,rejected,held):状态 uncertainty_json:j:不确定性
cognition_evidence_links|认知证据|target_revision_id:@object_revision_registry:目标版本 evidence_id:@evidence_items:证据 stance:e(support,oppose,neutral):立场 strength_method:t:强度方法 assessment:j:评估
cognition_predictions|预测|episode_id:@cognition_episodes:任务 target_ref:@object_registry:预测对象 predicted_outcome:j:预期结果 probability_kind:e(outcome,correctness):概率含义 probability:p:概率 due_at:t:核验时限 verification_rule:@rule_definitions:核验规则
cognition_plans|计划|goal_id:@goal_items:目标 version:i:版本 state:e(draft,active,paused,completed,cancelled):状态 previous_plan_id:?@cognition_plans:前版
cognition_plan_steps|计划步骤|plan_id:@cognition_plans:计划 step_no:i:序号 action_template:j:动作模板 preconditions:@rule_definitions:前置规则 expected_outcome:j:预期
cognition_plan_dependencies|步骤依赖|step_id:@cognition_plan_steps:步骤 depends_on_step_id:@cognition_plan_steps:依赖步骤 condition:@rule_definitions:条件
cognition_assessments|元认知评估|episode_id:@cognition_episodes:任务 assessment_type:t:评估类型 estimate:j:估计 information_gap:t:信息缺口 recommended_control:t:控制建议
cognition_assessment_outcomes|认知核验|assessment_id:?@cognition_assessments:评估 prediction_id:?@cognition_predictions:预测 outcome_ref:@action_results:结果 scoring_method:t:评分方法 score:r:分数
cognition_attention_allocations|注意分配|episode_id:@cognition_episodes:任务 target_revision_id:@object_revision_registry:关注版本 weight:p:权重 allocation_stage:e(before_decision,after_decision):记录阶段 method:t:方法
[记忆]
memory_items|记忆对象|current_revision_id:?@memory_revisions:当前修订 state:e(active,archived,retracted,deleted):状态 salience:p:显著性 access_policy_ref:@policy_versions:访问策略
memory_classifications|记忆分类|memory_id:@memory_items:记忆 axis:e(content,self_relation,temporal_function,other):分类轴 label:t:分类值 method_version:t:方法
memory_revisions|记忆修订|memory_id:@memory_items:记忆 revision_no:i:序号 content:t:内容 encoding_method:t:编码方法 correction_reason:?t:修正原因
memory_source_links|记忆来源|memory_revision_id:@memory_revisions:记忆修订 evidence_id:@evidence_items:证据 role:e(observed,inferred,summarized,restored):来源角色
memory_relations|记忆关系|from_memory_id:@memory_items:起点 relation_type:t:关系 to_memory_id:@memory_items:终点 evidence_id:@evidence_items:依据
memory_episode_details|情景扩展|memory_revision_id:@memory_revisions:记忆修订 event_ref:@perception_signals:经历输入 time_start:?t:开始时间 time_end:?t:结束时间 place_ref:?@world_entities:地点 outcome_ref:?@action_results:结果
memory_participants|情景参与者|memory_revision_id:@memory_revisions:修订 entity_id:@world_entities:参与对象 role:t:角色
memory_semantic_details|语义扩展|memory_revision_id:@memory_revisions:修订 belief_revision_id:@cognition_belief_revisions:信念版本 scope:j:范围
memory_procedure_details|程序扩展|memory_revision_id:@memory_revisions:修订 skill_ref:@capability_definitions:技能 applicability_rule:@rule_definitions:适用规则 procedure_version:t:程序版本
memory_autobiographical_details|自传扩展|memory_revision_id:@memory_revisions:修订 life_period:t:历史阶段 self_relevance:p:自我关联 identity_significance:t:身份意义
memory_prospective_details|前瞻扩展|memory_revision_id:@memory_revisions:修订 intention_id:@intention_items:意图 cue_rule_id:@rule_definitions:触发线索 target_time:?t:目标时间
memory_retrieval_runs|检索请求|activity_id:@activities:活动 query:t:查询 context_id:@context_snapshots:情境 retriever_version:t:检索版本
memory_retrieval_results|检索候选|run_id:@memory_retrieval_runs:检索 memory_revision_id:@memory_revisions:版本 rank:i:排序 score:r:检索分数 selection_reason:t:选择原因
memory_recall_products|召回重构|run_id:@memory_retrieval_runs:检索 reconstructed_content:t:召回产物 method_version:t:重构版本
memory_recall_sources|重构来源|recall_id:@memory_recall_products:产物 memory_revision_id:@memory_revisions:原记忆 evidence_id:@evidence_items:证据
memory_access_records|记忆使用|memory_revision_id:@memory_revisions:版本 activity_id:@activities:活动 operation:e(encoded,retrieved,read,used):操作 used_in_ref:?@object_registry:使用位置 outcome_ref:?@action_results:结果
memory_retention_rules|保留规则|scope:j:作用域 action:e(retain,downweight,archive,delete):动作 trigger:@rule_definitions:触发 policy_version:@policy_versions:策略
working_memory_items|工作记忆|activity_id:@activities:活动 content:?t:临时内容 object_revision_ref:?@object_revision_registry:引用版本 expires_at:?t:失效时间 item_kind:e(temporary,reference):形式
working_memory_activations|工作记忆激活|item_id:@working_memory_items:条目 activity_step_id:@activity_steps:步骤 activation:p:激活 attention_state:e(focused,available,inactive):关注状态
[价值]
value_dimensions|价值维度|definition:t:定义 scale:j:量表 theory_version:t:理论版本
value_dimension_relations|价值关系|from_id:@value_dimensions:起点 to_id:@value_dimensions:终点 relation_type:e(compatible,conflicting,other):关系 method:t:方法 evidence_id:@evidence_items:依据
value_profiles|价值版本|version:i:版本 previous_id:?@value_profiles:前版 effective_at:t:生效时间 update_commit_id:?@learning_update_commits:提交 normalization_rule:t:归一化规则
value_weights|价值权重|profile_id:@value_profiles:版本 dimension_id:@value_dimensions:维度 weight:r:相对权重 uncertainty_json:j:不确定性
value_activations|价值激活|profile_id:@value_profiles:版本 activity_id:@activities:活动 context_id:@context_snapshots:情境 dimension_id:@value_dimensions:维度 activation:p:激活
value_conflicts|价值冲突|activity_id:@activities:活动 resolution_ref:?@object_registry:处理依据 state:e(open,resolved,held):状态
value_conflict_members|冲突成员|conflict_id:@value_conflicts:冲突 dimension_id:@value_dimensions:价值 role:t:角色
value_behavior_measurements|价值行为效度|evaluation_run_id:@evaluation_runs:实验 decision_ref:@decision_records:决策 dimension_id:@value_dimensions:价值 score:r:评分
value_change_records|价值变化|old_profile_id:@value_profiles:原版 new_profile_id:@value_profiles:新版 proposal_id:@learning_update_proposals:提案 reason:t:原因
[目标动机]
goal_items|目标|source_ref:@object_registry:来源 content:t:目标 target_ref:?@world_entities:对象 state:e(candidate,accepted,active,paused,completed,cancelled,expired,failed):状态 success_rule:@rule_definitions:完成规则 stop_rule:@rule_definitions:停止规则 due_at:?t:期限
goal_relations|目标关系|from_goal_id:@goal_items:起点 to_goal_id:@goal_items:终点 relation_type:e(subgoal,depends_on,conflicts,supports):关系
goal_evaluations|目标评估|goal_id:@goal_items:目标 activity_id:@activities:活动 value_alignment:r:价值一致 expectancy:p:可达期望 cost:n:成本 risk:n:风险 urgency:p:紧迫 model_version:@model_versions:模型
goal_evaluation_factors|目标因素|evaluation_id:@goal_evaluations:评估 source_revision_id:@object_revision_registry:来源 factor_type:t:类型 contribution:r:贡献
goal_activation_batches|目标激活批次|activity_id:@activities:活动 strategy_version:t:策略 state:e(draft,finalized):批次状态
goal_activation_records|目标激活|decision_batch_id:@goal_activation_batches:批次 goal_id:@goal_items:目标 score:r:分数 probability:p:概率 selected:b:选中 strategy_version:t:策略
goal_transitions|目标转换|goal_id:@goal_items:目标 from_state:t:原状态 to_state:t:新状态 event_id:@perception_signals:事件 reason:t:原因
intention_items|持续意图|goal_id:@goal_items:目标 plan_id:?@cognition_plans:计划 trigger_rule:@rule_definitions:触发 state:e(proposed,active,paused,completed,abandoned):状态 abandonment_rule:@rule_definitions:放弃规则
intention_transitions|意图转换|intention_id:@intention_items:意图 from_state:t:原状态 to_state:t:新状态 reason_ref:@evidence_items:依据
motivation_states|动机状态|goal_id:@goal_items:目标 activity_id:@activities:活动 intensity:p:强度 source_type:t:来源 regulation_type:t:调节方式 persistence:p:持续性 satiation:p:满足程度 budget:j:资源预算
[习惯]
habit_items|习惯|response_template:j:反应模板 state:e(learning,active,inhibited,extinct):状态 procedure_memory_ref:?@memory_revisions:技能记忆
habit_cues|习惯线索|habit_id:@habit_items:习惯 context_rule_id:@rule_definitions:情境规则 match_method:t:匹配方法
habit_associations|线索反应联系|habit_id:@habit_items:习惯 cue_id:@habit_cues:线索 strength:p:强度 uncertainty_json:j:不确定性 learning_version:t:学习方法
habit_opportunities|线索机会|cue_id:@habit_cues:线索 activity_id:@activities:活动 match_score:p:匹配程度 action_taken:b:是否行动 control_mode:e(habit,goal_directed,mixed,unknown):控制方式
habit_activations|习惯触发|opportunity_id:@habit_opportunities:机会 candidate_id:?@decision_candidates:候选 triggered:b:触发 inhibited:b:抑制 inhibition_reason:?t:抑制原因
habit_learning_records|习惯更新|association_ref:@habit_associations:联系 before_value:p:原强度 after_value:p:新强度 feedback_id:@learning_feedback:反馈 update_commit_id:@learning_update_commits:提交
[关系]
social_actors|社会主体|entity_id:@world_entities:世界对象 actor_type:t:主体类型 identity_status:e(unverified,verified,disputed):身份核验
social_relationships|关系|actor_id:@social_actors:对象 state:e(active,dormant,ended,disputed):状态 current_revision:i:当前序号
social_relationship_dimensions|关系维度|definition:t:定义 scale:j:量表 method:t:方法
social_relationship_values|关系值|relationship_id:@social_relationships:关系 dimension_id:@social_relationship_dimensions:维度 value:r:数值 evidence_id:@evidence_items:依据
social_trust_assessments|信任判断|relationship_id:@social_relationships:关系 domain:t:领域 condition_rule:@rule_definitions:条件 dimension:t:可信特征 estimate:p:估计 uncertainty_json:j:不确定性
social_trust_evidence|信任依据|assessment_id:@social_trust_assessments:判断 evidence_id:@evidence_items:证据 stance:e(support,oppose,neutral):立场 attribution_ref:?@learning_attributions:归因
social_expectations|关系预期|relationship_id:@social_relationships:关系 expected_action:j:预期行动 context_rule:@rule_definitions:情境 probability:p:发生概率 outcome_ref:?@action_results:实际结果
social_interactions|互动|relationship_id:@social_relationships:关系 event_id:@perception_signals:输入 activity_id:@activities:活动 interaction_role:t:角色
social_relationship_changes|关系变化|relationship_id:@social_relationships:关系 dimension_id:@social_relationship_dimensions:维度 old_value:r:原值 new_value:r:新值 reason_ref:@evidence_items:依据 reversal_of:?@social_relationship_changes:撤销记录
[承诺]
commitment_items|社会承诺|debtor_actor_id:@social_actors:责任方 creditor_actor_id:@social_actors:受益方 kind:e(achievement,maintenance):承诺类型 antecedent_rule:@rule_definitions:生效条件 consequent_rule:@rule_definitions:履行条件 state:e(proposed,confirmed,active,performing,paused,renegotiating,fulfilled,released,impossible,expired,violated):状态 due_at:?t:期限
commitment_confirmations|承诺确认|commitment_id:@commitment_items:承诺 actor_id:@social_actors:确认者 event_id:@perception_signals:确认事件 confirmation_type:t:方式 grant_ref:?@grants:授权
commitment_transitions|承诺转换|commitment_id:@commitment_items:承诺 from_state:t:原状态 to_state:t:新状态 event_id:@perception_signals:变更事件 reason:t:原因
commitment_goal_links|履行目标|commitment_id:@commitment_items:承诺 goal_id:@goal_items:目标 role:t:用途
commitment_conflicts|承诺冲突|state:e(open,resolved,held):状态 resolution_ref:?@evidence_items:裁决 detected_at:t:发现时间
commitment_conflict_members|承诺冲突成员|conflict_id:@commitment_conflicts:冲突 commitment_id:?@commitment_items:承诺 policy_ref:?@policy_versions:规则 resource_ref:?@world_entities:资源
commitment_compliance_checks|维持型承诺检查|commitment_id:@commitment_items:承诺 interval_start:t:开始 interval_end:t:结束 result:e(pass,fail,unknown):结果 evidence_id:@evidence_items:依据
[内部状态]
state_definitions|状态定义|name:t:名称 unit:t:单位 direction:t:方向 measurement_kind:e(observed,estimated):来源类型 ttl:i:有效秒数 range_rule:@rule_definitions:正常范围
state_observations|状态测量|definition_id:@state_definitions:定义 value:r:观测值 observed_at:t:观测时间 source_ref:@evidence_items:来源 quality:e(valid,suspect,missing):质量
state_estimates|状态估计|definition_id:@state_definitions:定义 estimate:r:估计 uncertainty_json:j:不确定性 method_version:t:方法 expires_at:t:到期
state_estimate_sources|估计来源|estimate_id:@state_estimates:估计 source_revision_id:@object_revision_registry:依据 role:t:作用
state_activity_snapshots|采用状态|activity_id:@activities:活动 state_observation_id:?@state_observations:观测 state_estimate_id:?@state_estimates:估计
[决策行动]
decision_records|决策|activity_id:@activities:活动 goal_id:@goal_items:目标 context_id:@context_snapshots:情境 strategy_type:t:策略类型 strategy_version:t:策略版本 seed:?i:随机种子 state:e(draft,finalized):记录状态
decision_candidates|行为候选|decision_id:@decision_records:决策 action_template:j:动作模板 eligible:b:可选 blocked_reason:?t:屏蔽原因 score:r:分数 selection_probability:p:选择概率 selected:b:已选
decision_factor_contributions|决策因素|candidate_id:@decision_candidates:候选 factor_type:t:因素 source_revision_id:@object_revision_registry:来源 effect_path:t:直接或中介路径 contribution:r:贡献
action_intents|动作意图|candidate_id:@decision_candidates:候选 plan_step_id:?@cognition_plan_steps:步骤 tool_id:@tool_definitions:工具 arguments_json:j:参数 grant_version:@grants:授权记录 idempotency_key:t:幂等键 verification_rule:@rule_definitions:核验规则
action_attempts|执行尝试|intent_id:@action_intents:意图 attempt_no:i:尝试序号 started_at:t:开始 finished_at:?t:结束 runner_ref:t:执行器 state:e(pending,running,succeeded,failed,partial,unknown,cancelled):状态
action_results|执行结果|attempt_id:@action_attempts:尝试 state:e(succeeded,failed,partial,unknown):结果 receipt_artifact_id:?@artifacts:原始回执 outcome_ref:?@evidence_items:结果证据 error_type:?t:错误类型
action_effects|外部影响|intent_id:@action_intents:意图 entity_ref:@world_entities:受影响对象 effect_description:t:变化 observed_at:t:观测时间 evidence_id:@evidence_items:证据
action_verifications|动作核验|intent_id:@action_intents:意图 method_version:t:方法 result:e(pass,fail,unknown):结果 evidence_id:@evidence_items:证据
action_attributions|行动归属|action_id:@action_intents:动作 initiator_actor_id:@social_actors:发起者 authorizer_actor_id:@social_actors:授权者 executor_ref:t:执行器 evidence_id:@evidence_items:归属依据
[学习适应]
learning_feedback|学习反馈|prediction_ref:?@cognition_predictions:预测 result_ref:@action_results:结果 signal_type:e(fact,task,cost,risk,evaluation,other):信号 error_value:?r:数值误差 description:?t:文字反馈 source_ref:@evidence_items:来源
learning_attributions|结果归因|feedback_id:@learning_feedback:反馈 target_revision_id:@object_revision_registry:归因对象 cause_type:t:原因 estimate:p:可能性 evidence_id:@evidence_items:依据 evidence_level:e(association,intervention,controlled):证据级别
learning_update_proposals|学习提案|owner_module:t:所有者 target_object_id:@object_registry:目标对象 mechanism_version:t:机制 proposed_change:j:变化 scope:j:范围 risk:n:风险 state:e(proposed,trial,accepted,rejected,reverted):状态
learning_proposal_evidence|提案证据|proposal_id:@learning_update_proposals:提案 evidence_id:@evidence_items:依据 role:t:作用
learning_update_trials|更新试用|proposal_id:@learning_update_proposals:提案 baseline_ref:@evaluation_runs:基线 trial_version:t:试用版本 scope:j:范围 started_at:t:开始 ended_at:?t:结束
learning_update_evaluations|试用评价|trial_id:@learning_update_trials:试用 evaluation_run_id:@evaluation_runs:实验 benefit:r:收益 regression:n:退化 decision:e(accept,reject,continue):结论
learning_update_commits|更新提交|proposal_id:@learning_update_proposals:提案 old_revision_id:@object_revision_registry:旧版本 new_revision_id:@object_revision_registry:新版本 committed_at:t:提交时间 reversal_of:?@learning_update_commits:撤销提交
adaptation_standard_versions|适应标准|level:e(external,core,context,task):层级 scope:j:范围 criteria_json:j:标准 previous_id:?@adaptation_standard_versions:前版 authority_ref:@social_actors:授权者
adaptation_standard_changes|标准变化|old_id:@adaptation_standard_versions:旧版 new_id:@adaptation_standard_versions:新版 proposal_id:@learning_update_proposals:提案 independent_evaluation_ref:@evaluation_runs:独立评估
[身份自我]
identity_instances|生命实例|created_event_id:?@perception_signals:创建事件 state:e(active,suspended,ended,recovery):状态 generation:i:世代 controller_ref:?@social_actors:控制者
identity_lineage|实例谱系|parent_instance_id:@identity_instances:父实例 child_instance_id:@identity_instances:子实例 operation:e(copy,fork,migrate,restore):操作 common_checkpoint_ref:?@checkpoints:共同恢复点 event_id:@perception_signals:事件
identity_anchors|身份锚点|version:i:版本 anchor_data:j:锚点 previous_id:?@identity_anchors:前版 authority_ref:@social_actors:授权者
identity_continuity_checks|连续性检查|checkpoint_ref:@checkpoints:恢复点 dimension:e(instance,causal,functional,relational,narrative):维度 result:e(pass,fail,unknown):结果 evidence_id:@evidence_items:依据
identity_continuity_incidents|连续性损伤|check_id:@identity_continuity_checks:检查 damage_type:t:类型 severity:e(low,medium,high,critical):严重度 recovery_ref:?@maintenance_plans:恢复方案 state:e(open,recovering,resolved,irrecoverable):状态
self_capability_models|能力自我模型|capability:@capability_definitions:能力 conditions:@rule_definitions:适用条件 estimated_performance:p:预期表现 uncertainty_json:j:不确定性
self_capability_evaluations|自我模型校准|model_id:@self_capability_models:模型 evaluation_run_id:@evaluation_runs:实验 actual_performance:p:实际表现 calibration:n:校准误差
self_narrative_versions|自我叙事|period:t:历史范围 summary:t:叙述 previous_id:?@self_narrative_versions:前版 generator_version:t:生成版本
self_narrative_sources|叙事来源|narrative_id:@self_narrative_versions:叙事 memory_revision_id:@memory_revisions:记忆 evidence_id:@evidence_items:依据
[健康维护]
health_requirements|健康要求|capability_ref:@capability_definitions:必要能力 criticality:e(low,medium,high,critical):重要度 acceptable_rule:@rule_definitions:正常规则 policy_version:@policy_versions:策略
health_check_definitions|健康检查定义|requirement_id:@health_requirements:要求 method_version:t:检测方法 schedule:@rule_definitions:调度 independence_class:e(internal,external,independent):独立程度
health_observations|健康观测|check_id:@health_check_definitions:检查 source_revision_ref:@object_revision_registry:底层版本 result:e(pass,fail,unknown):结果 observed_at:t:时间 expires_at:t:失效
health_assessments|健康判断|dimension:t:维度 state:e(healthy,stressed,degraded,critical,recovering,unknown):健康状态 evidence_start:t:窗口开始 evidence_end:t:窗口结束 method_version:t:方法
health_incidents|健康事件|requirement_id:@health_requirements:要求 severity:e(low,medium,high,critical):严重度 state:e(open,contained,recovering,resolved):状态 detected_at:t:发现时间 impact_description:t:影响
health_capability_impacts|受损能力|incident_id:@health_incidents:事件 capability_ref:@capability_definitions:能力 availability:p:可用程度 restriction:t:限制
maintenance_plans|维护方案|incident_id:@health_incidents:事件 strategy:e(repair,isolate,degrade,rollback,help,stop):策略 grant_ref:?@grants:授权 expected_recovery:t:恢复目标 state:e(proposed,approved,running,completed,failed):状态
maintenance_attempts|维护尝试|plan_id:@maintenance_plans:方案 action_intent_id:@action_intents:动作 started_at:t:开始 result_ref:?@action_results:结果
maintenance_verifications|维护核验|attempt_id:@maintenance_attempts:尝试 check_id:@health_check_definitions:核验方法 result:e(pass,fail,unknown):结果 residual_damage:t:剩余损伤 verifier_ref:@social_actors:验证者
[运行权限实验]
grants|授权版本|subject:@social_actors:主体 capability:@capability_definitions:能力 resource_scope:j:资源范围 expiry:?t:到期 revoked_at:?t:撤销 version:i:版本
grant_changes|授权变化|grant_id:@grants:授权 event_id:@perception_signals:事件 operation:e(grant,revoke,expire):动作 authority_ref:@social_actors:授权者
policy_versions|边界策略|version:i:版本 mode:e(authorization,open):模式 scope:j:范围 effective_at:t:生效 authority:@social_actors:制定者
approval_requests|授权请求|action_ref:@action_intents:动作 requested_scope:j:范围 decision:e(pending,approved,rejected,expired):决定 decision_event_id:?@perception_signals:确认事件
jobs|持久任务|kind:t:类型 target_ref:@object_registry:对象 due_at:t:到期 state:e(queued,leased,waiting,succeeded,failed,cancelled):状态 lease_owner:?t:租约拥有者 lease_expiry:?t:租约到期 attempt:i:尝试次数
outbox|动作投递|intent_id:@action_intents:动作 dispatch_state:e(pending,leased,sent,unknown,completed,cancelled):状态 next_attempt_at:t:下次时间
checkpoints|恢复点|activity_id:@activities:活动 state_version:i:状态版本 schema_version:i:结构版本 release_id:t:部署 snapshot_ref:@artifacts:快照
evaluation_runs|实验|dataset_version:t:数据集 baseline_ref:?@evaluation_runs:基线 model_version:@model_versions:模型 seed:?i:种子 conditions:j:条件 state:e(planned,running,completed,failed):状态
metric_definitions|指标字典|name:t:名称 formula_version:t:公式 unit:t:单位 denominator_rule:t:分母规则 missing_rule:t:缺失规则 stratification:j:分层
metric_samples|指标样本|run_id:@evaluation_runs:实验 definition_id:@metric_definitions:指标 source_ref:@object_registry:样本来源 numerator:?r:分子 denominator:?n:分母 value:?r:指标值 uncertainty:j:不确定性
model_versions|模型版本|version:t:版本 artifact_ref:@artifacts:材料 hash:t:摘要 compatibility:j:兼容条件
configuration_versions|配置版本|version:t:版本 artifact_ref:@artifacts:材料 hash:t:摘要 compatibility:j:兼容条件
schema_migrations|结构迁移|version:i:版本 checksum:t:摘要 applied_at:t:执行时间 release_id:t:部署
deletion_requests|删除请求|subject_scope:j:范围 requested_at:t:请求时间 authority_ref:@social_actors:请求者 state:e(requested,blocked,cleaning,verified,failed):状态
deletion_effects|删除传播|request_id:@deletion_requests:请求 object_ref:?@object_registry:对象 artifact_ref:?@artifacts:材料 operation:t:操作 result:e(pending,done,failed):结果 verified_at:?t:验证时间
'''

CONTROL = r'''
[控制平面]
deployments|部署版本|release:t:版本 build_hash:t:构建摘要 schema_min:i:最低结构 schema_max:i:最高结构 state:e(candidate,testing,active,retired,failed):状态
process_runs|进程运行|deployment_id:@deployments:部署 instance_ref:t:业务实例标识 pid:?i:进程编号 started_at:t:开始 exited_at:?t:退出 user_stopped:b:用户停止
wake_checks|唤醒检查|process_run_id:@process_runs:进程 requested_at:t:请求 completed_at:?t:完成 result:e(pass,fail,unknown):结果 detail:j:检查证据
release_switches|部署切换|old_deployment_id:?@deployments:旧部署 new_deployment_id:@deployments:新部署 phase:e(prepared,quiesced,stopped,switched,verified,failed):阶段 evidence:j:交接证据
rollback_runs|回退|switch_id:@release_switches:切换 target_deployment_id:@deployments:目标 reason:t:原因 compatibility_result:e(pass,fail,unknown):兼容结果 result:e(pending,succeeded,failed):结果
backup_manifests|备份清单|deployment_id:@deployments:部署 snapshot_path:t:快照 hash:t:摘要 scope:j:范围 completed_at:t:完成时间
'''

UNIQUE = {
 'object_revision_registry': [('object_id','revision_no')],
 'world_entity_aliases':[('entity_id','alias')],
 'perception_signals':[('channel_id','external_id')],
 'activity_steps':[('activity_id','step_no','attempt')],
 'context_entity_links':[('context_id','entity_id','role')],
 'personality_trait_values':[('profile_id','dimension_id')],
 'personality_context_effects':[('profile_id','dimension_id','context_rule_id')],
 'value_weights':[('profile_id','dimension_id')],
 'memory_classifications':[('memory_id','axis','label')],
 'memory_retrieval_results':[('run_id','rank'),('run_id','memory_revision_id')],
 'habit_associations':[('habit_id','cue_id')],
 'social_actors':[('entity_id',)], 'social_relationships':[('actor_id',)],
 'social_relationship_values':[('relationship_id','dimension_id')],
 'goal_activation_records':[('decision_batch_id','goal_id')],
 'action_intents':[('tool_id','idempotency_key')],
 'action_attempts':[('intent_id','attempt_no')], 'action_results':[('attempt_id',)],
 'outbox':[('intent_id',)], 'schema_migrations':[('version',)],
 'personality_profiles':[('version',)], 'value_profiles':[('version',)],
 'policy_versions':[('version',)], 'identity_anchors':[('version',)],
 'metric_definitions':[('name','formula_version')],
}
EXTRA = {
 'identity_instances':['CHECK (id = instance_id)'],
 'personality_dimensions':['CHECK (scale_min < scale_max)'],
 'cognition_beliefs':['CHECK ((object_ref IS NOT NULL) + (literal IS NOT NULL) = 1)'],
 'evidence_items':['CHECK (origin_object_id IS NOT NULL OR origin_revision_id IS NOT NULL OR artifact_id IS NOT NULL)'],
 'perception_quality_checks':['CHECK ((signal_id IS NOT NULL) + (observation_revision_id IS NOT NULL) = 1)'],
 'cognition_assessment_outcomes':['CHECK ((assessment_id IS NOT NULL) + (prediction_id IS NOT NULL) = 1)'],
 'working_memory_items':["CHECK ((item_kind='temporary' AND content IS NOT NULL AND object_revision_ref IS NULL) OR (item_kind='reference' AND content IS NULL AND object_revision_ref IS NOT NULL))"],
 'commitment_conflict_members':['CHECK ((commitment_id IS NOT NULL) + (policy_ref IS NOT NULL) + (resource_ref IS NOT NULL) = 1)'],
 'state_activity_snapshots':['CHECK ((state_observation_id IS NOT NULL) + (state_estimate_id IS NOT NULL) = 1)'],
 'decision_candidates':['CHECK (eligible = 1 OR (selected = 0 AND selection_probability = 0 AND blocked_reason IS NOT NULL))','CHECK (selected = 0 OR eligible = 1)'],
 'learning_feedback':['CHECK (error_value IS NOT NULL OR description IS NOT NULL)'],
 'learning_update_commits':['CHECK (old_revision_id <> new_revision_id)'],
 'metric_samples':['CHECK (denominator IS NULL OR denominator <> 0 OR value IS NULL)'],
 'jobs':["CHECK ((state='leased' AND lease_owner IS NOT NULL AND lease_expiry IS NOT NULL) OR (state<>'leased' AND lease_owner IS NULL AND lease_expiry IS NULL))"],
 'deletion_effects':['CHECK (object_ref IS NOT NULL OR artifact_ref IS NOT NULL)'],
 'commitment_compliance_checks':['CHECK (interval_start <= interval_end)'],
 'health_assessments':['CHECK (evidence_start <= evidence_end)'],
 'deployments':['CHECK (schema_min <= schema_max)'],
}
REV = {
 'perception_observation_revisions':('observation_id','perception_observations'),
 'cognition_concept_revisions':('concept_id','cognition_concepts'),
 'cognition_belief_revisions':('belief_id','cognition_beliefs'),
 'memory_revisions':('memory_id','memory_items'),
}
PROFILE_REV = {
 'personality_profiles':('profile_object_id','version'),
 'value_profiles':('profile_object_id','version'),
 'identity_anchors':('anchor_object_id','version'),
}
TRANSITIONS = {
 'goal_transitions':('goal_id','goal_items',{'candidate':['accepted','cancelled','expired'],'accepted':['active','paused','cancelled','expired'],'active':['paused','completed','cancelled','expired','failed'],'paused':['active','cancelled','expired','failed']}),
 'intention_transitions':('intention_id','intention_items',{'proposed':['active','abandoned'],'active':['paused','completed','abandoned'],'paused':['active','abandoned']}),
 'commitment_transitions':('commitment_id','commitment_items',{'proposed':['confirmed','released'],'confirmed':['active','released','impossible'],'active':['performing','paused','renegotiating','fulfilled','released','impossible','expired','violated'],'performing':['paused','renegotiating','fulfilled','released','impossible','expired','violated'],'paused':['active','renegotiating','released','impossible','expired','violated'],'renegotiating':['active','released','impossible','violated']})
}

def schema_tables(source):
    tables=parse(source)
    parents={v[1] for v in TRANSITIONS.values()}
    result=[]
    for module,name,desc,fields in tables:
        fields=list(fields)
        if name in TRANSITIONS: fields.append(('transition_no','i','状态转换序号（从1开始）'))
        if name in parents: fields.append(('state_revision','i0','当前状态序号（初始0）'))
        if name in PROFILE_REV: fields.append((PROFILE_REV[name][0],'@object_registry','跨版本稳定配置对象'))
        result.append((module,name,desc,fields))
    return result

def parse(source):
    result=[]; module=''
    for line in source.strip().splitlines():
        if line.startswith('['): module=line[1:-1]; continue
        name,desc,fields=line.split('|')
        parsed=[]
        for field in fields.split():
            key,typ,meaning=field.split(':',2)
            parsed.append((key,typ,meaning))
        result.append((module,name,desc,parsed))
    return result

def column(key,typ):
    optional=typ.startswith('?'); typ=typ.lstrip('?')
    checks=[]
    if typ.startswith('@'): sqltype='TEXT'
    elif typ.startswith('e('):
        sqltype='TEXT'; checks.append(f"{key} IN ({','.join(repr(v) for v in typ[2:-1].split(','))})")
    else:
        sqltype={'t':'TEXT','j':'TEXT','r':'REAL','p':'REAL','n':'REAL','i':'INTEGER','i0':'INTEGER','b':'INTEGER'}[typ]
        if typ=='j': checks.append(f'json_valid({key})')
        if typ=='p': checks.append(f'{key} BETWEEN 0 AND 1')
        if typ in ('n','i','i0'): checks.append(f'{key} >= 0')
        if typ=='b': checks.append(f'{key} IN (0,1)')
    return f'{key} {sqltype}'+('' if optional else ' NOT NULL')+(' DEFAULT 0' if typ=='i0' else '')+''.join(f' CHECK ({c})' for c in checks)

def build(spec,control=False):
    tables=schema_tables(spec); names={x[1] for x in tables}
    sql=['-- Generated by scripts/development/build_database_schema.py. SQLite >= 3.37 with JSON support.',
         'PRAGMA foreign_keys = ON;', 'BEGIN IMMEDIATE;']
    dictionary=['# '+('Supervisor' if control else 'Runtime')+' 完整字段字典\n',
      '生成源：`scripts/development/build_database_schema.py`；与 SQL 同源生成。每表均列出全部物理列。FK 为延迟校验、默认禁止级联删除。\n']
    for module,name,desc,fields in tables:
        cols=['id TEXT PRIMARY KEY NOT NULL']
        if not control: cols.append('instance_id TEXT NOT NULL')
        cols += ["recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))"]
        if 'schema_version' not in [f[0] for f in fields]:
            cols.append('schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version >= 1)')
        if not control:
            cols += ['valid_from TEXT','valid_to TEXT', 'CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))',
                'UNIQUE (instance_id, id)',
                'FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED']
            if name not in ('object_registry','object_revision_registry'):
                cols.append('FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED')
        for key,typ,_ in fields: cols.append(column(key,typ))
        for key,typ,_ in fields:
            target=typ.lstrip('?')
            if target.startswith('@'):
                target=target[1:]; assert target in names, (name,key,target)
                # Lineage is the only intentionally cross-instance relationship.
                cross=name=='identity_lineage' and key in ('parent_instance_id','child_instance_id')
                if control or cross: cols.append(f'FOREIGN KEY ({key}) REFERENCES {target}(id) DEFERRABLE INITIALLY DEFERRED')
                else: cols.append(f'FOREIGN KEY (instance_id, {key}) REFERENCES {target}(instance_id, id) DEFERRABLE INITIALLY DEFERRED')
        for unique in UNIQUE.get(name,[]):
            cols.append('UNIQUE ('+', '.join(([] if control else ['instance_id'])+list(unique))+')')
        if name in REV: cols.append('UNIQUE (instance_id, '+REV[name][0]+', revision_no)')
        cols += EXTRA.get(name,[])
        constraints=[c for c in cols if c.startswith(('CHECK','UNIQUE','FOREIGN KEY'))]
        cols=[c for c in cols if c not in constraints]+constraints
        sql.append(f'-- {module}：{desc}\nCREATE TABLE {name} (\n  '+',\n  '.join(cols)+'\n) STRICT;')
        dictionary += [f'## {name} — {desc}（{module}）\n', '| 字段 | 类型／取值与约束 | 可空 | 含义 |','| --- | --- | --- | --- |',
            '| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |']
        if not control: dictionary.append('| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |')
        dictionary.append('| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |')
        if 'schema_version' not in [f[0] for f in fields]:
            dictionary.append('| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |')
        if not control: dictionary += ['| valid_from | TEXT；UTC | 是 | 业务有效开始 |','| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |']
        for key,typ,meaning in fields:
            dictionary.append(f'| {key} | `{typ.lstrip("?")}` | {"是" if typ.startswith("?") else "否"} | {meaning} |')
        dictionary.append('')
        rules=[x for x in cols if x.startswith(('UNIQUE','CHECK','FOREIGN KEY'))]
        dictionary.append('表级约束：\n\n```sql\n'+'\n'.join(rules)+'\n```\n')
    # Index FK columns: important both for joins and checking parent deletes.
    for _,name,_,fields in tables:
        for key,typ,_ in fields:
            if typ.lstrip('?').startswith('@'):
                sql.append(f'CREATE INDEX ix_{name}_{key} ON {name}('+('' if control else 'instance_id, ')+key+');')
    if not control:
        sql += runtime_triggers(tables)
        sql += ["""CREATE VIRTUAL TABLE memory_search USING fts5(
 content, memory_id UNINDEXED, instance_id UNINDEXED,
 content='memory_revisions', content_rowid='rowid', tokenize='unicode61'
);""",
            trigger('fts_memory_insert','memory_revisions','AFTER', 'INSERT INTO memory_search(rowid,content,memory_id,instance_id) VALUES(NEW.rowid,NEW.content,NEW.memory_id,NEW.instance_id);'),
            trigger('fts_memory_delete','memory_revisions','AFTER', "INSERT INTO memory_search(memory_search,rowid,content,memory_id,instance_id) VALUES('delete',OLD.rowid,OLD.content,OLD.memory_id,OLD.instance_id);",'DELETE'),
            trigger('fts_memory_update','memory_revisions','AFTER', "INSERT INTO memory_search(memory_search,rowid,content,memory_id,instance_id) VALUES('delete',OLD.rowid,OLD.content,OLD.memory_id,OLD.instance_id); INSERT INTO memory_search(rowid,content,memory_id,instance_id) VALUES(NEW.rowid,NEW.content,NEW.memory_id,NEW.instance_id);",'UPDATE')]
        sql += ['CREATE INDEX ix_jobs_due ON jobs(instance_id,state,due_at);',
          'CREATE INDEX ix_commitments_due ON commitment_items(instance_id,state,due_at);',
          'CREATE INDEX ix_goals_due ON goal_items(instance_id,state,due_at);',
          'CREATE INDEX ix_outbox_due ON outbox(instance_id,dispatch_state,next_attempt_at);']
    sql.append('COMMIT;')
    if not control:sql += ['', 'CREATE INDEX ix_state_latest_lookup ON state_observations(instance_id,definition_id,observed_at);']
    dictionary.insert(2,'类型码：t=TEXT，j=有效 JSON 文本，r=REAL，n=非负 REAL，i=非负 INTEGER，i0=非负 INTEGER 默认0，p=[0,1]，b=0/1，e(...)=枚举，@表=外键。各业务 FK 除谱系父子外均绑定 instance_id。\n')
    if not control:
        dictionary += ['## memory_search — 派生全文索引\n',
            '| 字段 | 类型 | 含义 |','| --- | --- | --- |',
            '| rowid | INTEGER | memory_revisions.rowid；关联内容行 |',
            '| content | FTS5 TEXT | 可检索的记忆修订内容 |',
            '| memory_id | UNINDEXED TEXT | 记忆标识 |',
            '| instance_id | UNINDEXED TEXT | 生命实例 |',
            '\nFTS5 外部内容表由触发器同步，可重建。查询必须 JOIN 当前有效记忆并核验权限；FTS 不负责授权。unicode61 不保证中文语义召回。SQLite 自动生成的 FTS 内部影子表不是业务接口。\n']
    return '\n\n'.join(sql)+'\n','\n'.join(dictionary)+'\n'

def trigger(name,table,timing,body,event='INSERT',when=None):
    return f'CREATE TRIGGER {name} {timing} {event} ON {table}'+(f' WHEN {when}' if when else '')+f' BEGIN\n{body}\nEND;'

def runtime_triggers(tables):
    sql=[]
    # Business rows auto-register; registry remains usable for abstract objects.
    for _,name,_,_ in tables:
        if name in ('object_registry','object_revision_registry'): continue
        sql.append(trigger('register_'+name,name,'AFTER',f"INSERT INTO object_registry(id,instance_id,kind) VALUES(NEW.id,NEW.instance_id,'{name}');"))
        sql.append(trigger('stable_'+name,name,'BEFORE',"SELECT RAISE(ABORT,'stable identity cannot change');",'UPDATE', 'NEW.id<>OLD.id OR NEW.instance_id<>OLD.instance_id'))
    for name,(owner,parent) in REV.items():
        sql.append(trigger('revision_'+name,name,'AFTER',f"INSERT INTO object_revision_registry(id,instance_id,object_id,revision_no,kind) VALUES(NEW.id,NEW.instance_id,NEW.{owner},NEW.revision_no,'{name}');"))
        # Current pointer must belong to its object; composite FK existence is deferred.
        for event in ('INSERT','UPDATE'):
            sql.append(trigger('current_'+parent+'_'+event.lower(),parent,'BEFORE',
                f"SELECT RAISE(ABORT,'revision belongs to another object') WHERE EXISTS(SELECT 1 FROM {name} WHERE id=NEW.current_revision_id AND ({owner}<>NEW.id OR instance_id<>NEW.instance_id));",event))
        sql.append(trigger('owner_'+name,name,'BEFORE',
            f"SELECT RAISE(ABORT,'revision pointer owner mismatch') WHERE EXISTS(SELECT 1 FROM {parent} WHERE current_revision_id=NEW.id AND id<>NEW.{owner});"))
    for table,(owner,seq) in PROFILE_REV.items():
        sql.append(trigger('profile_revision_'+table,table,'AFTER',f"INSERT INTO object_revision_registry(id,instance_id,object_id,revision_no,kind) VALUES(NEW.id,NEW.instance_id,NEW.{owner},NEW.{seq},'{table}');"))
    for event in ('INSERT','UPDATE'):
        sql.append(trigger('evidence_owner_'+event.lower(),'evidence_items','BEFORE',"SELECT RAISE(ABORT,'evidence source revision mismatch') WHERE NEW.origin_object_id IS NOT NULL AND NEW.origin_revision_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM object_revision_registry WHERE id=NEW.origin_revision_id AND object_id=NEW.origin_object_id AND instance_id=NEW.instance_id);",event))
        sql.append(trigger('learning_revision_owner_'+event.lower(),'learning_update_commits','BEFORE',"""SELECT RAISE(ABORT,'learning revision target mismatch') WHERE NOT EXISTS(
 SELECT 1 FROM object_revision_registry old JOIN object_revision_registry new ON new.object_id=old.object_id AND new.instance_id=old.instance_id
 JOIN learning_update_proposals p ON p.target_object_id=old.object_id AND p.instance_id=old.instance_id
 WHERE old.id=NEW.old_revision_id AND new.id=NEW.new_revision_id AND p.id=NEW.proposal_id);""",event))
        for table,value in [('personality_trait_values','central_value'),('personality_states','value')]:
            sql.append(trigger('trait_scale_'+table+'_'+event.lower(),table,'BEFORE',f"SELECT RAISE(ABORT,'trait outside dimension scale') WHERE NOT EXISTS(SELECT 1 FROM personality_dimensions d WHERE d.id=NEW.dimension_id AND d.instance_id=NEW.instance_id AND NEW.{value} BETWEEN d.scale_min AND d.scale_max);",event))
        sql.append(trigger('plan_owner_'+event.lower(),'cognition_plan_dependencies','BEFORE',"SELECT RAISE(ABORT,'dependency must use same plan') WHERE NOT EXISTS(SELECT 1 FROM cognition_plan_steps a JOIN cognition_plan_steps b ON a.plan_id=b.plan_id AND a.instance_id=b.instance_id WHERE a.id=NEW.step_id AND b.id=NEW.depends_on_step_id);",event))
    sql.append(trigger('goal_batch_initial','goal_activation_batches','BEFORE',"SELECT RAISE(ABORT,'create batch in draft');",when="NEW.state<>'draft'"))
    sql.append(trigger('goal_batch_finalize','goal_activation_batches','BEFORE',"""SELECT RAISE(ABORT,'invalid goal distribution') WHERE
 (SELECT count(*) FROM goal_activation_records WHERE decision_batch_id=NEW.id)=0 OR
 abs((SELECT total(probability) FROM goal_activation_records WHERE decision_batch_id=NEW.id)-1)>0.000001 OR
 (SELECT total(selected) FROM goal_activation_records WHERE decision_batch_id=NEW.id)<1;""",'UPDATE',"OLD.state='draft' AND NEW.state='finalized'"))
    sql.append(trigger('goal_batch_no_unseal','goal_activation_batches','BEFORE',"SELECT RAISE(ABORT,'cannot reopen goal batch');",'UPDATE',"OLD.state='finalized' AND NEW.state<>'finalized'"))
    for event in ('INSERT','UPDATE','DELETE'):
        ref='OLD' if event=='DELETE' else 'NEW'
        cond=f"EXISTS(SELECT 1 FROM goal_activation_batches WHERE id={ref}.decision_batch_id AND state='finalized')"
        if event=='UPDATE': cond+=' OR EXISTS(SELECT 1 FROM goal_activation_batches WHERE id=OLD.decision_batch_id AND state=\'finalized\')'
        sql.append(trigger('sealed_goal_batch_'+event.lower(),'goal_activation_records','BEFORE',"SELECT RAISE(ABORT,'finalized goal batch immutable');",event,cond))
    # Cyclic structural edges cannot be introduced by INSERT or UPDATE.
    for table,start,end in [('evidence_derivations','derived_evidence_id','parent_evidence_id'),('cognition_plan_dependencies','step_id','depends_on_step_id'),('identity_lineage','parent_instance_id','child_instance_id')]:
        for event in ('INSERT','UPDATE'):
            body=f"""SELECT RAISE(ABORT,'cycle detected') WHERE NEW.{start}=NEW.{end} OR EXISTS(
WITH RECURSIVE reach(node) AS (SELECT NEW.{end} UNION SELECT e.{end} FROM {table} e JOIN reach r ON e.{start}=r.node WHERE e.id<>NEW.id)
SELECT 1 FROM reach WHERE node=NEW.{start});"""
            sql.append(trigger('acyclic_'+table+'_'+event.lower(),table,'BEFORE',body,event))
    # Cue and habit cannot disagree even when both FKs exist.
    for event in ('INSERT','UPDATE'):
        sql.append(trigger('habit_owner_'+event.lower(),'habit_associations','BEFORE',"SELECT RAISE(ABORT,'cue belongs to another habit') WHERE NOT EXISTS(SELECT 1 FROM habit_cues WHERE id=NEW.cue_id AND habit_id=NEW.habit_id AND instance_id=NEW.instance_id);",event))
    # Seal decision sets only after normalization; later mutation is forbidden.
    sql.append(trigger('decision_finalize','decision_records','BEFORE',"""SELECT RAISE(ABORT,'invalid decision distribution') WHERE
 (SELECT COUNT(*) FROM decision_candidates WHERE decision_id=NEW.id)=0 OR
 abs((SELECT total(selection_probability) FROM decision_candidates WHERE decision_id=NEW.id)-1)>0.000001 OR
 (SELECT total(selected) FROM decision_candidates WHERE decision_id=NEW.id)<>1;""",'UPDATE',"OLD.state='draft' AND NEW.state='finalized'"))
    for event in ('INSERT','UPDATE','DELETE'):
        ref='OLD' if event=='DELETE' else 'NEW'
        cond=f"EXISTS(SELECT 1 FROM decision_records WHERE id={ref}.decision_id AND state='finalized')"
        if event=='UPDATE': cond += " OR EXISTS(SELECT 1 FROM decision_records WHERE id=OLD.decision_id AND state='finalized')"
        sql.append(trigger('sealed_candidates_'+event.lower(),'decision_candidates','BEFORE',"SELECT RAISE(ABORT,'finalized candidates are immutable');",event,cond))
    sql.append(trigger('decision_no_unseal','decision_records','BEFORE',"SELECT RAISE(ABORT,'cannot reopen finalized decision');",'UPDATE',"OLD.state='finalized' AND NEW.state<>'finalized'"))
    sql.append(trigger('decision_initial_draft','decision_records','BEFORE',"SELECT RAISE(ABORT,'create decision in draft');",when="NEW.state<>'draft'"))
    sql.append(trigger('authorized_candidate','action_intents','BEFORE',"SELECT RAISE(ABORT,'intent requires selected finalized candidate') WHERE NOT EXISTS(SELECT 1 FROM decision_candidates c JOIN decision_records d ON d.id=c.decision_id WHERE c.id=NEW.candidate_id AND c.selected=1 AND c.eligible=1 AND d.state='finalized');"))
    for transitions,(owner,parent,allowed) in TRANSITIONS.items():
        terms=[f"(NEW.from_state='{a}' AND NEW.to_state IN ({','.join(repr(b) for b in bs)}))" for a,bs in allowed.items()]
        sql.append(trigger('validate_'+transitions,transitions,'BEFORE',f"SELECT RAISE(ABORT,'invalid state transition') WHERE NOT ({' OR '.join(terms)}) OR NOT EXISTS(SELECT 1 FROM {parent} p WHERE p.id=NEW.{owner} AND p.instance_id=NEW.instance_id AND p.state=NEW.from_state AND NEW.transition_no=p.state_revision+1);"))
        sql.append(trigger('apply_'+transitions,transitions,'AFTER',f"UPDATE {parent} SET state=NEW.to_state,state_revision=NEW.transition_no WHERE id=NEW.{owner} AND instance_id=NEW.instance_id;"))
        sql.append(trigger('guard_'+parent,parent,'BEFORE',f"SELECT RAISE(ABORT,'state changes require transition record') WHERE NEW.state_revision<>OLD.state_revision+1 OR NOT EXISTS(SELECT 1 FROM {transitions} t WHERE t.{owner}=NEW.id AND t.instance_id=NEW.instance_id AND t.transition_no=NEW.state_revision AND t.from_state=OLD.state AND t.to_state=NEW.state);",'UPDATE','NEW.state<>OLD.state OR NEW.state_revision<>OLD.state_revision'))
        for event in ('UPDATE','DELETE'):
            sql.append(trigger('history_'+transitions+'_'+event.lower(),transitions,'BEFORE',"SELECT RAISE(ABORT,'state history immutable');",event))
    # Protect parent selection and revision ownership after insertion.
    for table in list(REV)+list(PROFILE_REV):
        owner,seq= (REV[table][0],'revision_no') if table in REV else PROFILE_REV[table]
        sql.append(trigger('version_identity_'+table,table,'BEFORE',"SELECT RAISE(ABORT,'version ownership is immutable');",'UPDATE',f'NEW.{owner}<>OLD.{owner} OR NEW.{seq}<>OLD.{seq}'))
        for event in ('UPDATE','DELETE'):
            # Explicit deletion workflow may redact/purge content; application controls authorization.
            sql.append(trigger('immutable_'+table+'_'+event.lower(),table,'BEFORE',"SELECT RAISE(ABORT,'revision immutable; append a correction or authorized deletion');",event,
                f"NOT EXISTS(SELECT 1 FROM deletion_effects e JOIN deletion_requests r ON r.id=e.request_id WHERE e.object_ref=OLD.id AND e.instance_id=OLD.instance_id AND e.operation IN ('redact','purge') AND r.state='cleaning')"))
    for table in ('object_registry','object_revision_registry'):
        sql.append(trigger('immutable_'+table,table,'BEFORE',"SELECT RAISE(ABORT,'registry immutable');",'UPDATE'))
    return sql

def main():
    OUT.mkdir(exist_ok=True)
    for spec,control,stem in [(SPEC,False,'runtime'),(CONTROL,True,'supervisor')]:
        sql,dictionary=build(spec,control)
        (OUT/f'{stem}.sql').write_text(sql)
        (OUT/f'{stem}-field-dictionary.md').write_text(dictionary)
    print(json.dumps({'runtime_tables':len(parse(SPEC)),'supervisor_tables':len(parse(CONTROL))}))

if __name__=='__main__': main()
