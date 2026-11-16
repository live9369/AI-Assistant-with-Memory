# IM14 效果记录与独立 shadow 接纳设计

日期：2026-11-10。依据冻结 TL-LOOP-0.1 contract/storage、Q01—Q12 和 IM07/08/12；不修改冻结规范或 DDL。仅合成隔离目录验证，不操作当前实例、不调用真实模型。

## 所有权和接口

新增 ToolLearningEffects.record_effect(entry,envelope) 消费冻结 record_effect。M14 独立保存不可变 EffectAssessment Product、tl_effect 与完整来源依赖，不写内容、决定、表示、工作状态或选择权。相同 work/assessment/metric 的跨命令复用只引用原产物；不同报告、失效说明是新不可变评估，旧数值不回填 0。IM07 缺测 Product 保留原件。M03 仍通过 ExperienceMeasurement.adopt_shadow → Learning.assess_measured_experience/propose_experience → Cognition.save_experience 独立校验和 CAS，不由 M14 直接写认知统计。

## 真实协议映射

metric_definition 必须真实 metric_definitions Ref；适配器逐字段核验 name/formula_version/unit/denominator_rule/missing_rule/stratification。唯一支持的数值量尺是 EXPERIENCE-MEASUREMENT-0.1 / prediction_brier_v1 的 EM03；metric_contract 字符串必须从实际定义映射，不能自由填写标签。其他 TL 内容忠实、命中、正确使用与独立 TL13—16 效果不能借该 gain 冒充。

测量报告必须来自同实例实际 experience-measurement 事件，并由 checked_report 重算承诺、标签封存、两臂、预测、实际预算、上下文和模型。绑定不可变 TL-EFFECT-BINDING-1：work、原 source、measurement、原 parent activity、case_scope、baseline、candidate、method_refs；baseline/candidate 为同次 registration 在预测前固定的两份真实 arm 工件（without_experience 的 common_context 与 with_experience 的固定 experience_snapshot），方法是同次 registration，不能把某一 TL 内容修订贴成实际未测的候选。当前真实能力通道核对该映射及旧 opportunity/source 谱系。无对应实际机会一律拒绝，不凭控制者标签制造收益。

报告 measured（含 0、负数）才允许 known gain；unknown 报告 → incomplete。not_measured/not_applicable 无报告；invalidated 必须实际 invalidation 事件且旧报告可定位，数值不可继续 known。retention/sample/independence/usage 精确投影原报告；independent_cases=null 仍是未知，不声称独立样本数量。数值不证明科学真实性、内容接纳、表示就绪或实际选择改善。

## 当前权限、F1、资源和幂等

EffectAuthority 默认拒绝。LocalEffectAuthority 只接受 LocalRuntimeOwners 当前进程/控制/政策/随机能力通道，原 work 两活动、原账户、期限与当前来源逐一重核；可信入口不由 JSON module 授权。原始 work 预算不重置；报告生成调用已由原 ExperienceMeasurement parent 记账，记录校验的读取另在原 work 预付真实 retrieval opportunity 并累计，未知保留占用。已耗尽/停止/撤权不能偷偷重开。

相同 dispatch_gate 覆盖检查、原件读取、来源依赖登记、保存及最终提交复核；F1 先到拒绝写入晚到正文。报告、registration、每个 dispatch/prediction、labels、固定来源及原 snapshot 均成为精确版本依赖，任何受影响输入失效使当前效果不可用。M03 显式采用前再次核对 TL 效果和所有依赖，并沿原接口保存 shadow-only/affects_selection=false；已有 legacy 只读兼容，不静默迁移。

## 隔离验收

用新临时 fixture 和确定性 prediction port 生成真实 sealed reports（替身只代替模型概率，不捏造报告）。验证缺测/不全/失效/正/0/负、保留否决、指标字段篡改、错 work/source/parent/Scope/候选/方法、假 report/标签/预测/预算、所有权限/F1/停止、预算不续费、跨键去重、提交回滚与丢确认、M03 显式接纳及失效后排除、内容和表示及实际选择不变。专项后冻结实现源码，由根统一全局门；不在兄弟编辑期间运行全局验证。

## 实际严格测量执行与最终接口（补充）

首版已有分类协议既保留 legacy parent，也接通 strict parent。`ExperienceMeasurement.run_predictions(..., strict_execution=StrictMeasurementExecution(kernel, provider), entry=...)` 在真实 TL-ACTIVITY-BUDGET-1 原活动下必须使用具名执行器，缺端口拒绝。不是把 runtime_event 伪装 thought_attempt：每个 paired prediction 创建实际 schema71 thought_request、thought_attempt、thought_result，保留 prepared/sent/received/failed 与完整请求／实际 provider invocation；登记 `/input` 完整 tl_input_dependency、固定原来源／快照／registration／binding 及摘要。真实来源 Scope 与统计 case_scope 分开保存。

`FreshMeasurementProvider` 继承现有独立 provider 的硬输出 cap、总时限、字节监督及实际用量采集，固定 V1 wait/probabilities 输出。当前 model/configuration/process/policy 与 recipient 每次重检，真实 FreshCapability/tokenizer 缺失默认拒绝；不将已安装 CLI 或调用者 bool 当能力。确定性专项端口拥有明确固定计费协议，只证明机械链。

预测的 read slice 及 model slice 均在同一原 parent 账户；不得更新 caps、转给 child、重领账户或忽略 allocation。模型调用的 input/output 分别计量，注册 tokens_per_call 仍是两者总上限；preflight 固定后再次计数不同则拒绝。读 slice 排除真实子调用耗时，实际 callback 耗时由模型 slice 计一次。unknown/overage 保留占用、停止后续，不根据新键重试。无入口能力时即使原协议允许 register，也不能开始 strict prediction。

report checker 同时重算原 Brier/retention 和 strict request/attempt/result、实际 wire、输入 manifest、原 account ledger/physical projection、route、维度测量、cap/deadline 映射。不是凭字符串或一个 checked bool 证明新 TL 内容收益。invalidated 保留历史计量事实，不保留当前 known gain。

`LocalEffects` 使用真实 LocalRuntimeOwners 能力通道。SDK record、register 与显式 M03 adopt 都安装 PhysicalReadMeter；M03 adopt 后沿真实 `CognitiveExperience.snapshot` 重新核报表及输入 F1/epoch/ACL，失效样本排除，旧数值保留历史。源在最后 save 前失效会由既有 M03 独立校验拒绝，整个入口持相同 gate。

IM13 所有者在共享 budget 模块增加默认拒绝 `evaluation_read_context`／`verify_evaluation_read`；IM14 只消费该端口。EffectBudget 私有 proof 固定真实 entry、原 work/account、当前 record_effect 请求、实际 retrieval run 和唯一 occurrence；仅忽略 completed/no_change/rejected 的 work 投影，没有新模型或工具机会。原 activity 真结束、halted、unknown、停止、到期和原 cap 均不能跳过。原活动真结束之后须另有合法评测工作／授权，本接口不复活旧账户。

数值支持范围仅 EM03 分类 shadow_snapshot 比较。baseline_ref/candidate_ref 指向预测前保存并实际读取的两份不可变 arm 工件，method_refs 指向同次 registration。strict packet 从实际 arm 工件构造 context 并登记其输入依赖；两臂分别为 without_experience 与 with_experience_snapshot，不是两个 TL 内容版本。TL 内容忠实、命中、正确使用、一般工具学习收益和语义独立性没有由本项测出，其他量尺及无真实依据的 not_applicable 默认 blocked。首次 not_measured 及 IM07 缺测产物不会被重写。

专项文件：`tests/test_tool_learning_effect.py`。所有测试新建临时合成实例；没有调用真实模型、当前实例或全局 runner。SDK 图扫描上限 4096 nodes/65536 rows；legacy snapshot protection 深度 16／图 4096，越界明确拒绝，不假报完整。当前保护对缺精确 field manifest 的 legacy 来源采用保守排除，可能比新 TL 范围更严格。

### 统计 Scope 的实际量尺与 case 绑定

`classification_scope` 从实际注册 cases、classes、label_commitment、common_context 摘要与 training_case_ids 确定性派生；claim_target 使用冻结合法枚举 `effect_statistic`，property/unit/domain/granularity/coverage 均为 EM03 分类量尺，conditions 固定每个 case ID/split/input 摘要及注册计分政策。时间总体外推不作断言，semantic independence 仍未知。register 前及 record/helper 中均逐字段比较实际 canonical Scope，不能先把指标贴成检索率／内容忠实／世界正确性再事前绑定。原 source Scope 独立保留，不拿统计 Scope 覆盖原命题资格。

第一次 63 项专项在加此语义约束前源码稳定通过，保留为 `im14-development/im14-pre-scope-special.json` 与原日志，明确是被收紧设计取代的开发证据；不能作为最终当前源码稳定验收。收紧后另一次最终专项及统一门分别出证，不覆盖历史。
