# 第二轮剩余工作：最终验收方案

状态：**方案就绪，尚未执行新一轮重测**。日期：2026-11-11。本文仅安排隔离合成实例与替身模型验收；不访问正式实例、认证文件或真实模型。产品实现由主任务另行设计、实施。

## 1. 本次必须证明什么

按依赖顺序完成下列事项，不能把早期版本结果补写成最终版本结果。

| 顺序 | 场景 | 验收结果 |
| --- | --- | --- |
| 1 | 保持原8模块、原17条持久化片段、原真实聊天路径，连续两轮 | 两次均成功，确有两次独立provider调用；第二轮包含第一轮合法记忆与对话关联，原预算内完成 |
| 2 | 既有0历史独立最小连续场景 | 原负载原样复验，确认该已知失败也修复；不能替代17历史主连续场景 |
| 3 | 必要故障/权限/完整输入回归 | 停止、撤权、源变更、回滚、跨连接/进程、未知观察器和预算失败等保护仍通过 |
| 4 | 冻结最终产品、夹具、SQL、配置和工具 | 后续所有性能/增长证据都绑定同一冻结目录摘要 |
| 5 | 原普通17负载，最终版独立三次计时 | 与封存旧版三次比较，中位耗时及实际返回行分别至少下降20%；输入不缩水 |
| 6 | 最终版0/17/50/100持久化历史增长 | 各档来源/选择范围/预算/输出有据可查；触原cap如实停止，不提额或截短输入 |
| 7 | 原11Memory+关系共享来源增长场景 | 原负载完整复验，确切说明是否进入模型、是否同一原件进入记忆和关系；按原TODO，触cap可记录增长限制 |
| 8 | 最终综合检查与交付 | 旧失败完整保留，原机制证据与最终变更影响可追溯，报告/TODO按真实条件更新 |

第1项是功能验收，不可因增长场景允许blocked而改写为“连续性通过”。模型替身只能验证工程路径、结构、来源和独立调用，不能证明真实模型理解、语言能力或科学效果。

## 2. 旧证据可以怎样使用

- 原封存旧版三次：145.216347875、146.978334250、143.217004750秒；中位145.216347875秒，行数每次1479635。只要原harness与合成夹具保持可比，就保留为预先固定旧基线，不重新挑选旧值。
- 预设时间门槛：最终三次中位数不高于116.173078300秒；行数中位至少下降20%。若未达门槛，记录原值，不追加挑快值的重跑。
- 117.552631625秒/19.050%及635178行/57.072%是**分层修复之前**的冻结测量；当前产品已改过两个文件，不能沿用为新最终源实测。
- `pf07-final-summary.json`中的`product_source_current_equals_final_three=true`属于该文件生成时的历史断言，不能被当作当前磁盘状态。
- 原全套1639项有1失败1错误；后续两项修复的287项复验已通过。原失败及其组合审计仍有效历史，不改写成一次全套PASS。新增实现应按真正影响安排新的必要回归，不能只搬旧标签。
- 原0/50/100档仅为中间源码的持久化历史增长证据。新最终源必须重跑；17档以最终计时/输出样例及来源审计覆盖，不把不同版本拼成同一条增长曲线。

## 3. 冻结范围与过程

现有`replay.py`和`scale.py`的`source_files_before/after`只覆盖`digital_life/**/*.py`，当前约133个文件；不能单独证明SQL、资源JSON、测试夹具、公共配置和执行工具未变。

最终验收前另生成公开输入清单，采用已有安全公开源码遍历机制，至少覆盖原完整门槛所用公开输入范围（此前372项；新增文件后按实际清单计数），包括：

- 产品Python、SQL/JSON资源及Web静态文件。
- 实际使用的测试夹具与新增测试。
- 主replay、scale、比较器、故障runner及完整验证脚本。
- 相关公开配置与构建依赖。

继续排除`work/`、`outputs/`、`config/local/`、运行库、token、认证和其它私密目录。计划状态JSON属于运行元数据，按既有规则独立审计，不能为了更新状态导致“产品源码变化”；其规范要求仍由原plan检查验证。

每次运行前后对照全部冻结文件路径与SHA256；新增、删除、修改都记录。只有运行间的完整冻结清单一致，才能合并为最终三次及最终增长曲线。若之后再改产品、夹具、SQL或工具，明确旧证据对应版本，并复验真正受影响场景；不以“只是搬函数/语义等价”替代用户要求的最终三次实测。

输出目录必须全新，不覆盖任何旧失败，建议使用新的`remaining-final-*`批次前缀。禁止向harness传正式实例目录；现有入口只接`--source`和`--output`，实例由夹具在TemporaryDirectory创建。

## 4. 连续两轮的具体验收

使用`evaluation/tool_learning_round2_scale.py`，原17历史与0历史分别独立创建实例，参数`--continuous 2`。这是实际`ControllerMaterialReader.send`路径，不用主replay的简化第二轮提交替代。

完整检查：

1. `passed=true`、`source_stable=true`，`runs`确有两项且均accepted；首轮保留成功，第二轮无错误或未进入模型的伪成功。
2. 两轮相同实例，不同activity/request，第二轮`predecessor_activity_id`准确指向首轮。
3. `continuous_proof`中`requests_distinct/all_independent/previous_success_preserved/predecessor_matches/old_materials_present`均真。
4. 两份实际provider raw捕获均为observed；两个完整packet/manifest、response、parsed及调用状态均留存，不能由替身常量重建返回证据。
5. 每次wire都是独立`system`+`user`双消息，`fresh=true`、`context_mode=fresh_request`，顶层无session/resume/previous_response等关联键。实例本身保存的历史与记忆是这次完整输入的一部分，并不等于传输层恢复上下文。
6. 第二轮conversation_context确有首轮用户“你好，我是liwei。”及合法memory_revision绑定；检查其manifest关系与来源，而不只搜索字符串。
7. 所有11组特征、原选择/覆盖/missing标记、源版本/Scope/条件/用途/接收者保留。每轮实际消耗不超原预留，原总cap和assembly份额不变，未知消费不伪填0。

现有scale已实现上述主要自动断言。另审查生成材料，确认没有通过改变fixture特征、召回数或输入字段使其过关。两轮正常成功的unknown应为0；注入未知消耗的反例则须保持真实unknown与hold，不能要求一律清零。

## 5. 三次性能计时与完整输入对照

主工具固定为`evaluation/tool_learning_round2_replay.py`，普通17档、`--continuous 1`，每次独立新实例，顺序运行。主harness旧SHA256为`7324de48f3f02d19b1fb2e9aafc498aab7284262a7f875ba9949e1fbc77e54db`；若harness必须变化，先写变更原因并重新建立可比基线，不能直接拼接旧三次。

计时窗口包含Engine.think、完整packet/manifest导出，不含夹具setup。固定合成世界时间、UUID和磁盘探针；真实monotonic及原计量规则不动。诊断跟踪和其它重CPU测试不与计时并行，三次不得在途中改源。主工具报告真实wall、预算actual、所有预留/settlement、源码前后hash。

新三次先各自验证完整manifest，再确认业务`/input`逐字段一致、新三次完整packet/manifest彼此一致。新旧全部packet也进行严格比较，不能只比较键数。原总cap必须一致；因少读而改变的packet派生limits可如实单列，但必须由真实assembly预留推导，连同相应manifest字段摘要及packet_digest一起解释，不能删差异后宣称全包相同。

使用既有比较器的完整bundle入口。若确有技术UUID差异，只能提供明确双射与精确JSON pointer见证，禁止按字段名猜测归一化；时间、Scope、条件、版本、权限、cap均不忽略。最终报告列原3值、新3值、中位、最慢、实际行/字节及门槛判定，不混入补采样例或诊断样例耗时。

主replay不捕获实际raw/response/parsed。最终普通17档须另用scale补采一次，并与旧普通17补采严格对照；若原scale工具和原旧夹具保持不变，可使用已封存旧补采，不应把其143.864秒加入三次性能统计。确认最终补采与三次计时产品/夹具同源，真实raw/response/parsed逐字节比较及状态比较均有独立摘要。

## 6. 增长测试与其限制

用同一最终冻结源与同一scale，逐一运行0、17、50、100档。17普通最终补采可复用于该档，但应在汇总中明确引用，不重复计为第二个独立样本。其余档各保存一份原始结果、完整输入/manifest、material-proof、实际raw/response/parsed、budget和前置memory/episode目录。

每档记录：持久化episode条数、实际入模episode/Memory/关系条数及原始引用、特征键/字段/依赖数、查询行/字节、wall、预算预留/实际/未知、是否调用模型与是否accepted。用明确ID/原文字段见证审查实际选择范围；“数据库有100条”不等于“100条历史全部入模”。既有17预置片段曾未被选择，新结果必须重新检查，不能沿用假设。

主比较只要求同负载内容等价；跨0/17/50/100档本来可能有不同真实材料，不能要求其输入完全一样或为了相等移除内容。每档按本档数据库真实选择结果判断完整性。

共享原11Memory负载保留`seed_shared_source`的真实入站、6条附加输入及PeopleRelations关系，不删额外活动。检查`same_original_evidence_bound`、记忆原件路径及关系值来源，保持“两个自述、未验证身份”的语义。若触原cap则留failed snapshot、阶段actual/reserved、实际调用数和停止原因；不得把停止前首轮输出当整个场景正例通过。

scale的wall包括material-proof、activity snapshot和输出工件采集，且由抓取器包裹替身返回，**不与主replay三次wall混算**。增长曲线仅在同一scale和冻结源内比较；不是纯模型耗时、真实tokenizer费用、真实模型质量或长期生命连续性的证明。

## 7. 复验与交付准则

新实现先通过其小端口与必要反例，再通过统一故障/完整输入差分。现故障runner硬编码287唯一用例；新增用例后须按实际loader清单审查并更新明确预期数量，不能删测试、降低唯一性断言或以数量代替断言结果。

最终完整系统回归按实现影响安排，保留438义务、1314重复引用和107裁决的原必要条件。若需新一次完整门槛，顺序在计时之外执行；临时loopback权限只用于隔离HTTP接口，不连接真实模型。不打开正式实例、不检查其状态或认证。完整回归通过也不能补写未通过的连续/性能/增长条件。

最终证据清单至少包括：最终公开输入hash、每次原始结果及完整包、对照报告及全部差异、两轮独立调用与记忆绑定证明、输出真实字节与摘要、增长选择范围审计、原cap/实际预留审计、必要保护复验、旧失败保留清单。报告/TODO与原计划仅追加真实复验引用；IM20—IM24仍保持原阻塞条件。

主任务未触发前，本方案不运行任何重CPU测试、不修改产品或工具、不更新主报告。

## 8. 已核对的确切执行入口

以下命令均在项目根目录执行；`--source .`仅指定公开源码树，不是实例目录。所有输出目录必须尚不存在；若失败，应增加新批次编号，不覆盖旧目录。只有主任务确认无其它CPU测试运行且允许启动后才执行。

连续主场景及既有最小失败复验：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evaluation/tool_learning_round2_scale.py --source . --output outputs/acceptance/performance-round2-continuation/continuous17-01 --history 17 --continuous 2
PYTHONDONTWRITEBYTECODE=1 python3 evaluation/tool_learning_round2_scale.py --source . --output outputs/acceptance/performance-round2-continuation/continuous0-01 --history 0 --continuous 2
```

完成必要保护复验并冻结后，主计时三次顺序执行：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evaluation/tool_learning_round2_replay.py --source . --output outputs/acceptance/performance-round2-continuation/final-repeat-01 --history 17 --continuous 1
PYTHONDONTWRITEBYTECODE=1 python3 evaluation/tool_learning_round2_replay.py --source . --output outputs/acceptance/performance-round2-continuation/final-repeat-02 --history 17 --continuous 1
PYTHONDONTWRITEBYTECODE=1 python3 evaluation/tool_learning_round2_replay.py --source . --output outputs/acceptance/performance-round2-continuation/final-repeat-03 --history 17 --continuous 1
```

最终增长与实际输出补采，逐项顺序执行：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evaluation/tool_learning_round2_scale.py --source . --output outputs/acceptance/performance-round2-continuation/final-growth-0 --history 0 --continuous 1
PYTHONDONTWRITEBYTECODE=1 python3 evaluation/tool_learning_round2_scale.py --source . --output outputs/acceptance/performance-round2-continuation/final-growth-17 --history 17 --continuous 1
PYTHONDONTWRITEBYTECODE=1 python3 evaluation/tool_learning_round2_scale.py --source . --output outputs/acceptance/performance-round2-continuation/final-growth-50 --history 50 --continuous 1
PYTHONDONTWRITEBYTECODE=1 python3 evaluation/tool_learning_round2_scale.py --source . --output outputs/acceptance/performance-round2-continuation/final-growth-100 --history 100 --continuous 1
PYTHONDONTWRITEBYTECODE=1 python3 evaluation/tool_learning_round2_scale.py --source . --output outputs/acceptance/performance-round2-continuation/final-shared11 --history 17 --continuous 1 --shared-source
```

统一故障runner入口如下；其预期用例数先由新增测试的实际清单固定，不能一边计时一边改runner：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evaluation/tool_learning_round2_fault_validation.py --output outputs/acceptance/performance-round2-continuation/final-faults
```

若实现影响需要完整门槛，保留原命令，另存新日志，不向旧证据写入：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify_tool_learning_task.py --task IM19
```

以上命令只创建合成临时实例；harness内明确禁用真实模型，严格夹具使用替身transport。真实HTTP接口回归如需临时loopback端口，由主任务按工具环境处理权限；不改为外网或正式实例验证。
