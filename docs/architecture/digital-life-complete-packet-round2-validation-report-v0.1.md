# 完整思考包第二轮隔离验证报告 V0.1

状态：**冻结源码的本轮验证已完成，PF07未满足全部验收条件，不标记完成。**

最终基准中位耗时由145.216秒降至117.553秒，改善19.050%，未达到预先固定的20%时间门槛；实际返回行下降57.072%，达到读取量门槛。完整业务输入、来源和原始输出对照通过。非空共享记忆／关系负载及真实连续两轮仍在原阶段预算内被阻断，原cap未提高。

未操作正式实例、未调用真实LLM API／本地真实模型，未执行正式唤醒或长期验收。所有思考均来自新建TemporaryDirectory中的完整8模块合成实例、确定性模型替身。

## 最终验收结论

| 条件 | 最终结果 |
| --- | --- |
| 同负载新旧各3次、时间中位数至少下降20% | **未达标：19.050%** |
| 实际行读取至少下降20% | **通过：57.072%** |
| 全部业务`/input`及来源、Scope、时间／条件不缩水 | **通过：逐字段精确相同，未归一化** |
| 完整manifest与原资源账户 | **通过：175字段、168依赖，实际子预留与总cap正确** |
| 实际provider raw／持久化response／parsed输出 | **通过：普通17负载补采逐字节相同、valid／accepted一致** |
| 11条Memory＋关系共同来源完整流程 | **blocked：原assembly scan/items子预留** |
| 同实例两轮真实聊天、history17 | **未证：首轮成功，第二轮assembly子预留阻断** |
| 独立history0最小两轮补充 | **未证：完整特征保留，第二轮仍触原assembly子预留** |
| 0／50／100条历史增长 | 早期中间源码验证通过；仅为未选episode持久化与选择边界证据，不冒称最终全历史扩展验证 |

最终冻结源通过PF06 named14的278项定向故障／引用／权限验证，不能替代PF08全量回归。此报告完成证据整理，不把未达到的PF07条件改为通过。

## 负载、隔离与计时方法

主比较使用完全未修改的`evaluation/tool_learning_round2_replay.py`，旧实现来自封存公开源副本，新实现来自最后冻结版本。新旧各3次顺序执行，单CPU，不安装SQL trace、栈采样或额外诊断计数器，不挑最快值，不在同源码失败后反复重跑筛成功。

合成世界UTC固定2031-01-02T03:04:05.678Z，磁盘读数及UUID序列固定；SQLite非now日期验证委托真实builtin。monotonic与原PhysicalReadMeter实际计量不动。计时窗口从Engine.think前，到packet／manifest读取和保存后结束，不是仅LLM延迟，也不冒称纯Engine方法含时。

“17”指数据库内17条预置`cognition_episodes`，**不是17轮对话全部送入模型**。最终普通补采直接保存17条真实数据库ID／题目并扫描packet＋manifest全文：这些旧题目及ID均0命中，实际绑定的是当前计算episode。完整8模块及11组业务特征始终保留。

主harness SHA256：`7324de48f3f02d19b1fb2e9aafc498aab7284262a7f875ba9949e1fbc77e54db`。

## 最终三次真实计时与计量

| 版本／次序 | 总窗口秒数 | 实际scan／items | 实际字节 |
| --- | ---: | ---: | ---: |
| 旧01 | 145.216347875 | 1,479,635 | 356,150,890 |
| 旧02 | 146.978334250 | 1,479,635 | 356,150,890 |
| 旧03 | 143.217004750 | 1,479,635 | 356,150,890 |
| 最终新01 | 117.445454000 | 635,178 | 188,251,615 |
| 最终新02 | 117.616215250 | 635,178 | 188,251,616 |
| 最终新03 | 117.552631625 | 635,178 | 188,251,617 |

旧中位数145.216347875秒；新中位数117.552631625秒，最慢117.616215250秒。预定时间门槛为不超过116.173078300秒，因此未通过。实际行减少57.072%，该门槛通过。字节1—2字节差额来自实际账户材料，不强行改写为相同。

三个最终新样本均成功、源码前后稳定、同源同harness，packet和manifest彼此逐字段精确相同。最终133个产品Python文件的规范摘要集合SHA256为`25fac4482701605519756835106ff7aaa5cc97016169503c751509052005a503`；完整逐文件摘要保存在比较附件。该摘要只指产品Python集合，不能冒称覆盖整个项目所有文件。

历史中间源码曾测得112.421秒中位数；本报告**不以它替换最终117.553秒**，也不从旧自然时钟419秒样例拼接本轮严格加速比。

## 完整输入及原预算推导

六个主样本保留11组特征、175个manifest字段、168条输入依赖。最终新三次的整个`/input`与旧基线精确相同：包括业务值、原件来源、修订、Scope、时间、条件及全部计算特征，没有仅比较数量或删字段后宣称等价。

完整packet不是字节相同，原始差异仅以下3个真实余额派生值：

| 路径 | 旧值 | 最终新值 |
| --- | ---: | ---: |
| `/limits/max_scan` | 857,240 | 905,620 |
| `/limits/max_items` | 857,240 | 905,620 |
| `/limits/max_bytes` | 116,509,614 | 123,183,099 |

manifest仅相应`/limits`字段digest和整体packet_digest改变，全部原始差异保留。这些limits与实际assembly子预留逐项对应：scan/items等于子预留；max_bytes等于实际246,366,199字节子预留的整数一半。读取减少使可用余额增加，未修改原总cap或原.5阶段份额。

三次每项实际消费均不超过自己的原预留，unknown为0。原总cap保持200万scan/items、512MiB、20万输入token、200输出token、8次attempt/tool、600秒机会。替身协议每次实际记1次attempt、100输入／20输出token；这是固定合成协议，不是实际LLM tokenizer或费用证明。

## 实际原始输出补采

主3次harness未保存provider原始body，不能用fixture常量冒称它采过输出。另用冻结`tool_learning_round2_scale.py`对正常旧／新17负载分别观测一次，均成功、源码稳定，新补采产品摘要与最终主三次精确相同。这两次不混入3次速度样本。

| 观测层 | 旧／新实际结果 |
| --- | --- |
| provider原始UTF-8响应 | 各393字节，逐字节相同 |
| 持久化response原bytes | 各189字节，逐字节相同、保存SHA＝登记hash |
| 持久化parsed原bytes | 各189字节，逐字节相同、保存SHA＝登记hash |
| 解析／接收状态 | 均valid／accepted |
| raw内structured body与存储body | 精确相同 |
| 业务input与完整manifest | 精确业务input相同，原validate_manifest通过 |

raw SHA256：`bbacb047eebc84ab4a85d8fad0af7b71f0e05cfb74fcf584cff7a03345af3b9d`。

response／parsed SHA256：`9a45316299f502ee36cae29acf06ba5043fd032df1b9048f54fcdbd07b795a2c`。

补采harness SHA256：`5f6fa20b6fce90c50f4d6c3e01a0779ce3e2532e43157eb69ac7230e33c13fd4`。捕获的是实际supervised transport返回值和实际thought_results工件，缺失明确unknown，不靠预期常量重建。

## 非空增长和连续对话的真实限制

共享负载通过真实合成控制输入、自动Memory编码、PeopleRelations公开owner接口建立共同来源：初始3条Memory增加8条到11条，关系对象2个、角色值1条。角色仅为两个独立自述支持的“自称liwei”，不等于身份认证或亲属事实；不手写来源边，不把人物名字当授权。

原共享08仍在assembly的762,183行子预留触界，实际字节206,440,494小于213,338,874；未进入模型。因此只能记录blocked，不能声称共同原件已完成两域入模正例。

原continuous06首轮成功134.093秒；第二轮已真实创建、旧身份／记忆保留，计算阶段通过，但assembly453,229行原子预留耗尽，未发生第二次LLM调用。

独立history0最小补充保留全部8模块、11域和原选择输入，不裁切原history17场景。首轮成功135.055秒；第二轮计算通过，随后assembly449,090行原子预留耗尽，字节139,795,320小于142,674,013。首轮实际fresh wire、raw和response保存完整，但仍只有1次调用，**不能声称两轮连续与两次fresh调用已经证明**。

上述实例均源码前后稳定、原cap及.5份额不改。错误原样保留，没有降负载挑成功。预算阻断保护正常，并不自动证明功能闭环已经达到要求。

## 早期增长、修复与历史证据范围

中间源码的0／50／100预置episode场景均成功，实际存储总数为1／51／101（含当前计算），字段175、依赖168。它们验证的是未选episode持久化增长及既有选择边界，不证明全历史入模或线性扩展；也不冒称是最后冻结源码重新执行过的规模样本。

完整非空验证曾发现并修复typed Evidence外键、controller native修订和8种primary配置事件owner缺口，修复后两轮已能进入第二次实际思考；仍存在上述资源边界。早期配置适配器反复初始化的计量放大、各版scan／byte触界及中间源码计时全部留存。未将未知来源泛化放行，未删高维特征或跳F1、ACL、Scope、停止和来源核验。

## 证据索引

- [最终冻结三次比较、逐文件源摘要、完整raw差异、实际子预留](../../outputs/acceptance/performance-round2/pf07-final-frozen278-comparison.json)
- [实际raw／response／parsed输出对照](../../outputs/acceptance/performance-round2/pf07-final-actual-output-comparison.json)
- [实际17条数据库目录与全文选择审计](../../outputs/acceptance/performance-round2/pf07-final-history-selection-audit.json)
- [原共享1—8所有失败](../../outputs/acceptance/performance-round2/pf07-shared-attempts-summary.json)
- [原连续1—6所有结果](../../outputs/acceptance/performance-round2/pf07-continuous-attempts-summary.json)
- [最小history0连续补充](../../outputs/acceptance/performance-round2/pf07-minimal-continuous-summary.json)
- [早期持久化规模及原coverage](../../outputs/acceptance/performance-round2/pf07-growth-history-summary.json)
- 历史逐次工作记录：`outputs/acceptance/performance-round2/pf07-validation-working-notes.md`。

本轮三次重复用于工程计时，不是独立科学样本N；固定模型替身验证数据和调用协议，不能证明真实模型的语言理解、人格量表效度或主观体验。PF08全量回归另行报告，不把它反推为上述未满足条件已经通过。
