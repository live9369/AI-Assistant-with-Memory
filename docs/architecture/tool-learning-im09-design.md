# IM09 M04固定版本表示、租约与C2设计

日期：2026-11-10；V0.1。冻结依据：TL-LOOP-0.1 §Representation/Handoff/Group/Response、存储附录§4/修订登记、Q07/Q08。前项IM08补充统一426项通过并绑定复验证据；本项只新synthetic，不接模型/当前实例。

## 接口与所有权

`ToolLearningRepresentation.claim(entry, envelope)`、`publish(entry, envelope)`保持冻结claim_representation/publish_representation。辅助`build(entry, claimed_request, claim_response)`只对已核当前租约做确定性TL-TEXT-1构造，不派发LLM/工具。M04拥有handoff租约/消费、representation/series/head、group ready及逐表示依赖；不改M03内容或work阶段。所有真实entry/worker/租约/来源/预算读取及保留权限由默认拒绝RepresentationAuthority端口核验。

## 固定输入与有界构造

C1 handoff绑定work/原account/decision/content revision/input_fingerprint。claim核真正M04身份、当前Control/停止/取消/期限/原共享预算和源资格，只领取pending/retryable或已过期leased；blocked不自动恢复、terminal不自动重领。CAS expected_generation，增加generation/attempts，以min(now+lease_seconds,总deadline)确定租约，旧worker不能延长或复活许可。

构造只读指定accepted修订，核Decision真实accept及版本相同、M03当前head仍等该修订；必须完整通过IM06当前用途represent的支持路径和直接屏障。正文按“来源性质→有限主张→时间/单位/条件→未知/冲突→证据定位”固定模板逐字段JSON呈现，不改写数值、Scope、ValueSlot、局限和证据。source_report保持原文报告身份，不新造世界判断、接纳或gain。不提供隐藏的纯表示模型调用。

Representation.claims/scope/source_refs与内容固定原件一致；body_artifact真实字节及digest精确绑定，TL-TEXT-1必须等确定性重构正文。新series身份只供C2一次登记，已存在series必须实际相同；representation_no按该series单调递增，content revision是另一版本轴。依赖consumer=实际tl_representation.id，明确指向指定content版本并保留支持/删除等不同关系；不在stable series累积全部历史支持。

资源上界：成员32、claims64、证据/依赖128、单次材料与正文1MiB；权威预算端口必须绑定每次实际操作发生、原work/account、请求指纹、仍有效预留/剩余额度和deadline。构造/重试真实成本沿原账户；默认无真实计量机会拒绝。IM11统一物理读取meter须包含M17.__walk_refs隐式重复原件/view读取；固定上界不是累计八维记账完成证明。

## C2与互依赖组

独立handoff在门禁下同事务核租约generation/worker/expiry、源和当前M03 head、真实blob和固定内容，再写representation、series head CAS、消费receipt、handoff published并清空worker/expiry、命令。旧表示可标superseded，但不改不可变原件；任何失败不回滚既有C1。提交未知通过原tl_command/handoff/head核对，不重复副作用。

组只能使用C1固定TL-C1-GROUP-MEMBERS-1清单，逐项核真实handoff/decision/content/format和完整当前主体权限。单个publish请求到达时可保存受当前保留权限保护的TL-C2-STAGE-1草稿事件（绑定原请求、lease generation、非秘密worker/principal身份和Representation），返回deferred，仍无ready表示/当前head。末个成员到达后重新核所有stage的当前租约、真实worker、材料保留、来源、预算与固定成员；同一个最终C2写全部必需表示/heads/消费和group ready，不暴露半组。过期旧stage不能复用新generation；草稿不是已发布对象，清理由IM12明确处理。

## 响应版本语义与M17修正

claim Response.current.object=tl_handoff，revision=当前row_revision、epoch=lease_generation，属于可变控制CAS，不是object_revision_registry修订。M17.__walk_refs按实际object kind识别此VersionToken并核真实handoff控制字段；普通Ref.revision和content/representation不可变修订仍严格走registry，不能伪造登记或把已知0改unknown。业务入口继续检查精确generation/worker/期限，引用存在不授予当前租约。

## 验收与后续归属

隔离验证真实领取递增/expired重领/旧worker拒绝、stop/lock/取消/总deadline/预算、各类Scope/unknown/false/0/null完整构造、body篡改/更强claims拒绝、native内容变更/来源F1先到与晚到、C2各写点回滚/提交未知/幂等异义、group缺员/expired成员/失败无半组、series多版本不混content版本、mutable控制token与严格Ref修订正反例。权威机械替身不是生产授权。IM10负责用途召回，IM11负责实际输入/预算编排，IM12清理与IM13恢复不在本项展开。


## 实现收紧

- stage绝不序列化entry、通道能力对象或凭证。只持久化worker/principal/authorization引用，末次由默认拒绝`resolve_stage_entry`重新解析当前可信通道。每成员读/源/租约/retention/提交核验使用实际成员entry；两个不可JSON化Channel对象的合成组验收覆盖此边界。M17/IM06既有字符串入口仅接内部固定适配标签，实际通道只保留在私有瞬时桥接中，不把标签当权限。
- stage工件本身作为真实consumer登记固定content修订和继承依赖；stage重复body工件登记delete依赖。build同事务就为body登记固定修订delete义务，未stage的正文也能由erase闭包追到。body不是所有历史版本共用的support节点，各修订支持仍在具体stage/representation。授权`read_built`重新核源/租约/保留权限，F1后拒绝；M17裸blob读取为内部技术接口，不是用户可直接调用的授权API。
- `_committing`瞬时保存每成员实际通道/固定request/原expiry。C2清空租约后仍核本次representation归属和fresh clock<原expiry，末次callback跨租约但总deadline有效也回滚；claim末次跨新expiry也不提交可用租约。stop/总deadline在所有回调后重核。
- 为旧表示ready→superseded/withdrawn补M17固定字段/实际M04的窄状态CAS入口，不开放原件修改。series首次循环FK同C2延迟核验，不创建NULL映射占位。

同连接C2事务中尝试嵌套F1必须拒绝，不能声称F1已持久提交；真正F1先后顺序以首成员stage提交后、独立F1、末成员publish的隔离测试证明。跨进程短事务仍由既有dispatch_gate顺序化。已引用草稿、build-only正文、stage事件/依赖与command载荷的物理清理由IM12逐目标核保留范围，不在本项删除。

最终提交末尾还执行无权威回调的全成员检查：统一核全部min(original lease expiry, work/budget/handoff deadline)、fresh stop/取消及消费row_generation/row_revision/receipt worker/expiry/representation/请求指纹，避免后查成员的慢回调令先查成员跨期。claim保留本次新控制快照，末次回调更换代次/worker同样拒绝。
