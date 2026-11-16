"""Merge approved runtime contract increments into a new, separate schema release."""
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
loader=importlib.util.spec_from_file_location('base_schema',ROOT/'scripts/development/build_database_schema.py')
base=importlib.util.module_from_spec(loader); loader.loader.exec_module(base)

INCREMENTS=r'''
[独立思考与运行]
thought_requests|独立思考请求|activity_id:@activities:活动 step_id:@activity_steps:步骤 request_key:t:幂等键 purpose:e(infer,plan,evaluate,verify,reflect):用途 task:t:任务 instruction_version:t:指令版本 output_schema_version:i:响应版本 request_artifact_id:@artifacts:完整请求 request_hash:t:请求摘要 input_manifest_hash:t:输入摘要 model_config_id:@configuration_versions:模型配置 model_version_id:@model_versions:模型 prepared_activity_revision:i:构造版本 expected_input_epoch:i:输入代次 expected_policy_epoch:i:权限代次 runtime_epoch:i:进程世代 process_run_id:t:控制进程标识 deadline:t:期限 token_budget:i:预算 attempt_limit:i:次数 retry_policy:j:重试 generation_config:j:采样 state:e(prepared,running,succeeded,failed,cancelled,superseded):状态 accepted_result_id:?@thought_results:接受结果 state_revision:i0:修订 request_parent_id:?@thought_requests:父请求 supersedes_request_id:?@thought_requests:替代请求
thought_request_inputs|思考输入清单|request_id:@thought_requests:请求 ordinal:i:顺序 role:t:角色 object_revision_id:?@object_revision_registry:对象版本 object_id:?@object_registry:不可变对象 artifact_id:?@artifacts:临时工件 content_hash:t:摘要 locator:j:定位 selection_reason:t:选择原因
thought_attempts|模型调用尝试|request_id:@thought_requests:请求 attempt_no:i:次数 state:e(queued,sent,received,timeout,failed,cancelled):状态 queued_at:t:入队 sent_at:?t:发送 finished_at:?t:完成 provider_request_id:?t:远端标识 error_code:?t:错误 usage_json:?j:用量 dispatch_token:t:发送标识 provider:t:提供方 model:t:实际模型 runtime_epoch:i:世代 process_run_id:t:进程标识
thought_results|模型响应|request_id:@thought_requests:请求 attempt_id:@thought_attempts:尝试 response_artifact_id:@artifacts:原始响应 response_hash:t:摘要 received_at:t:接收 parsed_artifact_id:?@artifacts:解析结果 validation_errors:j:错误 validation_state:e(valid,invalid,pending):校验 acceptance:e(pending,accepted,stale,duplicate,rejected):接受状态 reason_code:?t:原因 accepted_at:?t:接受时间
thought_state_events|思考状态历史|request_id:@thought_requests:请求 transition_no:i:序号 from_state:t:旧状态 to_state:t:新状态 reason_code:t:原因 result_id:?@thought_results:结果
activity_state_events|活动状态历史|activity_id:@activities:活动 transition_no:i:序号 from_state:t:旧状态 to_state:t:新状态 cause_event_id:@runtime_events:事件 expected_revision:i:修订 reason_code:t:原因
activity_budget_accounts|预算账户|activity_id:@activities:活动 revision:i0:修订 token_limit:i:token额度 tool_call_limit:i:工具额度 attempt_limit:i:尝试额度 time_limit_ms:i:时间额度 cost_limit_minor:?i:成本额度 currency:?t:币种
budget_reservations|预算预留|activity_id:@activities:活动 operation_ref:@object_registry:操作 operation_kind:e(thought_attempt,tool_attempt):类型 reservation_key:t:幂等键 reserved_tokens:i:token reserved_tool_calls:i:工具次数 reserved_attempts:i:尝试次数 reserved_cost_minor:?i:成本 state:e(reserved,settled,released,usage_unknown):状态 actual_usage:?j:实测 reserved_at:t:预留 settled_at:?t:结算
action_authorization_records|动作授权快照|intent_id:@action_intents:动作 grant_id:@grants:授权 approval_request_id:?@approval_requests:批准 proposal_revision:i:提案修订 arguments_hash:t:参数摘要 scope_snapshot:j:范围 policy_epoch:i:权限世代 issued_at:t:签发 expires_at:t:到期 revoked_at:?t:撤销 state:e(valid,revoked,expired,consumed):状态
action_state_events|动作状态历史|intent_id:@action_intents:动作 transition_no:i:序号 from_state:t:旧状态 to_state:t:新状态 cause_event_id:@runtime_events:事件 attempt_id:?@action_attempts:尝试 reason_code:t:原因
policy_epochs|权限代次|epoch:i:代次 policy_version_id:@policy_versions:策略 last_change_event_id:?@runtime_events:事件 updated_at:t:时间
runtime_events|持久事件信封|event_seq:i:序号 event_type:t:类型 source:t:来源 source_event_id:t:来源标识 correlation_id:t:关联 causation_event_id:?@runtime_events:起因 activity_id:?@activities:活动 lane:e(control,result,work,telemetry):通道 payload_object_id:?@object_registry:对象 payload_artifact_id:?@artifacts:工件 payload_hash:t:摘要 received_at:t:接收 authority_ref:?@social_actors:主体
consumer_receipts|消费确认|consumer_name:t:消费者 consumer_version:t:版本 event_id:@runtime_events:事件 state:e(pending,processing,processed,dead_letter):状态 attempt_count:i0:次数 lease_owner:?t:拥有者 lease_token:?t:令牌 lease_generation:i0:代次 lease_expires_at:?t:到期 last_error:?t:错误 processed_at:?t:完成
consumer_offsets|消费游标|consumer_name:t:消费者 consumer_version:t:版本 lane:t:通道 last_event_seq:i:序号 updated_at:t:时间
supervisor_commands|控制面命令|command_key:t:幂等键 kind:e(set_wake,clear_wake,request_maintenance,request_deploy):种类 schedule_generation:?i:计划代次 payload:j:载荷 payload_hash:t:摘要 state:e(pending,sent,acknowledged,rejected):状态 attempt_count:i0:次数 next_attempt_at:t:时间 ack_control_command_id:?t:确认标识 acknowledged_at:?t:确认 last_error:?t:错误 runtime_epoch:i:世代 process_run_id:t:进程
instance_wake_state|唤醒交接状态|desired_generation:i:期望代次 acknowledged_generation:i:确认代次 desired_due_at:?t:期望时间 acknowledged_due_at:?t:确认时间
initialization_runs|初始化运行|bootstrap_key:t:幂等键 schema_migration_version:i:模式 configuration_id:@configuration_versions:配置 phase:t:阶段 state:e(started,committed,failed):状态 error_code:?t:错误 completed_at:?t:完成
object_publications|对象发布|object_id:@object_registry:对象 state:e(constructing,ready,quarantined,redacted):状态 current_revision_id:?@object_revision_registry:发布版本 owner_module:t:所有者 validation_schema:t:校验版本 published_at:?t:时间 revision:i0:修订 reason_ref:?@evidence_items:依据
import_runs|恢复导入|source_artifact_id:@artifacts:来源 authority_ref:@social_actors:授权 mode:e(restore,import):方式 continuity_incident_id:?@identity_continuity_incidents:损伤 state:e(started,committed,failed):状态 started_at:t:开始 completed_at:?t:完成
'''

ADDITIONS={
 'activities':'revision:i0:修订 input_epoch:i0:语义代次 deadline:?t:期限 cancel_requested_at:?t:取消时间 cancel_reason:?t:取消原因 predecessor_activity_id:?@activities:前置活动 publication_state:e(constructing,ready,quarantined):发布',
 'activity_steps':'input_manifest_hash:?t:输入摘要 idempotency_key:t:幂等键 started_at:?t:开始 finished_at:?t:完成 accepted_output_ref:?@object_registry:输出 expected_activity_revision:i0:预期修订',
 'action_intents':'state:e(proposed,awaiting_approval,authorized,queued,dispatching,running,succeeded,failed,partial,unknown,cancelled):状态 proposal_revision:i0:提案修订 lifecycle_revision:i0:状态修订 arguments_hash:t:摘要 required_capability_id:@capability_definitions:能力 resource_scope:j:范围 deadline:?t:期限',
 'approval_requests':'proposal_revision:i0:提案修订 arguments_hash:t:参数摘要 tool_id:@tool_definitions:工具 required_capability_id:@capability_definitions:能力 expires_at:t:到期 requested_by:@social_actors:请求方 decision_by:?@social_actors:决定方 revision:i0:修订',
 'jobs':'lease_token:?t:令牌 lease_generation:i0:代次',
 'outbox':'authorization_record_id:?@action_authorization_records:授权 lease_owner:?t:拥有者 lease_token:?t:令牌 lease_generation:i0:代次 lease_expires_at:?t:到期 attempt_count:i0:次数 last_error:?t:错误',
 'action_attempts':'authorization_record_id:@action_authorization_records:授权 policy_epoch:i:权限代次 execution_token_hash:t:令牌摘要 arguments_hash:t:参数摘要 backend_operation_id:?t:后端标识 start_gate_at:?t:开始门禁 cancel_requested_at:?t:取消 runtime_epoch:i:世代 process_run_id:t:进程',
}
CONTROL_EXTRA=r'''
[控制增量]
control_commands|控制命令|instance_ref:t:实例 source:t:来源 command_key:t:幂等键 kind:t:类型 payload:j:载荷 payload_hash:t:摘要 generation:?i:代次 authority_kind:t:授权类型 authority_ref:t:授权者 state:e(received,running,succeeded,rejected,failed):状态 result_json:?j:结果 error_code:?t:错误 received_at:t:接收 finished_at:?t:完成
wake_schedules|唤醒计划|instance_ref:t:实例 generation:i:代次 next_due_at:?t:期限 enabled:b:启用 last_control_command_id:@control_commands:命令 updated_at:t:时间 last_firing_id:?@wake_firings:触发
wake_firings|唤醒触发|schedule_id:@wake_schedules:计划 generation:i:代次 scheduled_due_at:t:计划时间 fired_at:t:触发 source_event_id:t:事件 state:e(pending,delivered,acknowledged,suppressed):状态 runtime_ack_event_id:?t:确认 suppression_reason:?t:抑制原因
instance_control_state|实例控制|instance_ref:t:实例 user_stopped:b:停止 control_revision:i0:修订 runtime_epoch:i0:世代 active_process_run_id:?@process_runs:进程 last_stop_command_id:?@control_commands:停止命令
inbound_requests|离线输入|instance_ref:t:实例 source:t:来源 source_event_id:t:事件 request_kind:t:类型 payload_path:t:材料路径 payload_hash:t:摘要 authority_ref:t:授权 received_at:t:接收 expires_at:t:到期 retention_class:t:保留 state:e(received,waking,transferring,delivered,rejected,expired):状态 runtime_ack_event_id:?t:确认 delivered_at:?t:交付 last_error:?t:错误 attempt_count:i0:次数
control_sleep_handoffs|休眠交接|instance_ref:t:实例 runtime_epoch:i:世代 process_run_id:@process_runs:进程 sleep_generation:i:交接代次 wake_generation:i:唤醒代次 state_manifest_hash:t:状态摘要 phase:e(prepared,acknowledged,committed,sleeping,aborted):阶段 last_runtime_event_seq:i:事件边界 reason:?t:原因
'''

def merged_spec():
    lines=[]
    for module,name,desc,fields in base.parse(base.SPEC):
        extra=ADDITIONS.get(name,'')
        fields=list(fields)
        if name=='action_intents': fields=[('grant_id','?@grants','授权') if f[0]=='grant_version' else f for f in fields]
        lines += [f'[{module}]',name+'|'+desc+'|'+' '.join(':'.join(f) for f in fields)+(' '+extra if extra else '')]
    return '\n'.join(lines)+'\n'+INCREMENTS

def main():
    base.UNIQUE.update({
      'thought_requests':[('request_key',)],'thought_request_inputs':[('request_id','ordinal')],
      'thought_attempts':[('request_id','attempt_no'),('dispatch_token',)],
      'runtime_events':[('event_seq',),('source','source_event_id')],
      'activity_budget_accounts':[('activity_id',)],'budget_reservations':[('activity_id','reservation_key')],
      'policy_epochs':[('instance_id',)],'object_publications':[('object_id',)],
      'consumer_receipts':[('consumer_name','consumer_version','event_id')],
      'consumer_offsets':[('consumer_name','consumer_version','lane')],
      'supervisor_commands':[('command_key',)],'initialization_runs':[('bootstrap_key',)],
      'wake_schedules':[('instance_ref',)],'instance_control_state':[('instance_ref',)],
      'control_commands':[('source','instance_ref','command_key')],
      'inbound_requests':[('instance_ref','source','source_event_id')],
      'wake_firings':[('schedule_id','generation','scheduled_due_at')],
    })
    # instance_id is already added by base generator to unique keys.
    base.UNIQUE['policy_epochs']=[]
    base.EXTRA.update({
      'thought_request_inputs':['CHECK ((object_revision_id IS NOT NULL)+(object_id IS NOT NULL)+(artifact_id IS NOT NULL)=1)'],
      'runtime_events':['CHECK ((payload_object_id IS NOT NULL)+(payload_artifact_id IS NOT NULL)=1)'],
      'thought_requests':["CHECK ((state='succeeded' AND accepted_result_id IS NOT NULL) OR (state<>'succeeded' AND accepted_result_id IS NULL))"],
    })
    out=ROOT/'database'/'system-v2'; out.mkdir(exist_ok=True)
    for name,spec,control in [('runtime',merged_spec(),False),('supervisor',base.CONTROL+CONTROL_EXTRA,True)]:
        spec='\n'.join(line for line in spec.splitlines() if line.strip())
        sql,dictionary=base.build(spec,control)
        if name=='runtime':
            extra="""
CREATE UNIQUE INDEX uq_accepted_thought ON thought_results(instance_id,request_id) WHERE acceptance='accepted';
CREATE UNIQUE INDEX uq_policy_epoch ON policy_epochs(instance_id);
CREATE UNIQUE INDEX uq_wake_state ON instance_wake_state(instance_id);
CREATE INDEX ix_event_stream ON runtime_events(instance_id,event_seq);
CREATE INDEX ix_thought_due ON thought_requests(instance_id,state,deadline);
"""
            sql=sql.rsplit('COMMIT;',1)[0]+extra+'\nCOMMIT;\n'
        (out/(name+'.sql')).write_text(sql)
        resources=out.parents[2]/'digital_life'/'resources'
        resources.mkdir(parents=True,exist_ok=True)
        (resources/(name+'.sql')).write_text(sql)
        (out/(name+'-field-dictionary.md')).write_text(dictionary)
    print('Generated system-v2 definitions only; no life instance opened.')

if __name__=='__main__': main()
