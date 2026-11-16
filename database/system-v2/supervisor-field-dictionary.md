# Supervisor 完整字段字典

生成源：`scripts/build_database_schema.py`；与 SQL 同源生成。每表均列出全部物理列。FK 为延迟校验、默认禁止级联删除。

类型码：t=TEXT，j=有效 JSON 文本，r=REAL，n=非负 REAL，i=非负 INTEGER，i0=非负 INTEGER 默认0，p=[0,1]，b=0/1，e(...)=枚举，@表=外键。各业务 FK 除谱系父子外均绑定 instance_id。

## deployments — 部署版本（控制平面）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| release | `t` | 否 | 版本 |
| build_hash | `t` | 否 | 构建摘要 |
| schema_min | `i` | 否 | 最低结构 |
| schema_max | `i` | 否 | 最高结构 |
| state | `e(candidate,testing,active,retired,failed)` | 否 | 状态 |

表级约束：

```sql
CHECK (schema_min <= schema_max)
```

## process_runs — 进程运行（控制平面）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| deployment_id | `@deployments` | 否 | 部署 |
| instance_ref | `t` | 否 | 业务实例标识 |
| pid | `i` | 是 | 进程编号 |
| started_at | `t` | 否 | 开始 |
| exited_at | `t` | 是 | 退出 |
| user_stopped | `b` | 否 | 用户停止 |

表级约束：

```sql
FOREIGN KEY (deployment_id) REFERENCES deployments(id) DEFERRABLE INITIALLY DEFERRED
```

## wake_checks — 唤醒检查（控制平面）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| process_run_id | `@process_runs` | 否 | 进程 |
| requested_at | `t` | 否 | 请求 |
| completed_at | `t` | 是 | 完成 |
| result | `e(pass,fail,unknown)` | 否 | 结果 |
| detail | `j` | 否 | 检查证据 |

表级约束：

```sql
FOREIGN KEY (process_run_id) REFERENCES process_runs(id) DEFERRABLE INITIALLY DEFERRED
```

## release_switches — 部署切换（控制平面）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| old_deployment_id | `@deployments` | 是 | 旧部署 |
| new_deployment_id | `@deployments` | 否 | 新部署 |
| phase | `e(prepared,quiesced,stopped,switched,verified,failed)` | 否 | 阶段 |
| evidence | `j` | 否 | 交接证据 |

表级约束：

```sql
FOREIGN KEY (old_deployment_id) REFERENCES deployments(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (new_deployment_id) REFERENCES deployments(id) DEFERRABLE INITIALLY DEFERRED
```

## rollback_runs — 回退（控制平面）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| switch_id | `@release_switches` | 否 | 切换 |
| target_deployment_id | `@deployments` | 否 | 目标 |
| reason | `t` | 否 | 原因 |
| compatibility_result | `e(pass,fail,unknown)` | 否 | 兼容结果 |
| result | `e(pending,succeeded,failed)` | 否 | 结果 |

表级约束：

```sql
FOREIGN KEY (switch_id) REFERENCES release_switches(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (target_deployment_id) REFERENCES deployments(id) DEFERRABLE INITIALLY DEFERRED
```

## backup_manifests — 备份清单（控制平面）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| deployment_id | `@deployments` | 否 | 部署 |
| snapshot_path | `t` | 否 | 快照 |
| hash | `t` | 否 | 摘要 |
| scope | `j` | 否 | 范围 |
| completed_at | `t` | 否 | 完成时间 |

表级约束：

```sql
FOREIGN KEY (deployment_id) REFERENCES deployments(id) DEFERRABLE INITIALLY DEFERRED
```

## control_commands — 控制命令（控制增量）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| instance_ref | `t` | 否 | 实例 |
| source | `t` | 否 | 来源 |
| command_key | `t` | 否 | 幂等键 |
| kind | `t` | 否 | 类型 |
| payload | `j` | 否 | 载荷 |
| payload_hash | `t` | 否 | 摘要 |
| generation | `i` | 是 | 代次 |
| authority_kind | `t` | 否 | 授权类型 |
| authority_ref | `t` | 否 | 授权者 |
| state | `e(received,running,succeeded,rejected,failed)` | 否 | 状态 |
| result_json | `j` | 是 | 结果 |
| error_code | `t` | 是 | 错误 |
| received_at | `t` | 否 | 接收 |
| finished_at | `t` | 是 | 完成 |

表级约束：

```sql
UNIQUE (source, instance_ref, command_key)
```

## wake_schedules — 唤醒计划（控制增量）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| instance_ref | `t` | 否 | 实例 |
| generation | `i` | 否 | 代次 |
| next_due_at | `t` | 是 | 期限 |
| enabled | `b` | 否 | 启用 |
| last_control_command_id | `@control_commands` | 否 | 命令 |
| updated_at | `t` | 否 | 时间 |
| last_firing_id | `@wake_firings` | 是 | 触发 |

表级约束：

```sql
FOREIGN KEY (last_control_command_id) REFERENCES control_commands(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (last_firing_id) REFERENCES wake_firings(id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_ref)
```

## wake_firings — 唤醒触发（控制增量）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| schedule_id | `@wake_schedules` | 否 | 计划 |
| generation | `i` | 否 | 代次 |
| scheduled_due_at | `t` | 否 | 计划时间 |
| fired_at | `t` | 否 | 触发 |
| source_event_id | `t` | 否 | 事件 |
| state | `e(pending,delivered,acknowledged,suppressed)` | 否 | 状态 |
| runtime_ack_event_id | `t` | 是 | 确认 |
| suppression_reason | `t` | 是 | 抑制原因 |

表级约束：

```sql
FOREIGN KEY (schedule_id) REFERENCES wake_schedules(id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (schedule_id, generation, scheduled_due_at)
```

## instance_control_state — 实例控制（控制增量）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| instance_ref | `t` | 否 | 实例 |
| user_stopped | `b` | 否 | 停止 |
| control_revision | `i0` | 否 | 修订 |
| runtime_epoch | `i0` | 否 | 世代 |
| active_process_run_id | `@process_runs` | 是 | 进程 |
| last_stop_command_id | `@control_commands` | 是 | 停止命令 |

表级约束：

```sql
FOREIGN KEY (active_process_run_id) REFERENCES process_runs(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (last_stop_command_id) REFERENCES control_commands(id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_ref)
```

## inbound_requests — 离线输入（控制增量）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| instance_ref | `t` | 否 | 实例 |
| source | `t` | 否 | 来源 |
| source_event_id | `t` | 否 | 事件 |
| request_kind | `t` | 否 | 类型 |
| payload_path | `t` | 否 | 材料路径 |
| payload_hash | `t` | 否 | 摘要 |
| authority_ref | `t` | 否 | 授权 |
| received_at | `t` | 否 | 接收 |
| expires_at | `t` | 否 | 到期 |
| retention_class | `t` | 否 | 保留 |
| state | `e(received,waking,transferring,delivered,rejected,expired)` | 否 | 状态 |
| runtime_ack_event_id | `t` | 是 | 确认 |
| delivered_at | `t` | 是 | 交付 |
| last_error | `t` | 是 | 错误 |
| attempt_count | `i0` | 否 | 次数 |

表级约束：

```sql
UNIQUE (instance_ref, source, source_event_id)
```

## control_sleep_handoffs — 休眠交接（控制增量）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| instance_ref | `t` | 否 | 实例 |
| runtime_epoch | `i` | 否 | 世代 |
| process_run_id | `@process_runs` | 否 | 进程 |
| sleep_generation | `i` | 否 | 交接代次 |
| wake_generation | `i` | 否 | 唤醒代次 |
| state_manifest_hash | `t` | 否 | 状态摘要 |
| phase | `e(prepared,acknowledged,committed,sleeping,aborted)` | 否 | 阶段 |
| last_runtime_event_seq | `i` | 否 | 事件边界 |
| reason | `t` | 是 | 原因 |

表级约束：

```sql
FOREIGN KEY (process_run_id) REFERENCES process_runs(id) DEFERRABLE INITIALLY DEFERRED
```

