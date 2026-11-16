# 自反馈学习第一阶段实现报告

当前归属调整见[认知—经验V0.2报告](cognitive-experience-ownership-v0.2.md)：学习评估／提案、认知保存版本。下文保留本次调整前第一阶段实现与验证历史，不再以独立兴趣模型作为当前所有者。

日期：2026-11-08。作者：Codex 主 agent（/root），无委派。
任务：按[闭环设计 V0.1](self-feedback-loop-design-v0.1.md)实现意图、预期、观察、学习记录和兴趣经验影子投影，暂不改变实际选择，完成隔离验证并交接。正式实例保持锁定。

## 已实现什么

现在可以沿记录看到：问题从哪段经历提出，属于哪个影子意图，调查前准备核验什么，工具实际返回了什么，以及为什么学习收益仍无法判断。这些记录有固定 ID、原始证据引用，跨重启可读，重复回执不重复建立学习机会。

兴趣经验有了只读影子投影，可以重建“这类尝试通常有多少收益”的统计。当前执行产生的学习记录全部为 unknown，投影保持先验；没有把模型的自信、resolved 或 expected_gain 当成真实收获。后续阶段接入独立测量后，才可能获得真实的非零收益。

实际问题排序仍由既有 expected_gain−cost 路径决定。影子投影不进入模型输入、排序、随机选择、人格、价值或正式事实修改；没有新增模型调用或改变输出 schema。

## 本轮代码修改

| 文件 | 修改 |
| --- | --- |
| `digital_life/application/self_feedback.py` | 新增影子记录服务、默认关闭开关、controller 配置／检查／失效接口；记录快照、意图、绑定、预期、观察、学习机会、unknown评估和模型解释 |
| `digital_life/application/interest_model.py` | 新增只读 fold：区分正／负／实测零／未知，按单元和暴露去重，修订替换，失效和权限撤回排除贡献；不持久提交兴趣版本 |
| `digital_life/application/exploration.py` | 候选接纳／资源变化重开、活动绑定、观察及解释处挂接影子记录；原排序、工具约束与预算保留 |
| `digital_life/application/engine.py` | 在请求准备事务内封存原始人格／状态／记忆引用，并在工具派发前登记预期；只对启用影子记录的探索生效，不改普通任务的输出路由 |
| `digital_life/entrypoints/cli.py` | 新增 self-feedback status／enable／disable／projection；配置不解锁或启动推理 |
| `tests/test_self_feedback_shadow.py` | 新增记录链、去重、权限、重启、回滚恢复、CLI、停止与投影边界测试 |
| `scripts/run_self_feedback_stage1.py` | 新增封存源码的离线成对运行器；每个分支全新临时实例，保留原始轨迹和结果摘要 |

没有修改SQL、学习接受权限、人格／价值服务或旧运行基线。另一个任务的 GoalRegulation 变更已保留并纳入最终封存；验证后又出现 BehaviorPolicy 接入，涉及 engine、CLI、growth 和 thought_inspection 四文件变化，均保留。本轮影子功能没有接管选择，但不能把封存验证结论扩展到该后续整个集成工作区。

## 记录与影子边界

请求上下文在原 thought_request 准备事务内封存，意图引用该请求的真实人格版本及输入状态；若后来才启用、没有原快照，则明确 original-context-unknown，不用返回时的新人格冒充原人格。

影子意图按实例＋canonical question_id＋resource_revision 保持身份；资源确变时产生继任影子意图并保留前任引用。当前 root_goal_ref=null，活动只关联既有活动目标，没有创建会参与调度的新根目标。设计中的真实根意图／子目标持续调度仍属于下一阶段。

预期在 Engine 工具执行入口、实际 attempt 前登记。现有V2输出没有可量化预测，因此 prediction_distribution=null，并注明不可测原因。若恢复时实际派发已经发生，明确标 late-recovery，prepared_before_dispatch=false，不补造事前预测。纯缓存复用关联原结果／原预期，不冒充新的取证。

观察核对原 action_results 的 receipt、evidence 及所属活动；跨活动复用需要既有复用事件。一个原工具 result 只有一个学习暴露；不同活动可以各有观察关联，但不会因改述／复用建立多份收益。工具失败产生 unknown，不记为负学习收益。

模型事后解释单独标 unverified-model-interpretation，学习评估仍保持 unknown。来源撤回会使该证据在影子统计中排除；controller 可以显式失效机会，重放重建不再计入。操作只追加不可变事件与制品，不直接更新人格、记忆或事实。

`InterestModel.fold` 是数学投影器，不是证据认证器。正／负／零值来自单测的明确合成输入，用来验证公式、修订替换与撤销；没有任何生产接口把外部自报 gain 导入为已验证学习。当前自动记录只有 unknown，故示例中的非零 Q 不能算真实学习结果。

## 配置与控制

开关默认关闭；enable 需要 controller，且控制状态已停止、没有活动进程。disable 使用同一派发协调锁，停止记录新的片段；已有记录仍可检查。启用不会移除WAKE_DISABLED、resume运行或改变探索配置。

只对获授权的隔离实例，可使用：

```sh
python3 -m digital_life --data /path/to/isolated-instance self-feedback status
python3 -m digital_life --data /path/to/isolated-instance self-feedback enable
python3 -m digital_life --data /path/to/isolated-instance self-feedback projection
python3 -m digital_life --data /path/to/isolated-instance self-feedback disable
```

本轮没有对正式实例执行这些命令。尚无兴趣统计的实时commit路径，因此“停止后提交会影响选择的兴趣版本”在本阶段不存在。在途结果允许留下影子审计记录，这不等于开始新学习测量或改变后续选择。

## 隔离验证口径

专门测试24项，覆盖：默认关闭和权限、完整记录链、迟到恢复不伪造预期、重复接受、失败unknown、来源撤回、显式失效、跨Store重建、用户停止、旧排序、缓存跨问题复用、回执提交后事务回滚恢复、CLI不唤醒、人格中途改变仍引用原请求快照及影子数学投影。

离线成对运行器使用原125个G1材料／机制场景作为回归探针，每个场景分别关闭和开启影子功能；只使用注入式脚本模型，网络禁用，临时实例用完关闭。每个分支执行原场景断言、SQL完整性检查，并额外检查没有实时兴趣提交、影子内容没有进入模型输入。

两分支比较的是语义签名：模型动作、输入字段与指令、问题终态、调用次数、活动状态及实际目标数量。不同实例的ID、时间、文件元数据本来不同，所以不宣称完整请求逐字节相同。此比较也不证明所有真实模型轨迹永远相同。

完整运行器在调用前封存生产包、SQL资源、评测源码及材料，worker从source-snapshot加载；最终版本将工作目录也固定到归档，确保子进程使用归档依赖。初轮记录保留，正式采用加严后的复验结果。

## 最终验证结果

主 run：`sf-stage1-20261108T122356Z-52b3dc7f`。125/125成对场景通过，合计250次独立临时实例运行；启用与关闭的语义签名均一致。非法引用、重复接受、停止后派发、重复只读派发、预算越界均0。

启用分支记录302份请求上下文、121份意图及个体快照、118份绑定、86份预期、80份观察、79份学习机会及79份unknown评估；一次跨问题复用未新增学习暴露。数值运行收益样本为0，与当前缺少独立测量的事实一致。

专门测试24/24通过；最终完整回归285项中282通过、3个真实模型项按原开关跳过，耗时59.106秒。这不是285个真实学习样本。最终完整回归后的工作区漂移已另列，后续代码未被算入这次完整通过结论。检测到并发修改后，另对最新工作区复跑24项影子专项，24/24通过；这只是专项兼容检查，不替代最新整个集成版本的完整回归。

[结果指针](../../outputs/acceptance/self-feedback-stage1-latest.json)、[成对汇总](../../outputs/acceptance/self-feedback-stage1/sf-stage1-20261108T122356Z-52b3dc7f/aggregate.json)、[完整回归](../../outputs/acceptance/self-feedback-stage1/sf-stage1-20261108T122356Z-52b3dc7f/regression.json)、[完整性检查](../../outputs/acceptance/self-feedback-stage1/sf-stage1-20261108T122356Z-52b3dc7f/integrity.json)保留原轨迹与源码关系。

早期两个run均保留：`sf-stage1-20261108T121804Z-75e48215`、`sf-stage1-20261108T121918Z-fa81d95d`，均125对通过，分别早于运行器工作目录加严和原始请求快照补齐。主结论只采用最终run，不将这些同材料复验当成额外独立质量样本。

三个阶段run的清单／源码／逐分支证据摘要均已核对；旧5棵G1/G2证据树、旧基线和SQL保持。正式实例六文件摘要与任务开始时一致，WAKE_DISABLED保持，未打开正式数据库或执行模型。

本报告的结果是第一阶段隔离回归，不是新的正式G1门禁冻结，也没有复跑真实G2或更新原质量标签。

## 后续仍需实现

下一阶段才让意图进入实际目标图、提供完整个体快照和选择分布；之后再接独立预测测量、窄范围授权的兴趣提交、撤销和受预算控制的评估。当前没有自动人格变化、基础模型训练、真实收益校准或选择策略替换。

正式实例持续锁定，旧基线、旧G1失败和通过、旧G2先导证据均保留。
