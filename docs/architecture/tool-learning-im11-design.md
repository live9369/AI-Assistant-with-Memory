# IM11：实际输入、推理与外部使用门禁

版本：V0.1；日期：2026-11-10；状态：实现设计（仅隔离验证，不部署、不唤醒）。依赖：IM06、IM10 已完成。规范优先级仍为冻结 contract/storage/Q09，本文不改协议或 DDL。

## 1. 目标与启用边界

本项把前期服务的可信端口接到实际配置、控制、原始预算和模型适配器。新路径默认关闭；启用后不得回退到旧 Engine/Executor 路径、只读 audit、测试 reasoner 或未经追踪的普通记忆。旧 schema3 兼容的发布/回退验收归 IM15/16，本项保留旧行为回归而不宣称其具有 schema4 屏障。

接线分三层：`ToolLearningRuntime` 绑定单实例真实控制和认证入口；`FreshLearningProvider` 将固定 packet 转换为各实际 provider 请求；受控读取/调用监督器负责实际八维计量与总时限。服务仍拥有其原 C1/C2/F1 事务；Runtime 不以通用 SQL grant 代替 M03/M04/M12。

## 2. 固定输入与真实调用

IM07 的 TL-OBSERVATION-THOUGHT-1 packet 是学习推理唯一输入，包含真实 thought_requests.id、work_ref、固定 configuration/model/provider 引用、source/baseline、完整 Scope、输出契约和本次原剩余额度内的 limits/deadline。以可信 request.contract 选择学习 schema/validator，绝不依据响应自报版本。学习结果不塞 action.explanation，也不创建工具副作用。

普通严格思考必须对最终完整 packet 建逐字段 manifest：任务/当前观察、会话、召回、认知、人格、习惯、关系、动机/内部状态、探索与协调材料，以及配置/策略/模型。每一字段指明原 source token、固定修订、Scope、用途、recipient、field_path 和实际 JSON digest；不能仅登记 selected_memories。技术常量也须分类，不能以常量名掩盖用户材料。

准备材料持久化前核保留权限；全部依赖登记成功后才写装配完成证明，证明绑定整个固定 request hash、field/source manifest、当前输入集合与真实 request ID。部分登记保留追踪事实但不得派发。actual entry 和 result-use 使用 IM06 同一绑定快照；请求改变须新身份，不原地换正文。晚到响应在保留授权、全部源/版本/epoch、停止/取消/期限复检之前只留内存，不存正文或摘要。context、prepare/material、解释和结果的副本均登记实际可清理 consumer。

## 3. Provider 与总时限

remote_chat、Ollama、llama.cpp、Codex 均保留 action/exploration/cognition 独立契约，新增明确学习分支。HTTP 请求只包含固定系统契约和本次 packet，无 history/context 续传、无工具描述。路由、结构结束状态、refusal/incomplete、实际用量均单独核验；缺失供应方用量保持 unknown，不能以预留量或模型文本自报填补。

HTTP socket timeout 不等于总 deadline。生产调用经可终止的外层独立进程监督，父进程以单调时钟控制实际总期限与响应 byte 上限；到期终止并回收工作进程，晚到结果不发布，已进入的未知用量保持占用。进程组策略须覆盖嵌套子进程；不能依赖单元测试外层超时作为生产保证。替身传输也走相同监督边界，挂住/慢流/晚到均有反例。

Codex 每次新进程、空临时工作目录，不 resume/fork；禁仓库指令、工具、MCP、技能和用户配置等额外上下文。`--ephemeral` 仅不保存 rollout，并非干净上下文证明。能力必须由实际本地已核合同声明，不能仅凭网上新 flag 假定已装版本支持。当前未证实 CLI 输出 token 硬限，因此真实严格 Codex 路径 blocked_before_start；提供学习 schema/隔离命令构造与 synthetic capability 传输验证，不虚称已可严格调用真实账户。保持现配模型不迁移。

## 4. 原账户与受控读取

IM05 八维为 input_tokens/output_tokens/attempts/tool_calls/scan/items/bytes/elapsed_ms。所有阶段沿原账户先预留、实际入口登记、按真实消费结算；unknown 保守占用，未进入才可证明零成本释放。新 schema4 普通活动仅在首次创建时由真实策略的原始 caps 建一次读取账本，不能每次 query 新造 cap。旧活动缺原始 scan/bytes 等额度就明确拒绝严格读取，不猜值、补零或换账户。

本人已 entered/reserved 的合法阶段 slice 与全局剩余不同：IM07/08/09/10 的读取上限须从该原账户本次真实 slice 取得，不能预留后再以 global remaining=0 拒绝本人，也不能忽略他人占用。读权限绑定 work/account/operation_ref/请求指纹/阶段/尝试/预留和有效剩余，不可一个宽松 grant 无限重读。C1 内只能消费外层已预留机会，不新预留。

统一物理读取 meter 覆盖 M17 validate_pending/response/`__walk_refs` 的隐式 artifact 原件和 view 读取、依赖 metadata/屏障/Scope、重放、基线、正文、构造与复核重复读取。权限/epoch 不缓存；不可变材料如缓存需明确实际未发生二次物理读。时间实测，不把未测记已知0。审计仍严格只读，只受本地请求上限，不写共享账本。

## 5. 可信所有者与控制者复核

控制、策略、配置与模型 token 按其实际行版本/CAS/epoch 解释；静态已知0不是 unknown，不伪造 registry 修订。支持内容按固定 immutable revision 展开，稳定 owner 的 active 屏障仍有效。

管理 HTTP 既有 Bearer token 校验成功后才可调用具名内容复核 authoring helper，生成不可变 TL-CONTROLLER-CONTENT-REVIEW-1 记录；全绑定 proposal/digest/round/native_expected/legacy expected/Scope/policy/group/expiry。actor 字段等于 controller、工具审批或调用者传 bool 均不授权。停止/唤醒锁不妨碍已授权保护性撤回和只读审计，普通思考/动作仍拒绝。

八关必须由实际所有者核验。已配置 source_report 走真实来源/locator/字面/Scope 支持验证；world/method/causal 缺独立语义与反证能力只能 incomplete/candidate，控制者批准不产生科学真值。C1 后协调投影仍尊重 M14 所有权。

## 6. 隔离验收与交付

所有 provider 使用 fake transport，不连接外部模型网络、不读账户、不启动正式服务或真实 CLI；认证接口包含隔离loopback HTTP/Bearer验证，不能误写成从未启动隔离本地服务器。验证学习 schema 与 action schema 不串用；独立 packet/路由/实际 request ID；unknown 用量、错误/拒绝/不完整；挂住/慢流/晚到总期限；原预算 slice 与超额/重复进入；完整装配前不得回调；F1 先到及回调后撤回不得保留输出；配置/策略静态0与 CAS；认证复核绑定；真实 source_report 全链和不支持域候选；旧 provider/action/cognition 受影响回归。

实现不能以默认拒绝端口存在代替完成接线。若实际能力未具备，接口明确启动前拒绝并在报告列出精确受限路径；生产 provider 的真实模型验证另需用户授权。本项不实现 IM12 清理、IM13 恢复或当前实例更新。

## 官方资料依据

- [Codex CLI reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli)：独立执行、输出 schema 与配置选项。
- [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)：instructions/skills 配置需按本地实际能力核定。
- [Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)：请求选定 JSON schema，拒绝/不完整不等于成功结构结果。

## 7. 可变无原生修订源的真实观察版本桥

本地 trait/state/关系等白名单行没有 native revision 时，不能一直用 revision=0 代表内容。M17 的 `SourceSnapshots.capture` 在真实源所有者授权后，同事务写实际不可变 runtime_event 和完整 payload，并将那个真实 event ID 登记为稳定 origin 的递增技术 snapshot revision。payload 包含 origin Ref、字段 selector、实际值及 canonical digest、observed_at、native_revision=NA、scope 和 snapshot_revision。它仅声称观察到了这些内容，不能声称捕获了未观察到的中间变更或提供了原生 CAS。

M17 `validate_ref` 只对白名单原 kind 增加这一明确桥接分支，须核真实 event/object registry、来源类型、origin/实际 payload/snapshot revision 映射。普通 Ref 和真实 native revisions 保持原约束，不造空 registry 修订。输入资格选择指定 snapshot 的来源消费者，不混入其他快照支持。源身份屏障和源所有者权限仍在原 origin，真实 event/payload 都登记受管 read/delete 依赖；已有 active origin 屏障时保守阻断捕获和使用，不借重新采样恢复许可。

新读取发现值变化才追加实际新 snapshot；入口及结果使用仅重读固定 selector，比对原 digest，变化即拒绝旧请求，不能在资格检查或只读 audit 时新建/修复快照。未观察到的 A→B→A 不制造中间历史；实际观察过 A、B、A 则有三个真实观察版本。已有 native immutable revision 的类别直接用原版本。

## 8. 普通活动原始账本与阶段所有权

`ActivityResourceBudget` 的 owner 是实际 activities 行和原 activity_budget_accounts，不新建伪 tl_work。仅原活动创建事务内经真实初始 policy owner 核准后，保存不可变 TL-ACTIVITY-INITIAL-CAPS-1，活动 document 为 TL-ACTIVITY-BUDGET-1；复用 IM05 实际 reserve/entry/settle 算法。旧活动、使用后活动或已有分配不能补造初始 caps。旧 Budget 不能接管新账本。真实 ordinary recall 选择该原账本，旧缺八维者继续拒绝。

同一个普通活动既消费自身资源又分配 learning work 时，C0 除既有永久子分配外，额外计入原八维 ledger 的本人真实消费/预留，未知停止新分配；父继续执行也须扣全部子分配的 scan/items/bytes/input/output，而非只扣旧三维投影。阶段读机会必须绑定原 account、真实 run/attempt、唯一 occurrence 和剩余本人 slice。

逐维测量事实独立使用 TL-INFERENCE-MEASUREMENTS-1：保留每维 known/unknown、实测依据和 observed route，包括结构/路由失败及晚到结果。IM05 原账本仍仅全八维 known 才实际结算，任一未知则 usage_unknown 并保留完整预留，不部分释放；已知统计事实并未丢弃。elapsed 为本地单调实测，不是供应方账单时间；杀本地 HTTP transport 不代表远端执行已取消。

CAS-only 类别单列为实际 owner 白名单：activities.revision、goal_items.state_revision、commitment_items.state_revision、cognition_plans.version。其观察 payload.native_revision 为当时实际 CAS 的 known 数值（含0），snapshot_revision 仍是独立观察版本；live 入口同时核 CAS 与 selector/digest，值的 ABA 不能掩盖 CAS 增长。无 native 字段者才 NA；已有真正 immutable registry body 的类别直接使用原修订。

普通输入收据可在进程未运行时创建，activities.release_id 的必填技术值暂以 `UNBOUND:awaiting-real-runtime` 明确表示尚未绑定，绝不当真实发布版本。严格准备阶段只能绑定到 control.process_runs 所指实际 deployment 的 release/build，并保留实际 deployment/process/epoch 谱系；已经绑定其他发布的活动不能静默重标，须由恢复/发布流程处理。

当前 live_state 与历史观察通过完整 manifest/proof 的封存 usage 显式区分，不由调用者 bool 或stage名称改变。generic snapshot 版本核验只证明真实观察对象、原origin权限/屏障和映射；已合法生成的历史回复依赖当时观察，正常人格成长不将其抹去。实际准备后的 live_state 每次进入/结果使用均重新比对原 CAS/selector/digest，政策/配置/模型等当前控制字段另作 current_control 精确当前性核验。历史引用不会替代当前状态或将旧观察升级为当前世界事实。

## 9. 实际动作与管理使用边界

`StrictActionExecutor.dispatch(intent_id, backend=None)` 从当前真实进程建立M14/learn通道，接收方固定实际控制者；它独立核验真实Policy grant、参数hash/proposal revision及已采用thought_result的完整生产谱系。原活动账户预留tool_attempt，实际进入才消费授权；受监督的单次registry调用有总时限和字节界限。进入后失败／超时留下unknown与原占用，不重试、不把在途副作用说成已取消。成功receipt/result及实际副本登记read/delete来源，返回与持久化前重新核源。默认真实workspace工具由独立受管进程执行；测试替身仍经过同一实际入点。

`ControllerMaterialReader(store, bearer)` 只由实际Bearer验证建立history_audit会话。聊天、思考快照、实际provider wire和审批展示逐原件／派生源核实际控制者recipient，内存ACL不被管理身份覆盖。复用IM10只读审计谓词，全部SQL、依赖、屏障、工件和语义检查读受单次固定本地scan/bytes/time meter限制；不写run、event、working_memory或预算。stop/WAKE_DISABLED不阻止合法只读审计，也不撤销来源屏障。artifact必须实际属于相应owner字段，不能拿合格owner配任意blob。发消息另走真实控制面收据与原始账户创建，不触发唤醒。

## 10. 原生学习编排与计量接管

`StrictLearningCoordinator` 以当前受核运行进程能力连接C0→IM07→C1→C2。准入来源限真实本活动原始perception_signal或已产生的action_result；receipt／artifact／source_revision逐字段核实际归属，不重新执行工具。来源首先保持source_report；当前本地接纳所有者只能证明精确新事件范围内的字面报告，world/method/causal及未具比较依据的existing目标保持incomplete/candidate。G01—G08分别生成真实检查，不统一返回pass。控制者复核必须是Bearer authoring helper产生的不可变全绑定记录及真实认证事件，不能以actor字段代替认证。

整个assess实际读／写阶段先在原work账户预留真实retrieval run，安装PhysicalReadMeter；IM07具名 `read_operation_context` 为TL-ASSESS-READ-OPERATION-1，字段为request_fingerprint、work_ref、account_ref、run、reservation_id。IM07再次核原work/activity/account、实际entered reservation及同一请求绑定，并由实际编排所有者证明仅本次作用域有效；默认返回None沿既有局部读取路径，不能由caller bool接管。接管时复用真实run，不再为同一物理读另reserve/settle。外层只结算一次；guard、M17隐式读、产物保存、失败后实际已读均纳入。模型attempt单独原账本；受控模型调用区间显式暂停外层elapsed并在finally恢复，实测区间归模型attempt，不减估计值。wire字节归模型，主库物理读取／持久副本归read阶段；未知消费不补0。

C1/C2同样由外层真实run预留并覆盖全部重复复核和写入；具名read_byte_limit仅返回该本人entered slice的实际剩余，不因全局remaining已扣本人预留而变成0，也不返还他人slice。每个read_context绑定请求指纹、真实run/reservation/account、唯一作用域，C1中不新预留。组成员逐成员当前角色与来源核验，持久stage不保存认证能力。

性能记录：同一新synthetic普通Engine全高维计算链，fake transport的首轮182.648s，连接／不可变字节复用后128.606s，局部owner核验后126.491s，单门禁精确不可变Ref映射缓存后121.015s。不是日常性能验收通过；仍显著偏慢。缓存仅同实例／连接／真实gate读边界，任何同连接写清空，离开清空；不缓存权限、epoch、barrier、当前head或live digest，不跨模型入口／返回／外部实际用点。IM19须保留真实性能测量；不能删来源或放宽时限后宣称性能问题已解决。

## 11. 严格调度与内部新活动准入

strict feature在Engine.process_one最前分支，旧tick、StateCollector和旧GoalRegulation.claim不得先执行。内部准入不是控制者消息：由真实运行PID/epoch核定的具名调度所有者，根据已启用agenda/exploration配置、真实不可变触发事件、当前承诺状态/到期或探索代次/次数/间隔选择任务，绑定canonical任务hash及幂等键。生成信号source_actor=self，标记derived/self intent，不能冒充外部观察或控制者收据。承诺沿原promise/controller授权及verification保留完整来源。

创建与原账户八维caps绑定、原任务binding、必要TaskLoop配置和目标链接同事务完成；探索原max_rounds×3×4096 tokens、max_rounds×4 attempts、max_rounds tools与当前policy取交集，不在创建后抬限或覆写账本。既有代次binding、未完成活动、unknown或仍占用的机会均参与全局准入，不能靠另开账户绕过间隔/次数/占用。已失效触发、错hash、伪module、重放异义拒绝；同义重放复用原活动。仅新活动归本项，native waiting/review同work恢复仍归IM13。

模型传输字节机会为原packet envelope与原账户实际余额的较小者，具名execution_max_bytes只能进一步收紧实际监督器，不能修改固定packet；门禁物理读取占有自己的slice，不把原packet整个字节cap重复预留给模型。每input_epoch生成独立完整thought_request，旧epoch成功不替代下一次独立思考。

调度选择消耗属于实际进程/当前policy授权的housekeeping机会，不属于已有活动免费读取。每实例持久`strict.housekeeping.reserved`→`settled`最小管理事实；固定60s最小间隔、每周期1次，跨空tick/配置键/新进程均查询同一机会，时钟后退不能刷新；崩溃未结算或读取字节unknown保持占用，须显式协调后续处理。实际主库行、字节和单调耗时记录在settled，原固定管理见证的存储开销单列，不宣称由活动账本支付。机会最多10s、16,384 rows/items、8MiB且与当前policy caps取小值；不得用于模型/工具派发。先仅读两个最新配置确认enabled，禁用不扫描模块历史。工件读取前按真实event/signal/config/model/result owner闭合白名单核当前来源，未知owner拒绝；资格自身的受控metadata/映射读取仍在同meter下，不给任意正文raw后门。

IM11普通组合的逻辑资格容量统一为65,536行，和既有native组合一致，仍有节点/路径/行上限及原物理meter；超过或原物理预算更小均拒绝。不是放宽IM06的屏障/权限/版本语义，不新增活动额度。E2E10在16,384固定逻辑护栏处真实拒绝：333.925s、1,271,593行、333,909,781 bytes、0 unknown；未进入模型，不称模型失败。该开发log保留，源在继续修改，未保存当时完整不可变源码快照，不能当最终绑定证据。

轻量queue poll属于框架控制元数据，保留真实Runtime有限idle/poll cadence及每调用1s/1,024行/1MiB上限；不读任务或来源正文。实际StrictEngine.control_metrics累计poll次数、真实scan/bytes/elapsed和unknown次数，可由运行协调器监测；不是已有活动的扣账，不授模型/工具权限。选中job后所有活动材料与实际使用回原账户。它不受重内部source选择的60s锁延迟，避免人类新消息等待一分钟。

回滚新blob清理另经同根dispatch gate→无既有事务的新BEGIN IMMEDIATE，查询同blob根所有instance的storage_ref，引用证明与unlink处于同一实际SQLite排他写边界；不拿旧read snapshot证明无引用。仅本事务记录的同device/inode普通文件可删。nested rollback不在外层持DB锁时取gate，先保留到外层结束（即使外层成功也核未登记子blob）；提交结果未知、DB/gate错误、换inode或已有任意instance引用均保留。该技术回滚清理不等于IM12删除业务；实际受控读取仍纳当前meter，额度不足则保留待处理，不为清理绕过原预算。

## 12. 分层与行为审计补正

fresh学习端口位于纯domain.ports，八维资源词汇位于domain.tool_learning_resources；application保留原名称兼容reexport，infrastructure不得反向依赖application。

思考审计的behavior_decisions从真实`behavior_policy.selected`事件取得，以事件实际`/model_derivation`依赖→thought_result.request_id精准绑定本次request，再核不可变body.request及真实finalized/probabilistic decision归属。每个事件/工件与最终返回均走同一source/recipient审计，不由UI传入概率数组。legacy inspection使用独立behavior_snapshot变量，完整原input快照不能被最后一次行为记录覆盖。

G1隔离进程验收将child启动/Store打开就绪与实际callback entry分开：冷启动最多10s，Store就绪后原实际entry上限5s不变；记录child_started、store_opened、实际entry、blocked/异常、exitcode和实际顺序trace。02原观察没有子诊断，不能从后续通过倒推其具体原因或将它归因于后面的长E2E。

03的新G1诊断具体记录fork子进程exit=-11（SIGSEGV）、仅child_started且无store_opened，未进入资格或callback。G1改用spawn全新解释器/独立Store，继续真实entry、F1互斥与先后、第二次blocked和exitcode断言；不改生产G1算法。此结论不追溯替02补造原因，也不认证所有fork安全。现有supervisor仍仅对内建纯transport/workspace子回调使用fork，不在子回调打开/操作Store/SQLite；before_transport资格与持久化在父进程。任意自定义Python回调不承诺sandbox/fork安全。显式子异常或SIGSEGV保持消费unknown、无自动重试、父进程存活；local transport opportunity entered不等于远端模型确认收到。

## 13. 模型／读取elapsed唯一归属

排除窗口进入时固定外层计时端点，窗口内Store读取仍扣scan/items/bytes、仍检查原绝对deadline，但不能将child时长写进外层elapsed不可回退max；嵌套窗口只扣并集，异常finally恢复。Native整个实际fresh port含父侧绑定检查由模型机会拥有elapsed，进入后已耗时间从本人真实模型slice/配置上限扣除；不增加任何cap。IM07在实际port返回／异常时取得finished，之后IM06 result-use及保留核验属于read阶段，不能再次算Model时间。新机会在任何可能提前拒绝前清空provider旧临时测量，避免借用上次消耗；已知／未知账本协议不改。
