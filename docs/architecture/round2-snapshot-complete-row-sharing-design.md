# Snapshot完整原始行复用设计

状态：已实施，小端口10项及后续统一333项（含八档全8模块严格差分）通过；原真实连续验收尚待协调。2026-11-11。

## 本次边界

原17历史连续第二轮在第二次优化后仍触原assembly字节上限：212867925超过212867606，scan726772低于797601；前序calculated/live已降至181408/77241行。失败处是register_input提交检查读取consumer_dependencies，不等于该SQL独占总开销。

上轮只改LocalRuntimeOwners.source_access的完整行。SourceSnapshots._origin验证过source_access后又Store.row完整读取相同行，_native再读相同行CAS，LocalSnapshots.dependencies再读完整行。仍必须保留所有原值/selector/CAS/权限调用，不能裁列或省掉final校验。

## 最窄入口

SourceSnapshots增加私有完整行读取入口，仅满足全部条件时复用现有owner._source_row：

- 实际self是精确SourceSnapshots、实际authority是精确LocalSnapshots。
- authority.owner是精确LocalRuntimeOwners，其store与self.store同一对象。
- owner.snapshots正是self，owner.snapshot_authority正是实际authority。
- 当前store已有PhaseReadSet；不隐式开全局或跨阶段缓存。
- `logical_observer_required()`为真则完全走原Store.row且不新增checkpoint，保留未知/领域observer原完整SQL行和回调序列。只有无observer或既有精确busy技术路径才启用，不新增任何观察抑制状态。

缺任一条件就原Store.row。不能凭owner标记字段单独认证，不能让实际authority被替换后仍共享。

通过检查后，在每次取共享完整行之前执行实际phase.checkpoint(include_artifacts=True)。因此verify_source、verify_capture及verify_dependencies等callback之后的origin/native读取不会沿用旧DB/control/file状态；同连接变化全失效，外部/控制/file变化按原拒绝。capture事务仍原样，final origin及CAS比较仍原样执行，不跨写保留。

LocalSnapshots.dependencies仅在实际self/owner/snapshots绑定一致时委托同一入口读取该来源完整行；未知authority或没有阶段直接原SQL。所有后续外键、evidence、递归identity capture、producer lineage和每项资格核对不变。

## 验证与停止条件

1. 小端口在同一个合成Store中切原Store.row与新入口，逐字段比较origin完整selector/CAS及dependencies，记录实际SQL/scan/bytes。每次verify_source/owner.check照旧。观测真实/未知observer完整行序列，返回dict修改不能影响后续。
2. callback后同连接源revision修改、外部提交、控制停止、配置/被跟踪原件变化，必须在该次capture提交前拒绝/回滚；unknown/subclass/owner/store/snapshots/authority别名不一致不优化。
3. 若额外完整checkpoint的stat成本使小端口或全8差分显著变慢，先报告实际净收益/成本，不弱化freshness或继续盲加缓存。小端口时间不充当最终无观测计时。
4. 有真实净少读后才纳入全8模块严格差分与统一故障，再由根运行原连续17负载。全部cap/份额、特征、原件、权限、selector/CAS、事务和observer不变。

此设计不包含写集证明、事务批量重排或预算扩大，不提前宣称第二次模型调用已发生。

## 小端口与严格差分结果

新增10项3.302秒通过：完整selector/CAS/权限调用一致，返回dict独立性、未知authority/子类/owner别名不一致回退、未知observer完整原行及全序列精确同、dependencies完整lineage同、final source callback改revision及被跟踪原件在capture提交前拒绝/回滚、fixed读取旧事务快照期间外部提交拒绝。

首次外部提交测试尝试在capture的BEGIN IMMEDIATE内部另连接写，SQLite按原写锁正确报database locked，原错误保留。测试改为真实fixed读取路径持有旧BEGIN读快照时外部提交，才是可发生的WAL场景，保护通过。没有降低产品锁或断言。

32次同一_origin及_native探针：原65完整来源SELECT/84398字节，新1 SELECT/6126字节，actual scan均200（新增checkpoint的PRAGMA实际行仍计量）。观测循环约31.2→32.2毫秒，额外约1毫秒，无显著净成本结论外推。

七档完整8模块差分134.333秒通过，全部values、fields、live、bundle依赖、来源/权限调用、snapshot selector/value/native、cap与UUID精确一致。只切snapshot helper：旧端口实际59732行/15895744字节、观测16.2393秒，新59732行/15492708字节、观测14.1333秒；少403036字节，未出现明显checkpoint成本回退。观测时间不用于最终无观测三次门槛，0.4MB收益也不能代替连续第二轮实测。

证据目录：`outputs/acceptance/performance-round2/continuation/snapshot-row-small-port-01/`、`snapshot-row-small-port-02/`及`snapshot-row-seven-way-01/`全量七档payload。统一冻结前尚须纳入新10项及scale诊断4项，不提前标整体通过。

后续与纯内部依赖投影共同统一：333个唯一用例、307.759596334秒、0失败/错误/跳过，210份源输入前后稳定，exit0。包含新snapshot10、投影10、scale诊断4、原有故障和八档全8模块严格差分。最终结果`continuation/faults-03/result.json` SHA256 `a453dfc87ed7820faf4a058b55dfde56ce53937ea5766ef5598660ca4a23e565`。全部CPU退出，所有Python文件冻结；此证据仍不能代替真实连续第二轮。
