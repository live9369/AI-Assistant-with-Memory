# IM08 M03独立接纳、内容版本与C1设计

日期：2026-11-10；版本V0.1。依据冻结TL-LOOP-0.1、Q06/Q07及SQL字段，先设计后实现，只新合成隔离库，不接模型、不操作当前实例。

## 主入口与所有权

`ToolLearningAcceptance.decide(entry,envelope)`使用冻结decide_proposal。M03独立读UpdateProposal及原字节、全部具体Scope、目标/预期版本、来源资格和已知反证，不把M14的ready当许可。入口、政策、复核与八关回执由可信端口核定，默认拒绝。stop/lock/cancel/deadline/原预算身份与所有依赖在相同gate和C1事务内重核。

M03仅写Decision/content/group创建/handoff创建和依赖，不直接写tl_work。C1后工作可能仍awaiting_decision；`work_projection`只读持久Decision/handoff给M14/协调器返回恢复可核对的阶段建议。IM05具名协调入口持真正M14身份根据这些证据推进，崩溃后可重查而不重做C1；本项不冒充其角色更新work。表示领取/发布仍IM09。

## 政策和复核

已有policy_versions的scope中使用命名`tool_learning_acceptance`档：contract固定TL-ACCEPT-REVIEW-1、适用content_kinds、proposal_operations、require_controller_review=true、expires_at。缺档或不适用不能accept；open运行权限不等于知识自动接纳。

复核引用为已有perception_signals，绑定当前controller真实来源及不可变TL-CONTROLLER-CONTENT-REVIEW-1工件（proposal/ref+payload摘要、review_round、target expected、actual_scope、policy ref、accept/candidate/defer/reject/conflict/reuse verdict和expiry）。独立controller/M12核验端口必须确认该记录来自认证通道而非调用者插入一行的自报；默认拒绝。将现有工具action approval直接当内容复核禁止。

G01—G08各有真实所有者、Check方法/来源与实际当前结果；M03结构、字节定位和source_report字面支持本地复核，复杂含义/因果支持依真实所属域回执，不以八个bool或控制者语气代替。缺policy/review且没有更严重违规→candidate；可补材料defer；非法/支持失败reject；目标版本变化conflict；只有全部pass且明确已授权复核才能accept。

## 版本与旧cognition桥接

内容原件TL-CONTENT-1保留原proposal ref/摘要、全部claims、实际Scope、保留项/已知反证、源版本及政策复核谱系。native existing必须在当前head/期望版本上CAS；新修订append，旧决定/修订不回写，candidate修订不替换已有accepted head。新候选可有自己的candidate head但不能有当前表示义务。

旧cognition_beliefs/concepts是M03拥有的旧对象，但不能将其ID直接当tl_content ID。首次有明确复核的桥接创建独立native内容，并登记`derive`依赖到真实旧对象版本，闭合metadata使用保留field_path `/_bridges/TL-LEGACY-COGNITION-BRIDGE-1`标记；不修改旧belief/concept行，也不把旧shadow或held状态自动算世界事实。后续同legacy对象/类型的桥接从持久依赖查唯一native对象，再核旧当前版本及native head的实际期望，冲突不偷偷覆盖。涉及不同原基线的变更需要明确新复核。只接受TL链或实际cognition类型，memory/统计shadow不可冒充目标。

reuse只引用已accepted且当前资格合法的相同内容/原修订/原交接，不产生新修订或义务、不新增gain。一个proposal每review_round仅一次决定，新增复核或更改请求须IM13合法增加原work轮次；同键异义及同轮不同依据拒绝，不能覆盖候选变accepted。

## 互依赖组

atomic_group为已登记不可变TL-ACCEPTANCE-GROUP-1意图工件，成员完整列proposal/work/round/policy/review/expected/control/budget，属于同一M03 Principal。主Envelope绑定该工件，单个C1命令处理全部成员，逐项Decision单独保留；不嵌套提交、不假装多个主库事务原子。成员缺失/重复/组声明不一致拒绝。

原子组任何成员不可accept时不提交任何accepted head或新handoff；可统一记非接纳决定/原因，不报半组成功。全体accept时同事务生成tl_group及固定内容版本/必需TL-TEXT-1表示成员，state=pending；每个handoff引用同组。新头、决定、修订、组、持久义务、命令结果都一次提交。C2整组ready由IM09处理。

## 事务、幂等与验收

dispatch_gate→BEGIN IMMEDIATE→当前八关/源/全部实际目标/政策/复核重检→C1写入→当前再核→命令提交。耗尽attempt不禁止零新推理的决定事实，未知用量、超额、停止、撤权和期限仍阻断；不创建新预算/模型请求。提交未知按原command查询，不盲重跑。

隔离验证六操作、缺policy/review候选、伪复核/错绑定/八关失败、静态source版本、0/false/null/unknown、旧/native目标真实版本、同轮不可改、跨键幂等、CAS、复用无新增、互依赖组每写点故障全回滚、来源F1/stop提交竞争与当前读权限。实际科学支持/生产controller接线默认拒绝，不将机械替身当真实review或学习改善。


## 实现细化与字段映射（2026-11-10）

| 冻结/输入字段 | 主库映射与不变量 |
| --- | --- |
| proposal/Product.product_id、work_ref、processing_identity | tl_product.id/work_id/processing_identity逐项相等；实际M14原件只读，不改成M03产品 |
| review_round | tl_decision.proposal_id+review_round唯一；必须等当前work.review_round；同轮只能返回原决定或拒绝异义 |
| Decision.id/operation/checks/actual_scope/actor/policy_ref | tl_decision.id/operation及不可变Decision工件；M03真实授权，八门实际所有者回执 |
| content_ref/revision_ref/previous | tl_content与tl_content_revision；指定revision注册归属，previous保留真实Scope epoch，不硬编码0 |
| claims、Scope、preserved_content、unresolved_items | TL-CONTENT-1原件完整保存，含source_versions、proposal摘要和policy/review谱系 |
| per-revision来源依赖 | consumer=tl_content_revision；TL-DEPENDENCY-1闭合字段，source_revision_id映射真实登记；继承read/support/derive/delete等关系不混为一种 |
| legacy target.expected | 当前旧对象真实版本CAS，不硬塞ID；每修订桥接derive边用保留field_path，按revision→content查唯一native身份 |
| native_expected | 认证复核独立绑定真实native head；mode=new已生成candidate时也必需，不能沿用NA；旧legacy1→明确legacy2+native当前head可合法再评估 |
| handoff_refs/group | accept固定TL-TEXT-1、版本/decision/work/budget/deadline；组成员逐一真实授权、重复native目标提前拒绝；C1与命令同事务 |
| coordination projection | 只读Decision，M14/coordinator当前授权；candidate/defer/conflict默认waiting/decide，明确需新复核/合法新round；不隐式写work |

C1中任何八门blocked优先拒绝；fail优先于incomplete，缺policy/review、未知值或缺locator不能把已有硬违规降级。source_report字面匹配不能升级world/method/causal类别。多条证据中至少一条真实定位足以支持该原文source_report的字面值时，不把另一条定位缺失武断当全局失败；全部原证据、覆盖与实际所有者检查仍保留，复杂含义/独立支持须实际域核验。

现有head的CAS元数据读取与旧内容使用区分：`verify_target_metadata`默认拒绝，仅允许核真实对象/版本/Scope epoch及直接stable屏障，不沿旧支持图读取失效正文。新claims全部以自己的当前来源核验，因此A旧支持失效后可以由独立B、明确expected和新review产生修订。reuse、preserved_content或claims使用旧内容必须完整当前资格；reuse读取原件核语义相同，不增版本/义务/收益。

## C1读取预算端口与IM11义务

`verify_read_accounting(entry,request,work,snapshot,read_context,stage)`默认拒绝；每次读取发生的read_context都有唯一occurrence_id、逻辑请求指纹、原work/account、stage、deadline和当前remaining.bytes的前置cap。可信编排必须将每个真实发生绑定已预留的actual operation_ref/原账户/原请求和仍有效额度；不能凭一个阶段名或宽松bool无限重复evaluate。C1已经开始时不得新预留；外层先预留，事务内受控消费，外层实际settle，commit复核重复读取也计入，unknown保留并停止后续机会。

IM08不伪造retrieval/模型操作去补账，未实现IM11的真实调用编排计量。固定1MiB源字节、64 claims、128 evidence/继承依赖/桥扫描及65536字节policy/review等是技术上界，不是共享预算实际累计完成证明。机械替身只测试该端口默认拒绝、每次唯一绑定和当前额度截断；真实八维计量、实际operation_ref和前置限额及未知结算由IM11必须交付。本模块不接provider、不消费真实模型、不读当前实例。

组review与不可变意图互相引用时，由可信authoring端预分配稳定ID后一次登记，不能先写占位再改工件正文。组本身只能在每成员真实access和group权威核验后使用；没有认证authoring接线时默认拒绝。

最终复核收紧：桥接逐行通过IM06 `_metadata`校验闭合字段、consumer/source/版本/row映射，不能只信contract与field_path标签。所有权威回调结束后、真正提交前再次检查stop和精确deadline；末次G08跨过deadline且policy/review仍有效也拒绝。两项补充不改冻结合同。
