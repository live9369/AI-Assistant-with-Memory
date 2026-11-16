# PF06 共享读取故障验证设计 V0.1

状态：实施前故障设计。只创建临时合成实例，使用机械权威和替身回调；不打开已有实例、不调用真实模型。不执行长期唤醒。

## 验证原则

每个新增验证必须实际进入PhaseReadSet。涉及图重用的验证必须证明成功图已准备并命中，再注入故障；不能仅把原无缓存测试结果引用为共享机制证据。物理查询／文件读取继续使用原meter，逻辑遍历上限不变。预期异常必须来自真实入口，测试不能把所有异常笼统算通过。

## 故障矩阵

| 类别 | 夹具与入口 | 注入点 | 必须结果 |
| --- | --- | --- | --- |
| 来源撤权／更正／擦除 | F1原机械构造、Eligibility.check | 初读前、图命中后、authority读取中 | 当前epoch／屏障仍拒绝，不使用旧图许可 |
| 跨连接／进程 | 实际SQLite WAL读事务、第二连接与spawn进程 | 已缓存来源图后提交 | 原阶段拒绝，旧快照不能清缓存后继续 |
| 控制停止／代次／替换 | 原control.sqlite、已缓存图 | 检查中、组包后、调用前后 | 缓存不覆盖当前控制；返回不获准使用 |
| 文件变化 | 原登记blob、父目录、数据库路径 | 工件已读取／图已缓存后 | 同inode改写、同名替换、symlink和父目录替换拒绝 |
| 独立用途 | 同文不同原件、Scope、purpose、recipient；read/delete多路径 | 缓存命中前后 | 图准备可以共享，资格仍分别检查，erase沿delete路径拒绝 |
| 原生修订／观察桥 | tl_content r1/r2与runtime_events snapshot桥 | 图命中后来源撤回、注册映射变化 | 修订不串用，历史与当前不混淆，原映射核验保留 |
| 部分与未知 | 原meter、依赖游标半读、文件读取失败 | 初读中／预算边缘 | 半读不记完整结果，未知保留未知，真实行仍计量、低预算拒绝 |
| 模型边界 | 原Runtime.assemble/invoke，替身callback | 完整组包后、调用前、已进入callback后 | 调用前拒绝不进入；调用后拒绝不返回可用结果，不重试、不写thought_results |

Runtime机械夹具原先没有本地owner verification boundary。新增验证在每个资格检查入口单独创建共享阶段并预热该图；原invoke负责调用前后检查，阶段不跨替身callback。该夹具证明真实Runtime.invoke的新共享路径，不冒充真实模型能力或完整Engine吞吐量。原实际owner的完整Engine验证由PF07负责。

跨进程采用spawn或独立Python子进程，不fork持有SQLite／线程状态的解释器。线程测试使用独立SQLite连接，不在其它线程使用现有Store连接。文件破坏只发生在本测试TemporaryDirectory内。

## 交付与限制

交付tests/test_tool_learning_round2_faults.py、逐项测试输出及报告。保留失败，发现产品问题由主agent修复后定向复验。必须分别报告已测和未测，不把旧测试无缓存路径计入新路径覆盖；不做全套1398回归。

## PF05整改后的补充验证（待产品冻结后执行）

整图采用二次需求准入：首个成功遍历只记录受限需求，第二个同root成功才保存完整图，第三次及后续才允许命中。故障夹具预热两次后再拦截原遍历以证明真实命中；不减少原故障断言。

新增5个反例：同连接修改artifacts.hash、storage_ref后旧JSON／准备证明不能命中；完整hash／size／位置合法重绑定后必须读取新Scope；直接LocalEligibility.verify及verify_version端口在owner memo命中前也必须发现另一连接提交。直接owner测试只构造原合成StrictEngine夹具，不执行prepare／think。

本次补充只改测试与设计，未执行验证。产品冻结通知后再运行118项与5项新增（预计123项），保留原118项证据为历史版本，不冒称它覆盖整改后的实现。

补充执行结果：收到冻结通知后，targeted-frozen-02新增44项故障及必要旧定向套共126项全部通过，源码稳定。见报告当前结果小节。此前待执行字样为实施前历史记录。

第二处范围补充执行结果：Engine资料收集4项已纳入命名runner；targeted-frozen-05共130项全部通过、源码稳定，已确认测试进程结束并放行PF07独占计时。

Typed Evidence增量：原130项全部保留，纳入真实PeopleRelations／Memory证据关联的9项验证；targeted-frozen-06共139项通过、源码稳定，详见报告当前最新小节。未执行完整think，后续非空状态验收由PF07负责。

两项整改合并后：新增控制材料17项与控制器原生修订22项并保留此前139项，targeted-frozen-07共178项全部通过，source_stable=true；没有执行完整think，测试进程结束后放行PF07。
