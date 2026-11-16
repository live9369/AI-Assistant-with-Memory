# 连续两轮的低开销receipt计数模式

状态：先设计后实现；只改独立诊断脚本和其小测试，不改产品、原scale或主replay。日期：2026-11-11。

case5已定位首轮173次发证/接受/提交，而第二轮106次全fallback。根因修复后，需要确认真实两轮命中，但无需再承受17个方法的高频计时开销。

诊断脚本新增自有`--counters-only`。由诊断解析器移除此flag，再把其余原scale参数原样转发。该模式仍等原scale固定世界后安装，**仅包装StrictEngine._read_operation上下文**，记录固定阶段标签/序号、少量阶段时间与Store._input_certificate_stats固定整数的前后/delta。禁止安装LocalRuntimeOwners、Eligibility、PhaseReadSet、ToolLearningStore、ManagedConnection的17个方法包装；不调用SQLtrace或修改任何hook。

阶段时间只由进入/退出取样，原meter和账本照常。方法聚合仅剩`unattributed`时间桶，不能伪报17方法热点。报告明确`measurement_mode=counters-only`和实际安装清单，仍不是正式无观测三次性能样本。业务结果、raw输入输出、失败进度仍完全由未修改的scale保存。

新增两项小测试：其一确认自有flag不传入scale且原参数次序/值不变；其二用真实隔离小登记确认仅阶段包装、无方法事件，receipt仍发证/接受/提交且fallback=0。保留原5项测试。完成后冻结.py，等待主任务触发，不运行完整两轮。

## 强材料保留分支的可选计数

额外只读支持产品实际提供的`strong_material_accepted`和`strong_material_committed`整数。原attempted/issued/accepted/fallback/committed五键仍必须完整，不能以新字段替代。旧版本或旧fixture缺少新键时，原快照仍为observed，缺失新键保持absent，不能填0或把整个原快照降为unknown。阶段delta仅在前后都实际观察到同一整数键时计算；若仅一端存在，保留该端事实而不猜测另一端为0。

这些值由产品实际强材料接受/提交分支维护，诊断只读取，不把普通receipt接受误计为强材料保留。小测试分别验证旧五键原行为与新可选字段原值/delta；不改产品或原scale/replay。

## 文件签名lease的可选阶段统计

仅在阶段进出时读取产品实际提供的`Store._file_signature_stats`中整数`minted`、`hits`，报告为阶段的`file_signature_stats.before/after/delta`。缺少该对象或某个整数键则保持absent，不猜0；delta只计算前后都观察到的键。原receipt七键处理规则不变，不添加任何逐次文件或方法包装，不安装trace/observer，不影响实际lease选择。产品负责在真实mint/最早track_location复用分支递增，诊断绝不代替产品推算命中。

## GraphMaterial的可选阶段统计

同样只读`Store._graph_material_stats`，报告为阶段的`graph_material_stats.before/after/delta`，固定四个技术整数：`eligible`是实际首次策略判断次数而非unique根数，`stored`是实际入场次数，`returned`是完整GraphMaterial解码查找返回次数，`used`才是原逻辑scan预算足够且实际走命中消费分支的次数。不能以returned推定used，更不能把任一计数解释为授权/来源检查被省略。

对象或单键缺失均保持absent，不填0；旧fixture有前三键、无used时仍保留已观察前三键。delta仅对两端都有的整数计算，不新增逐调用包装。产品维护真实分支计数，诊断只在阶段进出复制这些Python整数；原receipt/file统计与主replay/scale保持不变。
