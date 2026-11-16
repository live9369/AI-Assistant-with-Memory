# IM11 严格运行接线实施记录

日期：2026-11-10。状态：实现及专项已收齐，待统一源稳定门禁；不能视为完成登记。

本项使用新建synthetic实例、确定性计费协议及fake transport；没有调用真实模型、Codex账户、外网端点或当前正式实例，没有部署或唤醒正式实例。认证接口验证包含隔离本地loopback HTTP/Bearer路径，不将其说成外部模型网络或正式服务。机械替身不认证生产模型能力。

## 已接线范围

- 普通Engine独立完整输入：真实原活动八维账户、所有字段来源manifest、实际T1—T13计算、当前向量与有界历史选择、会话前序与跨会话M04召回、当前实际recipient ACL、全新thought_request/attempt/result/实际provider wire谱系。旧认知world输出仅候选，不能旁路TL接纳。
- 新内部活动：strict process_one在旧tick/StateCollector前分支，真实agenda promise或exploration配置/代次/次数/到期/间隔选择任务，self-intent与真实触发联合依赖，一次初始化原账户；探索schema2及原输出验证/接受/真实工具反馈仍参与。每input_epoch是新的独立思考，非provider会话续传。
- 实际工具：Policy授权、参数/版本、源与接收方独立复核；原账户实际进入与消费；受管进程真实总时限；进入后unknown不重试。输出及人格/习惯/反馈等派生对象可追到实际结果和原输入。
- 原生学习：实际C0、四类Product、独立学习schema、真实Bearer编写的全绑定复核、G01—08分别核验、C1/C2、候选等待和M14投影。没有独立领域证据的world/method/causal内容不因控制者批准变成已证实事实。
- 管理使用：真实Bearer仅认证身份；聊天、思考、模型、审批、活动、健康和日志逐来源及实际接收方核验；停止/锁下合法审计零写，无模型或输入注册。发消息另走实际控制收据，不能唤醒。

## 计量及版本语义

物理读取meter包含SQL返回行、工件字节及M17隐式原件/视图验证，受原deadline约束。整次IM07读取接管需真实work/account/run/entered reservation与唯一请求绑定，不以caller bool关闭原计量。模型阶段独立预留，外层实测暂停/恢复，不重复结算模型时间。byte/time运行参数只能收紧固定包允许值及本人真实预留，不修改原包，不抬原账户caps。

provider测量逐维保留known/unknown、basis及实际observed route。IM05账本仍采用完整已知向量才settle；任一未知维度保持usage_unknown与原占用，已知事实保留在measurements中，不补0、不释放未知。

原地可变数据形成真实不可变观察snapshot/event；原native CAS与技术snapshot revision分开。generic历史引用不要求等于当前人格状态；live_state在实际入口/返回逐字段重比对。政策、权限、配置等必须当前。白名单不可变payload行可用技术VersionToken0，严格核实际artifact/digest/字段映射，普通Ref.known仍要求真实registry；有native修订或冲突registry不能回退0。

真实当前健康准入以只读完整SQLite/FK、磁盘、恢复锁和队列探针进行，不抬30s TTL、不重写封存包或旧state_observation。未知/失效关键探针拒绝。

## 已知限制

真实生产路由目前没有本项目已核定的可信输入计数/上界与完整硬限额合同，严格路径默认blocked_before_start。HTTP numeric输出限额/schema已接，不能凭兼容外观、模型名称或len(text)/4认证能力。Codex真实严格路径另缺已核输出token硬限额及已安装版本的完整干净上下文合同，保持拒绝；未迁移现用配置模型。假传输固定100 input-token计费协议只属于测试，不是BPE、真实context能力或生产配置。

历史性能开发测量保留：普通初轮182.648s，经只读连接/不可变映射与单边界精确去重为121.015s；启用八模块且17个历史episode的开发链曾在287—294s按真实资源slice/计数机会拒绝。包括1,184,634行、306,802,240 bytes的实际重复读取记录。这是严重性能限制，不能声称日常响应性能已达标；IM19须继续测量。原600s、2m scan/items、512MiB等总caps没有为通过而增大。

native同work waiting/review续处理归IM13；实际F2/F3传播与副本清理归IM12，当前不冒称物理删除已实现。生产领域支持/反证比较不由确定性端口代替。外层杀本地受管进程不证明远端服务取消或账单已取消。

## 开发验证

已完成专项包括真实工具/未知效果、管理停止零写与Bearer、native真实C0→C1→C2、静态0真实映射、snapshot CAS/历史/live、回滚仅移除本事务新inode、当前健康、内部准入及固定计费/真实byte slice。最新分组日志保存在/tmp/digital-life-im11-*；最终源稳定后统一门禁证据另行记录，不能用这些分组日志替代统一完成结论。

E2E09在用户中断时未结束、日志为空；残留会话无效且进程列表确认无验收残留，未计通过。E2E10的后续结果见下方开发记录；本项最终以源稳定统一门禁为准。

调度housekeeping补充：固定持久60s/每周期1次，最小管理消费事实记录真实主库scan/bytes/elapsed；无结算/unknown保持占用，配置/时钟后退/新进程不能换键领新机会。先确认enabled再读历史；未知artifact owner拒绝。该有限管理scope不授模型或工具能力，固定控制见证开销与活动资源账本分列。

E2E10实际在IM11组合原16,384逻辑扫描护栏处拒绝，333.925s、1,271,593行、333,909,781 bytes、0 unknown，模型尚未进入。开发log保留；当时完整不可变源码快照未保存，不用作最终sourceHash证据。具体组合容量已按设计调整为既有native的65,536，原600s/2m/512MiB未变，正在E2E11验证。


E2E11完整八模块与17个episode场景已通过：wall 434.118s，known scan/items 1,536,293，bytes 394,504,065，elapsed 433,883ms，unknown reservations 0；原600s/2m/512MiB不变。该成功仍使用synthetic固定100 input-token协议，且不是最终源码统一门禁（此后还有有限调度/控制面/验证器收尾）。不能把434s称日常可用性能。

调度轻量queue poll另属框架控制元数据：真实Runtime空闲循环0.25s sleep，每调用1s/1,024行/1MiB上限，StrictEngine.control_metrics累计真实次数/scan/bytes/elapsed/unknown；不读任务或源正文，不向已有活动扣账，也不授模型/工具许可。重source准入仍60s持久单次机会。控制者保护性取消是Bearer认证后的具名控制写，和纯GET审计分开，停止/锁仍不唤醒；日志导出复用同一源过滤器。

独立TaskLoop文件验证器的真实有界读取现在纳入当前物理meter：预核实际size，最多读取65,537字节以识别增长，实际bytes/scan/items入当前slice，失败未知保留。无meter的旧schema3调用保持原语义；此处不创建新预算。闭合验证器配置来自实际已注册TaskLoop/promise。

新增针对性验证包含：housekeeping空tick/clock后退/新真实process/未结算占用/未知owner；配置总deadline包括最后source guard；本人实际模型byte/time slice；错误account/run/重复read接管；input_epoch不复用旧成功；独立verifier读取计量；停止锁下Bearer保护性取消和同源日志导出。开发分组均已保存，不覆盖先前失败/中断日志。

## 实际源码清单

相对IM10绑定源码记录的实际变更／新增如下；根维护的公共验收脚本及独立UI补证另由根核定。

- `digital_life/application/authorization.py`
- `digital_life/application/chat.py`
- `digital_life/application/configuration.py`
- `digital_life/application/engine.py`
- `digital_life/application/execution.py`
- `digital_life/application/goal_regulation.py`
- `digital_life/application/habit_learning.py`
- `digital_life/application/memory_quality.py`
- `digital_life/application/personality_growth.py`
- `digital_life/application/scheduling.py`
- `digital_life/application/task_loop.py`
- `digital_life/application/telemetry/states.py`
- `digital_life/application/thought_inspection.py`
- `digital_life/application/tool_learning_acceptance.py`
- `digital_life/application/tool_learning_activity_budget.py`
- `digital_life/application/tool_learning_admission.py`
- `digital_life/application/tool_learning_budget.py`
- `digital_life/application/tool_learning_contexts.py`
- `digital_life/application/tool_learning_controller_read.py`
- `digital_life/application/tool_learning_eligibility.py`
- `digital_life/application/tool_learning_engine.py`
- `digital_life/application/tool_learning_execution.py`
- `digital_life/application/tool_learning_health.py`
- `digital_life/application/tool_learning_observation.py`
- `digital_life/application/tool_learning_recall.py`
- `digital_life/application/tool_learning_representation.py`
- `digital_life/application/tool_learning_runtime.py`
- `digital_life/application/tool_learning_runtime_learning.py`
- `digital_life/application/tool_learning_runtime_owners.py`
- `digital_life/application/tool_learning_source_snapshot.py`
- `digital_life/application/tool_learning_work.py`
- `digital_life/domain/ports.py`
- `digital_life/domain/tool_learning_resources.py`
- `digital_life/domain/tool_learning_sources.py`
- `digital_life/entrypoints/http.py`
- `digital_life/entrypoints/runtime.py`
- `digital_life/infrastructure/llm/fresh_learning.py`
- `digital_life/infrastructure/persistence/sqlite_store.py`
- `digital_life/infrastructure/persistence/tool_learning_meter.py`
- `digital_life/infrastructure/persistence/tool_learning_store.py`
- `digital_life/web/app.js`
- `tests/panel_fixtures.py`
- `tests/test_goal_regulation.py`
- `tests/test_tool_learning_acceptance.py`
- `tests/test_tool_learning_eligibility.py`
- `tests/test_tool_learning_observation.py`
- `tests/test_tool_learning_runtime.py`

## 统一门禁中断与回滚清理补正

首轮统一门禁在源码只读复核发现同根跨instance引用缺口后主动中断；记录为`outputs/acceptance/tool-learning/im11-development-probe-unified-01.json`及独立termination记录，保存真实当前source hash、命令和中断前后日志，exit130，未编造测试总数/稳定完成，未生成im11.json或完成登记。只向已核实本次验收PID90579发送SIGINT，没有宽泛kill或正式实例操作。

已补正所有instance的storage_ref引用核验、同根gate→新BEGIN IMMEDIATE证明与unlink原子边界、nested rollback延迟到外层结束核对、未知commit/DB/gate状态保留。新增真实A/B双identity共享blob根反例、真实并发SQLite writer阻止检查与unlink间新引用、外层成功的嵌套回滚、DB错与普通inode替换保留；既有shared/symlink/commit acknowledgement unknown反例仍保留。专项日志`/tmp/digital-life-im11-blob-root-repair-*`，后续重新冻结统一门禁为唯一完成证据。

补正后的相关13项已通过（5.811s）：原rollback四项、新全根/并发/嵌套/未知五项、native flow二项与Product lineage二项。没有重跑无变更的全部专项；现在再次冻结源码，以随后完整统一门禁登记为准。

## 首轮完整门禁与实质修复

统一02完成1179项：3 failure、0 error、0 skip，source稳定，832.700s；原`outputs/acceptance/tool-learning/im11.json`保留为失败证据，不是完成记录。完整enabled场景本轮443.372s、1,568,298行、397,724,134bytes、443,141ms已知消费、0 unknown。

三项问题：IM08历史断言只计原source边，未覆盖新增实际proposal生产谱系；G1 process在原启动与entry混合的5s等待中未到entry且原证据无子诊断；新provider/meter违反分层、反向import application。修复为逐修订核具体原source与proposal、无历史交叉且相同source不当独立支持；G1启动就绪与实际entry分开并完整诊断；端口和资源词汇移到纯domain、原app兼容reexport。G1原始具体原因无法由原证据还原，未被前缀复验强行解释为CPU负载或启动慢。相同全模块预加载、相同前置顺序的89项通过（36.608s），最终仍须完整统一验证。

另补根复核的两项实际展示回归：strict reader精准读取真实BehaviorPolicy事件并核源；legacy reader不覆盖完整input变量。真实BehaviorPolicy.select记录的3项专项通过（1.054s），包括真实概率/决策映射、完整input保留、停止/锁下零写、真实F1保护性源撤回后拒绝，以及legacy原输入保留。最初撤回夹具缺known work的开发错误已保留在probe25日志，改用真实当前C0 work，未放宽F1契约。

## 03诊断与最终收尾

统一03保留为`outputs/acceptance/tool-learning/im11-recheck-d8b132f1c92d43a8810881115c25bc55.json`：1182项、2 failure、0 error/skip、source稳定，web语法与实际离线DOM/请求smoke通过。完整enabled场景437.075s、1,550,185行、397,679,271bytes、436,846ms已知消费、0 unknown。

G1此次诊断已明确fork child exit=-11/SIGSEGV，仅child_started、没有Store_opened，尚未资格或实际callback；不是timeout或权限拒绝。改为spawn独立解释器/独立Store，不继承活SQLite/线程状态，原实际entry、F1互斥/先后/blocked及exitcode仍验证。02原失败无诊断，不能追溯断言原因相同。另一个旧GoalRegulation断言仅因序列化factors键序改变求和顺序而差1 ULP（0.7083393333333333与0.7083393333333332），生产算法不改；公式采用12位容差且分数0—1范围继续精确断言。

只读核对supervisor：内建worker只执行HTTP传输或受管workspace工具，不打开/操作Store/SQLite；源资格guard和持久化在父进程。未用G1 spawn变更认证所有fork安全，也未改写provider监督策略。新增子普通异常与SIGSEGV专项：只进入一次、父进程存活、usage unknown/保守原占用、无重试、无observed route；local transport_entered只表示本地机会进入，不证明远端模型收到。相关3项通过（0.980s）。随后冻结运行04全量，不将这些专项替代完成门禁。

## 04完整通过与elapsed局部复验

统一04：1183项、0 failure/error/skip、source稳定，实际web语法+离线DOM/请求检查通过，已登记complete。证据`outputs/acceptance/tool-learning/im11-recheck-f70a15d9e78747fca14b5ab1437d0407.json`，SHA256 `678f934aaaed36151f68751a6c2e8b0a441d58f94233534b8cdae6a6d2f34d0f`；原失败和中断历史不动。

04等待期另发现确定性的保守重复计时：10ms外层＋50ms排除窗口，窗口内time()令旧max保留60ms。不能据此推断旧长E2E一定误账（后段读取足够长可覆盖峰值）。按根裁定保留04完整通过，再小范围补正active pause、嵌套并集、异常恢复，并用真实原work八维账本验证elapsed守恒。该集成还确定IM07旧Model计时截点包含post-use guard，已改为实际port完成／异常的finished，后置核验属于read。Native父侧绑定检查纳同一排除窗口、模型slice扣除已过时间；提前失败清空上次provider临时测量，未知继续保守占用。没有改cap或权限／屏障条件。

开发probe29/30保留守恒失败记录；初次局部编辑误命中同名读取计时行，已恢复该读取分支并精确修正Model_usage，未进入稳定证据。probe32中夹具把材料read与Model post-use都算同一延迟，已改为按真实thought_requests上下文区分，未放宽生产校验。包含假时钟、窗口内真实Store读取／异常／嵌套、实际原预算成功／已消费后本地失败／后置核验归属／提前拒绝不借旧消费及受影响IM07路径的54项通过（23.484s）。随后局部稳定补证还包含分层5项；该补证追加绑定，不能替代04全量。IM12/IM19依赖门再覆盖最终全套，未为本修复重复18分钟全量。
