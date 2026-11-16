# Runtime 完整字段字典

生成源：`scripts/build_database_schema.py`；与 SQL 同源生成。每表均列出全部物理列。FK 为延迟校验、默认禁止级联删除。

类型码：t=TEXT，j=有效 JSON 文本，r=REAL，n=非负 REAL，i=非负 INTEGER，i0=非负 INTEGER 默认0，p=[0,1]，b=0/1，e(...)=枚举，@表=外键。各业务 FK 除谱系父子外均绑定 instance_id。

## object_registry — 对象登记（共同基础）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| kind | `t` | 否 | 对象表类型 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
```

## object_revision_registry — 版本登记（共同基础）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| object_id | `@object_registry` | 否 | 所属对象 |
| revision_no | `i` | 否 | 修订序号 |
| kind | `t` | 否 | 版本类型 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, object_id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, object_id, revision_no)
```

## world_entities — 世界对象（共同基础）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| entity_type | `t` | 否 | 对象类型 |
| canonical_name | `t` | 否 | 规范名称 |
| resolution_status | `e(unresolved,resolved,ambiguous)` | 否 | 解析状态 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## world_entity_aliases — 对象别名（共同基础）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| entity_id | `@world_entities` | 否 | 对象 |
| alias | `t` | 否 | 别名 |
| source_ref | `@evidence_items` | 是 | 来源 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, entity_id) REFERENCES world_entities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, source_ref) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, entity_id, alias)
```

## world_entity_relations — 对象关系（共同基础）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| subject_id | `@world_entities` | 否 | 主体 |
| relation_type | `t` | 否 | 关系类型 |
| object_id | `@world_entities` | 否 | 客体 |
| evidence_id | `@evidence_items` | 否 | 证据 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, subject_id) REFERENCES world_entities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, object_id) REFERENCES world_entities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## context_snapshots — 情境快照（共同基础）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| activity_id | `@activities` | 否 | 活动 |
| task_ref | `@goal_items` | 是 | 任务 |
| location_ref | `@world_entities` | 是 | 地点 |
| context_schema | `t` | 否 | 结构版本 |
| attributes_json | `j` | 否 | 情境属性 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, task_ref) REFERENCES goal_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, location_ref) REFERENCES world_entities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## context_entity_links — 情境对象（共同基础）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| context_id | `@context_snapshots` | 否 | 情境 |
| entity_id | `@world_entities` | 否 | 对象 |
| role | `t` | 否 | 角色 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, context_id) REFERENCES context_snapshots(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, entity_id) REFERENCES world_entities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, context_id, entity_id, role)
```

## artifacts — 材料载体（共同基础）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| hash | `t` | 否 | 内容摘要 |
| size | `i` | 否 | 字节数 |
| media_type | `t` | 否 | 媒体类型 |
| storage_ref | `t` | 否 | 存储位置 |
| retention_class | `t` | 否 | 保留分类 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## evidence_items — 来源证据（共同基础）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| origin_object_id | `@object_registry` | 是 | 来源对象 |
| origin_revision_id | `@object_revision_registry` | 是 | 来源版本 |
| artifact_id | `@artifacts` | 是 | 材料 |
| source_actor_id | `@social_actors` | 是 | 提供者 |
| method | `t` | 否 | 获取方法 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, origin_object_id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, origin_revision_id) REFERENCES object_revision_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, artifact_id) REFERENCES artifacts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, source_actor_id) REFERENCES social_actors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
CHECK (origin_object_id IS NOT NULL OR origin_revision_id IS NOT NULL OR artifact_id IS NOT NULL)
```

## evidence_derivations — 证据派生（共同基础）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| derived_evidence_id | `@evidence_items` | 否 | 派生证据 |
| parent_evidence_id | `@evidence_items` | 否 | 上游证据 |
| operation | `t` | 否 | 派生操作 |
| version | `t` | 否 | 方法版本 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, derived_evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, parent_evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## activities — 生命活动（共同基础）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| trigger_event_id | `@perception_signals` | 是 | 触发输入 |
| state | `e(pending,running,waiting_input,waiting_tool,paused,completed,failed,cancelled)` | 否 | 活动状态 |
| budget_json | `j` | 否 | 预算 |
| checkpoint_ref | `@checkpoints` | 是 | 恢复点 |
| release_id | `t` | 否 | 部署版本 |
| revision | `i0` | 否 | 修订 |
| input_epoch | `i0` | 否 | 语义代次 |
| deadline | `t` | 是 | 期限 |
| cancel_requested_at | `t` | 是 | 取消时间 |
| cancel_reason | `t` | 是 | 取消原因 |
| predecessor_activity_id | `@activities` | 是 | 前置活动 |
| publication_state | `e(constructing,ready,quarantined)` | 否 | 发布 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, trigger_event_id) REFERENCES perception_signals(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, checkpoint_ref) REFERENCES checkpoints(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, predecessor_activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## activity_steps — 活动步骤（共同基础）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| activity_id | `@activities` | 否 | 活动 |
| step_no | `i` | 否 | 步骤序号 |
| step_type | `t` | 否 | 步骤类型 |
| state | `e(pending,running,completed,failed,cancelled,unknown)` | 否 | 步骤状态 |
| input_ref | `@object_registry` | 是 | 输入 |
| output_ref | `@object_registry` | 是 | 输出 |
| attempt | `i` | 否 | 尝试次数 |
| input_manifest_hash | `t` | 是 | 输入摘要 |
| idempotency_key | `t` | 否 | 幂等键 |
| started_at | `t` | 是 | 开始 |
| finished_at | `t` | 是 | 完成 |
| accepted_output_ref | `@object_registry` | 是 | 输出 |
| expected_activity_revision | `i0` | 否 | 预期修订 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, input_ref) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, output_ref) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, accepted_output_ref) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, activity_id, step_no, attempt)
```

## activity_context_refs — 活动读取版本（共同基础）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| activity_id | `@activities` | 否 | 活动 |
| object_revision_id | `@object_revision_registry` | 否 | 精确版本 |
| role | `t` | 否 | 用途 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, object_revision_id) REFERENCES object_revision_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## rule_definitions — 规则版本（共同基础）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| name | `t` | 否 | 规则名称 |
| version | `i` | 否 | 版本 |
| expression_json | `j` | 否 | 声明式条件 |
| engine_version | `t` | 否 | 解释器版本 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## capability_definitions — 能力定义（共同基础）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| name | `t` | 否 | 能力名称 |
| description | `t` | 否 | 能力描述 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## tool_definitions — 工具定义（共同基础）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| name | `t` | 否 | 工具名称 |
| version | `i` | 否 | 工具版本 |
| input_schema | `j` | 否 | 参数结构 |
| capability_id | `@capability_definitions` | 否 | 所需能力 |
| supports_idempotency | `b` | 否 | 支持幂等可查询 |
| supports_query | `b` | 否 | 支持结果查询 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, capability_id) REFERENCES capability_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## perception_channels — 输入通道（感知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| kind | `t` | 否 | 通道类型 |
| capabilities | `j` | 否 | 能力 |
| verification_method | `t` | 否 | 验证方式 |
| state | `e(available,unavailable,unknown)` | 否 | 状态 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## perception_signals — 原始输入（感知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| channel_id | `@perception_channels` | 否 | 通道 |
| source_actor_id | `@social_actors` | 是 | 来源主体 |
| external_id | `t` | 是 | 外部去重标识 |
| artifact_id | `@artifacts` | 否 | 原始内容 |
| received_at | `t` | 否 | 接收时间 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, channel_id) REFERENCES perception_channels(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, source_actor_id) REFERENCES social_actors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, artifact_id) REFERENCES artifacts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, channel_id, external_id)
```

## perception_observations — 观察（感知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| signal_id | `@perception_signals` | 否 | 主输入 |
| context_id | `@context_snapshots` | 否 | 情境 |
| current_revision_id | `@perception_observation_revisions` | 是 | 当前修订 |
| state | `e(active,disputed,retracted)` | 否 | 状态 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, signal_id) REFERENCES perception_signals(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, context_id) REFERENCES context_snapshots(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, current_revision_id) REFERENCES perception_observation_revisions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## perception_observation_revisions — 观察修订（感知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| observation_id | `@perception_observations` | 否 | 所属观察 |
| revision_no | `i` | 否 | 序号 |
| content | `t` | 否 | 观察内容 |
| entity_ref | `@world_entities` | 是 | 对象 |
| locator_json | `j` | 否 | 原材料定位 |
| uncertainty_json | `j` | 否 | 不确定性 |
| extractor_version | `t` | 否 | 提取版本 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, observation_id) REFERENCES perception_observations(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, entity_ref) REFERENCES world_entities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, observation_id, revision_no)
```

## perception_observation_sources — 观察来源（感知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| observation_revision_id | `@perception_observation_revisions` | 否 | 观察修订 |
| signal_id | `@perception_signals` | 否 | 输入 |
| locator_json | `j` | 否 | 来源定位 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, observation_revision_id) REFERENCES perception_observation_revisions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, signal_id) REFERENCES perception_signals(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## perception_quality_checks — 感知质量（感知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| signal_id | `@perception_signals` | 是 | 输入 |
| observation_revision_id | `@perception_observation_revisions` | 是 | 观察修订 |
| check_type | `t` | 否 | 检查类型 |
| result | `e(pass,fail,unknown)` | 否 | 结果 |
| evidence_id | `@evidence_items` | 否 | 依据 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, signal_id) REFERENCES perception_signals(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, observation_revision_id) REFERENCES perception_observation_revisions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
CHECK ((signal_id IS NOT NULL) + (observation_revision_id IS NOT NULL) = 1)
```

## personality_dimensions — 人格维度（人格）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| parent_id | `@personality_dimensions` | 是 | 上级维度 |
| name | `t` | 否 | 名称 |
| definition | `t` | 否 | 定义 |
| scale_min | `r` | 否 | 下界 |
| scale_max | `r` | 否 | 上界 |
| direction | `t` | 否 | 方向 |
| theory_version | `t` | 否 | 理论版本 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, parent_id) REFERENCES personality_dimensions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
CHECK (scale_min < scale_max)
```

## personality_profiles — 人格版本（人格）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| version | `i` | 否 | 版本 |
| effective_at | `t` | 否 | 生效时间 |
| previous_profile_id | `@personality_profiles` | 是 | 前版 |
| update_commit_id | `@learning_update_commits` | 是 | 更新提交 |
| profile_object_id | `@object_registry` | 否 | 跨版本稳定配置对象 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, previous_profile_id) REFERENCES personality_profiles(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, update_commit_id) REFERENCES learning_update_commits(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, profile_object_id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, version)
```

## personality_trait_values — 特质值（人格）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| profile_id | `@personality_profiles` | 否 | 人格版本 |
| dimension_id | `@personality_dimensions` | 否 | 维度 |
| central_value | `r` | 否 | 中心值 |
| uncertainty_json | `j` | 否 | 不确定性 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, profile_id) REFERENCES personality_profiles(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, dimension_id) REFERENCES personality_dimensions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, profile_id, dimension_id)
```

## personality_states — 人格状态（人格）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| activity_id | `@activities` | 否 | 活动 |
| context_id | `@context_snapshots` | 否 | 情境 |
| dimension_id | `@personality_dimensions` | 否 | 维度 |
| value | `r` | 否 | 状态值 |
| value_origin | `e(configured,derived,estimated,measured)` | 否 | 数值来源 |
| method_version | `t` | 否 | 方法版本 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, context_id) REFERENCES context_snapshots(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, dimension_id) REFERENCES personality_dimensions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## personality_context_effects — 人格情境作用（人格）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| profile_id | `@personality_profiles` | 否 | 版本 |
| dimension_id | `@personality_dimensions` | 否 | 维度 |
| context_rule_id | `@rule_definitions` | 否 | 情境规则 |
| effect_parameters | `j` | 否 | 调节参数 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, profile_id) REFERENCES personality_profiles(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, dimension_id) REFERENCES personality_dimensions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, context_rule_id) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, profile_id, dimension_id, context_rule_id)
```

## personality_behavior_measurements — 人格行为测量（人格）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| evaluation_run_id | `@evaluation_runs` | 否 | 实验 |
| dimension_id | `@personality_dimensions` | 否 | 维度 |
| behavior_ref | `@action_results` | 否 | 行为结果 |
| score | `r` | 否 | 评分 |
| rater_method | `t` | 否 | 评分方法 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evaluation_run_id) REFERENCES evaluation_runs(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, dimension_id) REFERENCES personality_dimensions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, behavior_ref) REFERENCES action_results(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## personality_change_records — 人格变化（人格）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| old_profile_id | `@personality_profiles` | 否 | 原版 |
| new_profile_id | `@personality_profiles` | 否 | 新版 |
| proposal_id | `@learning_update_proposals` | 否 | 提案 |
| reason | `t` | 否 | 原因 |
| reversal_of | `@personality_change_records` | 是 | 撤销对象 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, old_profile_id) REFERENCES personality_profiles(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, new_profile_id) REFERENCES personality_profiles(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, proposal_id) REFERENCES learning_update_proposals(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, reversal_of) REFERENCES personality_change_records(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## cognition_episodes — 认知任务（认知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| activity_id | `@activities` | 否 | 活动 |
| question | `t` | 否 | 问题 |
| context_id | `@context_snapshots` | 否 | 情境 |
| method_version | `t` | 否 | 方法 |
| state | `e(open,resolved,paused,failed)` | 否 | 状态 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, context_id) REFERENCES context_snapshots(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## cognition_concepts — 概念（认知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| name | `t` | 否 | 名称 |
| definition | `t` | 否 | 定义 |
| current_revision_id | `@cognition_concept_revisions` | 是 | 当前修订 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, current_revision_id) REFERENCES cognition_concept_revisions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## cognition_concept_revisions — 概念修订（认知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| concept_id | `@cognition_concepts` | 否 | 概念 |
| revision_no | `i` | 否 | 序号 |
| definition | `t` | 否 | 定义 |
| evidence_id | `@evidence_items` | 否 | 依据 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, concept_id) REFERENCES cognition_concepts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, concept_id, revision_no)
```

## cognition_concept_relations — 概念关系（认知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| subject_concept_id | `@cognition_concepts` | 否 | 主体 |
| relation_type | `t` | 否 | 关系 |
| object_concept_id | `@cognition_concepts` | 否 | 客体 |
| evidence_id | `@evidence_items` | 否 | 证据 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, subject_concept_id) REFERENCES cognition_concepts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, object_concept_id) REFERENCES cognition_concepts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## cognition_beliefs — 信念（认知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| subject_ref | `@world_entities` | 否 | 主体 |
| predicate | `t` | 否 | 谓词 |
| object_ref | `@world_entities` | 是 | 客体 |
| literal | `j` | 是 | 字面值 |
| scope | `j` | 否 | 适用范围 |
| current_revision_id | `@cognition_belief_revisions` | 是 | 当前修订 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, subject_ref) REFERENCES world_entities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, object_ref) REFERENCES world_entities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, current_revision_id) REFERENCES cognition_belief_revisions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
CHECK ((object_ref IS NOT NULL) + (literal IS NOT NULL) = 1)
```

## cognition_belief_revisions — 信念修订（认知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| belief_id | `@cognition_beliefs` | 否 | 信念 |
| revision_no | `i` | 否 | 序号 |
| content | `t` | 否 | 命题 |
| acceptance_state | `e(accepted,held,rejected,expired)` | 否 | 接受状态 |
| uncertainty_json | `j` | 否 | 不确定性 |
| method_version | `t` | 否 | 方法 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, belief_id) REFERENCES cognition_beliefs(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, belief_id, revision_no)
```

## cognition_hypotheses — 竞争解释（认知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| episode_id | `@cognition_episodes` | 否 | 任务 |
| content | `t` | 否 | 解释 |
| state | `e(open,supported,rejected,held)` | 否 | 状态 |
| uncertainty_json | `j` | 否 | 不确定性 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, episode_id) REFERENCES cognition_episodes(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## cognition_evidence_links — 认知证据（认知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| target_revision_id | `@object_revision_registry` | 否 | 目标版本 |
| evidence_id | `@evidence_items` | 否 | 证据 |
| stance | `e(support,oppose,neutral)` | 否 | 立场 |
| strength_method | `t` | 否 | 强度方法 |
| assessment | `j` | 否 | 评估 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, target_revision_id) REFERENCES object_revision_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## cognition_predictions — 预测（认知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| episode_id | `@cognition_episodes` | 否 | 任务 |
| target_ref | `@object_registry` | 否 | 预测对象 |
| predicted_outcome | `j` | 否 | 预期结果 |
| probability_kind | `e(outcome,correctness)` | 否 | 概率含义 |
| probability | `p` | 否 | 概率 |
| due_at | `t` | 否 | 核验时限 |
| verification_rule | `@rule_definitions` | 否 | 核验规则 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, episode_id) REFERENCES cognition_episodes(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, target_ref) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, verification_rule) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## cognition_plans — 计划（认知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| goal_id | `@goal_items` | 否 | 目标 |
| version | `i` | 否 | 版本 |
| state | `e(draft,active,paused,completed,cancelled)` | 否 | 状态 |
| previous_plan_id | `@cognition_plans` | 是 | 前版 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, goal_id) REFERENCES goal_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, previous_plan_id) REFERENCES cognition_plans(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## cognition_plan_steps — 计划步骤（认知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| plan_id | `@cognition_plans` | 否 | 计划 |
| step_no | `i` | 否 | 序号 |
| action_template | `j` | 否 | 动作模板 |
| preconditions | `@rule_definitions` | 否 | 前置规则 |
| expected_outcome | `j` | 否 | 预期 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, plan_id) REFERENCES cognition_plans(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, preconditions) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## cognition_plan_dependencies — 步骤依赖（认知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| step_id | `@cognition_plan_steps` | 否 | 步骤 |
| depends_on_step_id | `@cognition_plan_steps` | 否 | 依赖步骤 |
| condition | `@rule_definitions` | 否 | 条件 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, step_id) REFERENCES cognition_plan_steps(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, depends_on_step_id) REFERENCES cognition_plan_steps(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, condition) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## cognition_assessments — 元认知评估（认知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| episode_id | `@cognition_episodes` | 否 | 任务 |
| assessment_type | `t` | 否 | 评估类型 |
| estimate | `j` | 否 | 估计 |
| information_gap | `t` | 否 | 信息缺口 |
| recommended_control | `t` | 否 | 控制建议 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, episode_id) REFERENCES cognition_episodes(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## cognition_assessment_outcomes — 认知核验（认知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| assessment_id | `@cognition_assessments` | 是 | 评估 |
| prediction_id | `@cognition_predictions` | 是 | 预测 |
| outcome_ref | `@action_results` | 否 | 结果 |
| scoring_method | `t` | 否 | 评分方法 |
| score | `r` | 否 | 分数 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, assessment_id) REFERENCES cognition_assessments(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, prediction_id) REFERENCES cognition_predictions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, outcome_ref) REFERENCES action_results(instance_id, id) DEFERRABLE INITIALLY DEFERRED
CHECK ((assessment_id IS NOT NULL) + (prediction_id IS NOT NULL) = 1)
```

## cognition_attention_allocations — 注意分配（认知）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| episode_id | `@cognition_episodes` | 否 | 任务 |
| target_revision_id | `@object_revision_registry` | 否 | 关注版本 |
| weight | `p` | 否 | 权重 |
| allocation_stage | `e(before_decision,after_decision)` | 否 | 记录阶段 |
| method | `t` | 否 | 方法 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, episode_id) REFERENCES cognition_episodes(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, target_revision_id) REFERENCES object_revision_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## memory_items — 记忆对象（记忆）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| current_revision_id | `@memory_revisions` | 是 | 当前修订 |
| state | `e(active,archived,retracted,deleted)` | 否 | 状态 |
| salience | `p` | 否 | 显著性 |
| access_policy_ref | `@policy_versions` | 否 | 访问策略 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, current_revision_id) REFERENCES memory_revisions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, access_policy_ref) REFERENCES policy_versions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## memory_classifications — 记忆分类（记忆）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| memory_id | `@memory_items` | 否 | 记忆 |
| axis | `e(content,self_relation,temporal_function,other)` | 否 | 分类轴 |
| label | `t` | 否 | 分类值 |
| method_version | `t` | 否 | 方法 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, memory_id) REFERENCES memory_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, memory_id, axis, label)
```

## memory_revisions — 记忆修订（记忆）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| memory_id | `@memory_items` | 否 | 记忆 |
| revision_no | `i` | 否 | 序号 |
| content | `t` | 否 | 内容 |
| encoding_method | `t` | 否 | 编码方法 |
| correction_reason | `t` | 是 | 修正原因 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, memory_id) REFERENCES memory_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, memory_id, revision_no)
```

## memory_source_links — 记忆来源（记忆）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| memory_revision_id | `@memory_revisions` | 否 | 记忆修订 |
| evidence_id | `@evidence_items` | 否 | 证据 |
| role | `e(observed,inferred,summarized,restored)` | 否 | 来源角色 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, memory_revision_id) REFERENCES memory_revisions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## memory_relations — 记忆关系（记忆）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| from_memory_id | `@memory_items` | 否 | 起点 |
| relation_type | `t` | 否 | 关系 |
| to_memory_id | `@memory_items` | 否 | 终点 |
| evidence_id | `@evidence_items` | 否 | 依据 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, from_memory_id) REFERENCES memory_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, to_memory_id) REFERENCES memory_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## memory_episode_details — 情景扩展（记忆）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| memory_revision_id | `@memory_revisions` | 否 | 记忆修订 |
| event_ref | `@perception_signals` | 否 | 经历输入 |
| time_start | `t` | 是 | 开始时间 |
| time_end | `t` | 是 | 结束时间 |
| place_ref | `@world_entities` | 是 | 地点 |
| outcome_ref | `@action_results` | 是 | 结果 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, memory_revision_id) REFERENCES memory_revisions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, event_ref) REFERENCES perception_signals(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, place_ref) REFERENCES world_entities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, outcome_ref) REFERENCES action_results(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## memory_participants — 情景参与者（记忆）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| memory_revision_id | `@memory_revisions` | 否 | 修订 |
| entity_id | `@world_entities` | 否 | 参与对象 |
| role | `t` | 否 | 角色 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, memory_revision_id) REFERENCES memory_revisions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, entity_id) REFERENCES world_entities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## memory_semantic_details — 语义扩展（记忆）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| memory_revision_id | `@memory_revisions` | 否 | 修订 |
| belief_revision_id | `@cognition_belief_revisions` | 否 | 信念版本 |
| scope | `j` | 否 | 范围 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, memory_revision_id) REFERENCES memory_revisions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, belief_revision_id) REFERENCES cognition_belief_revisions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## memory_procedure_details — 程序扩展（记忆）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| memory_revision_id | `@memory_revisions` | 否 | 修订 |
| skill_ref | `@capability_definitions` | 否 | 技能 |
| applicability_rule | `@rule_definitions` | 否 | 适用规则 |
| procedure_version | `t` | 否 | 程序版本 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, memory_revision_id) REFERENCES memory_revisions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, skill_ref) REFERENCES capability_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, applicability_rule) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## memory_autobiographical_details — 自传扩展（记忆）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| memory_revision_id | `@memory_revisions` | 否 | 修订 |
| life_period | `t` | 否 | 历史阶段 |
| self_relevance | `p` | 否 | 自我关联 |
| identity_significance | `t` | 否 | 身份意义 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, memory_revision_id) REFERENCES memory_revisions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## memory_prospective_details — 前瞻扩展（记忆）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| memory_revision_id | `@memory_revisions` | 否 | 修订 |
| intention_id | `@intention_items` | 否 | 意图 |
| cue_rule_id | `@rule_definitions` | 否 | 触发线索 |
| target_time | `t` | 是 | 目标时间 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, memory_revision_id) REFERENCES memory_revisions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, intention_id) REFERENCES intention_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, cue_rule_id) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## memory_retrieval_runs — 检索请求（记忆）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| activity_id | `@activities` | 否 | 活动 |
| query | `t` | 否 | 查询 |
| context_id | `@context_snapshots` | 否 | 情境 |
| retriever_version | `t` | 否 | 检索版本 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, context_id) REFERENCES context_snapshots(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## memory_retrieval_results — 检索候选（记忆）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| run_id | `@memory_retrieval_runs` | 否 | 检索 |
| memory_revision_id | `@memory_revisions` | 否 | 版本 |
| rank | `i` | 否 | 排序 |
| score | `r` | 否 | 检索分数 |
| selection_reason | `t` | 否 | 选择原因 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, run_id) REFERENCES memory_retrieval_runs(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, memory_revision_id) REFERENCES memory_revisions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, run_id, rank)
UNIQUE (instance_id, run_id, memory_revision_id)
```

## memory_recall_products — 召回重构（记忆）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| run_id | `@memory_retrieval_runs` | 否 | 检索 |
| reconstructed_content | `t` | 否 | 召回产物 |
| method_version | `t` | 否 | 重构版本 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, run_id) REFERENCES memory_retrieval_runs(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## memory_recall_sources — 重构来源（记忆）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| recall_id | `@memory_recall_products` | 否 | 产物 |
| memory_revision_id | `@memory_revisions` | 否 | 原记忆 |
| evidence_id | `@evidence_items` | 否 | 证据 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, recall_id) REFERENCES memory_recall_products(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, memory_revision_id) REFERENCES memory_revisions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## memory_access_records — 记忆使用（记忆）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| memory_revision_id | `@memory_revisions` | 否 | 版本 |
| activity_id | `@activities` | 否 | 活动 |
| operation | `e(encoded,retrieved,read,used)` | 否 | 操作 |
| used_in_ref | `@object_registry` | 是 | 使用位置 |
| outcome_ref | `@action_results` | 是 | 结果 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, memory_revision_id) REFERENCES memory_revisions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, used_in_ref) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, outcome_ref) REFERENCES action_results(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## memory_retention_rules — 保留规则（记忆）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| scope | `j` | 否 | 作用域 |
| action | `e(retain,downweight,archive,delete)` | 否 | 动作 |
| trigger | `@rule_definitions` | 否 | 触发 |
| policy_version | `@policy_versions` | 否 | 策略 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, trigger) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, policy_version) REFERENCES policy_versions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## working_memory_items — 工作记忆（记忆）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| activity_id | `@activities` | 否 | 活动 |
| content | `t` | 是 | 临时内容 |
| object_revision_ref | `@object_revision_registry` | 是 | 引用版本 |
| expires_at | `t` | 是 | 失效时间 |
| item_kind | `e(temporary,reference)` | 否 | 形式 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, object_revision_ref) REFERENCES object_revision_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
CHECK ((item_kind='temporary' AND content IS NOT NULL AND object_revision_ref IS NULL) OR (item_kind='reference' AND content IS NULL AND object_revision_ref IS NOT NULL))
```

## working_memory_activations — 工作记忆激活（记忆）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| item_id | `@working_memory_items` | 否 | 条目 |
| activity_step_id | `@activity_steps` | 否 | 步骤 |
| activation | `p` | 否 | 激活 |
| attention_state | `e(focused,available,inactive)` | 否 | 关注状态 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, item_id) REFERENCES working_memory_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_step_id) REFERENCES activity_steps(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## value_dimensions — 价值维度（价值）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| definition | `t` | 否 | 定义 |
| scale | `j` | 否 | 量表 |
| theory_version | `t` | 否 | 理论版本 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## value_dimension_relations — 价值关系（价值）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| from_id | `@value_dimensions` | 否 | 起点 |
| to_id | `@value_dimensions` | 否 | 终点 |
| relation_type | `e(compatible,conflicting,other)` | 否 | 关系 |
| method | `t` | 否 | 方法 |
| evidence_id | `@evidence_items` | 否 | 依据 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, from_id) REFERENCES value_dimensions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, to_id) REFERENCES value_dimensions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## value_profiles — 价值版本（价值）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| version | `i` | 否 | 版本 |
| previous_id | `@value_profiles` | 是 | 前版 |
| effective_at | `t` | 否 | 生效时间 |
| update_commit_id | `@learning_update_commits` | 是 | 提交 |
| normalization_rule | `t` | 否 | 归一化规则 |
| profile_object_id | `@object_registry` | 否 | 跨版本稳定配置对象 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, previous_id) REFERENCES value_profiles(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, update_commit_id) REFERENCES learning_update_commits(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, profile_object_id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, version)
```

## value_weights — 价值权重（价值）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| profile_id | `@value_profiles` | 否 | 版本 |
| dimension_id | `@value_dimensions` | 否 | 维度 |
| weight | `r` | 否 | 相对权重 |
| uncertainty_json | `j` | 否 | 不确定性 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, profile_id) REFERENCES value_profiles(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, dimension_id) REFERENCES value_dimensions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, profile_id, dimension_id)
```

## value_activations — 价值激活（价值）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| profile_id | `@value_profiles` | 否 | 版本 |
| activity_id | `@activities` | 否 | 活动 |
| context_id | `@context_snapshots` | 否 | 情境 |
| dimension_id | `@value_dimensions` | 否 | 维度 |
| activation | `p` | 否 | 激活 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, profile_id) REFERENCES value_profiles(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, context_id) REFERENCES context_snapshots(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, dimension_id) REFERENCES value_dimensions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## value_conflicts — 价值冲突（价值）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| activity_id | `@activities` | 否 | 活动 |
| resolution_ref | `@object_registry` | 是 | 处理依据 |
| state | `e(open,resolved,held)` | 否 | 状态 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, resolution_ref) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## value_conflict_members — 冲突成员（价值）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| conflict_id | `@value_conflicts` | 否 | 冲突 |
| dimension_id | `@value_dimensions` | 否 | 价值 |
| role | `t` | 否 | 角色 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, conflict_id) REFERENCES value_conflicts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, dimension_id) REFERENCES value_dimensions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## value_behavior_measurements — 价值行为效度（价值）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| evaluation_run_id | `@evaluation_runs` | 否 | 实验 |
| decision_ref | `@decision_records` | 否 | 决策 |
| dimension_id | `@value_dimensions` | 否 | 价值 |
| score | `r` | 否 | 评分 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evaluation_run_id) REFERENCES evaluation_runs(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, decision_ref) REFERENCES decision_records(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, dimension_id) REFERENCES value_dimensions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## value_change_records — 价值变化（价值）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| old_profile_id | `@value_profiles` | 否 | 原版 |
| new_profile_id | `@value_profiles` | 否 | 新版 |
| proposal_id | `@learning_update_proposals` | 否 | 提案 |
| reason | `t` | 否 | 原因 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, old_profile_id) REFERENCES value_profiles(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, new_profile_id) REFERENCES value_profiles(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, proposal_id) REFERENCES learning_update_proposals(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## goal_items — 目标（目标动机）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| source_ref | `@object_registry` | 否 | 来源 |
| content | `t` | 否 | 目标 |
| target_ref | `@world_entities` | 是 | 对象 |
| state | `e(candidate,accepted,active,paused,completed,cancelled,expired,failed)` | 否 | 状态 |
| success_rule | `@rule_definitions` | 否 | 完成规则 |
| stop_rule | `@rule_definitions` | 否 | 停止规则 |
| due_at | `t` | 是 | 期限 |
| state_revision | `i0` | 否 | 当前状态序号（初始0） |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, source_ref) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, target_ref) REFERENCES world_entities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, success_rule) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, stop_rule) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## goal_relations — 目标关系（目标动机）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| from_goal_id | `@goal_items` | 否 | 起点 |
| to_goal_id | `@goal_items` | 否 | 终点 |
| relation_type | `e(subgoal,depends_on,conflicts,supports)` | 否 | 关系 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, from_goal_id) REFERENCES goal_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, to_goal_id) REFERENCES goal_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## goal_evaluations — 目标评估（目标动机）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| goal_id | `@goal_items` | 否 | 目标 |
| activity_id | `@activities` | 否 | 活动 |
| value_alignment | `r` | 否 | 价值一致 |
| expectancy | `p` | 否 | 可达期望 |
| cost | `n` | 否 | 成本 |
| risk | `n` | 否 | 风险 |
| urgency | `p` | 否 | 紧迫 |
| model_version | `@model_versions` | 否 | 模型 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, goal_id) REFERENCES goal_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, model_version) REFERENCES model_versions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## goal_evaluation_factors — 目标因素（目标动机）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| evaluation_id | `@goal_evaluations` | 否 | 评估 |
| source_revision_id | `@object_revision_registry` | 否 | 来源 |
| factor_type | `t` | 否 | 类型 |
| contribution | `r` | 否 | 贡献 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evaluation_id) REFERENCES goal_evaluations(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, source_revision_id) REFERENCES object_revision_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## goal_activation_batches — 目标激活批次（目标动机）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| activity_id | `@activities` | 否 | 活动 |
| strategy_version | `t` | 否 | 策略 |
| state | `e(draft,finalized)` | 否 | 批次状态 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## goal_activation_records — 目标激活（目标动机）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| decision_batch_id | `@goal_activation_batches` | 否 | 批次 |
| goal_id | `@goal_items` | 否 | 目标 |
| score | `r` | 否 | 分数 |
| probability | `p` | 否 | 概率 |
| selected | `b` | 否 | 选中 |
| strategy_version | `t` | 否 | 策略 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, decision_batch_id) REFERENCES goal_activation_batches(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, goal_id) REFERENCES goal_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, decision_batch_id, goal_id)
```

## goal_transitions — 目标转换（目标动机）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| goal_id | `@goal_items` | 否 | 目标 |
| from_state | `t` | 否 | 原状态 |
| to_state | `t` | 否 | 新状态 |
| event_id | `@perception_signals` | 否 | 事件 |
| reason | `t` | 否 | 原因 |
| transition_no | `i` | 否 | 状态转换序号（从1开始） |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, goal_id) REFERENCES goal_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, event_id) REFERENCES perception_signals(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## intention_items — 持续意图（目标动机）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| goal_id | `@goal_items` | 否 | 目标 |
| plan_id | `@cognition_plans` | 是 | 计划 |
| trigger_rule | `@rule_definitions` | 否 | 触发 |
| state | `e(proposed,active,paused,completed,abandoned)` | 否 | 状态 |
| abandonment_rule | `@rule_definitions` | 否 | 放弃规则 |
| state_revision | `i0` | 否 | 当前状态序号（初始0） |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, goal_id) REFERENCES goal_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, plan_id) REFERENCES cognition_plans(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, trigger_rule) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, abandonment_rule) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## intention_transitions — 意图转换（目标动机）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| intention_id | `@intention_items` | 否 | 意图 |
| from_state | `t` | 否 | 原状态 |
| to_state | `t` | 否 | 新状态 |
| reason_ref | `@evidence_items` | 否 | 依据 |
| transition_no | `i` | 否 | 状态转换序号（从1开始） |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, intention_id) REFERENCES intention_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, reason_ref) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## motivation_states — 动机状态（目标动机）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| goal_id | `@goal_items` | 否 | 目标 |
| activity_id | `@activities` | 否 | 活动 |
| intensity | `p` | 否 | 强度 |
| source_type | `t` | 否 | 来源 |
| regulation_type | `t` | 否 | 调节方式 |
| persistence | `p` | 否 | 持续性 |
| satiation | `p` | 否 | 满足程度 |
| budget | `j` | 否 | 资源预算 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, goal_id) REFERENCES goal_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## habit_items — 习惯（习惯）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| response_template | `j` | 否 | 反应模板 |
| state | `e(learning,active,inhibited,extinct)` | 否 | 状态 |
| procedure_memory_ref | `@memory_revisions` | 是 | 技能记忆 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, procedure_memory_ref) REFERENCES memory_revisions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## habit_cues — 习惯线索（习惯）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| habit_id | `@habit_items` | 否 | 习惯 |
| context_rule_id | `@rule_definitions` | 否 | 情境规则 |
| match_method | `t` | 否 | 匹配方法 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, habit_id) REFERENCES habit_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, context_rule_id) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## habit_associations — 线索反应联系（习惯）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| habit_id | `@habit_items` | 否 | 习惯 |
| cue_id | `@habit_cues` | 否 | 线索 |
| strength | `p` | 否 | 强度 |
| uncertainty_json | `j` | 否 | 不确定性 |
| learning_version | `t` | 否 | 学习方法 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, habit_id) REFERENCES habit_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, cue_id) REFERENCES habit_cues(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, habit_id, cue_id)
```

## habit_opportunities — 线索机会（习惯）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| cue_id | `@habit_cues` | 否 | 线索 |
| activity_id | `@activities` | 否 | 活动 |
| match_score | `p` | 否 | 匹配程度 |
| action_taken | `b` | 否 | 是否行动 |
| control_mode | `e(habit,goal_directed,mixed,unknown)` | 否 | 控制方式 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, cue_id) REFERENCES habit_cues(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## habit_activations — 习惯触发（习惯）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| opportunity_id | `@habit_opportunities` | 否 | 机会 |
| candidate_id | `@decision_candidates` | 是 | 候选 |
| triggered | `b` | 否 | 触发 |
| inhibited | `b` | 否 | 抑制 |
| inhibition_reason | `t` | 是 | 抑制原因 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, opportunity_id) REFERENCES habit_opportunities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, candidate_id) REFERENCES decision_candidates(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## habit_learning_records — 习惯更新（习惯）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| association_ref | `@habit_associations` | 否 | 联系 |
| before_value | `p` | 否 | 原强度 |
| after_value | `p` | 否 | 新强度 |
| feedback_id | `@learning_feedback` | 否 | 反馈 |
| update_commit_id | `@learning_update_commits` | 否 | 提交 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, association_ref) REFERENCES habit_associations(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, feedback_id) REFERENCES learning_feedback(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, update_commit_id) REFERENCES learning_update_commits(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## social_actors — 社会主体（关系）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| entity_id | `@world_entities` | 否 | 世界对象 |
| actor_type | `t` | 否 | 主体类型 |
| identity_status | `e(unverified,verified,disputed)` | 否 | 身份核验 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, entity_id) REFERENCES world_entities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, entity_id)
```

## social_relationships — 关系（关系）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| actor_id | `@social_actors` | 否 | 对象 |
| state | `e(active,dormant,ended,disputed)` | 否 | 状态 |
| current_revision | `i` | 否 | 当前序号 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, actor_id) REFERENCES social_actors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, actor_id)
```

## social_relationship_dimensions — 关系维度（关系）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| definition | `t` | 否 | 定义 |
| scale | `j` | 否 | 量表 |
| method | `t` | 否 | 方法 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## social_relationship_values — 关系值（关系）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| relationship_id | `@social_relationships` | 否 | 关系 |
| dimension_id | `@social_relationship_dimensions` | 否 | 维度 |
| value | `r` | 否 | 数值 |
| evidence_id | `@evidence_items` | 否 | 依据 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, relationship_id) REFERENCES social_relationships(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, dimension_id) REFERENCES social_relationship_dimensions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, relationship_id, dimension_id)
```

## social_trust_assessments — 信任判断（关系）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| relationship_id | `@social_relationships` | 否 | 关系 |
| domain | `t` | 否 | 领域 |
| condition_rule | `@rule_definitions` | 否 | 条件 |
| dimension | `t` | 否 | 可信特征 |
| estimate | `p` | 否 | 估计 |
| uncertainty_json | `j` | 否 | 不确定性 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, relationship_id) REFERENCES social_relationships(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, condition_rule) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## social_trust_evidence — 信任依据（关系）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| assessment_id | `@social_trust_assessments` | 否 | 判断 |
| evidence_id | `@evidence_items` | 否 | 证据 |
| stance | `e(support,oppose,neutral)` | 否 | 立场 |
| attribution_ref | `@learning_attributions` | 是 | 归因 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, assessment_id) REFERENCES social_trust_assessments(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, attribution_ref) REFERENCES learning_attributions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## social_expectations — 关系预期（关系）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| relationship_id | `@social_relationships` | 否 | 关系 |
| expected_action | `j` | 否 | 预期行动 |
| context_rule | `@rule_definitions` | 否 | 情境 |
| probability | `p` | 否 | 发生概率 |
| outcome_ref | `@action_results` | 是 | 实际结果 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, relationship_id) REFERENCES social_relationships(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, context_rule) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, outcome_ref) REFERENCES action_results(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## social_interactions — 互动（关系）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| relationship_id | `@social_relationships` | 否 | 关系 |
| event_id | `@perception_signals` | 否 | 输入 |
| activity_id | `@activities` | 否 | 活动 |
| interaction_role | `t` | 否 | 角色 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, relationship_id) REFERENCES social_relationships(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, event_id) REFERENCES perception_signals(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## social_relationship_changes — 关系变化（关系）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| relationship_id | `@social_relationships` | 否 | 关系 |
| dimension_id | `@social_relationship_dimensions` | 否 | 维度 |
| old_value | `r` | 否 | 原值 |
| new_value | `r` | 否 | 新值 |
| reason_ref | `@evidence_items` | 否 | 依据 |
| reversal_of | `@social_relationship_changes` | 是 | 撤销记录 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, relationship_id) REFERENCES social_relationships(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, dimension_id) REFERENCES social_relationship_dimensions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, reason_ref) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, reversal_of) REFERENCES social_relationship_changes(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## commitment_items — 社会承诺（承诺）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| debtor_actor_id | `@social_actors` | 否 | 责任方 |
| creditor_actor_id | `@social_actors` | 否 | 受益方 |
| kind | `e(achievement,maintenance)` | 否 | 承诺类型 |
| antecedent_rule | `@rule_definitions` | 否 | 生效条件 |
| consequent_rule | `@rule_definitions` | 否 | 履行条件 |
| state | `e(proposed,confirmed,active,performing,paused,renegotiating,fulfilled,released,impossible,expired,violated)` | 否 | 状态 |
| due_at | `t` | 是 | 期限 |
| state_revision | `i0` | 否 | 当前状态序号（初始0） |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, debtor_actor_id) REFERENCES social_actors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, creditor_actor_id) REFERENCES social_actors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, antecedent_rule) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, consequent_rule) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## commitment_confirmations — 承诺确认（承诺）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| commitment_id | `@commitment_items` | 否 | 承诺 |
| actor_id | `@social_actors` | 否 | 确认者 |
| event_id | `@perception_signals` | 否 | 确认事件 |
| confirmation_type | `t` | 否 | 方式 |
| grant_ref | `@grants` | 是 | 授权 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, commitment_id) REFERENCES commitment_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, actor_id) REFERENCES social_actors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, event_id) REFERENCES perception_signals(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, grant_ref) REFERENCES grants(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## commitment_transitions — 承诺转换（承诺）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| commitment_id | `@commitment_items` | 否 | 承诺 |
| from_state | `t` | 否 | 原状态 |
| to_state | `t` | 否 | 新状态 |
| event_id | `@perception_signals` | 否 | 变更事件 |
| reason | `t` | 否 | 原因 |
| transition_no | `i` | 否 | 状态转换序号（从1开始） |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, commitment_id) REFERENCES commitment_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, event_id) REFERENCES perception_signals(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## commitment_goal_links — 履行目标（承诺）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| commitment_id | `@commitment_items` | 否 | 承诺 |
| goal_id | `@goal_items` | 否 | 目标 |
| role | `t` | 否 | 用途 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, commitment_id) REFERENCES commitment_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, goal_id) REFERENCES goal_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## commitment_conflicts — 承诺冲突（承诺）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| state | `e(open,resolved,held)` | 否 | 状态 |
| resolution_ref | `@evidence_items` | 是 | 裁决 |
| detected_at | `t` | 否 | 发现时间 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, resolution_ref) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## commitment_conflict_members — 承诺冲突成员（承诺）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| conflict_id | `@commitment_conflicts` | 否 | 冲突 |
| commitment_id | `@commitment_items` | 是 | 承诺 |
| policy_ref | `@policy_versions` | 是 | 规则 |
| resource_ref | `@world_entities` | 是 | 资源 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, conflict_id) REFERENCES commitment_conflicts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, commitment_id) REFERENCES commitment_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, policy_ref) REFERENCES policy_versions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, resource_ref) REFERENCES world_entities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
CHECK ((commitment_id IS NOT NULL) + (policy_ref IS NOT NULL) + (resource_ref IS NOT NULL) = 1)
```

## commitment_compliance_checks — 维持型承诺检查（承诺）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| commitment_id | `@commitment_items` | 否 | 承诺 |
| interval_start | `t` | 否 | 开始 |
| interval_end | `t` | 否 | 结束 |
| result | `e(pass,fail,unknown)` | 否 | 结果 |
| evidence_id | `@evidence_items` | 否 | 依据 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, commitment_id) REFERENCES commitment_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
CHECK (interval_start <= interval_end)
```

## state_definitions — 状态定义（内部状态）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| name | `t` | 否 | 名称 |
| unit | `t` | 否 | 单位 |
| direction | `t` | 否 | 方向 |
| measurement_kind | `e(observed,estimated)` | 否 | 来源类型 |
| ttl | `i` | 否 | 有效秒数 |
| range_rule | `@rule_definitions` | 否 | 正常范围 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, range_rule) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## state_observations — 状态测量（内部状态）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| definition_id | `@state_definitions` | 否 | 定义 |
| value | `r` | 否 | 观测值 |
| observed_at | `t` | 否 | 观测时间 |
| source_ref | `@evidence_items` | 否 | 来源 |
| quality | `e(valid,suspect,missing)` | 否 | 质量 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, definition_id) REFERENCES state_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, source_ref) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## state_estimates — 状态估计（内部状态）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| definition_id | `@state_definitions` | 否 | 定义 |
| estimate | `r` | 否 | 估计 |
| uncertainty_json | `j` | 否 | 不确定性 |
| method_version | `t` | 否 | 方法 |
| expires_at | `t` | 否 | 到期 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, definition_id) REFERENCES state_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## state_estimate_sources — 估计来源（内部状态）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| estimate_id | `@state_estimates` | 否 | 估计 |
| source_revision_id | `@object_revision_registry` | 否 | 依据 |
| role | `t` | 否 | 作用 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, estimate_id) REFERENCES state_estimates(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, source_revision_id) REFERENCES object_revision_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## state_activity_snapshots — 采用状态（内部状态）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| activity_id | `@activities` | 否 | 活动 |
| state_observation_id | `@state_observations` | 是 | 观测 |
| state_estimate_id | `@state_estimates` | 是 | 估计 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, state_observation_id) REFERENCES state_observations(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, state_estimate_id) REFERENCES state_estimates(instance_id, id) DEFERRABLE INITIALLY DEFERRED
CHECK ((state_observation_id IS NOT NULL) + (state_estimate_id IS NOT NULL) = 1)
```

## decision_records — 决策（决策行动）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| activity_id | `@activities` | 否 | 活动 |
| goal_id | `@goal_items` | 否 | 目标 |
| context_id | `@context_snapshots` | 否 | 情境 |
| strategy_type | `t` | 否 | 策略类型 |
| strategy_version | `t` | 否 | 策略版本 |
| seed | `i` | 是 | 随机种子 |
| state | `e(draft,finalized)` | 否 | 记录状态 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, goal_id) REFERENCES goal_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, context_id) REFERENCES context_snapshots(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## decision_candidates — 行为候选（决策行动）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| decision_id | `@decision_records` | 否 | 决策 |
| action_template | `j` | 否 | 动作模板 |
| eligible | `b` | 否 | 可选 |
| blocked_reason | `t` | 是 | 屏蔽原因 |
| score | `r` | 否 | 分数 |
| selection_probability | `p` | 否 | 选择概率 |
| selected | `b` | 否 | 已选 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, decision_id) REFERENCES decision_records(instance_id, id) DEFERRABLE INITIALLY DEFERRED
CHECK (eligible = 1 OR (selected = 0 AND selection_probability = 0 AND blocked_reason IS NOT NULL))
CHECK (selected = 0 OR eligible = 1)
```

## decision_factor_contributions — 决策因素（决策行动）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| candidate_id | `@decision_candidates` | 否 | 候选 |
| factor_type | `t` | 否 | 因素 |
| source_revision_id | `@object_revision_registry` | 否 | 来源 |
| effect_path | `t` | 否 | 直接或中介路径 |
| contribution | `r` | 否 | 贡献 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, candidate_id) REFERENCES decision_candidates(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, source_revision_id) REFERENCES object_revision_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## action_intents — 动作意图（决策行动）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| candidate_id | `@decision_candidates` | 否 | 候选 |
| plan_step_id | `@cognition_plan_steps` | 是 | 步骤 |
| tool_id | `@tool_definitions` | 否 | 工具 |
| arguments_json | `j` | 否 | 参数 |
| grant_id | `@grants` | 是 | 授权 |
| idempotency_key | `t` | 否 | 幂等键 |
| verification_rule | `@rule_definitions` | 否 | 核验规则 |
| state | `e(proposed,awaiting_approval,authorized,queued,dispatching,running,succeeded,failed,partial,unknown,cancelled)` | 否 | 状态 |
| proposal_revision | `i0` | 否 | 提案修订 |
| lifecycle_revision | `i0` | 否 | 状态修订 |
| arguments_hash | `t` | 否 | 摘要 |
| required_capability_id | `@capability_definitions` | 否 | 能力 |
| resource_scope | `j` | 否 | 范围 |
| deadline | `t` | 是 | 期限 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, candidate_id) REFERENCES decision_candidates(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, plan_step_id) REFERENCES cognition_plan_steps(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, tool_id) REFERENCES tool_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, grant_id) REFERENCES grants(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, verification_rule) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, required_capability_id) REFERENCES capability_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, tool_id, idempotency_key)
```

## action_attempts — 执行尝试（决策行动）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| intent_id | `@action_intents` | 否 | 意图 |
| attempt_no | `i` | 否 | 尝试序号 |
| started_at | `t` | 否 | 开始 |
| finished_at | `t` | 是 | 结束 |
| runner_ref | `t` | 否 | 执行器 |
| state | `e(pending,running,succeeded,failed,partial,unknown,cancelled)` | 否 | 状态 |
| authorization_record_id | `@action_authorization_records` | 否 | 授权 |
| policy_epoch | `i` | 否 | 权限代次 |
| execution_token_hash | `t` | 否 | 令牌摘要 |
| arguments_hash | `t` | 否 | 参数摘要 |
| backend_operation_id | `t` | 是 | 后端标识 |
| start_gate_at | `t` | 是 | 开始门禁 |
| cancel_requested_at | `t` | 是 | 取消 |
| runtime_epoch | `i` | 否 | 世代 |
| process_run_id | `t` | 否 | 进程 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, intent_id) REFERENCES action_intents(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, authorization_record_id) REFERENCES action_authorization_records(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, intent_id, attempt_no)
```

## action_results — 执行结果（决策行动）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| attempt_id | `@action_attempts` | 否 | 尝试 |
| state | `e(succeeded,failed,partial,unknown)` | 否 | 结果 |
| receipt_artifact_id | `@artifacts` | 是 | 原始回执 |
| outcome_ref | `@evidence_items` | 是 | 结果证据 |
| error_type | `t` | 是 | 错误类型 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, attempt_id) REFERENCES action_attempts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, receipt_artifact_id) REFERENCES artifacts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, outcome_ref) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, attempt_id)
```

## action_effects — 外部影响（决策行动）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| intent_id | `@action_intents` | 否 | 意图 |
| entity_ref | `@world_entities` | 否 | 受影响对象 |
| effect_description | `t` | 否 | 变化 |
| observed_at | `t` | 否 | 观测时间 |
| evidence_id | `@evidence_items` | 否 | 证据 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, intent_id) REFERENCES action_intents(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, entity_ref) REFERENCES world_entities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## action_verifications — 动作核验（决策行动）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| intent_id | `@action_intents` | 否 | 意图 |
| method_version | `t` | 否 | 方法 |
| result | `e(pass,fail,unknown)` | 否 | 结果 |
| evidence_id | `@evidence_items` | 否 | 证据 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, intent_id) REFERENCES action_intents(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## action_attributions — 行动归属（决策行动）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| action_id | `@action_intents` | 否 | 动作 |
| initiator_actor_id | `@social_actors` | 否 | 发起者 |
| authorizer_actor_id | `@social_actors` | 否 | 授权者 |
| executor_ref | `t` | 否 | 执行器 |
| evidence_id | `@evidence_items` | 否 | 归属依据 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, action_id) REFERENCES action_intents(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, initiator_actor_id) REFERENCES social_actors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, authorizer_actor_id) REFERENCES social_actors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## learning_feedback — 学习反馈（学习适应）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| prediction_ref | `@cognition_predictions` | 是 | 预测 |
| result_ref | `@action_results` | 否 | 结果 |
| signal_type | `e(fact,task,cost,risk,evaluation,other)` | 否 | 信号 |
| error_value | `r` | 是 | 数值误差 |
| description | `t` | 是 | 文字反馈 |
| source_ref | `@evidence_items` | 否 | 来源 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, prediction_ref) REFERENCES cognition_predictions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, result_ref) REFERENCES action_results(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, source_ref) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
CHECK (error_value IS NOT NULL OR description IS NOT NULL)
```

## learning_attributions — 结果归因（学习适应）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| feedback_id | `@learning_feedback` | 否 | 反馈 |
| target_revision_id | `@object_revision_registry` | 否 | 归因对象 |
| cause_type | `t` | 否 | 原因 |
| estimate | `p` | 否 | 可能性 |
| evidence_id | `@evidence_items` | 否 | 依据 |
| evidence_level | `e(association,intervention,controlled)` | 否 | 证据级别 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, feedback_id) REFERENCES learning_feedback(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, target_revision_id) REFERENCES object_revision_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## learning_update_proposals — 学习提案（学习适应）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| owner_module | `t` | 否 | 所有者 |
| target_object_id | `@object_registry` | 否 | 目标对象 |
| mechanism_version | `t` | 否 | 机制 |
| proposed_change | `j` | 否 | 变化 |
| scope | `j` | 否 | 范围 |
| risk | `n` | 否 | 风险 |
| state | `e(proposed,trial,accepted,rejected,reverted)` | 否 | 状态 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, target_object_id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## learning_proposal_evidence — 提案证据（学习适应）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| proposal_id | `@learning_update_proposals` | 否 | 提案 |
| evidence_id | `@evidence_items` | 否 | 依据 |
| role | `t` | 否 | 作用 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, proposal_id) REFERENCES learning_update_proposals(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## learning_update_trials — 更新试用（学习适应）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| proposal_id | `@learning_update_proposals` | 否 | 提案 |
| baseline_ref | `@evaluation_runs` | 否 | 基线 |
| trial_version | `t` | 否 | 试用版本 |
| scope | `j` | 否 | 范围 |
| started_at | `t` | 否 | 开始 |
| ended_at | `t` | 是 | 结束 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, proposal_id) REFERENCES learning_update_proposals(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, baseline_ref) REFERENCES evaluation_runs(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## learning_update_evaluations — 试用评价（学习适应）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| trial_id | `@learning_update_trials` | 否 | 试用 |
| evaluation_run_id | `@evaluation_runs` | 否 | 实验 |
| benefit | `r` | 否 | 收益 |
| regression | `n` | 否 | 退化 |
| decision | `e(accept,reject,continue)` | 否 | 结论 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, trial_id) REFERENCES learning_update_trials(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evaluation_run_id) REFERENCES evaluation_runs(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## learning_update_commits — 更新提交（学习适应）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| proposal_id | `@learning_update_proposals` | 否 | 提案 |
| old_revision_id | `@object_revision_registry` | 否 | 旧版本 |
| new_revision_id | `@object_revision_registry` | 否 | 新版本 |
| committed_at | `t` | 否 | 提交时间 |
| reversal_of | `@learning_update_commits` | 是 | 撤销提交 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, proposal_id) REFERENCES learning_update_proposals(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, old_revision_id) REFERENCES object_revision_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, new_revision_id) REFERENCES object_revision_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, reversal_of) REFERENCES learning_update_commits(instance_id, id) DEFERRABLE INITIALLY DEFERRED
CHECK (old_revision_id <> new_revision_id)
```

## adaptation_standard_versions — 适应标准（学习适应）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| level | `e(external,core,context,task)` | 否 | 层级 |
| scope | `j` | 否 | 范围 |
| criteria_json | `j` | 否 | 标准 |
| previous_id | `@adaptation_standard_versions` | 是 | 前版 |
| authority_ref | `@social_actors` | 否 | 授权者 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, previous_id) REFERENCES adaptation_standard_versions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, authority_ref) REFERENCES social_actors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## adaptation_standard_changes — 标准变化（学习适应）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| old_id | `@adaptation_standard_versions` | 否 | 旧版 |
| new_id | `@adaptation_standard_versions` | 否 | 新版 |
| proposal_id | `@learning_update_proposals` | 否 | 提案 |
| independent_evaluation_ref | `@evaluation_runs` | 否 | 独立评估 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, old_id) REFERENCES adaptation_standard_versions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, new_id) REFERENCES adaptation_standard_versions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, proposal_id) REFERENCES learning_update_proposals(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, independent_evaluation_ref) REFERENCES evaluation_runs(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## identity_instances — 生命实例（身份自我）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| created_event_id | `@perception_signals` | 是 | 创建事件 |
| state | `e(active,suspended,ended,recovery)` | 否 | 状态 |
| generation | `i` | 否 | 世代 |
| controller_ref | `@social_actors` | 是 | 控制者 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, created_event_id) REFERENCES perception_signals(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, controller_ref) REFERENCES social_actors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
CHECK (id = instance_id)
```

## identity_lineage — 实例谱系（身份自我）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| parent_instance_id | `@identity_instances` | 否 | 父实例 |
| child_instance_id | `@identity_instances` | 否 | 子实例 |
| operation | `e(copy,fork,migrate,restore)` | 否 | 操作 |
| common_checkpoint_ref | `@checkpoints` | 是 | 共同恢复点 |
| event_id | `@perception_signals` | 否 | 事件 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (parent_instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (child_instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, common_checkpoint_ref) REFERENCES checkpoints(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, event_id) REFERENCES perception_signals(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## identity_anchors — 身份锚点（身份自我）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| version | `i` | 否 | 版本 |
| anchor_data | `j` | 否 | 锚点 |
| previous_id | `@identity_anchors` | 是 | 前版 |
| authority_ref | `@social_actors` | 否 | 授权者 |
| anchor_object_id | `@object_registry` | 否 | 跨版本稳定配置对象 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, previous_id) REFERENCES identity_anchors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, authority_ref) REFERENCES social_actors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, anchor_object_id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, version)
```

## identity_continuity_checks — 连续性检查（身份自我）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| checkpoint_ref | `@checkpoints` | 否 | 恢复点 |
| dimension | `e(instance,causal,functional,relational,narrative)` | 否 | 维度 |
| result | `e(pass,fail,unknown)` | 否 | 结果 |
| evidence_id | `@evidence_items` | 否 | 依据 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, checkpoint_ref) REFERENCES checkpoints(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## identity_continuity_incidents — 连续性损伤（身份自我）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| check_id | `@identity_continuity_checks` | 否 | 检查 |
| damage_type | `t` | 否 | 类型 |
| severity | `e(low,medium,high,critical)` | 否 | 严重度 |
| recovery_ref | `@maintenance_plans` | 是 | 恢复方案 |
| state | `e(open,recovering,resolved,irrecoverable)` | 否 | 状态 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, check_id) REFERENCES identity_continuity_checks(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, recovery_ref) REFERENCES maintenance_plans(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## self_capability_models — 能力自我模型（身份自我）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| capability | `@capability_definitions` | 否 | 能力 |
| conditions | `@rule_definitions` | 否 | 适用条件 |
| estimated_performance | `p` | 否 | 预期表现 |
| uncertainty_json | `j` | 否 | 不确定性 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, capability) REFERENCES capability_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, conditions) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## self_capability_evaluations — 自我模型校准（身份自我）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| model_id | `@self_capability_models` | 否 | 模型 |
| evaluation_run_id | `@evaluation_runs` | 否 | 实验 |
| actual_performance | `p` | 否 | 实际表现 |
| calibration | `n` | 否 | 校准误差 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, model_id) REFERENCES self_capability_models(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evaluation_run_id) REFERENCES evaluation_runs(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## self_narrative_versions — 自我叙事（身份自我）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| period | `t` | 否 | 历史范围 |
| summary | `t` | 否 | 叙述 |
| previous_id | `@self_narrative_versions` | 是 | 前版 |
| generator_version | `t` | 否 | 生成版本 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, previous_id) REFERENCES self_narrative_versions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## self_narrative_sources — 叙事来源（身份自我）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| narrative_id | `@self_narrative_versions` | 否 | 叙事 |
| memory_revision_id | `@memory_revisions` | 否 | 记忆 |
| evidence_id | `@evidence_items` | 否 | 依据 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, narrative_id) REFERENCES self_narrative_versions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, memory_revision_id) REFERENCES memory_revisions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, evidence_id) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## health_requirements — 健康要求（健康维护）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| capability_ref | `@capability_definitions` | 否 | 必要能力 |
| criticality | `e(low,medium,high,critical)` | 否 | 重要度 |
| acceptable_rule | `@rule_definitions` | 否 | 正常规则 |
| policy_version | `@policy_versions` | 否 | 策略 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, capability_ref) REFERENCES capability_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, acceptable_rule) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, policy_version) REFERENCES policy_versions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## health_check_definitions — 健康检查定义（健康维护）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| requirement_id | `@health_requirements` | 否 | 要求 |
| method_version | `t` | 否 | 检测方法 |
| schedule | `@rule_definitions` | 否 | 调度 |
| independence_class | `e(internal,external,independent)` | 否 | 独立程度 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, requirement_id) REFERENCES health_requirements(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, schedule) REFERENCES rule_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## health_observations — 健康观测（健康维护）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| check_id | `@health_check_definitions` | 否 | 检查 |
| source_revision_ref | `@object_revision_registry` | 否 | 底层版本 |
| result | `e(pass,fail,unknown)` | 否 | 结果 |
| observed_at | `t` | 否 | 时间 |
| expires_at | `t` | 否 | 失效 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, check_id) REFERENCES health_check_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, source_revision_ref) REFERENCES object_revision_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## health_assessments — 健康判断（健康维护）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| dimension | `t` | 否 | 维度 |
| state | `e(healthy,stressed,degraded,critical,recovering,unknown)` | 否 | 健康状态 |
| evidence_start | `t` | 否 | 窗口开始 |
| evidence_end | `t` | 否 | 窗口结束 |
| method_version | `t` | 否 | 方法 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
CHECK (evidence_start <= evidence_end)
```

## health_incidents — 健康事件（健康维护）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| requirement_id | `@health_requirements` | 否 | 要求 |
| severity | `e(low,medium,high,critical)` | 否 | 严重度 |
| state | `e(open,contained,recovering,resolved)` | 否 | 状态 |
| detected_at | `t` | 否 | 发现时间 |
| impact_description | `t` | 否 | 影响 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, requirement_id) REFERENCES health_requirements(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## health_capability_impacts — 受损能力（健康维护）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| incident_id | `@health_incidents` | 否 | 事件 |
| capability_ref | `@capability_definitions` | 否 | 能力 |
| availability | `p` | 否 | 可用程度 |
| restriction | `t` | 否 | 限制 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, incident_id) REFERENCES health_incidents(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, capability_ref) REFERENCES capability_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## maintenance_plans — 维护方案（健康维护）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| incident_id | `@health_incidents` | 否 | 事件 |
| strategy | `e(repair,isolate,degrade,rollback,help,stop)` | 否 | 策略 |
| grant_ref | `@grants` | 是 | 授权 |
| expected_recovery | `t` | 否 | 恢复目标 |
| state | `e(proposed,approved,running,completed,failed)` | 否 | 状态 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, incident_id) REFERENCES health_incidents(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, grant_ref) REFERENCES grants(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## maintenance_attempts — 维护尝试（健康维护）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| plan_id | `@maintenance_plans` | 否 | 方案 |
| action_intent_id | `@action_intents` | 否 | 动作 |
| started_at | `t` | 否 | 开始 |
| result_ref | `@action_results` | 是 | 结果 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, plan_id) REFERENCES maintenance_plans(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, action_intent_id) REFERENCES action_intents(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, result_ref) REFERENCES action_results(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## maintenance_verifications — 维护核验（健康维护）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| attempt_id | `@maintenance_attempts` | 否 | 尝试 |
| check_id | `@health_check_definitions` | 否 | 核验方法 |
| result | `e(pass,fail,unknown)` | 否 | 结果 |
| residual_damage | `t` | 否 | 剩余损伤 |
| verifier_ref | `@social_actors` | 否 | 验证者 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, attempt_id) REFERENCES maintenance_attempts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, check_id) REFERENCES health_check_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, verifier_ref) REFERENCES social_actors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## grants — 授权版本（运行权限实验）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| subject | `@social_actors` | 否 | 主体 |
| capability | `@capability_definitions` | 否 | 能力 |
| resource_scope | `j` | 否 | 资源范围 |
| expiry | `t` | 是 | 到期 |
| revoked_at | `t` | 是 | 撤销 |
| version | `i` | 否 | 版本 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, subject) REFERENCES social_actors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, capability) REFERENCES capability_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## grant_changes — 授权变化（运行权限实验）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| grant_id | `@grants` | 否 | 授权 |
| event_id | `@perception_signals` | 否 | 事件 |
| operation | `e(grant,revoke,expire)` | 否 | 动作 |
| authority_ref | `@social_actors` | 否 | 授权者 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, grant_id) REFERENCES grants(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, event_id) REFERENCES perception_signals(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, authority_ref) REFERENCES social_actors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## policy_versions — 边界策略（运行权限实验）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| version | `i` | 否 | 版本 |
| mode | `e(authorization,open)` | 否 | 模式 |
| scope | `j` | 否 | 范围 |
| effective_at | `t` | 否 | 生效 |
| authority | `@social_actors` | 否 | 制定者 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, authority) REFERENCES social_actors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, version)
```

## approval_requests — 授权请求（运行权限实验）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| action_ref | `@action_intents` | 否 | 动作 |
| requested_scope | `j` | 否 | 范围 |
| decision | `e(pending,approved,rejected,expired)` | 否 | 决定 |
| decision_event_id | `@perception_signals` | 是 | 确认事件 |
| proposal_revision | `i0` | 否 | 提案修订 |
| arguments_hash | `t` | 否 | 参数摘要 |
| tool_id | `@tool_definitions` | 否 | 工具 |
| required_capability_id | `@capability_definitions` | 否 | 能力 |
| expires_at | `t` | 否 | 到期 |
| requested_by | `@social_actors` | 否 | 请求方 |
| decision_by | `@social_actors` | 是 | 决定方 |
| revision | `i0` | 否 | 修订 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, action_ref) REFERENCES action_intents(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, decision_event_id) REFERENCES perception_signals(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, tool_id) REFERENCES tool_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, required_capability_id) REFERENCES capability_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, requested_by) REFERENCES social_actors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, decision_by) REFERENCES social_actors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## jobs — 持久任务（运行权限实验）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| kind | `t` | 否 | 类型 |
| target_ref | `@object_registry` | 否 | 对象 |
| due_at | `t` | 否 | 到期 |
| state | `e(queued,leased,waiting,succeeded,failed,cancelled)` | 否 | 状态 |
| lease_owner | `t` | 是 | 租约拥有者 |
| lease_expiry | `t` | 是 | 租约到期 |
| attempt | `i` | 否 | 尝试次数 |
| lease_token | `t` | 是 | 令牌 |
| lease_generation | `i0` | 否 | 代次 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, target_ref) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
CHECK ((state='leased' AND lease_owner IS NOT NULL AND lease_expiry IS NOT NULL) OR (state<>'leased' AND lease_owner IS NULL AND lease_expiry IS NULL))
```

## outbox — 动作投递（运行权限实验）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| intent_id | `@action_intents` | 否 | 动作 |
| dispatch_state | `e(pending,leased,sent,unknown,completed,cancelled)` | 否 | 状态 |
| next_attempt_at | `t` | 否 | 下次时间 |
| authorization_record_id | `@action_authorization_records` | 是 | 授权 |
| lease_owner | `t` | 是 | 拥有者 |
| lease_token | `t` | 是 | 令牌 |
| lease_generation | `i0` | 否 | 代次 |
| lease_expires_at | `t` | 是 | 到期 |
| attempt_count | `i0` | 否 | 次数 |
| last_error | `t` | 是 | 错误 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, intent_id) REFERENCES action_intents(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, authorization_record_id) REFERENCES action_authorization_records(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, intent_id)
```

## checkpoints — 恢复点（运行权限实验）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| activity_id | `@activities` | 否 | 活动 |
| state_version | `i` | 否 | 状态版本 |
| schema_version | `i` | 否 | 结构版本 |
| release_id | `t` | 否 | 部署 |
| snapshot_ref | `@artifacts` | 否 | 快照 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, snapshot_ref) REFERENCES artifacts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## evaluation_runs — 实验（运行权限实验）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| dataset_version | `t` | 否 | 数据集 |
| baseline_ref | `@evaluation_runs` | 是 | 基线 |
| model_version | `@model_versions` | 否 | 模型 |
| seed | `i` | 是 | 种子 |
| conditions | `j` | 否 | 条件 |
| state | `e(planned,running,completed,failed)` | 否 | 状态 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, baseline_ref) REFERENCES evaluation_runs(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, model_version) REFERENCES model_versions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## metric_definitions — 指标字典（运行权限实验）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| name | `t` | 否 | 名称 |
| formula_version | `t` | 否 | 公式 |
| unit | `t` | 否 | 单位 |
| denominator_rule | `t` | 否 | 分母规则 |
| missing_rule | `t` | 否 | 缺失规则 |
| stratification | `j` | 否 | 分层 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, name, formula_version)
```

## metric_samples — 指标样本（运行权限实验）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| run_id | `@evaluation_runs` | 否 | 实验 |
| definition_id | `@metric_definitions` | 否 | 指标 |
| source_ref | `@object_registry` | 否 | 样本来源 |
| numerator | `r` | 是 | 分子 |
| denominator | `n` | 是 | 分母 |
| value | `r` | 是 | 指标值 |
| uncertainty | `j` | 否 | 不确定性 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, run_id) REFERENCES evaluation_runs(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, definition_id) REFERENCES metric_definitions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, source_ref) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
CHECK (denominator IS NULL OR denominator <> 0 OR value IS NULL)
```

## model_versions — 模型版本（运行权限实验）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| version | `t` | 否 | 版本 |
| artifact_ref | `@artifacts` | 否 | 材料 |
| hash | `t` | 否 | 摘要 |
| compatibility | `j` | 否 | 兼容条件 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, artifact_ref) REFERENCES artifacts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## configuration_versions — 配置版本（运行权限实验）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| version | `t` | 否 | 版本 |
| artifact_ref | `@artifacts` | 否 | 材料 |
| hash | `t` | 否 | 摘要 |
| compatibility | `j` | 否 | 兼容条件 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, artifact_ref) REFERENCES artifacts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## schema_migrations — 结构迁移（运行权限实验）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| version | `i` | 否 | 版本 |
| checksum | `t` | 否 | 摘要 |
| applied_at | `t` | 否 | 执行时间 |
| release_id | `t` | 否 | 部署 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, version)
```

## deletion_requests — 删除请求（运行权限实验）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| subject_scope | `j` | 否 | 范围 |
| requested_at | `t` | 否 | 请求时间 |
| authority_ref | `@social_actors` | 否 | 请求者 |
| state | `e(requested,blocked,cleaning,verified,failed)` | 否 | 状态 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, authority_ref) REFERENCES social_actors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## deletion_effects — 删除传播（运行权限实验）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| request_id | `@deletion_requests` | 否 | 请求 |
| object_ref | `@object_registry` | 是 | 对象 |
| artifact_ref | `@artifacts` | 是 | 材料 |
| operation | `t` | 否 | 操作 |
| result | `e(pending,done,failed)` | 否 | 结果 |
| verified_at | `t` | 是 | 验证时间 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, request_id) REFERENCES deletion_requests(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, object_ref) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, artifact_ref) REFERENCES artifacts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
CHECK (object_ref IS NOT NULL OR artifact_ref IS NOT NULL)
```

## thought_requests — 独立思考请求（独立思考与运行）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| activity_id | `@activities` | 否 | 活动 |
| step_id | `@activity_steps` | 否 | 步骤 |
| request_key | `t` | 否 | 幂等键 |
| purpose | `e(infer,plan,evaluate,verify,reflect)` | 否 | 用途 |
| task | `t` | 否 | 任务 |
| instruction_version | `t` | 否 | 指令版本 |
| output_schema_version | `i` | 否 | 响应版本 |
| request_artifact_id | `@artifacts` | 否 | 完整请求 |
| request_hash | `t` | 否 | 请求摘要 |
| input_manifest_hash | `t` | 否 | 输入摘要 |
| model_config_id | `@configuration_versions` | 否 | 模型配置 |
| model_version_id | `@model_versions` | 否 | 模型 |
| prepared_activity_revision | `i` | 否 | 构造版本 |
| expected_input_epoch | `i` | 否 | 输入代次 |
| expected_policy_epoch | `i` | 否 | 权限代次 |
| runtime_epoch | `i` | 否 | 进程世代 |
| process_run_id | `t` | 否 | 控制进程标识 |
| deadline | `t` | 否 | 期限 |
| token_budget | `i` | 否 | 预算 |
| attempt_limit | `i` | 否 | 次数 |
| retry_policy | `j` | 否 | 重试 |
| generation_config | `j` | 否 | 采样 |
| state | `e(prepared,running,succeeded,failed,cancelled,superseded)` | 否 | 状态 |
| accepted_result_id | `@thought_results` | 是 | 接受结果 |
| state_revision | `i0` | 否 | 修订 |
| request_parent_id | `@thought_requests` | 是 | 父请求 |
| supersedes_request_id | `@thought_requests` | 是 | 替代请求 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, step_id) REFERENCES activity_steps(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, request_artifact_id) REFERENCES artifacts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, model_config_id) REFERENCES configuration_versions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, model_version_id) REFERENCES model_versions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, accepted_result_id) REFERENCES thought_results(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, request_parent_id) REFERENCES thought_requests(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, supersedes_request_id) REFERENCES thought_requests(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, request_key)
CHECK ((state='succeeded' AND accepted_result_id IS NOT NULL) OR (state<>'succeeded' AND accepted_result_id IS NULL))
```

## thought_request_inputs — 思考输入清单（独立思考与运行）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| request_id | `@thought_requests` | 否 | 请求 |
| ordinal | `i` | 否 | 顺序 |
| role | `t` | 否 | 角色 |
| object_revision_id | `@object_revision_registry` | 是 | 对象版本 |
| object_id | `@object_registry` | 是 | 不可变对象 |
| artifact_id | `@artifacts` | 是 | 临时工件 |
| content_hash | `t` | 否 | 摘要 |
| locator | `j` | 否 | 定位 |
| selection_reason | `t` | 否 | 选择原因 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, request_id) REFERENCES thought_requests(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, object_revision_id) REFERENCES object_revision_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, object_id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, artifact_id) REFERENCES artifacts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, request_id, ordinal)
CHECK ((object_revision_id IS NOT NULL)+(object_id IS NOT NULL)+(artifact_id IS NOT NULL)=1)
```

## thought_attempts — 模型调用尝试（独立思考与运行）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| request_id | `@thought_requests` | 否 | 请求 |
| attempt_no | `i` | 否 | 次数 |
| state | `e(queued,sent,received,timeout,failed,cancelled)` | 否 | 状态 |
| queued_at | `t` | 否 | 入队 |
| sent_at | `t` | 是 | 发送 |
| finished_at | `t` | 是 | 完成 |
| provider_request_id | `t` | 是 | 远端标识 |
| error_code | `t` | 是 | 错误 |
| usage_json | `j` | 是 | 用量 |
| dispatch_token | `t` | 否 | 发送标识 |
| provider | `t` | 否 | 提供方 |
| model | `t` | 否 | 实际模型 |
| runtime_epoch | `i` | 否 | 世代 |
| process_run_id | `t` | 否 | 进程标识 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, request_id) REFERENCES thought_requests(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, request_id, attempt_no)
UNIQUE (instance_id, dispatch_token)
```

## thought_results — 模型响应（独立思考与运行）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| request_id | `@thought_requests` | 否 | 请求 |
| attempt_id | `@thought_attempts` | 否 | 尝试 |
| response_artifact_id | `@artifacts` | 否 | 原始响应 |
| response_hash | `t` | 否 | 摘要 |
| received_at | `t` | 否 | 接收 |
| parsed_artifact_id | `@artifacts` | 是 | 解析结果 |
| validation_errors | `j` | 否 | 错误 |
| validation_state | `e(valid,invalid,pending)` | 否 | 校验 |
| acceptance | `e(pending,accepted,stale,duplicate,rejected)` | 否 | 接受状态 |
| reason_code | `t` | 是 | 原因 |
| accepted_at | `t` | 是 | 接受时间 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, request_id) REFERENCES thought_requests(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, attempt_id) REFERENCES thought_attempts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, response_artifact_id) REFERENCES artifacts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, parsed_artifact_id) REFERENCES artifacts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## thought_state_events — 思考状态历史（独立思考与运行）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| request_id | `@thought_requests` | 否 | 请求 |
| transition_no | `i` | 否 | 序号 |
| from_state | `t` | 否 | 旧状态 |
| to_state | `t` | 否 | 新状态 |
| reason_code | `t` | 否 | 原因 |
| result_id | `@thought_results` | 是 | 结果 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, request_id) REFERENCES thought_requests(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, result_id) REFERENCES thought_results(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## activity_state_events — 活动状态历史（独立思考与运行）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| activity_id | `@activities` | 否 | 活动 |
| transition_no | `i` | 否 | 序号 |
| from_state | `t` | 否 | 旧状态 |
| to_state | `t` | 否 | 新状态 |
| cause_event_id | `@runtime_events` | 否 | 事件 |
| expected_revision | `i` | 否 | 修订 |
| reason_code | `t` | 否 | 原因 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, cause_event_id) REFERENCES runtime_events(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## activity_budget_accounts — 预算账户（独立思考与运行）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| activity_id | `@activities` | 否 | 活动 |
| revision | `i0` | 否 | 修订 |
| token_limit | `i` | 否 | token额度 |
| tool_call_limit | `i` | 否 | 工具额度 |
| attempt_limit | `i` | 否 | 尝试额度 |
| time_limit_ms | `i` | 否 | 时间额度 |
| cost_limit_minor | `i` | 是 | 成本额度 |
| currency | `t` | 是 | 币种 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, activity_id)
```

## budget_reservations — 预算预留（独立思考与运行）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| activity_id | `@activities` | 否 | 活动 |
| operation_ref | `@object_registry` | 否 | 操作 |
| operation_kind | `e(thought_attempt,tool_attempt)` | 否 | 类型 |
| reservation_key | `t` | 否 | 幂等键 |
| reserved_tokens | `i` | 否 | token |
| reserved_tool_calls | `i` | 否 | 工具次数 |
| reserved_attempts | `i` | 否 | 尝试次数 |
| reserved_cost_minor | `i` | 是 | 成本 |
| state | `e(reserved,settled,released,usage_unknown)` | 否 | 状态 |
| actual_usage | `j` | 是 | 实测 |
| reserved_at | `t` | 否 | 预留 |
| settled_at | `t` | 是 | 结算 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, operation_ref) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, activity_id, reservation_key)
```

## action_authorization_records — 动作授权快照（独立思考与运行）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| intent_id | `@action_intents` | 否 | 动作 |
| grant_id | `@grants` | 否 | 授权 |
| approval_request_id | `@approval_requests` | 是 | 批准 |
| proposal_revision | `i` | 否 | 提案修订 |
| arguments_hash | `t` | 否 | 参数摘要 |
| scope_snapshot | `j` | 否 | 范围 |
| policy_epoch | `i` | 否 | 权限世代 |
| issued_at | `t` | 否 | 签发 |
| expires_at | `t` | 否 | 到期 |
| revoked_at | `t` | 是 | 撤销 |
| state | `e(valid,revoked,expired,consumed)` | 否 | 状态 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, intent_id) REFERENCES action_intents(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, grant_id) REFERENCES grants(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, approval_request_id) REFERENCES approval_requests(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## action_state_events — 动作状态历史（独立思考与运行）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| intent_id | `@action_intents` | 否 | 动作 |
| transition_no | `i` | 否 | 序号 |
| from_state | `t` | 否 | 旧状态 |
| to_state | `t` | 否 | 新状态 |
| cause_event_id | `@runtime_events` | 否 | 事件 |
| attempt_id | `@action_attempts` | 是 | 尝试 |
| reason_code | `t` | 否 | 原因 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, intent_id) REFERENCES action_intents(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, cause_event_id) REFERENCES runtime_events(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, attempt_id) REFERENCES action_attempts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## policy_epochs — 权限代次（独立思考与运行）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| epoch | `i` | 否 | 代次 |
| policy_version_id | `@policy_versions` | 否 | 策略 |
| last_change_event_id | `@runtime_events` | 是 | 事件 |
| updated_at | `t` | 否 | 时间 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, policy_version_id) REFERENCES policy_versions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, last_change_event_id) REFERENCES runtime_events(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## runtime_events — 持久事件信封（独立思考与运行）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| event_seq | `i` | 否 | 序号 |
| event_type | `t` | 否 | 类型 |
| source | `t` | 否 | 来源 |
| source_event_id | `t` | 否 | 来源标识 |
| correlation_id | `t` | 否 | 关联 |
| causation_event_id | `@runtime_events` | 是 | 起因 |
| activity_id | `@activities` | 是 | 活动 |
| lane | `e(control,result,work,telemetry)` | 否 | 通道 |
| payload_object_id | `@object_registry` | 是 | 对象 |
| payload_artifact_id | `@artifacts` | 是 | 工件 |
| payload_hash | `t` | 否 | 摘要 |
| received_at | `t` | 否 | 接收 |
| authority_ref | `@social_actors` | 是 | 主体 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, causation_event_id) REFERENCES runtime_events(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, activity_id) REFERENCES activities(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, payload_object_id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, payload_artifact_id) REFERENCES artifacts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, authority_ref) REFERENCES social_actors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, event_seq)
UNIQUE (instance_id, source, source_event_id)
CHECK ((payload_object_id IS NOT NULL)+(payload_artifact_id IS NOT NULL)=1)
```

## consumer_receipts — 消费确认（独立思考与运行）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| consumer_name | `t` | 否 | 消费者 |
| consumer_version | `t` | 否 | 版本 |
| event_id | `@runtime_events` | 否 | 事件 |
| state | `e(pending,processing,processed,dead_letter)` | 否 | 状态 |
| attempt_count | `i0` | 否 | 次数 |
| lease_owner | `t` | 是 | 拥有者 |
| lease_token | `t` | 是 | 令牌 |
| lease_generation | `i0` | 否 | 代次 |
| lease_expires_at | `t` | 是 | 到期 |
| last_error | `t` | 是 | 错误 |
| processed_at | `t` | 是 | 完成 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, event_id) REFERENCES runtime_events(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, consumer_name, consumer_version, event_id)
```

## consumer_offsets — 消费游标（独立思考与运行）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| consumer_name | `t` | 否 | 消费者 |
| consumer_version | `t` | 否 | 版本 |
| lane | `t` | 否 | 通道 |
| last_event_seq | `i` | 否 | 序号 |
| updated_at | `t` | 否 | 时间 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, consumer_name, consumer_version, lane)
```

## supervisor_commands — 控制面命令（独立思考与运行）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| command_key | `t` | 否 | 幂等键 |
| kind | `e(set_wake,clear_wake,request_maintenance,request_deploy)` | 否 | 种类 |
| schedule_generation | `i` | 是 | 计划代次 |
| payload | `j` | 否 | 载荷 |
| payload_hash | `t` | 否 | 摘要 |
| state | `e(pending,sent,acknowledged,rejected)` | 否 | 状态 |
| attempt_count | `i0` | 否 | 次数 |
| next_attempt_at | `t` | 否 | 时间 |
| ack_control_command_id | `t` | 是 | 确认标识 |
| acknowledged_at | `t` | 是 | 确认 |
| last_error | `t` | 是 | 错误 |
| runtime_epoch | `i` | 否 | 世代 |
| process_run_id | `t` | 否 | 进程 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, command_key)
```

## instance_wake_state — 唤醒交接状态（独立思考与运行）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| desired_generation | `i` | 否 | 期望代次 |
| acknowledged_generation | `i` | 否 | 确认代次 |
| desired_due_at | `t` | 是 | 期望时间 |
| acknowledged_due_at | `t` | 是 | 确认时间 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## initialization_runs — 初始化运行（独立思考与运行）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| bootstrap_key | `t` | 否 | 幂等键 |
| schema_migration_version | `i` | 否 | 模式 |
| configuration_id | `@configuration_versions` | 否 | 配置 |
| phase | `t` | 否 | 阶段 |
| state | `e(started,committed,failed)` | 否 | 状态 |
| error_code | `t` | 是 | 错误 |
| completed_at | `t` | 是 | 完成 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, configuration_id) REFERENCES configuration_versions(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, bootstrap_key)
```

## object_publications — 对象发布（独立思考与运行）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| object_id | `@object_registry` | 否 | 对象 |
| state | `e(constructing,ready,quarantined,redacted)` | 否 | 状态 |
| current_revision_id | `@object_revision_registry` | 是 | 发布版本 |
| owner_module | `t` | 否 | 所有者 |
| validation_schema | `t` | 否 | 校验版本 |
| published_at | `t` | 是 | 时间 |
| revision | `i0` | 否 | 修订 |
| reason_ref | `@evidence_items` | 是 | 依据 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, object_id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, current_revision_id) REFERENCES object_revision_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, reason_ref) REFERENCES evidence_items(instance_id, id) DEFERRABLE INITIALLY DEFERRED
UNIQUE (instance_id, object_id)
```

## import_runs — 恢复导入（独立思考与运行）

| 字段 | 类型／取值与约束 | 可空 | 含义 |
| --- | --- | --- | --- |
| id | TEXT PRIMARY KEY | 否 | 稳定行标识 |
| instance_id | TEXT → identity_instances.id | 否 | 数据所属生命实例 |
| recorded_at | TEXT；默认 UTC 入库时间 | 否 | 入库时间；不代替发生时间 |
| schema_version | INTEGER；默认1，>=1 | 否 | 本行扩展结构版本；不代替迁移号 |
| valid_from | TEXT；UTC | 是 | 业务有效开始 |
| valid_to | TEXT；不得早于开始 | 是 | 业务有效结束 |
| source_artifact_id | `@artifacts` | 否 | 来源 |
| authority_ref | `@social_actors` | 否 | 授权 |
| mode | `e(restore,import)` | 否 | 方式 |
| continuity_incident_id | `@identity_continuity_incidents` | 是 | 损伤 |
| state | `e(started,committed,failed)` | 否 | 状态 |
| started_at | `t` | 否 | 开始 |
| completed_at | `t` | 是 | 完成 |

表级约束：

```sql
CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_from <= valid_to))
UNIQUE (instance_id, id)
FOREIGN KEY (instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, id) REFERENCES object_registry(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, source_artifact_id) REFERENCES artifacts(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, authority_ref) REFERENCES social_actors(instance_id, id) DEFERRABLE INITIALLY DEFERRED
FOREIGN KEY (instance_id, continuity_incident_id) REFERENCES identity_continuity_incidents(instance_id, id) DEFERRABLE INITIALLY DEFERRED
```

## memory_search — 派生全文索引

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| rowid | INTEGER | memory_revisions.rowid；关联内容行 |
| content | FTS5 TEXT | 可检索的记忆修订内容 |
| memory_id | UNINDEXED TEXT | 记忆标识 |
| instance_id | UNINDEXED TEXT | 生命实例 |

FTS5 外部内容表由触发器同步，可重建。查询必须 JOIN 当前有效记忆并核验权限；FTS 不负责授权。unicode61 不保证中文语义召回。SQLite 自动生成的 FTS 内部影子表不是业务接口。

