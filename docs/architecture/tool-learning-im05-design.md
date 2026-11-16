# IM05 工作、预算与协调状态详细设计

日期：2026-11-09；版本 V0.1；依据冻结 TL-LOOP-0.1 主契约§4/5/7及存储附录§2/3/8。先设计后实现，只验证新建合成实例，不接入当前实例或Runtime。

## 模块与接口

`application/tool_learning_work.py` 提供 `ToolLearningWork.admit(entry,envelope)`、`transition(entry,envelope,target,phase,reason)`、`snapshot(work_id)`。入库仍走IM04可信StorageAuthority，默认拒绝；授权端口收到完整请求，并在BEGIN及COMMIT前重新核对。公共请求自报module不能授予写权。

`application/tool_learning_budget.py` 提供工作原账户核对、剩余额度、预留、实际入口及已知/未知结算。它以work_id加载唯一learning_activity与account；保持原预算身份和期限，不借新请求或恢复新建账户。精确接口由该模块设计附录列出。

可信 `WorkAuthority.verify_source_origin` 必须解析实际来源类型、original_result/receipt与source_revision的真实归属，默认拒绝；不能仅凭请求hash或自报“新版本”生成新观察。`admission_allocation`返回具名`AdmissionAllocation(parent_budget)`，不是JSON布尔授权。其parent_budget是权威明确划定的普通父账户TL子工作**分配池上限**，不冒称从旧总token记录重建了输入/输出/扫描等历史分项实耗。当前外部来源不绑定本地FK，本项保守拒绝；后续来源适配有独立授权后再接线。

IM04的`OwnedTransaction`仅新增具名C0装配端口：只在M14的admit_observation事务内创建内部感知通道/信号、独立learning activity和唯一budget account；不放开通用旧表insert，不创建队列任务，不调用Engine.submit、Memory.encode、Goals或推理器。实际生产者取认证Principal.actor及module，原source/source_activity保留在触发工件内；内部信号不伪造控制者用户发言。

## C0与分层重复

顺序为外层dispatch gate→当前停止/取消/期限检查→IM04幂等事务→源/用途/材料检查→处理身份核对→具名装配activity/account→tl_work→原Response与command committed同事务。失效/源屏障真实解析尚依赖IM06；没有可信解析端口时默认拒绝，隔离替身不能当作生产授权。

命令幂等仍使用IM04逻辑指纹，排除command_id/control/budget，但每次仍核当前快照。工作processing_identity对固定source身份/版本/摘要/定位、source_activity、purpose及processing_method求规范指纹，排除纯请求、时间、预算和重试字段。相同处理身份换命令键复用原work，不建第二activity/account，不增加观察/证据/收益计数。

同一来源已存在而方法、范围或用途变化，不应靠新键静默获取新预算。本项只接受首次处理及精确重复；显式previous_work或同一原观察的不同加工意图均保守返回原work的阻断结果。受控再加工必须由后续业务服务落实明确用途、parent预算分配及原工作关联，本项不伪造分配。源对象不同而字节相同不视为同一观察。

独立原观察键排除通知source_activity、复制artifact身份和Slot说明/basis元数据；真实对象/修订及原结果/回执身份由可信来源解析器核定。同一原观察在新通知或新父活动中再次出现，不能新建工作或预算；真实不同来源即使字节相同仍保持不同身份。

源activity可以已完成，表示触发的原观察仍可授权使用；它的取消状态、原授权/源资格仍须可信门核对。新learning activity不借原activity的运行状态或队列获得派发许可。

## 不可变预算与期限

完整原Budget以命名`TL-WORK-BUDGET-1`文档保存到learning activity.budget_json；账户已有token_limit保存input+output总量、tool/attempt/time等技术上限，分项input/output/scan/items/bytes与原account_ref仍在文档保留并由预算服务逐项执行。未知货币额度不表示无限，本项无真实模型消费。

首次C0的Envelope.Budget.account_ref指已存在且属于source_activity的普通父账户；新child account ID在C0内部生成，child Budget绑定新ID，原Envelope Budget完整存为source_budget。条件工件同时固定budget/source_budget及真实account.time_limit_ms，不以重开时间重算。

父activity.budget_json保留旧字段，新增`tl_work_allocations={contract:"TL-WORK-ALLOCATIONS-1",caps:可信池Budget,allocations:{work_id:{activity_id,account_id,budget:子Budget}}}`。C0在同一BEGIN IMMEDIATE内封存池、扣已有永久子分配及父技术账本占用并追加唯一绑定，父account.revision CAS递增；任一C0写点失败全部回滚。input/output/scan/items/bytes等池向量约束所有TL子分配，物理tokens/tools/attempt还要扣旧reserved记录。父usage_unknown禁止新分配；不新增额度的精确历史重复仍可经当前权限核对返回。分配不冒充模型预留/实际消费，暂不自动返还。

旧`Budget.reserve`只在检测该命名分配账本时额外扣除子分配，防旧父路径继续双花；无账本旧行为不变。TL-WORK-BUDGET-1来源暂不能作为新的分配父级，避免未实现的递归分配。受控再加工额外分配仍未开启。

work.deadline与activity.deadline固定为请求deadline和合法源/父约束的较早值。后续请求只能缩小本次可用上限，不修改原账户、总cap或期限。预算预留不是实际回调或消费；未知结算保留原预留并阻断新派发，真实用量另存，失败/取消不释放已进入的未知成本。账户/工作绑定和预留原子性由独立隔离竞争测试核对。

## 协调与恢复边界

普通状态入口只允许冻结Work图中的前向处理/等待/阻断/停止/失败/终点；CAS递增row_revision。不能通过普通transition从waiting/blocked/failed/stopped重开processing或handoff_pending，不能递增review_round或更换budget/deadline/source/identity。认知复核必须有原work、明确条件变化及新命令，实际恢复入口留IM13。

协调使用`assess_observation`的固定内部方法`tl-work-transition/1`，其request_ref指向精确`{contract:"TL-WORK-TRANSITION-1",work_id,expected_revision,target,phase,reason}`意图工件，使状态意图进入冻结payload指纹；调用参数必须与工件完全一致。它是零成本协调机械，不冒充模型产物。processing=assess、awaiting_decision=decide、handoff_pending=represent、终点=complete；等待/阻断/失败/停止保留当前phase。业务交接/终点均需`verify_endpoint`真实持久证明，默认拒绝，IM07/08/09/14尚未接线时不能凭target进入。

transition核对完整原账户、请求各cap及剩余/未知状态。最后一次合法attempt结算后，零成本状态事实可只过滤attempts_exhausted，以保存已完成的事实；硬停机、取消、期限、unknown/halted仍阻断，派发/预留/实际入口没有此例外。有效快照仍标不能新派发，不能借协调重开工作或刷新额度。

条件工件记录原因、所处阶段和待解除条件；它不是解除许可。停机、取消、到期或耗尽保持阻断，不解除锁、不enqueue、不唤醒；终点不新增内容接纳或收益。snapshot只返回本工作持久状态/原绑定和预算快照，不顺手修复或恢复。

本地控制在可信verify/project回调之后重新读取，提交前不使用旧activity字典。全局锁/取消等拒绝通过本地例外返回，不为了报告停止而新建C0活动。snapshot区分持久state与effective_blocked，当前停机并不谎报已自动写入stopped；真正控制同步/屏障继续留IM06。

## 隔离验收

所有实例必须通过IM01新目录夹具创建。需要正例控制状态时，只对新建合成实例临时解除测试锁，且从不运行模型/工具；退出由夹具重锁停止。覆盖C0每写点故障全回滚、真实内部生产者、同键异义、跨键重复、多独立连接竞争、来源同字节不同身份、旧请求不刷新额度/期限、source完成态、取消/停止/到期/耗尽、合法前向CAS与非法恢复/review_round、预留/实际/未知区分。当前实例、冻结SQL、Runtime及版本启用均不修改。
