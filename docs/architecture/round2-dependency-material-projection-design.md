# 依赖图内部材料投影设计

状态：已实施，小端口10项及统一333项（含八档全8模块差分）通过；原连续第二轮待根复验。2026-11-11。

## 范围与不变条件

原连续第二轮目前受assembly字节预留限制。`tl_dependency`的SQL整行含技术登记时间`recorded_at`（24字符）及固定为1的`schema_revision`，但`ToolLearningEligibility._metadata`只使用id/instance、consumer/source/revision、relation/purpose/epoch、field_path和metadata_artifact_id；实际Scope、expected token及时间/条件在被hash核验的完整原件内，必须全部保留。

只给`_upstream_current`内部遍历增加独立固定query名`consumer_dependency_materials`，SELECT上述全部绑定列，不返回这两个未消费的技术登记列。数据库仍保存它们，不改schema或存储，不裁剪传给模型的任何字段，不聚合/压缩行逃计量。

原`consumer_dependencies`完整行目录和API不变。只有存在实际PhysicalReadMeter、且实际`row_observer is None`时才选新内部目录；没有meter、真实领域observer、未知observer（包括既有busy收集器）均原SELECT *。不安装观察器抑制状态，不把`logical_observer_required=False`代替“无observer”。

## 查询及缓存

新固定SQL仍同instance/consumer谓词、ORDER BY id及原LIMIT参数。逐行scan/items与max_rows/max_nodes、read/delete路径、循环/多路径逻辑预算全部照旧。每个实际返回行按实际编码字节计量。

独立query名产生独立缓存key，不能让完整行消费者命中缺列材料。新目录与原有有界多行目录采用相同完整结果/前缀复用、同一4096key/4MiB计量与所有原失效条件。切换observer时选择原完整目录，graph/prepared memo仍按既有observer保护拒绝捷径。

`_metadata`行绑定key随实际完整/内部材料行分别形成；所有consumer/source/ref/expected/epoch/revision owner/Scope/原件identity和hash核对保留。没有缓存授权判断，没有跨写或回滚保留例外。

## 验证

1. 原完整SQL与新内部SQL，同一实际tl_dependency行逐列核对：仅差recorded_at/schema_revision，其余全部值精确同；实际字节差必须来自真实返回列，行数相同。
2. 无meter及任意observer仍原完整行，全部字段/行通知序列精确一致；observer从None切入后不能复用内部缺列key。
3. `_metadata`输出、当前epoch、revision owner、Scope与完整原件hash反例，循环、多路径和read/delete及逐行max_rows预算沿用原严格故障集，并新旧图结果差分。
4. 新完整/截断/prefix缓存目录界限同原目录，取部分行不能偷偷预读；同连接写、回滚、外部/控制/原件变化沿用原失效与拒绝。
5. 全8模块增加仅关闭内部投影档，与全开档精确比较全部values/fields/来源与权限/Scope/selector/native版本/UUID/cap，记录真实scan和bytes。之后才统一冻结与原连续17测试。

此设计只去掉内部校验未用的两个登记技术列，不移除来源的科学时间/Scope/条件，不提高任何资源上限。

## 已有小端口证据

3条真实依赖行，完整SELECT实际1253字节，内部材料1070字节，scan/items仍3。逐列核对只差recorded_at/schema_revision，其余字段和值完全相同。净少183字节（每行61），无聚合、压缩或预读。

10项3.906秒通过，覆盖无meter与原完整API、unknown observer全行序列和切换后独立cache key、循环/read-delete/多路径与逐行node/row预算、metadata完整Scope/expected/epoch/owner绑定、原件篡改即时拒绝、完整/prefix与部分迭代、同连接追加后回滚、current epoch更新后拒绝。

首次实现直接访问meter.row_observer，碰到PhysicalReadMeter默认没有该属性而报AttributeError，已按项目原语义改为getattr(...,None)；首轮错误日志保留。第二轮篡改测试只捕获即时拒绝，没有捕获阶段退出再次检测篡改的Conflict，已让断言同时要求即时拒绝及退出拒绝，原错误保留；未削弱产品保护。

证据在`outputs/acceptance/performance-round2/continuation/dependency-material-small-port-02/`、`dependency-material-small-port-03/`及后续统一`faults-03/`；统一纳入新snapshot10、投影10和scale诊断4，不复用旧309项结果冒称新源码已过。

## 最终统一结果

333个唯一测试实际全部通过，307.759596334秒，0失败/错误/跳过，210个源输入前后稳定，exit0。八档全8模块全部values、features、fields、live、新字段、bundle依赖、snapshot selector/value/native、来源与权限调用序列、cap及UUID精确相同。

在其他新边界和完整行共享均开启的前提下，仅切依赖投影：`dependency_projection_off`实际59734行/15492733字节、观测16.2195秒；全开实际59734行/14966486字节、观测14.5859秒。净少526247字节，未减少依赖行或逻辑路径；观测时间不用于最终三次性能门槛，也不外推完整assembly必然通过。

原始八档全量payload与结果：`outputs/acceptance/performance-round2/continuation/projection-eight-way-01/`。统一结果`faults-03/result.json` SHA256 `a453dfc87ed7820faf4a058b55dfde56ce53937ea5766ef5598660ca4a23e565`。全部CPU已退出，Python源码冻结；真实连续第二轮仍需根另行运行。
