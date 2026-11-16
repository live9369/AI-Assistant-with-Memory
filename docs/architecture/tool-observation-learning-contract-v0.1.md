# 工具观察→学习→认知经验→记忆召回：首版精确契约

契约：TL-LOOP-0.1。日期：2026-11-09（Asia/Shanghai）。本文件是**设计规格**，不是已部署接口、SQL或运行结果。冻结状态以配套 `tool-observation-learning-freeze-v0.1.json` 为准。旧Q12预整理稿保留为历史，本文件及字段/存储附录为本版规范。

适用范围：单实例SQLite主库、受管blob与派生索引；保留既有独立LLM调用、权限/停止/恢复门禁。M14提出，M03决定内容，M04发布表示，M12判权限，M17执行技术保存；协调器无内容写权。冻结不授权业务编码、模型消费、清理、迁移或部署。

## 1 基础编码、版本与公共类型

采用JSON对象，UTF-8；所有列出的字段必需，只有显式标为optional者可省略。对象拒绝未声明字段、重复JSON键、NaN/Infinity、非法Unicode及不匹配类型；未知内容不按旧自由文本兜底。顶层 `contract` 固定TL-LOOP-0.1，`schema_revision`整数1。未来新增必需语义换契约版本，不让旧消费者静默接纳。

新记录ID为32位小写十六进制UUID；既有Ref.id是不透明的非空字符串（最多240字符），不得假设旧ID长度。UTC时间固定 `YYYY-MM-DDTHH:mm:ss.sssZ`；业务时间缺失用Slot，不以created_at代替。整数排除bool，浮点必须有限。原文不做隐形Unicode规范化。

| 类型 | 精确定义 |
| --- | --- |
| Ref | `{instance_id:string,id:string,kind:string,revision:Slot<int>}`；kind取下文表中对象类型或既有注册类型；同实例引用，跨实例仅授权外部来源且显式标明，不作本实例对象FK |
| Digest | `{algorithm:"sha256",hex:string[64 lowercase hex]}`；摘要绑定所声明字节/视图，不证明来源独立或内容为真 |
| Slot<T> | `{status:enum,value:T或null,reason_code:enum,reason:string,basis_refs:Ref[]}`；status为known/unknown/not_collected/not_applicable/withheld/conflicted/invalid；非known时value必须null，reason非空；known也保留全部字段，reason_code=none或source_reported_null；known/null只允许字段T明确包含JSON null且原来源报告null，不用于测量占位 |
| Reason | none/source_reported_null/not_measured/no_prior_prediction/missing_unit/ambiguous_entity/incomplete_source/unavailable_source/no_baseline/out_of_scope/not_requested/access_restricted/conflicting_support/invalid_locator/invalid_type/budget_limit/deadline/unsupported/other；other须非空reason；新原因不能自由变成许可 |
| VersionToken | `{object:Ref,revision:int>=0,epoch:int>=0}`；内容版本与资格代次不同；不存在旧对象用Slot<VersionToken>.not_applicable而非伪造revision=0对象 |
| Dependency | `{target:Ref,relation:enum,expected:VersionToken,consumer_purpose:enum}`；relation=support/derive/read/delete/representation/group；支持、读取和删除依赖不得混同 |
| Principal | `{actor:Ref,module:enum,recipient:Ref,purpose:enum,authorization:Ref}`；module=M01/M03/M04/M12/M13/M14/M17/coordinator/evaluator；purpose=learn/accept/represent/recall_experience/recall_episode/verify_source/evaluate/history_audit/propagate/erase/recover；purpose不是任意字符串授权 |
| Method | `{name:string,version:string,request_ref:Slot<Ref>,model_config_ref:Slot<Ref>}`；确定性转换无模型请求用not_applicable |
| Control | `{policy:VersionToken,configuration:VersionToken,source_epochs:VersionToken[],runtime_epoch:int>=0,input_epoch:int>=0,cancelled:bool}`；快照只用于绑定，实际操作前仍查询当前状态 |
| Budget | `{account_ref:Ref,deadline:UTC,max_attempts:int>=1,max_input_tokens:int>=0,max_output_tokens:int>=0,max_tool_calls:int>=0,max_scan:int>=0,max_items:int>=0,max_bytes:int>=0}`；额度有限，工作全生命周期共享，不能用换请求重置；下游取父预算剩余与本阶段上限的较小值 |
| Coverage | `{state:complete/partial/unknown,domain:Slot<string>,scanned:int>=0,limit:int>=0,truncated:bool,missing:Slot<string>[]}`；complete仅指声明域，不能表达全世界无反证 |
| Check | `{state:enum,checker:Principal,method:Method,at:UTC,targets:VersionToken[],reason:Reason,basis_refs:Ref[]}`；state的枚举由资格轴分别限定，不共用一个qualified |

幂等指纹使用既有Python JSON规范：sort_keys=true、ensure_ascii=false、separators=(',',':')、allow_nan=false，对输出UTF-8求sha256；不做等价数字/Unicode归一化。其他实现必须逐字节匹配参考编码，不能自称通用跨语言canonical JSON。未知值、字段顺序与数组顺序按此规定；数组业务排序在生产者生成时固定。

## 2 精确来源、范围与内容

EvidenceRef为 `{source:Ref,source_kind:tool_result/user_statement/system_event/model_output,original_result:Slot<Ref>,receipt:Slot<Ref>,artifact:Ref,source_revision:Slot<int>,digest:Digest,media_type:string,encoding:Slot<string>,view:Slot<Ref>,view_digest:Slot<Digest>,locator:Locator,origin_method:Method,observed_at:Slot<UTC>,reported_at:Slot<UTC>,coverage:Coverage,derivation_refs:Ref[],access_dependencies:Dependency[]}`。tool_result必须有known original_result及receipt；其他类型对应两字段not_applicable。artifact不可缺，视图缺失不等于原始视图可随便换。

Locator为四选一封闭对象：

- `{kind:"json_pointer",pointer:string}`：对绑定JSON视图，按RFC6901语义；重复键拒绝定位，嵌套JSON字符串须单独建立解析视图。
- `{kind:"text_range",start:int>=0,end:int>=start,quote:Slot<string>}`：Unicode码点半开区间，要求end不超过绑定文本长度；quote已知时须精确匹配。
- `{kind:"byte_range",start:int>=0,end:int>=start}`：绑定原字节，不能混成文本偏移。
- `{kind:"whole_artifact",justification:string非空}`：仅完整原子观察或工件整体状态，不能替代复杂对象的主张定位。

Scope为 `{subject:Slot<Ref>,subject_label:Slot<string>,property:string,claim_target:source_report/world_claim/method_claim/causal_claim/effect_statistic,temporal:{kind:observation/source_validity/general_candidate,start:Slot<UTC>,end:Slot<UTC>,bounds:point/closed/open/half_open/unknown},conditions:Slot<JSON>,domain:Slot<string>,unit:Slot<string>,granularity:Slot<string>,coverage:Coverage,exceptions:Ref[],limitations:string[]}`。每个实质主张有自己的Scope；unknown不扩大为全部条件/永久/无量纲；subject未消歧不能仅凭相同label合并。

Claim为 `{claim_id:ID,form:source_report/explicit_transformation/interpretation,subject:Slot<Ref>,predicate:string,value:Slot<JSON>,scope:Scope,evidence:EvidenceRef[1..],derivation:Method,limitations:string[]}`。source_report的已知10只表示来源报告10；世界事实、方法概括、因果及效果不能由此自动升级。

资格轴：source_check.state=readable/temporarily_unavailable/revoked/deleted/unknown；locator_check.state=not_checked/matched/unresolved/mismatch；support_check.state=not_assessed/supports_scoped_claim/insufficient/conflicting/not_applicable；readiness.state=not_checked/ready_for_handoff/needs_material/blocked/not_applicable。每轴用Check记录。M03决定与M04发布不在M14资格轴中预填。

## 3 四类M14产物与下游对象

Product共同字段为 `{contract,schema_revision,product_id:ID,instance_id:ID,producer:Principal,work_ref:Ref,purpose:Principal.purpose,method:Method,created_at:UTC,source_refs:EvidenceRef[],derivation_links:Dependency[],limitations:string[],missing_items:Slot<string>[],access_dependencies:Dependency[],revision_links:Slot<Ref>[],processing_identity:Digest,downstream_refs:Slot<Ref>[],checks:{source_check:Check,locator_check:Check,support_check:Check,readiness:Check},product_type:enum,body:按类型}`。

| product_type | body的完整必需字段 |
| --- | --- |
| ObservationExtract | `{observations:Claim[],coverage:Coverage,empty_reason:Slot<string>}`；有实质内容时observations至少1，不能空内容冒充提取覆盖 |
| ComparisonAssessment | `{baselines:VersionToken[],comparison_coverage:Coverage,comparisons:Comparison[],outcome:proposal_supported/no_change/conflict/insufficient/blocked}` |
| UpdateProposal | `{target:{owner:"M03",mode:existing/new,object:Slot<Ref>,expected:Slot<VersionToken>,content_kind:source_report/world_claim/method_claim/causal_claim},operation:add/confirm/temporal_add/correct/restrict/mark_conflict,claims:Claim[1..],rationale:string,preserved_content:Ref[],unresolved_items:Slot<string>[],atomic_group:Slot<Ref>}`；existing目标和expected必须known且一致，new两者not_applicable，不能预分配M03版本 |
| EffectAssessment | `{measurement_state:not_measured/incomplete/measured/invalidated/not_applicable,measurement_ref:Slot<Ref>,baseline_ref:Slot<Ref>,candidate_ref:Slot<Ref>,method_refs:Ref[],metric_definition:Ref,case_scope:Scope,gain:Slot<number>,retention_components:Slot<JSON>,sample_counts:Slot<JSON>,independence:Slot<JSON>,usage:Slot<JSON>}`；gain已知须测量完成且原报告合格，允许0或负值，不能改变旧gain语义 |

Comparison为 `{observation:Ref,baseline:Slot<VersionToken>,comparable:Slot<bool>,basis:Ref[],difference:enum,support:Ref[],counterevidence:Ref[],limitations:string[]}`。difference封闭集合为temporal_add/correction/restriction/confirmation/conflict/not_comparable/no_change/insufficient/new_object/new_property。comparable非known/true时不得把差异作为反证或数值平均；new_object/new_property须说明旧覆盖，检索未命中不等于不存在。

Decision为 `{id:ID,work_ref:Ref,proposal_ref:Ref,review_round:int,actor:Principal,policy_ref:Ref,checks:G01..G08的Check,operation:accept/candidate/defer/reject/conflict/reuse,actual_scope:Scope,content_ref:Slot<Ref>,revision_ref:Slot<Ref>,previous:Slot<VersionToken>,reason:Reason,coverage:Coverage,handoff_refs:Ref[],created_at:UTC}`；候选/冲突/拒绝不写accepted资格。reuse引用已有版本且无新接纳计数。候选新内容可有M03 candidate版本，但普通经验用途禁止、没有当前表示义务；被拒绝新提案不生成内容版本。

Representation为 `{id:ID,series_ref:Ref,representation_no:int>=1,content_ref:Ref,content_revision:VersionToken,decision_ref:Ref,format_version:"TL-TEXT-1",body_artifact:Ref,body_digest:Digest,claims:Claim[1..],source_refs:EvidenceRef[1..],scope:Scope,limitations:string[],dependencies:Dependency[],group:Slot<Ref>,published_at:UTC}`。正文按“来源性质→有限主张→时间/单位/条件→未知/冲突→证据定位”顺序生成，禁止增加新判断。改格式增加表示版本，不增加内容接纳或gain。

## 4 统一请求、响应与幂等

每个写操作Envelope为 `{contract,schema_revision,command_id:ID,instance_id:ID,principal:Principal,work_ref:Slot<Ref>,idempotency_key:string[1..240],expected:Slot<VersionToken>,control:Control,budget:Budget,payload:各操作定义}`。创建工作时work_ref.status=not_applicable，后续均为known且value是Ref；不以null假装存在工作。

Response为 `{command_id:ID,operation:string,disposition:applied/reused/deferred/rejected/blocked/stopped/failed,owner:module,result_refs:Ref[],current:Slot<VersionToken>,reason:Reason,error_code:Error,coverage:Coverage,retry:{allowed:bool,condition:Slot<string>,resume_work:Slot<Ref>},committed_at:Slot<UTC>}`。未提交不能有known committed_at；输入/权限未知不填“已提交”。公开投影隐去无权者不可见ID、计数和原因，仅给通用unavailable；内部审计保留合法细分。

Error封闭集合：NONE、CONTRACT_UNSUPPORTED、STRUCTURE_INVALID、UNAUTHORIZED、SOURCE_UNAVAILABLE、SOURCE_INVALID、SUPPORT_INSUFFICIENT、VERSION_CONFLICT、IDEMPOTENCY_CONFLICT、POLICY_MISSING、GROUP_NOT_READY、LEASE_STALE、STOPPED、CANCELLED、DEADLINE_EXCEEDED、BUDGET_EXHAUSTED、STORAGE_FAILED、COMMIT_UNKNOWN、COVERAGE_INCOMPLETE、ERASURE_BLOCKED、RESTORE_BLOCKED。Error不等于全链状态；正常无变更/候选可NONE而仍不表示可作当前事实。

幂等查找键 `(instance_id,operation,idempotency_key)`；第一次请求保存指纹与结果。指纹涵盖principal的actor/module/recipient/purpose/authorization、work_ref、expected、payload、契约和处理方法；command_id及执行时快照不计指纹，但control/budget即便重复仍必须重新核对，不允许原许可复活。相同键不同指纹返回IDEMPOTENCY_CONFLICT，不能覆盖旧对象。认知复核需新review_round及新逻辑命令键，只有明确解除条件变化才能继续，仍共享原work与预算；重复历史结果经当前授权投影后返回，不重新计算收益。

## 5 精确操作表

这里是未来服务操作名，不是当前Python方法。均使用§4Envelope/Response，禁止直接写他域表。读请求不因此获得工具/模型执行许可。

| 操作／入口所有者 | payload字段 | 原子提交与返回对象 |
| --- | --- | --- |
| admit_observation / M14 | `{source:EvidenceRef,purpose:learn/evaluate,source_activity:Ref,processing_method:Method,previous_work:Slot<Ref>}` | C0工作+幂等记录+活动/预算绑定；返回work或有限等待/拒绝/停止；先控制→分层重复→用途→材料和预算 |
| assess_observation / M14 | `{source:EvidenceRef,baseline_refs:VersionToken[],baseline_coverage:Coverage,method:Method}` | 单工作产物提交Extract/Comparison/Proposal/Effect中的实际产物引用；无变更或不足有明确原因；模型在主事务外调用 |
| decide_proposal / M03 | `{proposal:Ref,review_round:int>=0,policy:Ref,review:Slot<Ref>,atomic_group:Slot<Ref>}` | C1决定/新内容修订/当前头/持久表示义务/组标记/幂等结果；候选、拒绝、defer、reuse不同结果，不强制产生义务 |
| claim_representation / M04 | `{handoff:Ref,expected_generation:int,worker:Ref,lease_seconds:int[1..300]}` | 领取单工作与递增lease_generation；返回固定版本与材料；总deadline优先；租约只管理构造，不授予内容权 |
| publish_representation / M04 | `{handoff:Ref,lease_generation:int,worker:Ref,representation:Representation}` | C2表示+映射+消费确认+组就绪及幂等结果；CAS/权限/源版本/制品检查后发布；失败不回滚C1 |
| recall / M04 | §6RecallRequest（只读检索语义；正常活动的检索轨迹按原权限记账） | RecallResult；控制者只读审计入口不调用prepare、不修复索引、不生成学习或模型活动 |
| apply_invalidation / 变更权威域，M12复核 | `{change_id:ID,kind:correct/revoke/erase/conflict/unavailable,source:VersionToken,replacement:Slot<VersionToken>,affected_scope:Scope,subjects:Ref[],purposes:purpose[],expected_epoch:int,evidence:EvidenceRef[],erase_scope:Slot<Ref>}` | F1当前资格屏障+持久传播义务+新epoch+幂等结果；多原因独立；erase_scope仅erase必需known授权计划 |
| acknowledge_propagation / 各目标所有者 | `{barrier:Ref,generation:int,domain:module,targets:Ref[],coverage:Coverage,actions:Ref[],verification:Ref}` | F2本域结果与确认；F3只有必需域覆盖完整/清理已核验才能标传播/清理各自完成，权限仍由独立屏障控制 |
| resume_work / 原业务所有者，既有恢复入口 | `{work:Ref,expected_work_revision:int,conditions:Ref[],reconciliation:Ref}` | 原work续处理及新有效租约/代次；COMMIT_UNKNOWN先核对持久结果；failed job不被自动领取，不重做原动作来猜提交 |
| record_effect / M14 | `{work:Ref,measurement:Slot<Ref>,assessment:EffectAssessment}` | 保存效果产物/提案，M03通过既有独立入口接纳统计版本；不提升世界事实、内容资格或普通召回可用性 |

所有写提交和发送/使用边界检查当前实例、权限、原source epoch、预期内容版本、停止/取消、期限和剩余预算。未知提交返回COMMIT_UNKNOWN且禁止盲重放；查询原幂等记录/持久义务后才能确认或续未完成阶段。

## 6 召回精确字段及用途矩阵

RecallRequest为 `{contract,schema_revision,request_id:ID,instance_id:ID,activity_ref:Slot<Ref>,context_ref:Slot<Ref>,principal:Principal,entry:execution/controller_audit,query:string,target_scope:Scope,exact_refs:Ref[],version_mode:current/specified/as_of,as_of:Slot<UTC>,group_required:bool,allowed_kinds:enum[],control:Control,budget:Budget,index_fallback:deny/bounded_primary}`。specified须exact_refs非空；as_of须时间known；controller_audit只允许history_audit/verify_source/evaluate且无生成/修复副作用，不能借此执行普通学习。

RecallResult为 `{request_id:ID,retrieval_run:Slot<Ref>,purpose:purpose,method:Method,checked_at:UTC,coverage:Coverage,completion:complete/partial/not_ready/blocked/unavailable/stopped,empty_reason:Slot<Reason>,items:RecallItem[],gaps:Slot<string>[],dependencies:Dependency[]}`。complete且items=[]必须有known empty_reason；空相关集合不是确认世界不存在。内部细分丢失/权限/损坏，公开诊断不得泄漏隐藏对象的存在及数量。

RecallItem为 `{id:ID,kind:episode/accepted_content/source_evidence/candidate/history/shadow_statistic,memory_ref:Slot<Ref>,memory_revision:Slot<VersionToken>,representation_ref:Slot<Ref>,representation_revision:Slot<VersionToken>,content_ref:Slot<Ref>,content_revision:Slot<VersionToken>,decision_ref:Slot<Ref>,body:string,body_digest:Digest,origin_kind:EvidenceRef.source_kind,processing:raw/extract/transform/infer,source_refs:EvidenceRef[],scope:Scope,limitations:string[],value_slots:Slot<JSON>[],usage_state:current/candidate/historical/conflicted/blocked,group_ready:Slot<bool>,relations:Dependency[],selection:{method:Method,score:Slot<number>,reason:string},control:Control,dependencies:Dependency[]}`。

普通recall_experience只返回M03已接纳、当前用途合格且C2及组就绪的accepted_content；recall_episode保留旧文字/经历合法路径，明确原始性质；verify_source可返回合法source_evidence但不能伪装accepted_content。evaluate/history_audit可在授权范围读取candidate/history/shadow_statistic，均不得转为当前事实或实际选择。原始路径无M03引用的字段用not_applicable；被屏障影响且无公开权限者不返回该条，不能以blocked条目泄漏ID。

原子C2未完成不允许认知临时直读；索引损坏只允许授权、有限、已提交表示的主库回退。整条正文、来源性质、Scope、未知/冲突与必要定位一同计预算，装不下移除整项并标partial，不能只裁掉限制。排序分不是事实概率或gain。

## 7 状态机和组/屏障规则

所有可变行有 `row_revision:int>=0`，每次合法转换CAS递增1，旧工作器不写新状态。不可变版本不原地更新；权威删除按授权清理协议，不能以不可变拒绝删除。

| 状态轴 | 允许转换（其余拒绝） | 必要守卫/写者 |
| --- | --- | --- |
| Work | admitted→processing/waiting/blocked/stopped；processing→awaiting_decision/completed/no_change/waiting/blocked/failed/stopped；awaiting_decision→handoff_pending/completed/no_change/waiting/blocked/rejected/stopped；handoff_pending→completed/waiting/blocked/failed/stopped；waiting/blocked/failed/stopped→processing或handoff_pending；completed/no_change/rejected无出边 | M14/协调器只写工作状态；最后一组续处理仅resume_work，条件解除、当前授权、原预算/期限有效。继续点由持久阶段确定，不重跑已提交阶段 |
| Handoff | pending→leased/blocked/obsolete；leased→published/retryable/blocked/permanent_failure/obsolete；retryable→leased/blocked/obsolete；blocked→pending/obsolete；expired leased→leased（新代次） | M04；当前租约、固定内容版本与所有屏障重检；blocked解除不自动运行；published/permanent_failure/obsolete终态，重建需新表示工作但同内容版本且不新计学习 |
| Decision | 每个review_round一次写入accept/candidate/defer/reject/conflict/reuse，不回写 | M03；新review_round需原工作恢复条件/预算；accept才可创建当前表示义务，candidate只作分析；旧决定保留历史 |
| Content | 新candidate或accepted；新修订可accepted/candidate；当前使用另受conflicted/restricted/revoked/invalid屏障约束 | M03唯一版本写者；有版本更正链，禁止按全局最大版本自动选真。semantic补偿以新修订，恢复不复活删除正文 |
| Representation | 发布时ready；ready→superseded/withdrawn；当前用途仍可受独立屏障阻断 | M04；已发布旧表示不被旧租约回写，修复新增表示版本并显式CAS当前映射 |
| Group | pending→ready/obsolete；ready→obsolete | C1互依赖组全部决定/版本/义务一次提交；C2整组必需表示+组ready一次提交，已知缺任何一项不得报组ready |
| Barrier | active→resolved | F1合法变更发起域+M12；只有明确原因解除及当前支持核对可resolve，不能整体清除其他active原因；历史屏障保留 |
| Propagation | pending→processing/blocked；processing→verified/blocked/failed；failed/blocked→processing | 各业务域F2；原计划/预算/代次复检；verified仅声明所列目标和覆盖，不等于权限恢复 |
| Erasure | planned→cleaning/blocked；cleaning→verified/partial/blocked；partial/blocked→cleaning | M12授权计划，各所有者执行；逐目标检查body/blob/index/登记备份；缺覆盖不verified，远端unknown不算已删除 |

外部原回执、M14产物、M03决定/版本、M04表示、效果评估有各自身份和计数。Work completed仅表示它的指定合法终点完成；拒绝/候选等不能被聚合器算成“内容发布”。等待/失败恢复不新增独立case、曝光、学习收益或时间预算。

## 8 默认接纳政策与输入/输出门禁

首版政策档 `TL-ACCEPT-REVIEW-1`：不启用无人监督的内容接纳。source_report、world_claim、method_claim、causal_claim均须G01—G08及绑定提案/基线/实际范围的已有控制者复核记录；缺政策或缺复核→candidate（不能自动制造许可），可补材料→defer，格式/权限非法→reject/blocked。统计EffectAssessment使用已有独立测量校验入口且保留shadow资格。控制者复核不能覆盖失效来源、越权、未支持命题或预算/停止门禁。未来自动规则是另一个明确版本，不由本次冻结暗中开启。

独立输入清单记录每个来源/派生物的 `{field_path:JSON Pointer,source:VersionToken,dependencies:Dependency[],purpose,recipient,body_digest:Digest,gate_epoch:int}`，包括旧稿§6列出的全部入口以及测量输入、所有响应、公共回复和登记派生副本。准备/装配、真实generate/tool回调、响应保留前、接纳、交付、外部动作分别重检，保留G1互斥和在途事实。一个selected_memories摘要不能替代全清单。所有实际选择消费者仍维持原授权，新链启用不暗含写人格/意图/概率函数。

F1与发送同一实例协调门禁，先拿门禁后开主事务；模型调用在主事务外，已有同步回调持门禁直到返回的G1边界不放宽。源修订/屏障先提交则后续入口拒绝；入口先进入则外部F1可能等待完成。同线程重入仍按已在途处理。接收前发现删除范围涵盖正文，不先落盘再补删；仅记允许的完成/费用/处置信息，未知实际费用不能记0，秘密hash也不可自动保留。

恢复来自旧备份时必须核对镜像外可信排除记录；没有记录或无法确认当前源/权限时保持RESTORE_BLOCKED。通用代码回退不移除屏障、删除计划或已经提交的内容修订，不回滚世界或自动发第三方更正。

## 9 Q11精确合并

继承TL-EVAL-0.1，不调整其阈值或预算。设计与材料分开：下列常量冻结，真实模型/路由/价格、账户货币额度、评审身份及材料/提示摘要是运行前的必填绑定；缺项状态blocked_before_start，不是接口设计留空。

| 分区 | case/arm/repeat/query | 用途与控制 |
| --- | --- | --- |
| DEV | 24 × E/N/O × 1；最多三查询/各trial | 8类各3题，原库存示例只在DEV，永久不作正式材料 |
| TARGET | 800 × E/N × 3；各case三查询 | 8类各100；same_observation/new_question/boundary，主TL13只用new_question |
| RETENTION | 2000 × E/N × 3；各case一查询 | 5类各400，与TARGET无来源/答案共享；E追加隔离更新，基础能力与N一致 |
| MECH | 全Q01—Q09裁决/未来题面、Q10的20类逐项映射；每必要分支3次 | 枚举冻结后数量锁定；确定性替身、无真实模型/外部动作；保留完整G1，跨线程/跨进程各24种×3次 |

E走I01—I06完整链；N保留原观察审计但普通经验查询不能偷带工具答案/更新摘要/目标会话；O仅DEV来源查证。case来源簇、同义变体、三查询/三repeat不能扩独立样本；模板家族相关性另做敏感性分析。每case/repeat两臂从同一干净学习前快照隔离复制，运行实例ID/组身份独立，不能让相同主体副本并行冒充正式实例；基础材料内容相同不要求运行主体ID相同。克隆工具必须在授权实验命名空间重绑定实例与FK/权限，或串行恢复受控隔离快照；未实现安全重绑定前不能用手工复制可运行的同身份目录替代隔离。

冻结随机化arm seed=20261109；bootstrap seed=20261108、10000次、case等权/三repeat先case内平均、95%区间；TARGET TL13下限>0，RETENTION TL14下限≥-0.02。质量门继承Q10及Q11：E的TL03≥95%、TL04≥90%、宏观recall@5≥90%、TL06≥90%；重大错误/泄漏零，机制全覆盖、必需证据/标签完整。正式N不须通过被刻意拿掉的学习覆盖门；TL07机制100%，正式分层单列。至少20case不是功效证明；Q11的SD/功效只是规划假设，不据实测方差事后追改门槛。

每逻辑trial最多6模型尝试，学习≤3，TARGET三查询各≤1、RETENTION一查询≤1；不能把空余名额挪给失败查询重试。每次预留32768 token、输入≤24000、输出≤8000；trial只读工具≤4、单调用180秒、trial观察1200秒。批额/全run/父工作剩余额同时约束；正式16800逻辑trial，尝试上限100800、预留token3303014400、工具67200；DEV72 trial、432尝试、14155776 token，单独分账；MECH管理资源另封存。

正式28批×100 case，每批两臂/三重复，最多3600尝试、117964800 token，整个run最长14天、同时≤4 trial。批分配及顺序须在运行前封存，批间不看显著性续跑。所有重试、基础设施替代trial及失败消耗均在原逻辑trial/批/run上限内；基础设施替代最多1次，只作敏感性分析，不替代主分析原分配结果，不新增case或重置学习预算。

硬违规停止整个run新派发，保留已在途事实/用量，未运行项not_run；证据/评审缺失不可通过，实际违规fail；缺失不能掩盖已观察违规。只获DEV许可不运行正式；无物理清理范围授权时破坏性题not_run，不据替身报真实清理通过。

## 10 冻结后的交接

本规范与字段/存储附录、冻结记录共同构成设计首版；Q01—Q11裁决保留为依据，旧Q12草稿保留历史。GAP中的“未实现”转为明确实现任务，不是仍未裁决的设计缺口。材料制作、MECH完整实例清单、模型能力/成本绑定与独立评审就位是后续执行准备，不冒称已制作或已通过。业务编码仍暂停，正式实例和主路线机器状态不变。


### 规范补充：复核、资源和隔离身份

- review_round属于tl_work，从0开始，不放进不可变UpdateProposal内容。decide_proposal的review_round必须等于当前工作值；resume_work仅在phase=decide、明确解除条件或当前基线发生合法变化且预算仍有效时递增。旧轮次只返回其授权可见的历史结果，不能覆盖新决定。
- C1组内有不可接受项则不提交任何accepted头或表示义务；可另提交整组非接纳决定/原因审计，不能把审计记录当半组成功。
- 每次真实模型/工具派发前，评测侧在独立预算账本同一事务检查并预留logical_trial、batch、run额度；不得只靠各独立activity的账户累加后事后发现超额。结算actual与unknown分别保留，原预留在消费未知前不释放为可再用。
- 接收Response中的owner是操作业务所有者，不是调用者可提供的授权字段；request Principal.module只供校验，真正身份/授权由可信运行通道确认，不能靠JSON自报M03取得写权。
- E/N隔离身份的必要运行ID差异应预登记，不改变基础认识/原来源/目标查询的语义；组名、盲评标签及其他组输出不进入待测模型。未知或不支持的身份重绑定不自动复制可运行实例。


### 规范补充：枚举和终点消歧

G01—G08分别使用Check，state集合为pass/fail/incomplete/blocked/not_applicable。UpdateProposal的accept要求八项均pass；不适用的子检查须说明，不能把整个必需门标not_applicable来接纳。其他Decision保留实际检查结果及原因，不因失败审计就写成accept。

Work.processing→completed仅用于已预先指定的纯评估终点且全部必需产物已提交；Work.awaiting_decision→completed仅用于本次指定合法终点为candidate/conflict而无当前表示义务的决定。两者phase=complete并关联明确Decision/Effect，不计作接纳或发布覆盖；学习应处理的可学习题全部候选仍不能通过TL04。accepted且需表示必须走handoff_pending→completed，不能提前完成。

Handoff离开leased时清空当前worker/expiry，旧租约信息保留在审计；领取增加lease_generation和attempts，仍不超过原工作预算。过期、停止或权限阻断不自动续期：到期/耗尽可记permanent_failure，临时停止记blocked且明确解除条件。新表示修复工作仍关联同一内容和来源，真实修复成本要计，不新计学习。

Response.result_refs指向类型化结果工件/权威对象；claim的Response.current.epoch给新lease_generation，revision给当前row_revision，固定输入经原授权M17读取，不能通过引用越权读取正文。读取C1/C2结果需当前资格检查，历史提交事实不等于现在可使用。

MECH manifest固定结构为 `{version:string,cases:Fault[],coverage:{decision_id:string,case_refs:Ref[],rationale:Slot<string>}[],g1_baseline_ref:Ref,manager_limits:{wall_ms:int>0,disk_bytes:int>0,max_trace_bytes:int>0},sealed_at:UTC,digest:Digest}`；cases非空、全部裁决/未来题面/Q10检查逐项有映射或可核对的不适用理由，实际数量从封存cases得出。管理限额须有限known，未齐不能启动。

正式批次形成方法：TARGET按Q11八类既定顺序、RETENTION按Q11五类既定顺序，各类内部按封存case_id升序连接，TARGET在前、RETENTION在后，每100case一批，固定28批；arm/repeat派发顺序再按Q11种子封存，不根据中途结果换批。此为材料生成后的确定装配，不填造未制作题库。

正式实验中，接纳复核者只能按冻结政策读取learning-input及其合法支持，不得读取隐藏query-input、controller-truth、盲化映射或向待测模型回传评测评分。其角色与评测真值/盲评身份在run-manifest中分别声明并核对；需要独立人员未就位时不得启动正式评测。控制者复核不是给学习链输送答案的通道。
