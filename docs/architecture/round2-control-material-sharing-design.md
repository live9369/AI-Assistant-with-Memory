# 同阶段控制核对材料共享设计

状态：设计定稿并实施，17项新增控制材料测试及既有局部回归共66项通过；等待统一PF06与完整场景验收。仅延伸PF04／PF05事实读取，不改变原预留份额或业务cap。

## 问题与可行性

共享Memory+Relation场景在调用模型前耗尽assembly子预留710873 scan，整体实际1289126仍小于200万总cap。不能扩大assembly的0.5份额或删关系资料来绕开失败。LocalRuntimeOwners.control／principal／configuration为每个来源节点重复读取主库中的当前配置、policy_epochs与控制源barrier；这些是相同阶段的核对材料，适合固定事实共享。控制库process／epoch／pid／stop与允许结论不适合缓存。

## 固定目录与原谓词

| 固定事实 | 查询语义 | 原检查必须保留 |
| --- | --- | --- |
| policy_epochs材料 | 同实例SELECT *，保留原返回顺序、全部行及原首行选取规则 | 每次principal重新建立并比较actor/module/recipient/purpose/policy；空数据仍失败 |
| latest_configuration | 同实例按rowid DESC LIMIT 1读取id、artifact_ref、hash；control和configuration共同使用该完整行 | 配置必须存在；原配置／模型owner和完整性检查不减少 |
| active_control_barrier材料 | 同实例、明确cfg/policy ID参数、state=active的原SELECT 1 LIMIT 1 | 每次control仍根据该事实执行拒绝谓词，不能存allowed/grant |
| schema版本 | 本轮建议继续实际PRAGMA user_version | 每次验证类型与2/3/4范围，未知版本仍拒绝，不降低schema4保护 |

所有目录键包含同实例与完整查询参数；受现PhaseReadSet generation、4MiB／4096键、逐行原meter及退出清理约束。不缓存Control DB结果或control()成功结果。

## 配置材料的完整性

配置JSON不能仅以cfg(id,artifact_ref,hash)为键延长原进程级_configuration_cache：还要核对artifact完整身份（instance、id、hash、size、media_type、storage_ref），原始字节继续由安全工件读取核验摘要；配置行hash与所指artifact hash矛盾时拒绝。阶段内纯JSON可按该完整身份共享，调用者拿独立对象；进入新阶段后首次使用不能把旧进程配置对象当成新阶段的文件完整性证明。同连接合法新配置、artifact映射改动或文件变化必须失效／拒绝。

## 新鲜度和不能共享的部分

control每次仍实际读取控制库instance_control_state和process_runs，比较当前active process、runtime epoch、PID、退出和stop状态，实际调用assert_execution_allowed。check每次仍验证entry存在、重新构造并比较完整principal。source／version／epoch／barrier、用途、接收者、read/delete路径、逻辑扫描预算及原调用前后边界均保留。

同连接DML变化在facts查缓存前触发checkpoint并重建generation；foreign连接／进程提交、控制库变化及文件替换仍终止旧阶段。实际模型／工具／外部回调不共享；直接owner端口仍有check_depth=0时的新鲜度检查。阶段内不建立跨调用长事务。

PRAGMA user_version写入不增加total_changes；事务内未提交的本连接PRAGMA写入也不能只靠observer/data_version捕获。因此本轮保留该实际读取最简单可靠。若以后要共享PRAGMA，必须先提供可靠的本连接PRAGMA写入失效机制与真实负例，不能凭固定正常路径永不写版本就缓存。

## 必须执行的负例与量化验收

1. 同阶段多次control／principal：主库三类材料只首读，Control DB实际查询次数仍随每次调用增加；原校验仍逐次执行。
2. 缺policy、缺配置、多个同实例policy行时结果／失败与原行为一致；未知schema版本仍拒绝。
3. 同连接更新policy_epochs、插入新configuration、激活cfg或policy barrier之后，下一真实入口重新核对并拒绝旧principal／被阻断来源。
4. foreign连接与真正子进程分别改policy/config/barrier，旧事务中的阶段不能清空后继续旧snapshot；必须拒绝。
5. 控制库stop、process替换、epoch/PID变化、WAKE_DISABLED、restore锁仍实际拒绝，不因主库事实命中放行。
6. 修改artifact行但cfg行不变、同名blob替换／篡改、合法新配置，以及调用者修改返回JSON，都不能污染后续配置判断。
7. 实际回调前后和下一阶段重新读取；raw callback注入写入不能借旧资料越过原检查。
8. 保留assembly原0.5预留和所有总cap，使用完整共享来源场景复验。目标是减少约20万重复主库返回行，但以实测为准；不足或仍超支如实保留失败，不调份额、不删输入、不把少读当成少检查。


## 实施与局部验证

产品修改仅runtime_owners与readset：增加三类固定事实目录；policy_epochs完整消费后共享，latest_configuration由control／principal／configuration共同使用；控制barrier仅共享原始存在性材料。control的真实Control DB／process查询、assert_execution_allowed以及PRAGMA user_version没有删除。configuration移除旧进程级字典缓存，phase内准备键包含opaque phase.stamp对象本身、generation、配置行和完整工件身份；phase外每次走安全fresh读取。stamp用object()，不消耗业务UUID序列、不进入模型。固定marker计入该内部键的编码账，其余数据部分按真实编码字节计量，Python对象开销仍与既有定义分列。

新17项actual owner测试与既有49项优化局部回归合计66项通过（11.359秒），0失败／错误。实测同阶段连续3次owner.check，policy_epochs／latest_configuration／active-control-barrier主库材料各只首查1次，而Control DB process_runs实际查询3次、执行状态检查至少3次、PRAGMA user_version至少3次。每个entry／actor／module／purpose／recipient谓词仍重新判断。

负例包含本连接policy重绑定、新配置改变actor、cfg与policy barrier激活；其它连接policy／config／barrier变化以及真正子进程提交；停止／epoch／PID、WAKE与restore锁；事务内本连接PRAGMA user_version=999；配置文件跨phase与midphase篡改、artifact映射变化、返回JSON被调用者修改、缺配置和缺policy。所有实际模型调用均未执行。

foreign最初使用UPDATE hash=hash作为变化注入，该操作没有改变数据库字节，不能要求data_version变更；最终测试使用真实hash变更，不放宽探针。此轮未跑完整Engine，不声明已经省20万行或共享场景通过；须保持原assembly0.5份额及总cap重新验证。

## 配置安全读器复用回归修正

共享03定位到配置phase外fresh读取每次重建ToolLearningStore，会触发两轮全表DDL核验，导致calculated-contexts异常增加约80万scan。修正为复用owner已初始化的eligibility.artifacts，原安全行读取、O_NOFOLLOW、size/hash核验与meter全部保留。

ToolLearningStore.read_artifact增加仅技术性的可选fresh=False；默认行为不变。configuration在phase外显式fresh=True绕过本次旧raw bytes命中，但不清空其它缓存、不重置预算，并原样记录新实际文件字节；phase内仍按阶段文件身份和首次摘要核验共享。调用只发生于LocalRuntimeOwners自己的普通ToolLearningStore，既有_MeteredStore等调用默认路径未改。

新增6项配置读器回归，加原17项控制负例与49项优化局部回归共72项通过（21.033秒），0失败／错误。实际10次phase外configuration调用无table_info，scan/items各30，计量11780字节，含10次真实314字节配置文件fresh读取；证据：`outputs/acceptance/performance-round2/configuration-reader-reuse-unit.json`。

真实8模块_contexts入口已运行：每个真实configuration调用内部table_info严格为0；完整_contexts仍保留原GoalRegulation.assess→ActivityResourceBudget一次初始化的40条schema查询，按原meter收费，不冒称全部0。另一个普通默认features关闭的真实_contexts入口总table_info为0，未mock配置或领域计算。same-meter且无phase时中途配置blob篡改、普通fresh篡改与新增DDL未知source仍拒绝。未修改GoalRegulation、预留份额、总cap或benchmark，未运行完整Engine。等待统一PF06及完整共享负载复验。
