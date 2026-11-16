# 修订登记存在性材料共享设计

状态：设计定稿并实施，修订存在及逻辑读取新增15项、相关局部回归合计100项通过；等待统一PF06和完整场景复验。

## 背景

共享05已满足assembly原bytes预留，但在模型调用前耗尽原743615 scan预留。不能增加stage0.5份额、总cap或截短资料。本次仅合并两个同阶段反复查询的存在性材料，不缓存版本有效／授权结论。

## 两处精确复用

LocalEligibility.verify_version对SNAPSHOT_KINDS查询object_revision_registry的id后只检查是否为None；WHERE为同instance、object_id、revision_no且kind=runtime_events。该谓词与既有facts('snapshot_bridge',object_id,revision)的SELECT 1完全相同，可复用同一固定事实。原方法调用、principal／entry核验、source／完整Ref映射、revision owner、epoch与barrier等后续判断保留。不能把存在一条runtime event登记解释为快照正文真实或当前有权使用。

has_registered_revision原SQL为两个同实例精确索引查找UNION ALL LIMIT 1，返回“对象ID或修订ID有登记”。新增registered_revision_presence固定事实目录，阶段内按同store／instance／完整object_id共享；阶段外保留原SQL与索引行为。不能改回OR，也不能凭True推断kind／revision／owner或许可。

## 参数安全与生命周期

该UNION SQL有两次instance绑定。调用者只能提供一个object_id，readset内部固定展开为(instance_id,object_id,instance_id,object_id)。该queryname必须显式验证参数数量，拒绝尾instance或其它额外参数，不能开放调用者控制第二分支实例。缓存键仍是queryname与完整object_id，所属store／instance由原阶段身份绑定。

新事实受既有4MiB／4096键、真实meter行读取、generation／同连接写入失效、其它连接／进程提交拒绝、旧事务拒绝及退出清理约束。原始未知／不足预算不记0，不改变逻辑遍历预算。存在性命中不跨模型、工具、回调或下一阶段。

## 必须执行的同库验证

- 新旧UNION在object_id、revision id、缺失ID、其它实例ID、不同kind／owner／revision记录上逐项真假一致；EXPLAIN仍为两个精确索引分支。
- 单实例两个scope／用途／接收者共享存在材料，但原完整qualification仍逐次拒绝错误scope／Ref／version／owner／principal，不能复用成功许可。
- verify_version及_upstream在真实登记入口使用同snapshot_bridge事实，重复物理读取减少；不同revision不能混合。
- 同连接新增或改变修订登记后，原absence不能继续命中；foreign连接与真正子进程变更、旧读事务和阶段切换按既有guard重新检查／拒绝。
- 参数数量超过一个必须拒绝，不接受调用者指定第二分支instance；两个新合成实例之间的相同文本／ID材料不串用。
- 不改原完整高维特征、selector、召回、source hash、ACL／epoch／barrier、fresh字节读取、stage预留和总cap。先局部验证与PF06，再完整共享／连续场景计时。


## 实施与局部结果

readset增加registered_revision_presence固定目录及内部单参数展开；has_registered_revision阶段外仍执行原UNION ALL精确索引查询。verify_version仅在logical_observer_required为False时复用snapshot_bridge；未知observer或真正领域来源捕获区间保留原SELECT id，避免丢掉runtime event UUID。只有exact DomainReadCollector原busy=True且原on_row立即返回的受信作用域可复用存在事实。

与计算阶段协作：readset exact／complete-prefix命中按实际迭代逐行调用notify_logical_row，不重复物理计量；prepared／graph在logical_observer_required=True时禁命中、保存和准入。track_artifact消费lazy单行；旧iterator在phase退出后拒绝交付，包含absence，不能在新meter复活旧阶段缓存。meter／Engine／contexts的可信作用域实现由独立任务负责，本任务未改这些文件。元数据投影仍按“任何observer存在都保留完整行”，没有扩大省列范围。

新10项修订存在与5项逻辑缓存测试，加相关局部回归合计100项通过（27.049秒），0失败／错误。覆盖同库旧UNION真值／索引、参数尾instance拒绝、scope／错误Ref／revision／principal拒绝、同连接新增版本、跨连接／真正进程及旧事务变化、observer原id列保留与受信busy共享、懒消费只通知已用行、未知busy属性不能冒充、替换observer不能命中准备，以及phase退出iterator拒绝。

真实register_dependency既有登记入口同库各调用两次，返回同一持久化依赖ID：无共享presence查询4次、snapshot存在查询8次；共享后分别2次和2次，来源／权限核验继续执行。证据：`outputs/acceptance/performance-round2/revision-existence-registration-unit.json`。这只是目标查询减少，不是完整思考耗时或整体quota通过声明。未执行fullthink，预留份额和总cap不变。
