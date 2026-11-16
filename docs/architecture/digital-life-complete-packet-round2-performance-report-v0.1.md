# 完整思考包第二轮优化报告 V0.1

状态：**最终验收未全部通过**。分层修复前性能测量冻结版的中位耗时改善19.050%，低于预设20%；真实连续聊天第二轮仍在原assembly扫描预留处停止，尚未达到连续性验收标准。共享记忆增长另有原资源上限限制。不能据部分改进宣称本轮全部完成。

范围始终限于新建TemporaryDirectory合成实例与确定性模型替身；没有打开、检查状态、写入或唤醒正式实例，没有读取真实认证材料或调用真实模型/API。IM20—IM24仍blocked。

## 实施结果

同一检查阶段内按需共享登记、修订、依赖和原件材料。每个字段仍保留自己的来源身份、版本、Scope、时间、条件、关系路径、用途与接收者；所有消费者重新核验资格，不按相同文本合并来源或共享授权。

读集使用原4MiB/4096键上限。实际SQL返回行、字节及原件读取真实计量，逻辑图/节点限制保留。原200万scan/items、512MiB等总cap以及assembly原0.5份额没有提高。主库同连接写入、外部连接/进程提交、控制代次、文件与目录变化、回滚和未知事务结果仍使材料失效或拒绝。

本轮补齐typed Evidence reason_ref真实外键owner、Controller的native revision-id解析及受约束primary runtime事件来源，未扩大任意来源的权限。已登记引用kind及完整instance/object-or-id/revision/kind修订映射只在纯校验路径读取必要材料；真实或未知row observer仍走原完整行与来源观察。配置适配器复用避免重复初始化PRAGMA目录，固定控制材料可共享，控制进程/停止/锁等检查仍真实执行。

最后讨论的跨写保留缓存/可信写集方案**仅为未实施草案**。现有裸连接不能充分证明UDF/trigger/重入影响，因此没有以total_changes差值或方法名猜测“安全写入”，也没有更改原登记检查顺序/事务划分。

## 分层修复前冻结版：同源三次性能对照

主比较使用原未修改`evaluation/tool_learning_round2_replay.py`，旧版为实施前封存源。两版各3次独立新建同等合成夹具，顺序执行，不并发争CPU；固定世界时间、UUID和磁盘探针，真实monotonic与PhysicalReadMeter不变。窗口包含think和完整packet/manifest导出，不是单独LLM延迟。

| 指标 | 封存旧版 | 最终冻结新版 | 结论 |
| --- | ---: | ---: | --- |
| 第1次秒数 | 145.216347875 | 117.445454000 | 保存原值 |
| 第2次秒数 | 146.978334250 | 117.616215250 | 保存原值 |
| 第3次秒数 | 143.217004750 | 117.552631625 | 保存原值 |
| 中位秒数 | 145.216347875 | 117.552631625 | 下降19.050%，**未达20%** |
| 最慢秒数 | 146.978334250 | 117.616215250 | 不只报告最好值 |
| 每次实际返回行 | 1,479,635 | 635,178 | 下降57.072%，达到20% |

时间门槛为不超过116.173078300秒，最终中位超出1.379553325秒；没有追加挑选快值的重跑。此前112.421秒/22.584%的三次结果属于后续owner与安全修复之前的**历史中间源码**，不能代替本最终结论。

最终3次133个产品Python源文件逐项相同、前后稳定，来源目录摘要`25fac4482701605519756835106ff7aaa5cc97016169503c751509052005a503`。主harness SHA256始终为`7324de48f3f02d19b1fb2e9aafc498aab7284262a7f875ba9949e1fbc77e54db`。

[最终三次比较、原始差异和实际预算](../../outputs/acceptance/performance-round2/pf07-final-frozen278-comparison.json)。

## 完整输入与真实输出

新旧`/input`没有归一化，全部业务内容、特征、来源、版本、Scope、时间与条件逐字段严格相同。新3次完整packet和manifest彼此精确相同；175字段、168依赖及完整11组业务输入没有删除。

完整新旧packet并不相同：原账本余额派生的`max_scan/max_items`从857240变905620，`max_bytes`从116509614变123183099；manifest另有`/fields/173/digest/hex`及`/packet_digest`两个相应摘要差异。实际assembly子预留推导已核对，scan/items等于实际子预留、bytes为其原一半；原总cap完全相同，每项actual不超其reserved，unknown为0。没有抹掉这些差异后冒称全packet一致。

旧3次主harness没有捕获模型输出，不能追溯声称已观察。为此另用同一冻结scale对普通旧/新17负载各补采一次：真实provider raw均393字节，SHA256 `bbacb047eebc84ab4a85d8fad0af7b71f0e05cfb74fcf584cff7a03345af3b9d`；持久化response与parsed各189字节，SHA256均`9a45316299f502ee36cae29acf06ba5043fd032df1b9048f54fcdbd07b795a2c`。各项逐字节相同、实际JSON解析一致，validation=valid、acceptance=accepted；完整manifest重新校验通过。原始bytes在真实返回/工件处观测，不用fixture常量重建。该单次补采窗口不加入主3次性能统计。

[真实输出对照](../../outputs/acceptance/performance-round2/pf07-final-actual-output-comparison.json)。

## 增长限制与未解决连续性

17条指数据库预置合成cognition_episodes，**不是17轮对话均入模**。此前0/50/100持久化档通过，但题目与预置历史ID在实包均无命中，只绑定本次计算episode；它们是历史数据库增长的中间源码证据，不能冒称最终源全量历史入模扩展能力。[实际历史覆盖审计](../../outputs/acceptance/performance-round2/pf07-cognition-history-material-audit.json)。

原11条Memory与真实PeopleRelations共享来源负载没有减少。最终shared08计算通过，assembly在188.409秒达到原762183行预留，实际字节206440494低于213338874；0次模型调用。这是TODO允许如实报告的增长cap限制，不是正例通过。[共享增长原始结果](../../outputs/acceptance/performance-round2/pf07-shared-source-08/result.json)。

**连续对话第二轮尚未达到标准，是未解决工程问题。** 最终continuous06/history17首轮134.093秒成功；第二轮已接受真实聊天并通过计算，在211.485秒达到assembly原453229行预留，第二次模型调用未发生。独立history0最小补充仍保留完整8模块和全部实际选择输入，不裁切原17负载：首轮135.055秒成功，第二轮212.939秒达到原449090行预留，仍只有1次provider调用。因此不能声称已证明两次独立wire、连续记忆闭环或两轮完整输出；单次fresh wire无session/resume键不能代替此证明。

- [17历史连续两轮真实结果](../../outputs/acceptance/performance-round2/pf07-continuous-06/result.json)
- [0历史独立最小连续补充](../../outputs/acceptance/performance-round2/pf07-continuous-minimal-01/result.json)

初期typed Evidence/native revision/primary事件owner缺口已修复并通过定向验证；后续完整流程确实推进至assembly原扫描上限。这些修复不能掩盖连续功能仍未通过。全部8份共享失败、6份17历史连续失败及最小补充保留，不覆盖、不skip、不降低负载追通过。

## 故障验证与完整回归

分层修复后最终PF06 named15为287/287唯一用例通过，0失败/错误/跳过，107.553941125秒；205公开源码输入前后稳定。保留原278项并加入未知collector/子类反例及完整架构、诊断模块。覆盖停止/撤权/更正/擦除、不同用途/接收者、read/delete、多路径/环、同/外连接与线程/进程、控制与目录/工件替换、回滚与未知事务、原预算/unknown及真实observer/全8模块严格差分。

[最终修复后冻结故障证据](../../outputs/acceptance/performance-round2/pf06-faults/targeted-frozen-15/result.json)，SHA256 `15e008964c79e77abdcbe013f95b166423d63884c8627ea274e8c89ff9200e9f`。

完整IM19原一次离线回归已执行：1639项，1538.985秒，1失败、1错误、0跳过，372公开输入前后稳定，exit1。失败为meter反向导入应用contexts，违反原分层断言；错误为诊断测试用`__new__`手造旧phase夹具缺少真实生命周期。原`passed=false`保留，不能写成1639项单次全部通过。

原机制覆盖真实通过：438/438义务、1314/1314重复引用、107/107裁决，1485实际执行记录（1455被引用）；不据此推断独立科学样本数。两项离线前端检查exit0，不包含浏览器布局验证。

[原1639项完整封存](../../outputs/acceptance/tool-learning/im19-recheck-5acbe57b238b4b23a83e72677be66085.json)。

两项最小修复已完成：精确collector类型、方法、meter与busy认证搬至应用contexts入口，基础设施仅保留私有受管ContextVar状态；未知observer仍保守，不使用任意类型注册表或动态导入绕过分层断言。诊断测试改用真实临时Store/phase，保留原命中和图保留上限断言，并新增真实Row及无第二次SQL检查。完整相关组合80项、增强反例及最终统一287项均实际通过。

产品分层修复后，上述117.553秒仅为修复前冻结源码实测；最终修复源尚未重测三次，不得把边界等价主张冒充最终源实测。详细PF07验证报告与145份冻结证据仍保留测量当时版本。组合审计确认原372输入与当前372输入之间仅7处预期变化：2产品文件、4相关测试、PF06 runner；原1485机制记录、coverage及原全套证据共1487份文件hash完全不变，145份PF07冻结证据hash亦全部有效。

[最终组合复验及逐文件影响审计](../../outputs/acceptance/performance-round2/final-composed-regression-audit.json)。结论是“原全套1失败1错误，修复后相关复验通过”，**不是新的1639项单次全套PASS**。PF08验证执行与审计已完成，但PF07时间、连续性及最终源计时/增长复验条件仍待完成。

## 明确剩余工作

0. 分层修复后最终源码尚未重测同负载三次；117.552631625秒属于修复前冻结版，最终源码计时仍待补证。
1. 在保持完整输入、所有原保护和预算不变的前提下，将同负载三次中位耗时进一步降至116.173078300秒以内，再用固定harness验收；本轮不凭历史112秒结果代过。
2. 修复真实连续聊天第二轮登记/上溯的重复读取，使原cap内完成两次独立模型调用及输入/输出闭环；保留17与0历史现有失败作回归，先设计再实施。
3. 0/50/100条持久化历史的增长结果仅属中间源码证据，最终278冻结源未重验；后续PF07须补同源复验及实际历史选择审计，本轮不追加CPU。
4. 共享11Memory增长若继续优化，应先确定实际重复链路，再复验原负载；不得通过减少字段、来源、召回量或提高cap改变结论。

这些是后续工程TODO，不解锁真实模型、正式部署、正式科学评测或24小时唤醒。

## 关联文档

- [任务与验收状态](../plan/complete-packet-performance-round2-todo-v0.1.md)
- [第二轮详细设计](digital-life-complete-packet-round2-design-v0.1.md)
- [最终详细验证报告](digital-life-complete-packet-round2-validation-report-v0.1.md)
- [故障与所有历史记录](digital-life-complete-packet-round2-fault-report-v0.1.md)
- [仅草案、未实施的写集方案](round2-certified-registration-write-design.md)
