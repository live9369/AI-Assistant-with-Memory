# Ref修订映射材料按需读取与共享设计

状态：设计定稿、实施及142项源码稳定定向验证通过，等待统一PF06与完整负载复验。

## 依据与范围

shared07在原assembly预算拒绝：bytes212320742大于预留212320727，scan761286小于762183，0模型调用。实际trace为runtime.assemble→register_dependency commit→validate_token→validate_ref的snapshot桥接SELECT * object_revision_registry。保持原11条Memory＋关系负载、所有字段／selector、原stage0.5份额、总scan／bytes cap及计费定义。

当前validate_ref三个修订分支后续仅使用rev.id和rev.object_id。rev.id定位并校验真实snapshot event；rev.object_id核对version_owner。其它筛选字段由原WHERE精确限定。可以在不承担领域来源观察的纯校验路径减少未使用的校验元数据列，并按完整查询身份共享；不能改变版本判定或用SELECT 1代替映射。

## 两个固定映射目录

| 目录 | SQL返回 | 完整条件 | 使用分支 |
| --- | --- | --- | --- |
| revision_mapping_by_object | id,object_id | instance_id、object_id、revision_no、kind均等值 | STABLE_REVISIONS的对象根；SNAPSHOT_KINDS fallback |
| revision_mapping_by_id | id,object_id | instance_id、id、revision_no、kind均等值 | 直接版本Ref |

stable的kind仍是STABLE_REVISIONS[value.kind]，direct仍是value.kind，snapshot fallback仍固定runtime_events。保留原先direct/stable未命中才尝试snapshot的控制流。不得复用缺kind过滤的selected_revision，不把snapshot_bridge／registered_revision_presence的存在性当作映射，不把不同revision或kind放进同一个cache key。

两者都是固定表／列／WHERE的目录，instance由store绑定，调用者只传对象／版本ID、revision和kind；不接受SQL片段或尾instance。参数全部绑定，不放宽same-instance约束。缓存键包括queryname及完整参数，所属store／connection／instance沿用原phase身份。absence也只能在同一有效generation内共享。

## 不得改变的判断与材料

每次仍执行原Ref结构及instance检查、source_kind／expected_kind比较、known／unknown语义、stable／direct／snapshot分支、version_owner比较。snapshot的JOIN object_registry及instance/id/kind/source过滤、event_type、payload_artifact_id／payload_hash、完整snapshot正文、origin id/kind/instance、snapshot_revision及value digest全部保留。source／version／ACL／epoch／barrier／用途／recipient／read-delete路径和grant逻辑不改。

未知修订不能推断为0或忽略；非known Ref带version_owner仍按原错误拒绝。直接版本Ref与对象根不是同一种身份：前者使用revision登记id查找，后者使用object_id查找；不能混用。

## 真实来源观察保护

仅logical_observer_required=False时用新映射材料：无observer，或exact DomainReadCollector原busy=True且on_row立即返回的受信技术作用域。logical_required=True时保留三个分支原SELECT * object_revision_registry，实际完整id／object_id及其它字段继续按原顺序交给observer，保持source／selector序列。

未知observer、替换callback、伪busy属性或已结束的可信作用域不能获得投影／准备捷径。元数据event／artifact此前按“任意observer存在保留完整行”的规则不扩展，不泛改计算／Controller／runtime。事实缓存命中继续按已消费行通知必要的逻辑观察，不虚报物理行。

## 生命周期与计量

沿用4MiB／4096键、原实际返回行／字节计量、outer结束与rollback generation、nested rollback临时材料清理、未知raw commit拒绝、foreign connection／process及旧snapshot拒绝。原始bytes只在现有持续file/hash证明下共享。不能读完SELECT *后按两列收费；必须SQL实际只返回两列才减少字节，物理事实命中才减少返回行。

不加Ref／version／grant许可缓存。已有pureRef memo规则不放宽，own写／foreign变化／outer事务结束／所有真实rollback继续失效。lazy iterator不跨阶段或已结束事务复活。

## 定向用例计划

1. **同库严格对照**：真实observer强制原完整行路径，与无observer映射路径比较完整返回Ref或异常类型／消息。覆盖known／unknown／not-applicable、带owner的unknown、absence、wrong kind／expected_kind／revision／owner、跨instance。
2. **stable与直接native**：同一memory对象的r1/r2分别定位原修订；直接memory_revision／native row Ref仍按id查找，错误对象根／版本id不能互换。
3. **snapshot桥**：保留原已登记event和正文；wrong event_type／source／join kind、missing event／artifact、cross-owner／wrong origin.kind／instance、payload hash、snapshot revision和value digest损坏均等价拒绝。
4. **kind严格性**：同object/revision但不同kind的登记不能被误复用；snapshot仅runtime_events。验证新目录完整参数，尾instance／额外参数不能改变绑定或跨实例命中。
5. **写入／回滚／并发**：同连接新增修订后旧absence失效；nested phantom修订／metadata回滚后拒绝；foreign connection与真正进程改变登记、旧读事务及未知raw COMMIT仍拒绝；正常known outer结束不误拒合法r2或delete-only。
6. **真实与未知observer**：完整registry修订行及其UUID序列送入真实DomainReadCollector；未知／替换observer保持完整SELECT *。受信busy技术作用域可共享，但不能少掉原busy=False领域来源。
7. **实际登记入口**：同库register_dependency／register_input原真实检查及返回持久化映射一致，统计目标修订SQL和实际meter scan／bytes下降。不同reason slot不等于同一个Ref许可。
8. **预算与正文**：高预算功能对照外，单列实际列字节、原件全文、hash／size／symlink及原正文预检；不改变预算上限、份额或unknown，不把metadata投影称为模型输入减少。
9. **完整差分与故障回归**：全8模块values、features、fields、live、新字段、source／selector／version、permission uses、snapshot、UUID和caps严格一致；原F1 r2/delete-only、stop／revoke／erase、callback、rollback／unknown及外部gap回归继续通过，再统一PF06。

## 交付与分工

实施预期仅readset、ToolLearningStore及新修订映射测试；runtime_owners若无必要不动。Controller／runtime.py不需要修改。先targeted与严格差分，冻结后由统一验收协调者运行原261／新增项及完整shared／continuous；不在本任务重复运行wholethink，也不把局部减少列数当作整体通过。


## 实施与验收记录

新增固定revision_mapping_by_object／revision_mapping_by_id，精确校验三个调用参数（ID、revision、kind），instance固定来自store。ToolLearningStore的stable、direct与snapshot fallback在logical_observer_required=False时读取两列事实，True仍执行原SELECT *。后续event／JOIN／完整正文／hash／owner逻辑未删改。runtime_owners、Controller／runtime、Engine、contexts、meter和cap未改。

新增测试模块 `tests.test_tool_learning_revision_mapping`，9项通过；与既有metadata、UoW、kind、existence、logical、calculation、F1fault、collection、configuration及control局部回归合计142项通过（68.875秒），0失败／错误／跳过，公共源码前后稳定。包含真实Memory stable根与direct r1/r2、snapshot映射、kind严格性、observer完整行、同／外连接和真正进程、nested rollback、真实登记及全8严格差分。既有snapshot损坏／hash／预算／symlink与F1 r2/delete-only回归继续通过。

源码清单摘要SHA256：`0e98aa339e81817cc1ca2ac7c62da275669770b9a80980ca2c3239cf88913cd0`。完整模块、源码逐文件摘要与结果见 `outputs/acceptance/performance-round2/revision-mapping-targeted/result.json`，逐项执行日志在同目录tests.log。

同数据库同一runtime_events修订映射：原全行与新事实的id和object_id完全一致，scan/items同为1；元数据实际计量271→88字节。真实register_dependency加同版本不同reason检查，返回同一持久化依赖，目标映射查询8→2。证据 `outputs/acceptance/performance-round2/revision-mapping-material-unit.json`。这是局部材料读取减少，未宣称整体shared／continuous已经通过，也未执行wholethink。
