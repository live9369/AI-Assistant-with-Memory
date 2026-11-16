# IM19 机制验收执行设计

状态：实施中。仅新建合成临时命名空间、确定性provider；禁止正式/当前实例读写、真实模型/账户/API及长期服务。冻结contract/storage/Q01—12/DDL不修改。

执行分为受管外层监督、逐实体夹具映射、原G1继承和统一离线回归。IM17静态清单438项/1314计划重复不是执行证据。每条映射必须记录原case、具体输入/变异、真实边界、预期终点、实际断言和证据；一个真实场景可证明多条规范，但重复次数按实际执行计，不按映射条数增殖。没有实现的映射明确unmapped，不能用generic pass补齐。

受管监督使用新解释器、独立进程组和一次性临时根；入口、readiness、结果分开。超时终止整个受管进程组，成功/异常也清理遗留后代。未知外部动作不自动重跑。每次结果以排他创建方式封存stdout/stderr、退出码、期限、入口/就绪事件、结果与临时工件摘要；失败不覆盖。后代逃逸进程组不在此能力承诺内，测试夹具禁止脱离组。

具体故障点必须在真实C1/C2/F1事务写入之前/之后注入，核对整个事务回滚与既有行保留；线程和新解释器跨进程分别握手，不能用线程冒充进程。G1原65场景/60材料使用原实现及实际检查，不删历史失败。

完成门为必需机制实际三次轨迹、全链双向谱系/默认关闭/旧功能保持、原G1复验及公共verify_task IM19全离线回归；缺失或失败阻止complete。统一门禁止import real_model，DIGITAL_LIFE_REAL_MODEL=0，IM20准备测试纳入。冻结源/测试/报告后才运行公共门，期间不改源；source before/after稳定且零fail/error/skip才可complete。确定性重复不构成独立科学样本，真实模型和语义收益不在此结论内。

实施审计确认两处既有范围缺口，并以真实反例/实际路径补齐：

- 明确同一对象及非时间Scope的两个有先后顺序点时刻，观察比较形成temporal_add新目标而不推进旧Scope的head。原版本/原证据保留，M03无review仅candidate；未知、重叠、跨单位/域/主体或旧晚到不推断。新旧源的当前资格分别检查。
- Q03获权复习/再加工原先对previous_work全部拒绝。新增显式ControllerReprocessingAuthor及StrictLearningCoordinator.reprocess SDK：当前真实controller bearer、显式有限policy、不可变grant、previous最终row_revision、精确原source/locator、真实方法plan或当前M03 baseline版本/练习ordinal、原parent及deadline/caps均绑定。默认关闭；不添加自动循环或启动入口。原work终止事实与旧产物不变，未知/耗尽继续阻断；同ordinal换ID不能重用授权。新的受限处理占同一原父总额度，不把处理次数增加解释成独立观察或效果样本。基线变化还要求先前真实比较记录及实际新head，无此证明拒绝；实际本地coordinator默认baseline owner仍拒绝，不能冒称已实现通用基线语义判断。

后续实质审计另补两条：同一原source/digest/locator的单一旧source_report解析错误形成correct提案，独立来源分歧仍conflict，不能猜测旧解析出错原因。原False/0冲突测试改成真正独立源，baseline夹具的native literal改为与实际typed值一致的精确JSON（0/false/null不合并）。

全称反例仅实现显式有限本地来源记录registry的具名owner：controller bearer与当前限定domain policy、native关系及认证membership statement、当前M03 head内结构化全称表达和实际原source定位共同构成可核basis。实际StrictCoordinator显式baseline_refs路径产出restrict Product，再进入M03 candidate，零自动handoff；保留原概括Ref/反例Ref/语义proof派生边与未知剩余子集，不生成新全称。没有任意自然语言量化解析能力，默认owner/权限关闭；示例严格声明原始text值"7"/"10"，不冒称数值转换或外部库存事实。当前版本/来源/实际会员关系在提案提交guard重检，未入场owner和仅JSON/空owner relation不能授权。

Q07-A11最小实现保持冻结TL-TEXT-1：五段中文/英文标题映射固定，claims/scope/evidence等五段JSON逐字保持。显式upgrade SDK以实际controller bearer、当前有限policy和ordinal授权M03新增同decision/content/work/account/deadline的handoff；M04在同series写新表示号，不新建工作/产品/内容决定/收益。已completed work仅在UpgradeSession具名能力中可进行本次M03/M04的准确local retrieval；新model/tool、其他读取、布尔伪capability、原activity终态、unknown/halted/stop/额度/期限仍拒绝。grant/方法/新handoff/表示/正文均保留源派生关系。atomic group升级明确blocked，不拆掉group装完成。当前policy变化、F1、C2写后失败保留旧ready表示且不丢失败机会；同ordinal换新命令复用原义务。

## Final frozen execution gate

The companion `tool-learning-mechanism-bindings-v0.1.json` retains all 438 exact
obligation identities and the 88 numbered-decision projections. Each binding names
its concrete runtime variant or exact existing unittest, source/assertion locator,
injection boundary and required observation. Unique existing fixtures execute
once per repeat, with actual assertion parameters, committed temporary-database
snapshots, bounded blob observations and SQL trace evidence. Shared bindings cite
the same execution IDs; they do not create new opportunities or scientific samples.

The public IM19 verifier writes `coverage.json` in its unique run directory and
requires all 438 obligations, all three repeat references and all 107 decisions.
An empty/static catalog cannot complete the task. Every source implementation
hash is checked, and all earlier offline suites, web checks and ten IM20
preparation tests remain included. `tests/test_real_model.py` is never imported.

Native legacy recall uses registered encoding plus all provenance roles to
separate raw/extracted/transformed/inferred material. Unknown or mixed encoding
is rejected. Only actual execution/recall_episode excludes the exact current
trigger SourceRef; different sources with identical text remain independently
addressable historical reports. Source-report conflicts are tested as an explicit
same-instance M14 comparison/M12 F1/M04 recall/controller-source-audit composition.
Both ordinary source uses are blocked, and current permitted original-source
audit retains both values without rewriting stale derived dependencies. This is
not automatic world-semantic conflict detection.
