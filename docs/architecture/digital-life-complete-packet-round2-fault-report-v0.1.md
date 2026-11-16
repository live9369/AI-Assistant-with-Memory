# PF06 共享读取故障验证报告 V0.1

状态：新增故障验证及必要旧机制定向回归通过。性能门槛、完整Engine输入等价、增长曲线和全量回归留在PF07／PF08，不由本报告替代。

本次未修改产品代码。只使用TemporaryDirectory中新建合成实例、机械权威及替身回调；没有访问正式实例，没有真实模型、网络账户或长期唤醒。

## 结果

新增 `tests/test_tool_learning_round2_faults.py` 共39项。与ReadSet、图共享、严格比较器、原Eligibility、AssemblyGate、引用边界、原始预算及物理meter回归合并：**118项通过，0失败、0错误、0跳过，24.940秒**。测试期间产品、相关测试和验证工具源码摘要前后一致。

运行器：`evaluation/tool_learning_round2_fault_validation.py`。证据：

- `outputs/acceptance/performance-round2/pf06-faults/targeted-named-01/tests.log`
- `outputs/acceptance/performance-round2/pf06-faults/targeted-named-01/result.json`
- 结果SHA256：`2f853dcd6d2fce063c786f2a3a3cf6521c4592426ba235550443e1a4c713f19f`

## 新机制实际覆盖

| 类别 | 已实际验证的行为 |
| --- | --- |
| 初读与图命中后来源变化 | 已撤回源不获准；缓存图命中后revoke／correct／erase仍被epoch／屏障拒绝；读取过程中改变上游epoch仍拒绝 |
| 同连接、跨连接、线程与进程 | 同连接更改不沿用旧图；已建立旧SQLite读快照时，另一连接、另一线程连接和真正子进程提交均拒绝旧阶段 |
| 控制变化 | 图命中后停止、取消、runtime_epoch变更、control.sqlite替换；完整组包后与替身调用内停止，均不能继续使用旧许可 |
| 文件 | 已缓存图所引用blob同inode篡改、blob目录symlink替换；公共Store原始工件缓存命中后的同inode改写与同名inode替换均拒绝 |
| 用途与来源身份 | 图命中后不同purpose／recipient仍调用各自authority；相同原话的两个独立event不合并；不同Scope条件、read/delete及多路径保留；delete路径不冒充支持，erase仍沿删除义务阻断 |
| 原生与观察版本 | 原tl_content的r1／r2和独立支持路径在真实图命中后仍正确区分，撤回r1不误伤独立r2；snapshot bridge图真实命中后，破坏观察事件登记映射仍拒绝 |
| 预算与未知 | 图命中不省略逻辑扫描预算；物理行在原meter逐行收费；部分消费游标不保存完整结果；阶段PRAGMA也计量；过期拒绝；工件读取中断保持未知；原ActivityBudget未知消耗保持全部hold；追踪溢出关闭重用并恢复实际读取 |
| 实际Runtime模型边界 | 原Runtime.assemble/invoke在每次资格检查中实际使用独立共享阶段：完整组包后revoke／correct／erase不进入替身回调；替身已进入后撤回／更正／擦除不返回可用结果，不写thought_results；未知替身异常只进入一次，无自动重试；部分组包不能进入 |

新图故障用例通过拦截`_upstream_current`证明第二次确实命中准备图，而不是只在共享上下文里运行未命中的旧流程。原生修订及snapshot桥也包含实际命中断言。

Runtime机械夹具不使用生产LocalEligibility。验证为其每个`_check`单独安装读集、按可信合成权限准备图，然后执行原Runtime调用前后流程；读集不跨替身callback。这验证调用边界与缓存故障处理，不声明生产owner的完整Engine故障组合已穷尽。

## 发现、修正与保留的失败

首次新增34项运行出现4个测试夹具问题：3个在手动旧读事务内错误调用公开check，被原事务入口保护先拒绝；改为该场景应检验的内部`_check`。1个给meter只留一行但忽略阶段PRAGMA也消耗行数，改为在阶段启动后给定明确的剩余一行。首轮日志保留，第二轮34项通过；补充4项后第三轮38项通过；再增加原预算未知hold成为39项。

首次118项总跑使用stdin主入口，既有spawn进程回归无法加载`<stdin>`导致1项失败，未归因为产品问题。已保存该日志及JSON，改为具有`__main__`保护的命名运行器后118项全部通过。没有删掉失败测试或放宽产品约束来取得通过。

历史日志位于同一pf06-faults目录的first-run.log、second-run.log、third-run.log和final-targeted.log／json。结果以targeted-named-01为准，旧失败保留供核对。

## 覆盖边界

- 本次不是所有故障×所有时刻×所有模块的笛卡尔穷举。撤回／更正／擦除在真实Runtime调用前后均测；控制epoch与文件替换在共享检查阶段测，不声称它们每种都在完整Engine调用后重复。
- 不把机械authority通过当成真实账户授权能力证明。ACL、当前owner、完整高维输入及完整Engine统一覆盖仍须PF07／PF08确认。
- Runtime层本身不落存模型结果；本次断言不能获得返回值且无thought_results，不代替Engine层所有晚到结果处理验证。
- `stat`及data_version是变化探针，不宣称抵御任意系统权限写者的原子攻击。原摘要验证和模型前后边界仍保留。
- 尚未进行真实模型、正式实例、24小时运行、科学效果评价，也未改变IM20—IM24阻塞状态。

## PF05整改后的冻结复验（当前结果）

状态：冻结复验通过。此前118项为整改前历史证据；当前结果为新增44项故障加82项必要旧定向回归，共126项全部通过，0失败、0错误、0跳过，26.827737792秒。原预计123项增加3项，为PF05整改新增的图机制用例；未删旧断言。

产品、相关测试和验证工具源码摘要前后一致，无变更文件。测试进程已正常退出，不与后续PF07计时并行。本次未改产品、未运行完整Engine。

证据：outputs/acceptance/performance-round2/pf06-faults/targeted-frozen-02/result.json及同目录tests.log。

结果SHA256：368e37f989a9d052d0038741cba445c0e29cb9d2b223f94f8a14b4071376de10。

调整及新增：

- 所有依赖图命中的验证先执行两次成功需求，第三次拦截原遍历确认命中；保留原撤回、更正、擦除、预算及调用前后拒绝断言。
- 同连接单改artifacts.hash，旧准备证明不能命中，实际摘要检查拒绝。
- 同连接单改artifacts.storage_ref，旧JSON不能命中，实际摘要检查拒绝。
- 同连接完整合法更换hash、size及storage_ref后，读取新Scope，不能返回旧JSON。
- 直接LocalEligibility.verify及verify_version在已有本地memo后，仍发现其它连接提交并拒绝旧阶段。仅构造合成owner，不执行Engine.prepare或think。

原证据和失败记录全部保留。此前覆盖边界继续有效；126项通过不代替完整Engine输入等价、速度门槛、增长表现或PF08全量回归。

## 两处Engine收集边界补充后的复验记录

Engine资料收集边界的静态审核见round2-read-boundary-audit.md。features共享范围限于本地资料收集，conversation共享范围仅限discovery，后续_recall在边界外；未跨模型、工具或网络回调。原快照写入仍经Store.tx及generation失效。

命名runner已纳入新增test_tool_learning_round2_collection模块4项，定向总数由126增加至130。新增4项实际调用StrictEngine收集入口，未执行完整think；测试中的单表窄选择只验证边界，不被当作完整输入验收。

- targeted-frozen-03：126项通过，25.8405秒；运行时新增独立scale验证工具，source_stable为false。产品和既有测试未变；该结果保留但不当成最终冻结证据。
- targeted-frozen-04：130项全部通过，26.910569292秒；仅scale工具在运行期间最后编辑，source_stable仍为false。结果SHA256：c3b1ada22327066ae293b767c1060146b934bd43c5c061dda5f1bd5fb9bf2b6e。未修改其稳定标记或隐藏变化。
- scale工具负责人确认所有.py定稿后，才启动targeted-frozen-05最终复验；不与完整基准并行。

最终冻结结果：targeted-frozen-05共130项全部通过，0失败、0错误、0跳过，27.18226675秒。192个产品、相关测试及验证工具公开.py文件摘要前后一致，source_stable=true。运行进程exit0已确认退出，随后通知主agent及性能负责人可以开始PF07独占计时。

当前冻结证据：outputs/acceptance/performance-round2/pf06-faults/targeted-frozen-05/result.json及tests.log。

结果SHA256：8dd07e08fef8cd92037888bdbd0259a8d2e2a830890d95f82c5c15dae6a198d9。

后续统一回归以此130项及当前源码为基线，原03／04工具变更记录和全部历史故障日志继续保留。本报告没有把定向边界测试作为完整Engine输入或速度门槛的替代。

## Typed Evidence来源关联修复后的冻结复验（当前最新）

命名runner保留此前130项，并纳入test_tool_learning_typed_evidence模块9项；targeted-frozen-06共139项全部通过，0失败、0错误、0跳过，33.392691417秒。193个公开产品、相关测试和验证工具.py摘要前后一致，source_stable=true。

scale工具摘要精确匹配负责人冻结值：5f6fa20b6fce90c50f4d6c3e01a0779ce3e2532e43157eb69ac7230e33c13fd4。原replay工具未变。本次未改产品，不运行完整think。

证据：outputs/acceptance/performance-round2/pf06-faults/targeted-frozen-06/result.json及同目录tests.log。

结果SHA256：4a10ed03ae3c47e8e5bc6356dd6564f1083885f777ceaa807ca054b987a4d643。

9项实际覆盖：真实PeopleRelations及Memory生成同源资料后，关系features可回溯到原signal；selector不含reason_ref仍保留真实证据来源；可空Evidence FK跳过NULL；错误注册kind、缺失证据、跨实例证据、只有registry没有真实Evidence row、修订属于其它origin、artifact指向错误kind均拒绝。真实关系_features调用不执行模型。

静态审核：仅实际FK目标evidence_items.id按包装来源解析；核对同实例Ref、真实Evidence row、artifact kind和origin_revision owner后，指向真实origin，而不把Evidence包装作为独立事实。未发现新增阻断项。

已确认测试进程exit0退出，并通知主agent及性能负责人放行下一轮非空shared／continuous隔离验证。此前130项和所有历史记录保留；本结论仍不替代完整Engine输入、增长曲线、性能门槛及全量回归。

## 控制材料读取与控制器原生修订解析合并后的冻结复验（当前最新）

命名runner完整保留此前139项，纳入test_tool_learning_control_materials的17项和test_tool_learning_controller_native的22项。targeted-frozen-07共178项全部通过，0失败、0错误、0跳过，41.844468459秒。

195个公开产品、相关测试与验证工具.py摘要前后一致，source_stable=true。scale工具摘要保持5f6fa20b6fce90c50f4d6c3e01a0779ce3e2532e43157eb69ac7230e33c13fd4。此次仅修改命名runner纳入新测试，产品未改；不执行完整think。

证据：outputs/acceptance/performance-round2/pf06-faults/targeted-frozen-07/result.json及同目录tests.log。

结果SHA256：d766b8131f39823a9112a0fdc87d619ad4015eb1d4765561bec69e6b9aa976b9。

原caps和时间份额保持，由控制材料17项及原预算／meter回归继续验证；controller native的9类实际映射、原生source链、错误owner／number／kind、Memory ACL、外部actor及审核用途拒绝均在本轮执行。原139项及全部历史失败／源码变更记录保留，不用新用例替代旧断言。

已通过wait确认测试进程exit0结束，随即通知主agent与性能负责人放行shared03、continuous02和后续PF07。并非完整连续思考已通过，仍待这些后续场景实际验证。

## 配置读取适配器复用修复后的最终定向复验（当前最新）

named08在当前产品上178项全部通过、源码稳定，但新增配置reader的6项位于独立test_tool_learning_configuration_reader模块，未被旧control_materials模块自动包含，故没有把178项声称为184项。该结果及其日志保留。

补齐模块后，targeted-frozen-09完整保留原178项并执行新增6项，**184项全部通过，0失败、0错误、0跳过，52.344924291秒**。196个公开产品、相关测试及验证工具.py摘要前后一致，source_stable=true。scale工具摘要继续为5f6fa20b6fce90c50f4d6c3e01a0779ce3e2532e43157eb69ac7230e33c13fd4。

新增6项实际覆盖：复用配置reader后十次读取不重复扫描DDL而实际行／字节仍计量；phase外新鲜读取发现工件篡改；同一meter无phase仍重新核验配置bytes；未知新表不获得source权限；真实_contexts收集入口配置部分不重新初始化reader；默认_contexts入口table_info为零。原有GoalRegulation相关独立DDL核验仍保留，未通过改caps或时间份额取得通过。

证据：outputs/acceptance/performance-round2/pf06-faults/targeted-frozen-09/result.json及同目录tests.log。

结果SHA256：44708aae425daa2db40143bfaf930efe17cb569354ab6a21531968ac525dfc4f。

已通过wait确认测试进程exit0结束，随即通知主agent及性能负责人放行shared04。本次未修改产品、未运行完整think；shared03计量放大失败证据和全部旧记录继续保留。完整非空shared／continuous及规模、性能门槛仍须PF07实际完成。

## 校验投影与原始配置报告合并后的冻结复验（当前最新）

命名runner保留原184项，加入test_tool_learning_validation_projection的13项与test_tool_learning_controller_events的23项。targeted-frozen-10共220项全部通过，0失败、0错误、0跳过，66.833024834秒。

198个公开产品、相关测试及验证工具.py摘要前后一致，source_stable=true。scale工具摘要仍为5f6fa20b6fce90c50f4d6c3e01a0779ce3e2532e43157eb69ac7230e33c13fd4。

证据：outputs/acceptance/performance-round2/pf06-faults/targeted-frozen-10/result.json及同目录tests.log。

结果SHA256：ae27ed635baec26f91c9bd552276c193d58a3404f136d86c0235ae71b7e17882。

投影用例证明纯校验可读取所需列，但存在任何row_observer时保留完整行及真实collector来源；配置报告用例证明实际8模块collector的原始配置来源和chat回读可以合法核验，未知事件、错误绑定、payload参数／actor／摘要、审核用途和world_claim仍拒绝。原native22项、预算、meter及其它旧保护检查全部保留，没有改caps、时间份额或高维信息。

已通过wait确认进程exit0结束，并通知主agent与性能负责人放行shared05和continuous03。此次不执行完整think，不把220项定向通过描述为完整连续两轮已经通过。此前continuous02等失败证据和所有历史记录保留。

## 计算来源共享合并后的第一次统一复验（失败保留，未放行）

named11已完整纳入原220项与calculation_sharing12、revision_existence10、cached_logical_rows5，启动前assert总数247。运行247项，0断言失败、4项异常，97.845709292秒；源码前后稳定。不能视为通过，未放行PF07。

4项均在旧F1故障场景出现同连接合法提交被误报外部变化：原生r2版本、delete-only用途本应在局部撤回后继续有效；另两项在阶段出口发现相同误报。新readset.read在写事务内发现total_changes后更新阶段状态，而TLStore原始COMMIT未通知明确事务结束，之后observer／WAL变化被误判outside phase。没有放宽旧assert，已交并行readset/store负责人修正受信UoW边界；未知raw COMMIT仍应拒绝。

独立设计审查同时要求：ROLLBACK不减少total_changes，故结束时不能仅靠该计数保留pureRef映射；回滚新工件被清理后也不能保留其tracking/raw证明。缓存清理不得重置meter实际消耗、unknown状态或预算。异常恢复不得掩盖原业务异常，不能自动重放外部动作。

全部失败trace与源快照保留于outputs/acceptance/performance-round2/pf06-faults/targeted-frozen-11/。修复后须重新冻结统一复验，当前最新通过仍是整改前named10，不能把其220项证明套用于尚未通过的新源码。

## 受信UoW边界修复后的统一复验（当前最新通过）

保留named11全部247项并加入实际模块test_tool_learning_owned_transaction_boundaries的14项；启动前加载计数assert261。targeted-frozen-12运行261个唯一test IDs，全部通过，0失败、0错误、0跳过，102.885375375秒。202个公开产品、相关测试和验证工具.py摘要前后一致，source_stable=true；scale工具摘要5f6fa20b6fce90c50f4d6c3e01a0779ce3e2532e43157eb69ac7230e33c13fd4保持。

证据：outputs/acceptance/performance-round2/pf06-faults/targeted-frozen-12/result.json及同目录tests.log。

结果SHA256：4839da57da4b422a1dfcd4dcfd06c5171d35ca10bfa600cd879c855352755809。

原4个F1异常场景在原断言下恢复通过；14项新验证覆盖受信BEGIN前检查、已知COMMIT／ROLLBACK通知、未知结果拒绝、rollback清理纯Ref与未登记工件事实且不重置计量／预算、事务结束旧iterator失效及nested rollback独立代次。全八模块计算内容／来源／selector／native版本严格差分亦在本统一运行通过。

该修复明确区分受信事务结束与未知raw COMMIT，不通过猜测外部变化或重基线来放行。named11失败和全部历史证据继续保留。whole-vs-source范围说明、原caps／.5份额及全部原有源／权限检查保留。

已通过wait确认测试进程exit0结束，随即通知主agent与性能负责人放行原负载shared06和continuous04。本次没有完整think，也不以局部261项通过宣称真实连续第二轮已通过；PF07须继续实际验证。

## 引用kind校验优化后的最终冻结复验（当前最新通过）

完整保留原261项，加入test_tool_learning_reference_kind的8项。启动前加载assert269；targeted-frozen-13执行269个唯一test IDs，全部通过，0失败、0错误、0跳过，104.406017958秒。203个公开产品、相关测试及验证工具.py源码摘要前后一致，source_stable=true。

证据：outputs/acceptance/performance-round2/pf06-faults/targeted-frozen-13/result.json及同目录tests.log。

结果JSON SHA256：60197c4ba593400fe0140547bbfb98a7e60978b9c44f89e7d9cb6eb76c886813。

完整203项源码目录的SHA256（对source_before按sort_keys=True、separators=(',',':')规范JSON编码；source_after完全相同）：d499c86a36457ba5350bc017dfdecc97366ef0c0cb5027cc20240543841d4874。完整逐文件before/after均保留在结果JSON。

下列摘要直接来自本次实际冻结快照，不从后续工作区推测：

| 源码文件 | SHA256（before = after） |
| --- | --- |
| digital_life/application/tool_learning_runtime.py | 22bb29484f1601c8421c3ccde467c2febd107b73ef2b811c8555a776ef2f1b45 |
| digital_life/application/tool_learning_runtime_owners.py | aabec9a846cc3d7bb81d6fdb538e0a146c97e0982f4e556aecfee6b71a75c74b |
| digital_life/application/tool_learning_eligibility.py | 75a4978fd6ca68c834d65d64fc59188417ed96b4a8cf3519611e23bc37c3c838 |
| digital_life/application/tool_learning_engine.py | ff0a499fcdd68b36b941ebd80b906584751b7b63af882df53d7df21a6e13c02c |
| digital_life/application/tool_learning_contexts.py | df194e1c34c76ac47c3bc2bea57a18ee3d2c877dcec5a1ee44eebf34700bd075 |
| digital_life/infrastructure/persistence/tool_learning_store.py | 4bca35a5edb0538bffd4a3279312a63c242e64bb8deb8bbe4837dd2b3cf565b5 |
| digital_life/infrastructure/persistence/sqlite_store.py | 4ee3452b60071c260ab3d52ac3449dea670d3310c49a9daf9b4cf0c9a797ecf1 |
| digital_life/infrastructure/persistence/tool_learning_readset.py | 9f3f8350f09e6f2ce8b9de726eeb9325c259b811e7ac7d94466b16c73393be5d |
| digital_life/infrastructure/persistence/tool_learning_meter.py | acf953e8c02d8383a4834fab02e65d9b799247d8592eaa978661c1863cb2bdc7 |
| tests/test_tool_learning_reference_kind.py | aeafaaa7d42d8b1d2b8ed199fe807507cea3b9fc519f32e4dde223860b981a85 |
| evaluation/tool_learning_round2_fault_validation.py | 95291e2c16a33a8d16e60d73aaa68a5b42642ce37fc2f61c22ebd013b6624e52 |
| evaluation/tool_learning_round2_scale.py | 5f6fa20b6fce90c50f4d6c3e01a0779ce3e2532e43157eb69ac7230e33c13fd4 |

本轮包含全八模块严格内容／来源／selector／native版本差分、原4个F1回归和受信事务14项；新8项与旧断言均保留。原caps、.5份额、Source／Whole范围说明和未知消耗保护不变。此前所有失败及中间证据完整保留。

已通过wait确认运行进程exit0结束，随即通知验收协调者，由其按队列放行PF07 shared07与continuous05；本agent不重复调度。没有运行完整think或正式实例，不把269项局部通过冒称连续完整验收通过。

## 修订映射校验优化后的冻结复验（当前最新通过）

保留原269项并加入实际test_tool_learning_revision_mapping模块9项。启动前加载assert278；targeted-frozen-14执行278个唯一test IDs，全部通过，0失败、0错误、0跳过，109.273296458秒。204个公开产品、相关测试及验证工具.py摘要前后一致，source_stable=true。

证据：outputs/acceptance/performance-round2/pf06-faults/targeted-frozen-14/result.json及同目录tests.log。

结果JSON SHA256：c7289ab1d2ff31733c33da035840160b415367979fe96234eac18e297ac4bd7c。

204项源码source_before规范JSON目录SHA256（sort_keys=True，separators=(',',':')；source_after相同）：cf7fa6b127a869810d14fc4fe54fa1f4509b3802afa2c9de4179226389eb2650。完整逐项前后值在结果JSON，不以报告生成时工作区状态替代运行快照。

| 文件 | 实际冻结SHA256（before = after） |
| --- | --- |
| digital_life/infrastructure/persistence/tool_learning_readset.py | de1e9673e1ba4671e31716ac7bf8b56ebcb0c24b0a50c3b16765f2ea30bd1c30 |
| digital_life/infrastructure/persistence/tool_learning_store.py | f744dd170a243e6a77cc647c000ee42a379053b67d0e38dfbfbe6e2d4d89cc04 |
| tests/test_tool_learning_revision_mapping.py | d7d8d21f7dc6c312eab778c7d0b62e24a75cf0466c909360ca1789ae229abad0 |
| evaluation/tool_learning_round2_fault_validation.py | ed6935e1217eb0d518068f196bc7354a50495936d2919dc4e46cbe7a5df2796b |

readset与TLStore摘要在起跑前亦核对与交接值完全一致。旧4处F1故障、事务边界14项、全八模块严格内容／来源／selector／native版本差分及原有权限／计量断言全部保留。原caps、.5份额和whole-vs-source测量说明不变，历史失败及所有中间记录未删。

已通过wait确认进程exit0退出，随后仅通知验收协调者按队列继续PF07，无重复调度或产品修改。本次不执行完整think或正式实例，278项局部通过不替代后续真实负载和连续场景结论。

## 最终分层修复及PF06 named15组合复验

原完整验收1639项的1个架构FAIL和1个旧诊断夹具ERROR保持封存，原IM19结果未改写为通过。此次产品仅修改application/tool_learning_contexts.py与infrastructure/persistence/tool_learning_meter.py：精确DomainReadCollector类型、原on_row方法、meter与busy认证移到应用入口，基础设施仅保留私有受管ContextVar状态，未知或替换observer仍走保守分支。没有反向导入、动态导入规避或任意类型注册。设计见round2-observer-layer-boundary-fix.md。

测试仅更新calculation_sharing、cached_logical_rows、revision_existence的helper导入及performance_diagnostic真实临时Store/phase夹具；新增unknown/subclass用例令callback self/method及busy匹配，仍拒绝非精确类型。诊断保留原命中、图保留、超限、计数全部断言，增加真实Row与没有二次物理SQL断言。无其他产品修改。

先运行相关完整模块80项，43.606秒、0失败/错误/跳过；增强的未知/子类单项另通过。随后保存统一runner再冻结源码，named15保留原278项，加未知/子类1项、architecture完整5项、performance_diagnostic完整3项，loader断言287个唯一测试。结果实际287项全部通过，0失败、0错误、0跳过，进程exit0，107.553941125秒；205个Python源码输入前后完全一致。包含八模块内容/来源/selector/native-version严格差分及原故障校验，没有运行完整think、真实模型或正式实例。

证据：outputs/acceptance/performance-round2/pf06-faults/targeted-frozen-15/result.json；SHA256：15e008964c79e77abdcbe013f95b166423d63884c8627ea274e8c89ff9200e9f。原失败日志和结果全部保留。此次107.55秒是测试套耗时；原117.55秒仍仅代表修复前冻结源码的完整负载测量，最终源码完整think计时未重测，不混写为本次性能结果。原机制1485条记录与原完整套结果由协调者按源码影响范围组合审计；本报告不冒称重新运行1639项完整套。
