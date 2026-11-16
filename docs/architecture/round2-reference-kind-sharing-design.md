# Ref登记种类材料共享设计

状态：设计定稿并实施，8项新增测试及相关局部回归合计123项通过，等待统一PF06和完整场景复验。

## 目的与精确范围

共享06在原assembly bytes预留边界拒绝。validate_ref的object_registry SELECT *实际上只使用row.kind；instance和id已由WHERE固定。ref()等调用已使用同谓词facts('source_kind',id)，可共同读取同一实际kind材料，减少同对象不同Ref slot／reason／revision检查时的重复元数据读取。

仅logical_observer_required=False的纯校验路径复用source_kind；这包括无observer，以及exact DomainReadCollector在明确受信busy作用域内原on_row立即return的技术准备。logical_required=True（未知observer、被替换observer、真实领域捕获busy=False）继续原SELECT *，保留所有返回UUID／selector来源。没有外部省列开关。

不缓存Ref本身的“有效”结论：每次仍验证Ref结构、同instance、value.kind及expected_kind。unknown／known及不同reason slot可以共享数据库kind，但完整revision分支、revision owner、snapshot event、原件全文／hash、source／version、ACL／epoch／barrier继续执行。原有pureRef memo仍受原精确键与全部失效规则约束，不扩大许可复用。

## 失效与计量

沿用现source_kind固定目录及同store／instance／完整id键，4MiB／4096键上限不变。own write、foreign connection／process、主库／控制库／文件变化、outer结束及真实rollback的材料失效规则全部沿用。lazy命中仍按消费通知必要的逻辑观察，不重复收费物理行。

SQL实际返回kind或命中已读取事实才减少实际行／字节；不全读后少报，不改meter定义，不删高维内容、domain字段或召回。stage0.5份额、总cap及数据选择保持原值。

## 负例和验收

- 同库原SELECT *与source_kind路径在valid、missing、wrong kind／expected_kind、external instance、known／unknown、wrong revision／owner、snapshot正文映射情况下接受或异常一致。
- 同一对象多种合法reason slot和不同revision分别校验；只共享kind查询，不让一次valid Ref代替其它Ref判断。
- 缺登记后同连接新增、同连接受信写／rollback、foreign连接／进程及旧读事务变化继续失效／拒绝；未登记phantom Ref不能因缓存活过回滚。
- ref()、validate_ref、实际register_dependency入口共同使用同kind事实，度量物理查询与实际meter变化，返回字段／持久化映射不变。
- 未知observer、真实collector busy=False原完整registry行仍送入观察器；受信busy技术路径才共享，替换callback和伪busy属性不能冒充。
- 全8模块计算values／字段／source／selector／version／permission uses／UUID／caps严格差分不变，再统一PF06及完整共享／连续场景。不以局部查询减少宣称整体门槛已过。

## 进一步静态候选（未批准实施）

validate_ref的object_revision_registry三类SELECT *也仅使用id与object_id：stable对象的(instance,object_id,revision_no,kind)、直接版本Ref的(instance,id,revision_no,kind)，以及snapshot fallback的(instance,object_id,revision_no,kind=runtime_events)。必要时可设计对应固定映射材料；必须保留各自kind过滤和两种owner语义，不能将SELECT 1存在性当作完整映射。当前先不实施；如仍触限，应以新诊断确定收益后设计同库差分和collector保护，避免泛改版本／grant／scope规则。


## 实施与局部结果

产品仅修改ToolLearningStore.validate_ref的登记行分支：logical_observer_required=False复用既有source_kind；True仍原SELECT *。Ref结构／同instance／kind／expected_kind及原revision／event／owner／原件全文与hash判断保留，没有新增Ref结果许可缓存或修改readset目录。

8项新增reference-kind及既有validation／UoW／readset／review／existence／logical／control／configuration／collection／graph／calculation-sharing共123项通过（59.927秒），0失败／错误，含完整8模块严格计算差分。负例覆盖wrong kind／expected_kind／instance／revision／owner、缺失→本连接登记、foreign connection／真实process、旧事务、nested rollback；原真实observer仍收到完整registry字段。

同库一个未版本化Ref：接受结果一致，scan/items同为1；原完整registry行计量218字节，纯kind材料35字节。真实register_dependency加unknown／known／不同reason slot检查，持久化依赖ID相同，目标registry查询13→1。两条路径使用真实observer选择保留全行分支，未mock验证方法。证据：`outputs/acceptance/performance-round2/reference-kind-sharing-unit.json`。这不是完整思考耗时或整体共享负载已通过的声明。

未执行fullthink，未改Engine、contexts、meter、业务数据／selector、stage份额或总cap；后续revision元数据候选仍未实施。
