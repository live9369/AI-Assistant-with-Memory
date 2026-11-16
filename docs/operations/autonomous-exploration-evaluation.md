# 自主探索 G1 隔离评测操作

适用协议：[AE-EVAL-1.0](../research/autonomous-exploration-evaluation-v1.md)。范围仅为workspace-read机制验证，推理器为固定Python夹具，不调用真实模型。

## 当前版本：AE-RUNTIME-1.1

默认运行器现在选择V1.1；新基线直接测试当前工作区（含Chat），无需旧Engine覆盖。使用：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/verification/verify_exploration_contract_v1_1.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/development/run_exploration_g1.py --baseline v1.1
```

原60材料和51旧场景全部保留，新增6个机制场景，共117个trial。[修复报告](../architecture/autonomous-exploration-stop-dispatch-repair.md)记录本次117/117通过，原失败run不覆盖。新版本同步gate会令跨线程／进程停止等待已进入的回调；在途竞争夹具先发起停止线程，回调退出后再等待其提交，不能在回调内同步等待自己释放gate。

`--baseline v1`只支持原V1完整源码或其已解释的单一Chat差异，不会把本轮其他改动忽略掉；需要重现旧运行时应使用旧run归档源码。当前正常G0入口是V1.1检查器，原V1检查器对新源码失败是预期版本差异。

以下为原V1操作与证据格式说明，保留历史范围；当前以本节和新契约为准。

## 首版运行说明（历史）

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/development/run_exploration_g1.py
```

不提供实例目录参数；每个trial只使用运行器自行创建的TemporaryDirectory。默认输出到`outputs/acceptance/ae-g1/<唯一run_id>/`，已有run不覆盖。默认每trial看门狗30秒，`--timeout`允许1–120秒；评测子进程禁用socket，工作区工具通过既有Executor和registry在临时目录执行，不启动模型服务、HTTP服务或常驻Runtime。

启动前检查正式实例`work/primordial00/WAKE_DISABLED`；存在正式实例但缺锁则拒绝。对正式目录普通文件计算前后摘要，不读取其配置执行、不解锁、不迁移。正式实例不存在时记录not_present，不能宣称验证了某个实际正式实例的锁。

G1失败的退出码为1，是评测结论，不应当作“运行器坏了”后删掉结果。看门狗或证据缺失也不算通过。每个失败trial保存原始结果；后续独立trial继续运行，修订工具后创建新run，不覆盖旧run。

## 材料与场景

材料位于`evaluation/exploration/materials/cases-v1.json`：A–F各10，共60个具名上下文。它们是作者编写的G1机制夹具，未经独立质量评审，不是已登记并通过盲评的G2正式集。反例、缺证、世界变化等用于检查观察的传递和状态响应。

场景位于`scenarios-v1.json`：27个机制场景及24个停止／派发交错场景。总共111个trial；不是协议G2的720次trial。每个trial只有一次，不把相同B01材料上的多个故障场景当作多个独立质量case。

推理器只返回可控V1/V2结构。材料的oracle不交给生产模型；本版根本没有真实模型运行。夹具中的resolved只用于验证机制，不能进入M01、M02、M04–M08等质量得分。

## 冻结版与当前工作区

当前工作区engine.py在冻结后增加了对话上下文逻辑，其摘要不匹配V1。`evaluation/exploration/frozen_engine_v1.py`是移除这段新增逻辑后逐字节匹配原摘要的评测副本，**不替换生产文件**。

运行器只允许这一已解释差异，且冻结副本必须匹配原基线摘要；其他冻结文件不符直接拒绝。manifest分别保留当前工作区G0失败和被测冻结副本G0通过的证据。每个worker再次检查冻结文件及全部生产Python/SQL/JSON依赖摘要；所有源码归档在source-snapshot中。不能把冻结副本结果说成新增对话版本已通过G1。

如果冻结版与当前工作区完全相同，则直接测试当前版本；如果需要验证其他变更，先做变更审阅并创建新的基线，不扩大差异白名单或重写原摘要。

## 停止时序

矩阵覆盖disable、user_stop和实际第二线程／连接提交的dispatch_competition；各自覆盖模型和工具的四个位置：准备前、发送事务提交后但回调调用前、回调在途、结果提交后。

工具“准备前”指进入执行准备前（动作提案已获得允许的临时开放策略），模型“准备前”指thought请求准备前。模型没有工具审批，“授权后”位置对应请求检查和发送预留事务提交完成。

发送边界注入通过评测装配层包装Store.tx，在事务真正提交后调用实际停止接口；不改变生产逻辑、不在模型或工具回调中增加保护。回调入口记录实际dispatch时间；停止接口返回后记录stop_committed。第二线程竞争是预设的可重放交错，不宣称穷尽所有并发时序。

在途调用可以在停止前开始并在停止后返回；M11只统计停止提交后新开始的回调派发。trace使用monotonic_ns，包含请求、尝试、操作ID；既有数据库sent_at不替代该时序。M12仍无统一确认接口，保持not_evaluable。

## 聚合与制品

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/development/aggregate_exploration_g1.py outputs/acceptance/ae-g1/<run_id>
```

聚合器核对manifest、数据集、基线、证据索引和每个trial结果及证据摘要，重新从snapshot/artifacts/trace计算M03、工程M09、只读派发M10、M11和M13。原始attempt成本单列，实际token和单位有效探索成本不伪造；其余质量指标保持not_run。

主要制品：

- manifest.json及manifest.sha256：调用前封存的材料、源码、场景、配置、预算、事件计划、排除政策。
- cases.json、baseline.json、source-snapshot：对应输入和源码归档；必要时另有frozen-engine.py。
- trials/<id>/snapshot.json、artifacts.json：活动、请求、结果、预算、证据和制品内容。
- trace.json与live-trace.jsonl：单调时序完整记录与看门狗中断前的追加记录。
- result.json、worker.stdout/stderr：断言、错误、摘要及退出码；无证据的超时保留为失败，不强行补零。
- evidence-index.json及摘要：输出结果校验链，防止重聚合时误用被改写的结果。
- formal-instance-guard.json：正式目录前后摘要。
- aggregate.json：门结论、原始计数、缺失与失败清单，以及16项指标的明确状态。

没有数字签名或外部时间戳；这些摘要用于版本与证据完整性复核，不声称可抵抗拥有全目录写权限者重写全部证据。
