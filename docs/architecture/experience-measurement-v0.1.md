# 经验效果测量：系统工程实现 V0.1

最新状态：后续真实Codex先导已完成，4题／8次调用未见改善（gain=0），详见[先导报告](experience-codex-pilot-v0.1.md)。下文的零真实调用与459项回归数字记录首轮机制实现，保留为历史证据。

日期：2026-11-08。作者：Codex 主agent（/root），无委派。
任务：实现“使用经验前后有没有变好”的量化设计，保持学习评估／提案、认知保存经验版本的分工。正式实例继续锁定，测量结果不参与实际选择。

依据：[认知—经验归属](cognitive-experience-ownership-v0.2.md)、[闭环设计](self-feedback-loop-design-v0.1.md)。本轮完成可执行的受控对照测量，不代表已证明真实模型学习有效、内在意图成熟或正式G2通过。

## 1 简单说明：现在能测什么

给同一个预测模型同一组未用于本次更新的检查问题，分别不提供经验、提供一份固定的认知经验快照。两边预测全部保存后，才揭示答案，比较预测误差。另放一组旧任务，检查新经验有没有损害原有表现。

可记录：预测误差改善、退步、确实为零、无法测量；以及调用数、实际token用量、每次预测耗时。缺预测、缺答案或用量未知不补成零。测得的误差差值不是“智力提高百分比”，也不替代人格和意图对主观意义的判断。

当前只实现分类概率的Brier测量，不覆盖所有经验价值、一般技能、长期收益或基础模型权重训练。普通自主探索仍用原来的调用和选择路径；测量只由controller显式开启和运行。

## 2 完整数据链与业务归属

```text
原观察／学习机会
  → 登记检查问题、经验快照、评分规则和答案承诺
  → 封存不带经验／带经验的预测
  → controller揭示承诺对应的检查答案
  → 测量器重新计算误差差值及旧能力退步
  → Learning评估并提出经验更新
  → Cognition核对报告后保存影子经验版本
```

| 内容 | 所有者／实现 | 边界 |
| --- | --- | --- |
| 原始经历、观察和来源 | 原结果／记忆、SelfFeedback挂接 | 不改写原回执，不重复制造证据 |
| 测量方法及报告 | 学习侧应用用例 ExperienceMeasurement | 不决定人格或目标价值，不直接保存认知经验 |
| 收获评估与提案 | Learning.assess_measured_experience／propose_experience | 不能自报数字绕过封存报告 |
| 经验版本与当前视图 | Cognition.save_experience／experience_snapshot | 仍为shadow-not-world-fact，不提升世界事实 |
| 概率预测能力 | domain/experience.py的PredictionPort | 独立新请求，不接检查答案和工具权限 |
| 现有模型适配 | infrastructure/llm/experience_prediction.py | 使用已有模型路由，不更改日常schema，不执行模型提出的动作 |

生命工程仍将经验归入认知M03、评估与提案归入学习M14。系统工程把测量编排、模型端口、存储和所有权检查分别落实；没有新增第二套“兴趣分数所有者”。

## 3 测量约定

登记2—20个检查case，至少一个target和一个retention。单次token预留范围现为1—32768，默认512；2026-11-08为兼容Codex固定输入开销，从旧上限4096扩展，父活动总预算与超额停止规则不变。只登记case_id、input和split，不把标签放进预测请求；case_id不得与声明的training_case_ids重叠。共同上下文固定，两组只在是否附加认知经验快照上有语义区别，顺序按case交替；超时余量只作为适配器控制参数，不交给语言模型作判断。

答案承诺为sha256(私有nonce＋规范化答案)，nonce至少32字符，应由操作者随机生成并保密。两个分支的所有预测记录必须先封存，才能揭示完全匹配的标签集合和nonce。登记后改答案、标签提前揭示、之后补预测均被拒绝。事件顺序、输入哈希、同一模型身份和父活动预算预留在报告核对时再次检查。

这些检查能约束系统API的数据流，不能证明操作者真的没有把答案写进问题，或提供了独立、正确的数据。标签资格明确标controller-attested，不伪称独立盲评或外部事实认证。真实效果研究仍需审核材料、重复与独立评审；报告independent_cases=null，不从两条样本计算强置信保证。

### 数值规则

K类Brier = 0.5 × Σ(p_k−y_k)^2，范围[0,1]；二元时等于常用的(p−y)^2。target_gain为target组平均的“原误差−带经验误差”。retention_regression为retention组最大的正向误差增加，最低0。

首版项目规则是：没有旧能力退步时，gain=target_gain；有退步时，gain=min(target_gain, −retention_regression)。因此不能因新任务改善就忽略旧任务受损。原始分量同时保存，不只给总分；这是明确的项目评分政策，不是科学界通用常数。

无有效预测／已知用量时gain=null、unknown。准确测得0才为measured_zero；负值如实保留。测量报告、逐case分数、实际调用数、用量和预测引用均可追溯。

## 4 认知如何接受测量结果

Learning先重新核对封存报告，再形成带measurement_ref的新评估修订。原来源、机会、暴露键和报告结果必须一致。认知经验单元的测量维度改为prediction_brier_v1，和原unmeasured-v1区分，不混装不同量尺。

Cognition保存数值经验前再次按原预测／标签重算报告，拒绝没有measurement_ref、篡改gain、未完成或已失效的报告。正常的unknown旧路径不变。重复采用同一评估不新增经验版本；同一机会同一量尺的新评估按revision替换当前贡献，不把重复检查膨胀成独立经历。

认知经验契约升级为COGNITIVE-EXPERIENCE-SHADOW-0.3，读取0.2历史；旧unknown事件不重写，新数值评估使用0.3约定。旧二进制不能被当成支持新测量的完整读取器，部署仍需同步组件，本轮没有部署正式实例。

报告失效或来源撤回后，当前认知视图排除有关贡献并改变snapshot_revision，原评估和经验版本保留。CLI采用仍只保存影子状态，不改变实际意图、问题排序、人格、价值或事实确认。

## 5 系统边界与预算

测量开关默认false，启用需要controller且实例控制状态已停止、没有活动进程。实际预测还要求WAKE_DISABLED已由其他授权流程解除、运行未被用户停止、影子记录与原探索仍启用且世代匹配，父活动未取消。启用测量本身不会解锁或resume。

每次预测前重检这些条件，在同一派发gate内预留预算并进入回调。gate每次回调结束就释放，外部停止可在下一次调用前提交；在途结果可以留审计，不继续新调用。模型I/O不能放进SQLite写事务。进程崩溃留下未核对dispatch时停止重放，不自动重复调用。

测量调用计入原观察所属活动的Budget，不因新建测量run重置。每case最多两个调用；先检查剩余整组预算，调用前仍逐次原子预留。用量未知或超过单次预留后停止后续调用。部分适配器只提供观测后的实际用量，不能宣称硬token上限；外层超时也不能强行中断任意不合作的Python端口。

调度、停止、授权、隐私及原SQL结构保持；测量调用的operation_ref是独立measurement_dispatch事件，预算operation_kind复用thought_attempt，但不伪造普通thought_requests记录。实际成本由测量报告和预算账本共同解释。

## 6 现有模型接口和操作入口

ExperiencePredictionPort把请求包装成现有V1：action必须是wait，explanation必须是仅含probabilities的JSON字符串。不会执行返回的工具动作，错误动作或格式被拒绝。请求独立，不包含history／messages／续接ID，标签和nonce不进预测输入。适配器取真实input/output token用量；缺用量不补估计值。

现有configured_reasoner可按显式配置接入。真实模型参数修订、随机性、材料质量和盲评仍需另行登记；本轮适配器使用模拟reasoner验证，没有调用真实模型或声称跨供应商效果。

对获授权的隔离实例提供命令：

```sh
python3 -m digital_life --data /path/to/isolated-instance experience-measurement status
python3 -m digital_life --data /path/to/isolated-instance experience-measurement enable
python3 -m digital_life --data /path/to/isolated-instance experience-measurement register --input registration.json
python3 -m digital_life --data /path/to/isolated-instance experience-measurement predict --run RUN_ID --config MODEL_CONFIG.json
python3 -m digital_life --data /path/to/isolated-instance experience-measurement reveal --run RUN_ID --input private-labels.json
python3 -m digital_life --data /path/to/isolated-instance experience-measurement evaluate --run RUN_ID
python3 -m digital_life --data /path/to/isolated-instance experience-measurement adopt --report REPORT_ID
python3 -m digital_life --data /path/to/isolated-instance experience-measurement invalidate --run RUN_ID --reason "标签来源已撤回"
```

predict会触发指定模型，必须显式传配置；不自动选模型、切换路由或从本地失败回退到付费服务。token预留需覆盖实际输入输出；默认512主要适合短输入／构造端口，真实模型应先登记合适预算，不能靠反复注册越过父活动额度。本轮只在临时实例执行测试，没有对正式实例执行上述命令。

registration.json格式：

```json
{
  "opportunity_ref": "EXISTING_OPPORTUNITY",
  "cases": [
    {"case_id":"new-1","input":"未用于本次更新的新任务","split":"target"},
    {"case_id":"old-1","input":"未用于本次更新的旧能力检查","split":"retention"}
  ],
  "classes":2,
  "label_commitment":"64-character-sha256-commitment",
  "common_context":{},
  "training_case_ids":[],
  "tokens_per_call":4096,
  "wall_seconds":120
}
```

私有标签文件仅在预测封存后通过reveal提交：`{"labels":{"new-1":1,"old-1":0},"nonce":"private-random-nonce-at-least-32-characters"}`。案例ID不重叠只能排除明显重复，不能替代语义泄漏审核。

## 7 代码与验证材料

新增experience_measurement应用服务、PredictionPort领域接口、现有reasoner预测适配器、CLI处理器及概率测量测试。Learning新增assess_measured_experience／validate_measured_experience，Cognition数值保存与快照依赖检查复用该验证器。经验版本仍只有认知一个写入点，没有改变Engine的选择路径或原学习机会自动记录方式。

新增`evaluation/experience_measurement.py`构造端口和`scripts/run_experience_measurement.py`源码封存运行器；保留10类构造控制的原始预测、标签揭示顺序、预算及认知版本。它们测试机制，不是经验有效的真实样本。原125场景继续用开关两分支检查实际行为未接入。

已完成：10/10数值控制条件通过；125/125成对场景（250临时分支）通过；专项75/75通过；完整回归459项中456通过、3项真实模型测试跳过，无失败。真实模型调用为0，因此当前证据证明测量流程可用，不证明模型已经学会或经验已经有效。

证据：`outputs/acceptance/experience-measurement/experience-measurement-20261108T132441Z-a92936f2`；选择回归：`outputs/acceptance/experience-measurement-regression/sf-stage1-20261108T132442Z-12cc654b`；汇总指针：`outputs/acceptance/experience-measurement-latest.json`。

正式实例6个文件摘要未变，SQL和旧基线未变，原5组封存证据核对一致。完整回归对应记录的源码；其后工作区另有并发修改 `digital_life/application/people_relations.py`，已保留，不能把本次完整回归扩展为该后续修改的验证结论。原失败证据及中间运行全部保留。

后续已获授权开展小规模真实模型隔离对照，见[Codex先导报告](experience-codex-pilot-v0.1.md)。上述10组控制和完整回归仍是前一轮离线证据，不改写为真实模型结果。
