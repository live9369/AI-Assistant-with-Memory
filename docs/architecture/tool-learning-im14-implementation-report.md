# IM14 实施报告

状态：实现及最终专项完成，65 项通过且本项源码前后 SHA 完全一致；等待根统一源码稳定隔离门。没有正式部署、当前实例操作或真实模型调用。所有概率、工具材料及身份均来自新建临时合成实例，不是学习收益实证。

## 实际接线

- `tool_learning_effects.py`：冻结 `record_effect`、不可变 Product/tl_effect、跨命令去重、精确依赖、实际 EM03 metric_definition 字段映射、真实当前能力通道、独立 M03 shadow 入口。
- `tool_learning_effect_measurement.py`：严格原 parent ActivityResourceBudget 下的真实 thought_request/attempt/result 生命周期、完整输入登记、实际 FreshMeasurementProvider wire／用量、两臂封存及校验。
- 既有 `experience_measurement.py`：严格执行器显式选择与默认拒绝；强化实际请求、两臂、预算、预测结果／report 重算；原有正常 legacy 报告及数值语义保留。
- `tests/test_tool_learning_effect.py`：新合成专项。公共 runner、冻结 normative 文档和 DDL 均未修改。共享 `evaluation_read_context` 由根协调 IM13 所有者实现，IM14 仅消费其默认拒绝的可信接口。

EffectAssessment 与原报告精确对应：已测 0／负数保持 known；未测、预测不全、真实 invalidated 各保留不同状态及原因，不把缺测填零。保留 target_gain、retention_regression、实际案例数、未知独立样本数及逐次实耗。统计资格不等于科学真实性、认知内容接纳、表示就绪或实际选择许可。

## 指标、Scope 与原报告

`metric_contract` 只由真实 metric_definitions 的 name/formula_version/unit/denominator_rule/missing_rule/stratification 严格映射到 `EXPERIENCE-MEASUREMENT-0.1/prediction_brier_v1/EM03`；不能以自由字符串代替定义。其他指标或无独立依据的 applicability exemption 保持拒绝，不被改写为零收益。

case_scope 由实际注册 cases/classes、label commitment、common_context 摘要及 training IDs 派生为冻结合法 `effect_statistic`。注册前冒充 retrieval/content/world 指标、或注册后换 Scope／case／候选，均拒绝。基线和候选是预测前保存并实际读取的 without_experience / with_experience_snapshot 两份工件；method_ref 指向原 registration。它们代表原分类协议的冻结 shadow snapshot，不能贴成某个未实际使用的 TL 内容版本。

有完整 pre-dispatch TL binding 的报告才可接入新 record_effect。仅有旧 report Ref 或 checked 标签不足以成为新 TL 效果证明。原 legacy `checked_report/adopt_shadow` 继续走已有独立入口，原有效报告可重算，旧字段和历史不重写。内容忠实、检索、正确使用、一般工具学习收益、总体泛化与语义独立性没有由本项测出。

## 当前使用、资源和保存边界

M14/M03 使用 LocalRuntimeOwners 实际 process/epoch/policy/recipient 随机能力通道，JSON module 标签不授予权限。原来源／snapshot／注册材料、每个预测／实际请求与结果、labels、arm、actual wire 及 metric 全部绑定当前权限、精确版本和 F1；原 source Scope 与统计 Scope 分开。

独立 FreshMeasurementProvider 复用既有干净上下文、tokenizer／硬 output cap、总期限和字节监督。缺真实能力默认拒绝，包括未核实的安装 CLI。合成 fixed-charge 端口只验证接口／封存机制，不是生产 tokenizer 或供应方实耗证明。

预测读机会和模型机会沿原 parent 账户；record／M03 校验读沿原 work 账户逐次实测，不续费、不改变 allocation/caps/deadline。unknown、超额、未对账 dispatch 保留占用并停止后续；真实已执行成本不会洗为零。terminal work 的具名 evaluation_read_context 只允许原账户有限 retrieval；原 activity 真结束、停止、halted、unknown、到期均不跳过，不获得新模型或工具机会。

record、全部最终输入重检、可见性回调后复核、实际保存与 M03 显式 adopt 持相同 gate。M14 不写内容／表示／认知统计版本；M03 独立重算后沿旧 Learning → Cognition.save 写 shadow-only，affects_selection=false。真实 F1／report invalidation／来源 ACL 失效后，既有 `CognitiveExperience.snapshot` 排除已采用样本，历史数值不改成零。legacy 缺 field manifest 时保护采取保守排除，可能比新链 Scope 更严格。

## 核验与界限

先前 63 项（28 新专项 + 35 原测量兼容）在当时源码稳定通过，已保留为 `outputs/acceptance/tool-learning/im14-development/im14-pre-scope-special.json` 与对应日志；因后续 canonical Scope 语义收紧，明确仅为历史开发证据。

当前最终专项：30 个 IM14 场景 + 35 个原测量兼容场景，共 65 项通过，耗时 211.083 秒。`outputs/acceptance/tool-learning/im14-special.json` 记录实际命令、起止时间、本项源码前后 SHA 和完整日志摘要；`source_stable_during_special=true`。完整日志为 `outputs/acceptance/tool-learning/im14-development/im14-final-special.log`。这不是全仓统一源码稳定通过的声明。场景覆盖严格真实封存全链、M03 显式采用、0／负／不全／失效、retention veto、事前／事后 Scope 与输入／组件错配、指标字段、真实原账户／unknown／cap／default-deny、跨键去重、当前 stop／ACL／F1 与晚到结果、原 receipt 缺失、C1 外独立事务保护及 effect 写点回滚。

SDK 图上限为 4096 nodes／65536 rows；legacy 保护 ancestry 深度 16、图 4096，未知或越界拒绝，不假报完整。真实 dataset 的语义独立性和标签科学真实性没有自动证明；真实提供方能力也没有被本专项验证。统一全局门及计划 complete 由根在所有兄弟停止编辑后处理，本报告不代替该门。
