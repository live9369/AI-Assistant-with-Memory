# 自主探索 G1 材料、运行器与隔离验证报告

日期：2026-11-08（Asia/Shanghai）。作者：Codex 当前主 agent（/root）。  
状态：评测工具交付完成；冻结V1的G1未通过，不能进入G2。  
依据：[AE-EVAL-1.0](../research/autonomous-exploration-evaluation-v1.md)。操作见[评测运行说明](../operations/autonomous-exploration-evaluation.md)。

## 1 任务与结论

用户要求补齐评测材料、运行器、指标聚合，先按正式契约完成G1隔离验证，正式实例保持锁定，并更新报告和交接。

最终运行`g1-20261108T081148Z-babea897`：111个trial，105通过、6失败，零缺失证据、零看门狗超时。失败均为停止提交后仍新派发调用，依照契约零违规规则，G1=fail。G2/G3未运行。没有修改生产源码或重写原冻结摘要来获得通过结果。

最终证据入口：

- [聚合结果](../../outputs/acceptance/ae-g1/g1-20261108T081148Z-babea897/aggregate.json)
- [调用前封存manifest](../../outputs/acceptance/ae-g1/g1-20261108T081148Z-babea897/manifest.json)
- [正式实例前后检查](../../outputs/acceptance/ae-g1/g1-20261108T081148Z-babea897/formal-instance-guard.json)
- [完成记录](../../outputs/acceptance/ae-g1/g1-20261108T081148Z-babea897/completion.json)
- [工具及相关回归](../../outputs/acceptance/ae-g1-tooling-tests.json)：57项通过，无跳过。它不替代G1判定。

## 2 被测版本与工作区差异

原V1机器基线的engine.py摘要为`6b2388caac404b2991a8a183bd0205d7fc09276a274b529f5786882c8e16e419`。本轮开始时当前engine.py已新增Chat上下文接入，因此原完整性检查对当前工作区报告失败；方法签名未变化。此改动并非本轮评测工具写入。

已确认，移除该新增块可逐字节还原冻结源码。本轮将其保存为`evaluation/exploration/frozen_engine_v1.py`，在worker内只覆盖导入位置，不修改实际engine.py。运行器仅允许这一已解释差异，冻结副本必须精确匹配原摘要；其余冻结文件不符就拒绝。

因此结论分开：

| 检查范围 | 结论 |
| --- | --- |
| 当前工作区与原冻结基线完全一致 | 否，G0原检查失败，差异保留于manifest.workspace_g0 |
| 实际被测的冻结引擎副本及其他冻结文件 | G0通过 |
| 被测冻结V1的workspace-read机制 | G1失败 |
| 新增Chat上下文版本的完整G1 | 本轮未宣称验证 |

73个运行依赖文件和10个评测输入文件已记录摘要并归档源码，每个worker再次核对输入；当前Chat代码未被删除或覆盖。冻结副本是可核验的测试制品，不是第二套生产框架。

## 3 本次新增工具和材料

- `evaluation/exploration/materials/cases-v1.json`：A–F各10个具名上下文，共60个G1材料，含经历、工作区文件、世界变化和独立保留的oracle说明。
- `evaluation/exploration/materials/scenarios-v1.json`：27项机制及24项停止时序场景，共51项。加60个材料贯通检查构成111个trial。
- `evaluation/exploration/harness.py`：临时实例、固定推理器、工具回调、真实接口故障注入、单调时序和完整制品导出。
- `evaluation/exploration/scenarios.py`：来源、权限、V1/V2、多轮、额度、恢复、去重、容量深度及停止矩阵。
- `evaluation/exploration/aggregate.py`：从带摘要的原始记录重算指标，不相信成功标签或夹具自评分。
- `scripts/run_exploration_g1.py`：每trial独立子进程，提前封存manifest、禁止socket、独立临时实例和看门狗、前后正式实例摘要保护。
- `scripts/aggregate_exploration_g1.py`：校验输入和证据后独立重聚合。
- `tests/test_exploration_evaluation.py`：7项有意义的正反例检查，包括篡改、缺证、停止违规、未测质量不填分、正式实例变化及材料覆盖。

材料是G1工程夹具，尚无独立质量盲评，不能当作已登记的60个独立G2正式case。多个B01故障试验不冒充多个统计独立样本。本轮没有真实模型调用、评审员质量标签、消融运行或成本消费；预留token不当作实际token。

## 4 覆盖与结果

| 范围 | 结果 |
| --- | --- |
| 默认关闭与锁定、内部来源、伪造／撤权／修订引用、V1/V2 | 对应机制场景通过 |
| 工具成功不直接解决、轮次／活动／尝试／工具／token预留预算 | 对应场景通过 |
| 问题与回执去重、配置世代、未知／失败工具、模型失败 | 对应场景通过 |
| 已提交观察后新epoch、准备请求后保守恢复、Executor回执提交后恢复 | 3个恢复场景通过 |
| 用户工作优先、文本／候选数量／深度／容量边界 | 对应场景通过 |
| 60个材料的观察字节及夹具处置贯通 | 60/60通过；不是质量评分 |
| 三种控制×四个时点×两种调用 | 18/24通过，6/24失败 |

27个机制场景均通过。三个停止控制是disable、user_stop、dispatch_competition（真实第二线程和独立控制库连接提交停止）；四个位置为准备前、发送事务提交后回调前、回调在途、结果提交后；两种调用为model、tool。

## 5 六项失败及可复核原因

| 控制方式 | 模型派发证据 | 工具派发证据 |
| --- | --- | --- |
| disable | [trace](../../outputs/acceptance/ae-g1/g1-20261108T081148Z-babea897/trials/scenario-disable-authorized_before_dispatch-model/trace.json) | [trace](../../outputs/acceptance/ae-g1/g1-20261108T081148Z-babea897/trials/scenario-disable-authorized_before_dispatch-tool/trace.json) |
| user_stop | [trace](../../outputs/acceptance/ae-g1/g1-20261108T081148Z-babea897/trials/scenario-user_stop-authorized_before_dispatch-model/trace.json) | [trace](../../outputs/acceptance/ae-g1/g1-20261108T081148Z-babea897/trials/scenario-user_stop-authorized_before_dispatch-tool/trace.json) |
| dispatch_competition | [trace](../../outputs/acceptance/ae-g1/g1-20261108T081148Z-babea897/trials/scenario-dispatch_competition-authorized_before_dispatch-model/trace.json) | [trace](../../outputs/acceptance/ae-g1/g1-20261108T081148Z-babea897/trials/scenario-dispatch_competition-authorized_before_dispatch-tool/trace.json) |

六项均出现如下因果顺序：已有检查通过 → 发送预留事务提交 → 停止接口真正返回 → 记录stop_committed → 模型或工具回调开始dispatch。

这是单调时钟和请求／操作ID可复核的有序交错，不是从数据库sent_at推测。故障注入没有更改生产权限检查，也没有在回调入口替生产代码拦截调用。发送前已检查许可，但检查与调用之间没有覆盖这段窗口的停止协调。工具路径中Executor在初始检查和授权后提交发送事务，再调用backend；模型路径在检查与预留后调用generate。

这与“已在途调用在停止后返回”不同：失败的回调实际开始在stop_committed之后。即使模型结果随后被标stale，也不能消除已经发生的新派发违规。G1不能用105/111的平均通过率抵消该缺陷。

## 6 指标聚合

| 指标／不变量 | 最终结果 | 范围限制 |
| --- | --- | --- |
| M03引用接纳完整率 | 169/169，非法接纳0 | 工程引用合法性，不是语义真实性 |
| M09恢复连续率 | 3/3 | 预注册工程场景，同一B01，无总体质量区间 |
| M10只读重复派发 | 0/4机会 | 只读工作区；写副作用not_evaluable |
| M11停止后新派发 | 6次，24个停止边界 | 契约要求0，因此失败 |
| M13预算越界 | 0 | 现有预留与次数规则，不含尚未实现的活动硬墙钟截止 |
| 每请求多次accepted | 0 | 独立接受约束 |
| M12停止确认延迟 | not_evaluable | 无统一确认接口，不宣称固定毫秒内停止 |
| M14单位有效探索成本 | not_evaluable | 无独立有效探索分母；原始模型attempt268、工具attempt77另报；实际tokens为null |
| M01/M02/M04–M08/M15/M16 | not_run | 没有用夹具回答伪造质量或因果得分 |

所有度量带分子分母、范围、缺失、证据入口及方法；分母0不填0成功率，质量指标不借工程样本计算区间。

## 7 运行与复验

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_exploration_g1.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/aggregate_exploration_g1.py outputs/acceptance/ae-g1/g1-20261108T081148Z-babea897
```

冻结版预期退出码1，因为G1确实失败。第二条只重聚合已有证据，不重新调用模型／工具；聚合源摘要及时间保留于aggregate.json。

前两个开发运行也保留原始制品：`g1-20261108T080736Z-be50fb24`、`g1-20261108T081001Z-cc138f8f`，均复现105通过、6失败。首轮是初版工具输出，后续补了输入归档、看门狗轨迹和完成元数据；不得将三个运行合成333个独立实验，也不以新运行覆盖失败历史。最终以本报告指定的最后一次完整封存运行为证据入口。

工具测试与相关回归共57项通过，覆盖聚合器对manifest／result／证据篡改的拒绝、缺证不通过、停止违规重算、正式实例变化不通过，以及旧探索、全系统和层级约束。它们运行在当前工作区，不能替代冻结版G1结果。

## 8 正式实例与后续任务

正式实例存在且WAKE_DISABLED保持存在，6个普通文件的前后摘要完全一致。未打开正式实例执行，未启用探索，未启动真实模型、网络服务、常驻任务、生产Runtime或部署；未修改源码、SQL、模型配置和冻结契约。

下一步需要设计停止与实际派发的协调／线性化边界，覆盖模型和工具两条路径、控制停止和配置世代变化，保留在途与未知执行的证据语义。修复应形成新运行契约／源码基线，而不是只在回调前随意加一次检查后宣称消除了全部竞争。将六个失败交错纳入新版本必过回归，再运行完整G1。

同时需审阅当前新增Chat上下文与探索的兼容性并形成明确被测版本。G1通过前G2/G3保持未运行。本轮没有把真实模型运行器、独立标签系统和完整消融聚合宣称为已完成。
