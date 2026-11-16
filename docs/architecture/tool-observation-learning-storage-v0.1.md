# TL-LOOP-0.1 字段与存储映射附录

版本V0.1，2026-11-09。规范依附[首版契约](tool-observation-learning-contract-v0.1.md)。下列为未来SQLite STRICT表设计，**不是建表SQL或已创建数据库**。冻结状态以freeze记录为准。

## 1 通用列及约束

新表默认都有 `id TEXT PK`（新UUID32）、`instance_id TEXT NOT NULL`（FK identity_instances）、`recorded_at TEXT NOT NULL`（UTC毫秒）、`schema_revision INTEGER NOT NULL=1`、`UNIQUE(instance_id,id)`。除显式nullable列外均NOT NULL；TEXT的enum只能取本附录/主契约列举值；JSON列必须json_valid并经契约结构验证。row_revision及代次从0开始、CAS每次加1。bool列INTEGER CHECK 0/1，所有计数非负；业务字段的unknown用Slot JSON而非SQL NULL。SQL NULL仅用于明确不存在的技术关联，不能表示未知事实。

所有本实例外键采用 `(instance_id,ref_id)` 复合约束、DEFERRABLE INITIALLY DEFERRED。新对象同步注册object_registry；原始来源为已有对象时复用既有注册引用，跨实例外部来源只保存已授权的类型化Ref工件，不伪造本实例FK。父对象不可级联删业务历史；删除由明确授权计划逐目标执行并留允许的墓碑，不保存秘密正文/hash。新的内容关系/状态字段由对应所有者的服务入口修改，不授予通用Store额外业务权。

`*_artifact_id` FK既有artifacts；工件须先有可校验字节才能被主库引用。数据字典中的body_json与artifact不得双重当权威：大正文用artifact，行保存结构化索引/身份/摘要；契约完整载荷的工件是不可变序列化原件，当前状态取权威行和屏障。工件与行不一致报SOURCE_INVALID/STORAGE_FAILED，不挑一份方便的继续。

## 2 原对象复用

| 既有对象 | 复用字段/作用 | 不适用之处 |
| --- | --- | --- |
| activities、context_snapshots | 学习工作独立的受授权活动、上下文及停止/期限关联；source_activity另指原观察活动 | 不改原活动ID重做工具；新学习活动不增加独立来源 |
| activity_budget_accounts、budget_reservations、thought_requests/results/attempts | 每逻辑工作唯一活动预算账户；实际模型尝试/独立请求和实际用量，重试共享账户 | 预算预留不是实际派发或实际消费；原预算截止不能因重新提交延长 |
| action_results、action_attempts、evidence_items、artifacts | 原回执、真实执行结果和字节/视图引用 | 不把结果ID字符串当学到的正文 |
| runtime_events、object_registry、object_revision_registry | 不可变阶段事件、全链对象引用及可查版本 | 事件存在不替代当前head/资格/交接状态 |
| memory_items/revisions及检索/访问记录 | 保留原文字/经历；必要时建立到新表示的映射和检索记录 | 不借Memory.revise改变M03内容；不从旧memory类别推测新经验接纳 |
| policy/authorization、恢复/删除/备份对象 | 原控制权、作用范围、恢复锁及明确受管副本 | 现有局部删除done不代替跨表/文件/索引验证；source_updates是代码发布，不是本链来源更正 |

## 3 新表精确字段

通用列不重复。JSON字段的类型是首版契约中对应命名类型，不是任意对象。外键表名省略tl_前缀仅为可读；本节所有业务表正式设计名都带tl_。

| 表/唯一写者 | 其他列及类型 | 唯一键、外键与索引 |
| --- | --- | --- |
| tl_command / 操作接收所有者 | operation TEXT、idempotency_key TEXT、fingerprint TEXT[64]、principal_artifact_id、work_id TEXT nullable、result_artifact_id nullable、state TEXT pending/committed/failed、row_revision INTEGER | UNIQUE(instance,operation,idempotency_key)；work→tl_work；result→artifacts；按work索引。业务提交与result/committed一起落盘；未知外部提交不凭pending盲重试 |
| tl_work / M14及协调器 | learning_activity_id TEXT、source_activity_id TEXT、source_artifact_id TEXT、purpose TEXT、processing_identity TEXT[64]、state TEXT、phase TEXT admit/assess/decide/represent/complete、review_round INTEGER、conditions_artifact_id TEXT、control_artifact_id TEXT、method_artifact_id TEXT、deadline TEXT、budget_account_id TEXT、row_revision INTEGER | learning_activity→activities唯一；source_activity→activities；budget_account→activity_budget_accounts唯一；UNIQUE(instance,processing_identity)；索引(state,deadline)。phase/状态组合按主契约，completed等终态phase=complete |
| tl_product / M14 | work_id TEXT、product_type TEXT、payload_artifact_id TEXT、processing_identity TEXT[64]、supersedes_id TEXT nullable、source_fingerprint TEXT[64] | work→tl_work、supersedes→本表；UNIQUE(instance,work,product_type,processing_identity)。四类Product精确载荷在payload，来源/Scope/Slot不能仅留自由文本 |
| tl_content / M03 | content_kind TEXT、head_revision_id TEXT nullable、row_revision INTEGER | head→tl_content_revision；索引(kind)。对象ID不因新版本变化；head只能指同content的修订；事务延迟FK允许初始分配 |
| tl_content_revision / M03 | content_id TEXT、revision_no INTEGER≥1、decision_id TEXT、product_id TEXT、payload_artifact_id TEXT、status TEXT candidate/accepted、previous_revision_id TEXT nullable | content→tl_content；decision→tl_decision；product→tl_product；previous→本表且同content；UNIQUE(instance,content,revision_no)；索引decision/product。新修订只追加，当前使用限制在屏障而非回写旧payload |
| tl_decision / M03 | work_id TEXT、proposal_id TEXT、review_round INTEGER、decision_artifact_id TEXT、operation TEXT、content_revision_id TEXT nullable、policy_ref_id TEXT、created_at TEXT | proposal→tl_product且必须UpdateProposal；content_revision→tl_content_revision；policy→object_registry；UNIQUE(instance,proposal,review_round)。defer/reject无新修订，reuse可引用原修订；candidate不可创建当前表示义务 |
| tl_group / M03创建、M04就绪 | group_key TEXT、members_artifact_id TEXT、state TEXT pending/ready/obsolete、row_revision INTEGER | UNIQUE(instance,group_key)；成员工件列固定内容版本及必需表示需求，发布时不能悄加成员；索引state |
| tl_handoff / M03创建、M04领取/完成 | work_id TEXT、content_revision_id TEXT、decision_id TEXT、group_id TEXT nullable、format_version TEXT、input_fingerprint TEXT[64]、state TEXT、lease_worker_id TEXT nullable、lease_generation INTEGER、lease_expires_at TEXT nullable、attempts INTEGER、deadline TEXT、budget_account_id TEXT、representation_id TEXT nullable、receipt_artifact_id TEXT nullable、row_revision INTEGER | 引用work/revision/decision/group及budget；worker→object_registry；representation→tl_representation；UNIQUE(instance,content_revision,format_version,input_fingerprint)；索引(state,lease_expires_at,deadline)。无租约时worker/expiry NULL；published必须representation及receipt非NULL |
| tl_representation / M04 | series_id TEXT、content_revision_id TEXT、decision_id TEXT、format_version TEXT、representation_no INTEGER≥1、payload_artifact_id TEXT、body_artifact_id TEXT、body_digest TEXT[64]、group_id TEXT nullable、state TEXT ready/superseded/withdrawn | FKseries→tl_representation_head及revision/decision/group；UNIQUE(instance,series,representation_no)；state维护不改变不可变payload；body_digest仅内部合法完整性用途，删除范围涵盖则清除 |
| tl_representation_head / M04 | content_id TEXT、format_version TEXT、representation_id TEXT、expected_content_revision_id TEXT、row_revision INTEGER | UNIQUE(instance,content,format_version)；均复合FK；head表示必须指向相同content的指定修订。映射不是M03内容head |
| tl_dependency / 登记消费者与原所有者核对 | consumer_ref_id TEXT、source_ref_id TEXT、source_revision_id TEXT nullable、relation TEXT、purpose TEXT、expected_epoch INTEGER、field_path TEXT、metadata_artifact_id TEXT | consumer/source→object_registry，修订→object_revision_registry；UNIQUE(instance,consumer,source,relation,purpose,field_path,expected_epoch)；SQL不靠nullable字段作唯一关键。索引(source,relation)、consumer；读/支持/删除关系分开 |
| tl_source_epoch / 变更权威域+M12 | source_ref_id TEXT、scope_key TEXT[64]、scope_artifact_id TEXT、epoch INTEGER、row_revision INTEGER | UNIQUE(instance,source,scope_key)；source→object_registry，scope_artifact_id→artifacts。scope_key对应不可变授权范围工件，变化范围不能靠改hash脱离既有屏障 |
| tl_barrier / 变更权威域+M12 | change_id TEXT、source_ref_id TEXT、source_epoch INTEGER、kind TEXT、scope_artifact_id TEXT、authorization_ref_id TEXT、state TEXT active/resolved、resolution_artifact_id TEXT nullable、row_revision INTEGER | change_id→tl_change；UNIQUE(instance,change_id)；source→registry、authorization→registry；索引(source,state,source_epoch)。仅同原因明确解除才填resolution并resolve |
| tl_change / 合法源生产者+M12 | change_key TEXT、fingerprint TEXT[64]、payload_artifact_id TEXT、kind TEXT、source_ref_id TEXT、expected_epoch INTEGER、result_epoch INTEGER | UNIQUE(instance,change_key)，同键异指纹拒绝；source→registry；result_epoch=expected_epoch+1，仅F1内写入 |
| tl_propagation / 各目标业务所有者 | barrier_id TEXT、domain TEXT、targets_artifact_id TEXT、coverage_artifact_id TEXT、state TEXT、generation INTEGER、verification_artifact_id TEXT nullable、deadline TEXT、budget_account_id TEXT、row_revision INTEGER | barrier→tl_barrier；UNIQUE(instance,barrier,domain,generation)；索引(state,deadline)。verified须验证非NULL、complete覆盖、未决目标零；生成新代次不清旧屏障 |
| tl_erasure_target / M12计划、对象所有者执行 | barrier_id TEXT、plan_ref_id TEXT、target_ref_id TEXT、location_kind TEXT database/blob/index/cache/managed_backup/remote、state TEXT pending/removed/verified/blocked/unknown、verification_artifact_id TEXT nullable、row_revision INTEGER | barrier→tl_barrier、plan/target→registry；UNIQUE(instance,barrier,target,location_kind)；remote无独立确认只能unknown；verified必须合法验证，不能靠本地没搜到 |
| tl_input_dependency / 请求装配者登记、M12/M03/M04核对 | request_ref_id TEXT、source_ref_id TEXT、source_epoch INTEGER、source_revision_ref_id TEXT nullable、field_path TEXT、purpose TEXT、recipient_ref_id TEXT、body_digest TEXT nullable、retention_state TEXT allowed/blocked/erase_pending/erased、row_revision INTEGER | request/source/recipient→registry，修订→object_revision_registry；UNIQUE(instance,request,source,field_path,purpose,recipient)；索引(source,retention_state)。body_digest在删除涵盖时清除，禁止把它当无敏感的永久墓碑 |
| tl_effect / M14 | work_id TEXT、product_id TEXT、measurement_ref_id TEXT nullable、metric_contract TEXT、state TEXT not_measured/incomplete/measured/invalidated/not_applicable、payload_artifact_id TEXT | product→tl_product且EffectAssessment；measurement→registry；UNIQUE(instance,product)。measured必须真实合格measurement、known数值及相应证据；不更新内容头/表示头 |
| tl_recall_item / M04 | retrieval_run_id TEXT、rank INTEGER≥0、kind TEXT、target_ref_id TEXT、payload_artifact_id TEXT、origin_result_id TEXT nullable、control_artifact_id TEXT | run→memory_retrieval_runs，target→object_registry（类型须对应memory_revision或tl_representation），origin_result→memory_retrieval_results；UNIQUE(instance,run,rank)、UNIQUE(instance,run,target)。payload为完整RecallItem，非新认知接纳；按target/run索引，派生依赖必须登记 |

所有source/target引用先验证对象类型与实际业务归属，注册表FK只验证存在性，不授予写权。decision/content_revision的循环关联在C1同事务满足；group成员与每个handoff一致，整组检查不能只靠一个任意JSON ready值。

C0的工作+独立学习activity+budget账户+幂等结果同事务创建；source_activity不一定仍在运行，但必须保留授权关联。budget的原始总上限不因新表示、恢复或评测替代trial重置。工作内部实际模型仍用既有thought_*；许可只作用于已授权阶段，不借创建活动自动唤醒。

## 4 索引、事务及写入顺序

1. **C1**：门禁→事务→重检→M03决定/内容修订/head/组+持久handoff+tl_command结果→提交。互依赖组任何必需成员失败全回滚。未提交不发生成任务。
2. 构造：M04原子领取handoff、检查总预算/租约及当前源，事务外构造固定输入的表示。LLM若被授权参与转换，仍独立调用并登记全部输入；更强语义输出转候选，不作为纯表示发布。
3. **C2**：已校验blob就绪→门禁→事务→源/权限/版本/租约重检→表示/映射/消费确认/组ready/幂等结果→提交。group所有必需表示在同一最终提交中切换到ready，不发布半组当前视图。
4. 索引是对已提交ready表示的派生工作；索引更新失败不回写C1/C2失败，不提升检索命中。更新水位与内容版本分别保存；允许的有界回退只读合法主库表示。
5. **F1**：门禁→事务→合法变更、当前epoch/权限核对→tl_change+source_epoch递增+active barrier+全部必需传播义务+失效输入资格→提交。先阻断，不等索引或远端处理。
6. **F2/F3**：各域在原代次/预算内处理并确认，跨介质逐目标；删除中的晚到响应在正文工件写入前重查保留资格。verified不等于屏障解除；恢复资格必须再次读取当前源/授权/其他屏障。
7. 主库提交结果不明只读核对tl_command/handoff及头映射；新租约仅接未完成阶段。文件预置但主库未引用的孤立制品由显式受管回收计划处理，不能扫描后自行接纳；被引用但缺失阻断，不恢复为“正常空”。

## 5 评测存储隔离

实验材料/标签/盲评/统计不进入生产主库。独立评测库具有 `run、case、query、trial、attempt、label、review、fault、usage、metric` 十类设计记录，每类有run_id、版本及来源工件引用：

- run：协议/实现/代码/提示/模型精确版本与路由、随机顺序、种子、预算、时钟、访问角色、材料摘要与封存时间、状态blocked_before_start/registered/mechanism/dev/formal/stopped/completed/incomplete/failed。
- case：case_id、partition DEV/MECH/TARGET/RETENTION、category、source_cluster_id、template_family:Slot<string>、learning_input_ref、truth_ref（控制者域）；UNIQUE(run,case_id)。模板相关性不能假称独立。
- query：query_id、case_id、kind same_observation/new_question/boundary/retention、query_input_ref、k=5；TARGET三类齐，RETENTION仅retention。
- trial：trial_id、case_id、arm E/N/O、repeat 1..3、logical_trial_id、replacement_of:Slot<Ref>、snapshot_ref、phase、status、assigned_order；正式E/N三repeat，DEV E/N/O一次；UNIQUE(run,case,arm,repeat,original/replacement)；每logical_trial原始最多1、替代最多1，替代不扩大原分析分母。
- attempt：attempt_id、trial_id、logical_trial_id、phase learn/query、query_id:Slot<Ref>、request_ref、actual_callback_entry:Slot<UTC>、receipt:Slot<Ref>、outcome、cost_ref；真实attempt不由sent账本推断；整个逻辑trial预算共用。
- label：query_id、claim_id、expected_support、scope/unknown/相关集合/正确终点/major_error标准；仅controller-truth域，label制作/复核身份和材料封存版本必需，待测链不得读取。
- review：盲化item_id、reviewer_id、原标签/理由/定位、分歧裁决引用、盲化风险及时间；两名独立评审，不以同模型自评替代。
- fault：机制分支ID、Q裁决/题面及TL指标、注入点、预定先后、真实入口/屏障/提交/恢复轨迹、预期和实际终点；覆盖清单另有版本与封存摘要，数量不能凭预留名称冒充制作完成。
- usage：所有实际尝试、工具次数、tokens、耗时、预留/实际/未知分开；account_ref关联logical_trial、batch、run三级；已知零不等于未知，实际费用由运行前核查价格及账单供证据。
- metric：TL01—16、对象层次、case/trial/组、分子/分母或原始样本、单位、来源、计算版本、缺失状态、区间、判定、范围；单评审/先导不能标正式通过。

数据库对所有评测类型增加主键及run内唯一性，引用均限同run；文件ACL分learning/query、controller-truth、fault-plan、blind-review和run-manifest角色。真值/盲化映射不随运行包公开。case摘要进入运行清单时只暴露允许的内容，未知货币额度不能用NULL默认无限。

## 6 迁移和回退的精确边界

当前主库版本2/3不声称已经包含上述对象。实施目标主库版本**4**；需同期更新Store/schema migration、Runtime版本检查、Releases兼容校验与部署声明，不能仅创建表就绕过现有2/3上限。control.sqlite若需要迁移其格式，必须另列显式迁移；本版不要求改控制表结构，发布工件增加 `capabilities:["TL-LOOP-0.1"]` 能力声明，由升级后的可信部署端核对，不把旧代码的未知能力当兼容。

迁移前：停止且无运行进程、备份和校验、盘点旧数据、准备经隔离验证的兼容版本4且实现全部屏障/输入门禁的桥接基线与候选。迁移在单主库事务内创建新结构/注册约束/版本记录，完整性核对后提交；失败事务回滚，外部预置制品仍按受管回收。对旧shadow、旧记忆不批量生成accepted或TL表示；仅显式新工作可进入本链。

回退只允许已验证、schema范围涵盖4且声明TL-LOOP-0.1并执行同一屏障的桥接版本。不存在兼容回退基线时禁止迁移；运行后若所有兼容版本均失败，保持停止/降级，不启动旧2/3版本，不自动降库、不恢复抹掉新历史的旧备份。桥接版本可禁用新学习，但不能禁用读取/输出的现有屏障。恢复旧镜像还需当前可信排除记录，不能从迁移备份复活已删内容。

这是后续实施必须完成的兼容任务，不是本轮执行迁移，也不改变T12现有回退能力的历史范围。

## 7 评测字段的精确定型与分母键

本节补全§5类型；每个记录具有 `{contract:"TL-EVAL-0.1",schema_revision:1,id:EvalID,run_id:EvalID,created_at:UTC}`，EvalID为1—128个ASCII字母数字及`_.:-`。正文/标签存隔离工件，非opaque自由文本；所有 `*_ref` 均为同run Ref，跨库活动引用另有source_instance，不能写成评测库内FK。以下字段全部必需；可无实际值者使用Slot，不省略。PK为(run_id,id)，列举的唯一键也均含run_id。

| 记录 | 完整业务字段（使用主契约类型；JSON为明确受对应子规范约束的对象） | 唯一性及关系 |
| --- | --- | --- |
| Run | protocol_ref:Ref、code_digest:Digest、configuration_ref:Ref、prompt_refs:Ref[]、model_ref:Slot<Ref>、route:Slot<string>、materials_manifest:Slot<Ref>、review_roster:Slot<Ref>、price_evidence:Slot<Ref>、currency:Slot<string>、money_limit:Slot<number>、account_limits:Slot<JSON>、mechanism_manifest:Slot<Ref>、arm_seed:int=20261109、analysis_seed:int=20261108、bootstrap_samples:int=10000、concurrency_limit:int=4、deadline:UTC、state:§5枚举、budget_ref:Ref | 每run绑定一个协议/代码/材料版本；started后不可改参数来追认结果 |
| Case | partition:DEV/MECH/TARGET/RETENTION、category:string、source_cluster_id:EvalID、template_family:Slot<string>、learning_input_ref:Ref、truth_ref:Ref、base_snapshot_ref:Ref | UNIQUE(partition,id)；source_cluster_id不得跨DEV/TARGET/RETENTION，材料质控先确认独立性 |
| Query | case_id:EvalID、query_kind:same_observation/new_question/boundary/retention、input_ref:Ref、truth_ref:Ref、k:int=5 | UNIQUE(case_id,query_kind)；TARGET三项齐，RETENTION一项；DEV不进入正式统计 |
| Trial | logical_trial_id:EvalID、case_id:EvalID、arm:E/N/O、repeat:int[1..3]、occurrence:original/replacement、replacement_of:Slot<Ref>、snapshot_ref:Ref、instance_ref:Ref、phase:registered/learning/querying/finished、status:registered/running/completed/failed/stopped/not_run/infrastructure_invalid/incomplete、assigned_order:int>=0、outcome_ref:Slot<Ref>、budget_ref:Ref | UNIQUE(case_id,arm,repeat,occurrence)；logical_trial_id关联原分配，replacement与其共享case/arm/repeat；只能指一个original，最多1次，不新增独立分母 |
| Attempt | trial_id:EvalID、logical_trial_id:EvalID、phase:learn/query、query_id:Slot<EvalID>、request_ref:Ref、reservation_ref:Ref、actual_callback_entry:Slot<UTC>、receipt_ref:Slot<Ref>、outcome:prepared/in_flight/received/failed/unknown/stopped、usage_ref:Slot<Ref> | learn时query_id=not_applicable；query须known；同query原trial一次，基础设施替代仍受logical_trial总上限；禁止普通供应方错误反复查询 |
| Label | query_id:EvalID、claim_id:EvalID、support:supported/unsupported/conflicting/unknown、expected_scope:Scope、expected_slots:Slot<JSON>[]、relevant_refs:Ref[]、expected_terminal:string、major_error:bool、rationale:string、evidence_refs:EvidenceRef[]、author_id:EvalID、reviewer_id:EvalID | UNIQUE(query_id,claim_id)；truth域隔离，必须独立作者/复核角色，不给待测学习链 |
| Review | blind_item_id:EvalID、reviewer_id:EvalID、label_ref:Ref、original_rating:pass/fail/not_evaluable、reason:string、locator:Locator、resolution_ref:Slot<Ref>、unblinding_risk:Slot<string> | UNIQUE(blind_item_id,reviewer_id)；2名独立评审，分歧裁决为单独Ref，保留原评分 |
| Fault | mechanism_case_id:EvalID、decision_refs:string[]、metric_ids:TL01..TL16[]、fixture_ref:Ref、injection_stage:string、planned_order_ref:Ref、actual_trace_ref:Slot<Ref>、expected_terminal:string、actual_terminal:Slot<string>、status:planned/running/completed/not_run/failed | 具体fixture/分支/时序在mechanism_manifest枚举并封存，缺轨迹不判完成；不能用任意字符串省略决策覆盖 |
| Usage | logical_trial_id:EvalID、attempt_ref:Slot<Ref>、reservation_ref:Ref、input_tokens:Slot<int>=0、output_tokens:Slot<int>=0、tool_calls:Slot<int>=0、elapsed_ms:Slot<number>=0、currency_amount:Slot<number>=0、evidence_refs:Ref[] | 唯一绑定真实消费事件（reservation_ref+attempt_ref+计量种类），多副本/重放不重复记账；未知不按0结算 |
| Metric | metric_id:TL01..TL16、metric_version:string、partition:Case.partition、arm:E/N/O/paired、case_id:Slot<EvalID>、trial_id:Slot<EvalID>、level:claim/work/query/trial/case/partition/run、numerator:Slot<int>=0、denominator:Slot<int>=0、samples_ref:Slot<Ref>、unit:string、coverage:Coverage、method:Method、source_refs:Ref[]、status:not_run/missing/not_applicable/insufficient_sample/not_evaluable/measured、interval:Slot<JSON>、judgment:pass/fail/incomplete/not_evaluable/exploratory、scope:Scope | 率必须同时known分子/分母且分子≤分母；真实分母0为not_applicable，不得以0/0判pass；连续样本可用samples_ref而不造整数分子 |

数值后的≥0约束只适用于Slot.status=known的非空实际值；未测、缺失和不适用仍按Slot保留。Metric.interval已知时为 `{method:"paired_case_bootstrap"或"wilson",confidence:0.95,lower:number,upper:number,resamples:Slot<int>,seed:Slot<int>}`；lower≤upper，bootstrap固定10000/20261108；Wilson相应resamples/seed为not_applicable。延迟未完成样本保存右删失标志和观察截止，不放入“完成样本p95”。

Run仅在材料/标签/模型精确能力与价格/货币额度/评审/完整MECH管理限额全部known、通过离线机制和DEV前置且另有运行许可时可离开blocked_before_start。Label/Review的角色未就位是执行阻断，不允许运行器伪造独立人选来满足结构。Run completed仅表示预登记运行及记录完成，统计判定仍独立；存在硬fail不能转pass，未完成不以completed代替结果。


## 8 版本注册及检索映射补充

C1创建tl_content_revision时同步写object_registry和object_revision_registry，后者object_id=tl_content.id、revision_no=内容修订号、kind=tl_content_revision。表示系列使用稳定tl_representation_head.id；C2创建每个tl_representation版本时同步注册object_revision_registry，object_id=series_id、revision_no=该系列单调递增representation_no、kind=tl_representation。不能把表示修订挂在content.id下与内容修订号碰撞。初次系列/表示/头映射的循环引用在同一C2事务延迟核对；旧content版本/格式差异不能悄悄重置系列版本。RecallItem.representation_revision引用该系列版本，content_revision引用独立M03内容版本。

新链正常召回复用memory_retrieval_runs的运行/活动身份，返回项统一存tl_recall_item；旧memory_retrieval_results与memory_access_records仍只能引用memory_revisions，不把表示UUID硬塞入其外键。TL项若引用旧文字结果可存origin_result_id，统一统计以逻辑query及tl_recall_item为准，不能两张表各算一份命中/独立证据。表示的retrieved/read/used消费由tl_recall_item及tl_input_dependency/后续结果的有类型依赖记录，原文字仍保留旧访问记录。

控制者controller_audit保持只读：不创建retrieval_run、tl_recall_item、working_memory或访问写入，不修复索引；返回临时投影的retrieval_run为not_applicable，临时条目ID不宣称已持久化。所有实际模型输入的消费轨迹仍必须在正常受授权活动中保存，不能借audit入口生成模型调用。

C0的学习活动必须使用内部触发通道并保留实际生产者，原工具/用户来源作为不可变Ref关联；不能直接沿旧submit默认把学习生成内容冒充新的控制者话语。该装配适配器是后续实现要求，不声称当前Engine.submit已有正确入口。
