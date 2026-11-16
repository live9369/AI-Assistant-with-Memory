# 第二轮共享读取边界：前置代码审查

状态：只读审查材料，非PF02／PF03定稿。须结合PF01实测选择优化点。本次未运行实例、模型或测试，未修改产品代码。

## 结论

可以在同一检查阶段共同读取固定来源材料，但不应把一次`_check`的允许结论作为其它用途的允许结论。优先优化确定的数据库事实读取与依赖元数据解码；每个字段的来源绑定、用途、接收者、当前epoch、屏障和执行状态仍独立检查。不能直接扩大现有缓存的生命周期。

## 现有代码事实

| 位置 | 当前行为 | 扩展时的限制 |
| --- | --- | --- |
| `tool_learning_meter.immutable_reference_boundary` | 持有dispatch gate，ContextVar保存引用映射；本连接`total_changes`变化清空 | 只覆盖本连接写入；gate只阻挡遵守同一gate的写者，不能阻止原始SQL或文件改动 |
| `LocalEligibility.verification_boundary/_already` | 本地owner的version/source核对按完整参数与本连接写入计数记忆 | 不能当成主库／控制库／文件仍未变化的证明；新共享层不能进一步放大该假定 |
| `ToolLearningEligibility._upstream` | 每个consumer依次读依赖，读取元数据，保留版本、scope、delete路径与限额 | 同根图可共享原始行及已验证元数据，不能删除返回项、路径或少扣逻辑遍历预算 |
| `_metadata` | 操作内元数据缓存，以依赖行全部内容为键 | 命中并不重新读文件；不同依赖行或变更阶段不能仅按artifact ID拼接 |
| `ToolLearningEligibility.callback` | authority callback后重新check；actual callback后再check及request context | 回调是新鲜度边界，不得携带前一阶段允许结论或共享读集跨过它 |
| `Store.control_reader/LocalRuntimeOwners.control` | 控制库按dev/ino重开，当前读process／epoch／stop | 控制库状态独立于主库；不可被主库写计数代替 |
| `ToolLearningStore.read_artifact` | 受限目录与O_NOFOLLOW读取，size/hash检查；meter内缓存原始bytes | 缓存是完整性已核验的材料快照，不代表磁盘路径后来没有替换／篡改 |

## 建议的最小安全方案

1. 共享层是**阶段内、按需、有上限的事实读取表**，不是全局查询缓存；阶段必须有明确进入、退出和异常清理，复制context之后不能复活关闭的阶段。
2. 用固定白名单查询接口表达事实：来源登记、指定版本、指定consumer的有序依赖行、指定来源的屏障行。查询键保留实例、表／查询类型和完整参数。未知查询、写SQL、回调不走缓存。不要用任意SQL字符串自动缓存所有SELECT。
3. 先完成读取范围授权，再读指定来源；不预扫全库、不跨recipient／purpose合并授权。共同原话可以共享读取，但每个记忆、关系、目标仍保留完整消费关系。
4. 主库事实应受同一SQLite读事务／快照约束。新阶段重新建立读集；任何本连接写入直接清空或结束共享阶段。不能为了共享开启跨模型或工具调用的长事务。
5. 其它连接／进程变化必须有独立检测与验收。`PRAGMA data_version`可帮助发现同连接观察到的其它连接提交，但只在同一连接比较，并非所有库／文件变化证明；事务内快照不能代替下一阶段新鲜读取。主库文件身份变化、控制库代次变化或无法证明一致时终止本阶段，重新从原安全入口检查或拒绝。
6. `control.sqlite`、WAKE_DISABLED及restore锁继续实时检查；不得从数据库事实表返回缓存的执行许可。必须保留回调后的检查。不可协作的文件变化需要独立文件身份／内容核对；仅比较mtime／size不能证明内容未变。
7. 对artifact，若本轮要跨更多调用共享，先明确“本阶段固定材料”与“下一次实际使用前当前来源”的区别，保留原始工件的摘要与来源绑定。文件替换／损坏的注入必须在真实入口验证，不应只测试内存函数。
8. 每次实际SQL返回行和实际文件读取仍通过原meter；缓存命中不假造物理读取，但依赖扫描的逻辑节点／关系预算按原流程扣减。批量结果应在拿出每行前执行原余额检查，不能用`fetchall`先绕过计量后再检查。
9. 先采用按需重复键合并，再评估小批量同表取行。大规模预取可能读取原路径并不需要的数据并超支；没有PF01证据前不建议一次把所有来源和工件装进内存。

## 必须保留及新增的测试入口

已有入口可复用，不应声称目前已经覆盖跨进程原始SQL和文件变化的全部新要求：

- `tests/test_tool_learning_runtime.py::ImmutableReferenceBoundaryTests`：引用缓存不缓存epoch／barrier，本连接映射变化清空。
- `tests/test_tool_learning_eligibility.py`：authority callback stop、same-thread F1、thread／process gate、上游barrier、cycle、行上限、很多input后的根barrier。
- `tests/test_tool_learning_performance.py`：原／新upstream完整重复项、路径、cycle与limit差异比较。
- `tests/test_tool_learning_runtime.py::OriginalActivityBudgetTests`及相关actual read测试：未知消耗、工件大体积预检、失败字节、暂停期实际读取与elapsed归属。

新增应分别验证：

1. 相同原话被多consumer引用，读取减少但authority调用与输出绑定没有少；同文不同原件、不同版本／scope／purpose／recipient不误合并。
2. 本连接变更；其它连接及真正其它进程提交；主库路径替换；控制库变更与替换；blob同名替换、同inode内容改写及symlink。
3. 每种变化分别在阶段中、组包后、模型前、替身模型返回后发生；旧允许结果不能穿过边界，撤回内容不能晚落存。
4. cache容量／分批边缘、预算刚好足够与少一项、未知文件读取、部分读取／异常退出、嵌套阶段与复制ContextVar后使用。
5. 原／新对照不得只比计数；比较有序关系、scope全内容、版本、业务内容及拒绝类别；随机技术ID只做明确映射，不能擦除主张时间和条件。

## 留给PF02／PF03确认

- PF01是否显示SQL往返还是JSON结构／解码／当前owner核验占主要独立耗时？
- 选择事实查询memo、consumer邻接行共享，还是批量查询；哪个能在原cap内降低实际读量？
- 文件和非协作写入要求怎样落在真实入口：立即拒绝、结束阶段再检查，还是完全禁用该来源共享？
- 阶段边界能否以现有verification boundary直接表达，还是需更细分（不得凭命名认定其安全）？

以上为实现前审查意见，并非已经通过的验收结论。

## PF02／PF03设计独立复核

复核对象：`digital-life-complete-packet-round2-design-v0.1.md`。

PF01证据中总独占耗时154.409588209秒，信息收集2.833900050秒、组装1.295051415秒；commit的407350条SQL中403913条重复，input_use的191304条中187867条重复，与设计描述一致。来源检查合计约146秒。明确20%耗时和20%实际行读取改善门槛、原cap不动、每消费者逻辑预算不动，是可验收的条件。

设计已正确选择只在本地只读boundary安装按需ReadSet、不跨未知callback共享、不在旧SQLite快照清缓存后继续应付外部提交。该设计可进入PF04实施；实现仍需验证边界闭合，尤其是本地旧memo也要在命中前经过相同的新鲜度探针。

完整输入验收仍存在一个待解问题：原benchmark的独立实例具有随机ID、SQLite默认真实时间、时间导出的动机和deadline值及机器空闲磁盘数值。仅比较175字段／168依赖不能证明完整业务内容一致；不能用删除全部时间与摘要的normalizer掩盖差异。

为此新增严格工具 `evaluation/tool_learning_round2_compare.py` 和8项验证 `tests/test_tool_learning_round2_compare.py`：

- 比较完整packet与manifest，先用原`validate_manifest`验证原始摘要和覆盖。
- ID转换只接收明确的一一映射和逐个JSON pointer证据，不自动按字段形状、文本或顺序猜测。
- 原始绑定验证后，仅根据转换后的完整packet重算manifest派生的packet_digest与field.digest。其它摘要差异照实报错。
- 时间、Scope、条件、版本、cap、数组顺序、业务数值、空项均不忽略；类型变化与缺字段失败。
- 本工具不能凭映射声明两个独立夹具等价；所有采用的映射路径在报告公开。

建议PF07的强比较使用独立进程的固定合成时钟、UUID序列和磁盘探针值，且保留真实monotonic耗时和原账户计量。Python utc固定尚不足：SQLite DEFAULT strftime(...,'now')、StateCollector的datetime.now都必须有明确合成输入。旧源码与新源码使用完全相同的夹具及合成输入；不修改生产源码。另以真实时间单独重复性能测量，报告其派生余额差异。若无法建立可靠重放，应保留逐路径差异、如实标记完整输入等价尚未完成，不能用数量比较替代。

## PF04产品代码静态审查（实施中）

范围：只读审查当时的ReadSet／Store／meter／本地owner实现，未运行完整Engine、未替代PF06实测。PF05并行修改可能使下述行位置变化，修复后须复核。

设计已落地的正确方向：主连接与独立observer分别观察data_version，外部提交不在旧快照内清空重读；主库及控制库身份／状态探针；blob父目录身份；关闭ContextVar读集；逻辑预算与实际读取计量分开。新图缓存保存来源事实，不新增通用authority许可缓存。

发现两个需要解决的阻断候选：

1. 当时`ToolLearningStore.read_artifact`已调用track_location，而`Store.read_artifact`、`Store.artifact`的已有文件命中路径未跟踪。两者可从同一meter.artifact_cache获取资料；新阶段保留物料缓存时，未注册的文件不在checkpoint的blob清单里。应将追踪放到公共缓存读写入口，或补齐每个Store路径。不能只证明TL入口安全便认定全部缓存安全。
2. `clear(preserve_material=True)`保留metadata_cache。但`_metadata`缓存的不只是JSON bytes：还包含当次Ref验证、版本登记与revision projection核对。依赖行内容不变而本连接修改登记／版本投影时，相同cache key可跳过这些核验。建议写入／事务generation变化后清metadata验证缓存，或将其明确拆为仅JSON解码共享、映射核对仍每次执行。原始工件bytes在完整文件追踪下可以独立保留。

其它待验收事项：

- `LocalEligibility._already`自身当时没有checkpoint；直接verify调用路径需保证同等新鲜度检查，不应仅依赖常见`_check`外层。由`tool_learning_recall._walk_source`直接verify的路径须核对。
- 4MiB是ReadSet编码facts／graphs及文件身份记录上限，不是所有Python缓存和复制对象的总内存上限。meter raw／metadata和owner memo有独立生命周期，报告应准确说明；追踪溢出后禁止命中不等于禁止继续保留未跟踪bytes。
- 跟踪blob父目录已覆盖其替换；仍须在PF06实际验证数据库／WAL／控制库、root及父目录改动、不同进程提交，以及回调后入口。
- stat和data_version探针不宣称对具有任意系统写权限者构成原子锁。文件原始fd读取／hash验证、阶段出口核验和模型前后原边界仍必要。
- exact LocalEligibility限制未知authority不获得共享是正确方向；若发生本地可写authority回调，必须失效，不能把“本地”当作只读证明。

本节仅审查发现，不将未实测路径标为通过。

## Engine资料收集边界复核（PF06第三次冻结）

只读复核tool_learning_engine.py两处新增verification_boundary：

- `_features`：在原`_read_operation`安装的物理meter内部，共享范围只含原表选择、来源登记／观察快照、本地权威及资格核验。没有provider、模型、工具或网络调用。退出时先关闭verification/readset，再退出原read operation并结算，不把共享读集带入账户结算或下一次思考。
- `_conversation`：共享范围止于前序活动／线程绑定／候选记忆发现。`_recall`位于with之后，不持有此前读集。原dispatch gate为可重入的本地协作锁，没有新增跨模型的长事务。

收集快照的本地写入仍通过Store.tx及已测试generation清理；新边界没有把这些写入默认为不变事实。本次静态审查未发现两处范围扩展的阻断项。该结论不替代PF06当前冻结复验，也不等同完整think吞吐量验收。
