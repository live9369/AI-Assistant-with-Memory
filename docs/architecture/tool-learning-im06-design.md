# IM06 依赖登记、F1屏障与最终资格门设计

日期：2026-11-09；版本V0.1。依据冻结TL-LOOP-0.1主契约§5/7/8与存储附录§3/4；先设计后实现，仅新建合成库验证，不部署、不迁移、不操作当前实例。

## 责任与接口

同一个实现者完成IM06，避免把有内部耦合的模块误列成独立IM任务。`tool_learning_eligibility.py`提供Scope键、当前代次、依赖/输入消费登记、当前资格检查及可信同步替身回调边界；`tool_learning_invalidation.py`提供`ToolLearningInvalidation.apply(entry,envelope)`。默认权威端口全部拒绝，没有真实来源/M12授权解析器时不能产生生产许可。仅依赖已完成IM04/05，不提前实现IM07或后续任务。

依赖登记为内部具名技术端口，不自造冻结第十一项业务操作；其元数据完整保留Dependency/Scope/field_path。重复同义返回原记录，异义拒绝；source/consumer/request/recipient均校验实例、注册kind及真实修订归属。输入消费只能登记到已有明确依赖，正文摘要按Digest核验，不凭临时字符串生成许可。

## 范围、代次与屏障

`scope_key`为不可变Scope的规范JSON摘要。它用于准确索引而非权限隔离证明。缺精确scope代次行时读值为0，F1首次以期望0写代次1；后续原行CAS加1。不同scope键不能回避旧屏障：检查遍历同来源所有active屏障，并沿已登记依赖检查上游。不同的来源对象和同字节副本不自动合并；身份别名由可信来源域解析。

本地只有完全相同Scope能确定重叠；其他情况为unknown，按可能重叠处理。可信权威可依据真实范围返回明确disjoint；不能凭property、主体标签或改hash自行断言无关。purpose非空列表限定影响用途；subjects不在本地擅作实体消歧。历史核查也须当前资格判断，不能把history_audit当屏障旁路。

## F1原子事务

锁序固定为dispatch_gate→主库BEGIN IMMEDIATE。先严格校验apply_invalidation Envelope及当前控制，再调用真实来源所有者/M12核验端口；source VersionToken、replacement、evidence、erase_scope实际归属须核定，不把Principal.module、文本或摘要当授权。

同事务写tl_change、递增/初始tl_source_epoch、独立active tl_barrier、全部必要tl_propagation及受影响输入retention_state，再写原tl_command结果。change_key使用payload.change_id的稳定事件身份，指纹绑定完整冻结payload，不含command_id/control/budget。相同事件经新命令重放只读复用，不二次加代次；相同事件不同实质载荷拒绝。旧expected_epoch拒绝。每个变化各有屏障，不合并原因、不提供resolve。

传播初始登记全部九个封闭模块域的pending义务，传播计划可补各域targets，缺计划仍生成九域pending骨架；即使域内空列表，也只表示计划内没有列出对象，初始coverage仍unknown，不宣称清理/传播完成。本地已发现依赖对象保留在扫描义务内；扫描超限或计划缺失时coverage为partial/unknown，并保留后续扫描义务，不能因此拒绝合法根屏障使旧数据继续可用，也不能截断后假称完整。输入失效沿实际依赖闭包标blocked，erase标erase_pending；已有erased不复活，已有erase_pending不被普通变化降级。

传播计划、当前版本/策略与源变化依据均由可信端口给出并在提交/结果投影前重新读取当前控制、源版本和授权。F1不消费新模型/工具额度，不用耗尽工作阻止紧急资格屏障；绑定的原账户只供后续义务，不刷新其额度或期限。停止状态下的管理失效需专门可信管理授权，不解除WAKE_DISABLED，不调用普通推理。

## 最终资格与G1

资格检查核对当前Control来源域、source VersionToken、scope epoch、所有上游active屏障及已持久输入资格；权限服务异常不猜正常空结果。图遍历有限且有循环检测，不能只看直接source或通知是否到达。

可信同步替身入口持dispatch_gate执行最终检查，结束主库只读事务后才进入回调，并持门禁至返回。若F1先提交，则回调不能开始；回调先进入，则其他线程/进程F1等待回调退出再提交。同线程重入F1允许记录实际已经在途，返回后的使用检查拒绝受影响结果；不虚报即时取消或远端已经收到。预留或prepared/sent记录不算实际回调，测试计数来自真实本地函数入口。

## 验收与边界

新建IM01合成schema3夹具加载既有增量SQL；正例仅临时允许合成控制状态，退出重锁并停止。验证默认拒绝、真实引用/旧代次/同键异义、F1各写点故障及提交未知核对、九域义务齐备、输入资格原子失效、多原因不互相解除、scope换键/unknown重叠、依赖循环/上限、线程与跨进程先后和同线程重入。

不实现F2/F3确认、物理清除、屏障解除、完整恢复或新旧全链运行入口贯通；对应IM11/12/13/19继续保留。仅确定性替身验证机制，无真实模型、外部工具、网络或当前实例操作。真实权威、预算实际派发接线与全量MECH验收不能由本项替代。


## 已实现字段与权威端口

内部依赖元数据为`TL-DEPENDENCY-1{consumer,dependency,field_path,scope}`，逐字段核对实际行及object_revision_registry；input只绑定已登记的read依赖，输入/输出保留关系不冒充支持。注册权威取得consumer/request/relation/purpose/field_path/digest完整上下文并在begin/commit核验。普通公开check拒绝接管调用者已有主库事务，保证先门禁后事务；内部注册复用其已持门禁的事务。

`verify_callback`取得固定快照及实际request/activity/全部inputs，回调前后均核用途、recipient、取消、期限、上游版本/屏障及输入资格。调用者字典在入口深复制，回调不能通过修改原token/Scope把返回后校验换绑到其他来源。`barrier_applies`取得完整已持久payload、主体/用途/recipient以及依赖路径；未知按适用处理，只有可信明确不适用才跳过。F1直接输入失效使用相同明确适用核验，不把标签不同当不适用。

delete-only路径不因普通conflict/unavailable屏障自动算作内容支持失效；erase仍可阻断保留/使用并产生清理义务。F1传播目标是保守扫描超集，不表示所有目标已被判假。缺计划及暂不可用计划生成九域pending扫描义务，不等待F2成功才保护根源。

范围遍历限制同时含max_nodes（默认256）及max_rows（默认1024）的边/屏障/输入扫描数；重复同节点的多条边也计数。资格门超限拒绝，F1超限只标partial/unknown并保留扫描义务，根屏障不因枚举不齐消失。计划targets有界截取并标partial，绝不把截取后的列表写为complete。此为每次有限资格阶段的读界限，不是完整图已扫描证明。


## F1结果Slot的静态来源修正

F1只提交资格代次和屏障，并不创建新的内容/来源修订对象。因此Response.current统一为技术not_applicable，reason说明从返回barrier Ref及不可变change payload查具体源版本和result_epoch。静态来源可以合法具有已知revision=0而不在object_revision_registry伪造修订；其known零仍完整保存在change payload，source_epoch/barrier记录真实递增代次。此技术Slot不表示源不存在、未知或被删除，也不削弱M17对known VersionToken登记的一致性规则。


## 2026-11-10 依赖修正：指定修订的支持路径

IM08接纳修订暴露原门禁按稳定content展开全部历史支持的缺陷。TL内容与表示系列的资格检查现在以调用者明确VersionToken选中object_revision_registry中的唯一修订，以修订Ref作为依赖consumer；仍对稳定owner检查其当前Scope epoch和active屏障，不把旧支持混进新修订。普通既有对象沿原依赖结构处理；缺少指定native修订登记拒绝。

F1闭包保留(owner, exact_revision)而不是仅owner；到达修订consumer时，同时保留修订Ref技术路径，并沿source_ref_id=owner、source_revision_id=该修订（或未知）的下游边传播。输入失效按owner+精确source_revision_ref_id匹配，未知关联保守阻断；九域pending及有界扫描规则不变。此设计不改冻结的source+Scope epoch作用域：直接对稳定owner做F1仍推进该Scope代次，调用者须重新取得真实当前资格。

接纳模块必须将事实支持登记在每个tl_content_revision上，不能在稳定content上累积历史边，不能仅改变field_path规避唯一约束。旧认知桥接同样使用闭合TL-DEPENDENCY-1和保留field_path标记，不添加未声明metadata字段。
