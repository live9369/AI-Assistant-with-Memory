# IM07 观察准入、提取、比较与产物设计

日期：2026-11-09；版本V0.1；依据冻结TL-LOOP-0.1及Q04/Q05。先设计后实现；只新合成隔离实例，不操作当前实例或启动真实模型。

## 固定请求与处理声明

`ToolLearningObservation.assess(entry,envelope)`使用冻结assess_observation操作。payload.method.request_ref绑定已登记不可变`TL-OBSERVATION-PLAN-1`：Scope、主体Slot、predicate、所需四类产物、可选效果metric Ref、是否需要有限独立解释。声明和原work的processing_method一致；产物/预算/来源身份不能通过换方法偷偷刷新。

来源原artifact字节/摘要/media_type、locator与所声明视图逐项核对。JSON pointer、Unicode text_range、byte_range和完整原子工件沿IM02解析；0、false、来源明确null独立保留。缺字段或定位失败不猜值，有限等待/不足有持久原因；格式和权限错误有明确拒绝/阻断。工具返回正文只是数据，代码不接执行器、不重复原工具。

## 产物与比较

ObservationExtract生成可精确定位的source_report Claim；所见10只表示来源报告10，Scope保持声明边界和未知，不转换为world/causal truth。纯解析不调用模型。

ComparisonAssessment使用请求中固定VersionToken及已保存typed Claim材料。每个baseline真实对象/版本/字节和资格均核定，不能把检索不到当从未知道；部分覆盖如实保留。完全相同主体/property/时间/条件/unit/粒度等Scope才采用精确比较；同值可确认/无变化，不同值保留conflict和双方支持，不按新旧选赢家。不可比明确not_comparable，缺材料为insufficient；保留未知/反证及旧Scope，不覆盖历史。

UpdateProposal只提出M03意图（add/confirm/mark_conflict等），不产生Decision/content revision/head/表示，不把提案当接纳。目标是具体baseline版本或明确新对象。EffectAssessment仅产生not_measured/incomplete报告，gain unknown；没有真实测量不得填0或正收益。metric_definition必须真实Ref，未指定所需metric则有限等待，不伪造定义。效果后续接线IM14。

四类Product完整头部/Checks/来源/Scope/依赖与body分别保存tl_product原件；所有引用实际核定，产品、命令结果和工作阶段变化同事务。跨键同加工身份已有Product只复用，不多计观察/证据/收益。

## 预算、资格与独立思考

读取和推理按IM05原work账户共享，读取scan/items/bytes和思考input/output/attempt均持久记账。实际调用在主库事务外，IM06检查来源/所有baseline/全部已登记请求输入，并在真实本地callback入口持相同dispatch_gate；返回后再检查资格与当前控制，晚到失效结果不作为有效Product提交。

可选`ObservationThoughtPort.generate_fresh`每次接收完整独立JSON包，没有history/session/先前provider response等隐式上下文；输出仅解释rationale/limitations/missing，不可直接制造可接受世界主张或收益。thought_requests/attempts/results保存完整输入输出和校验状态，真实入口见证来自本地回调调用路径而非prepared/sent。端口默认拒绝，现有action-schema适配器不被静默当成学习推理器；隔离确定性替身验证接口与异常，无真实模型消费。

失败/未知用量保留原额度占用；已进入回调不能按零费用释放。明确未进入才经独立可信预算核验释放；没有新请求/重试自动续期。模型失败不无限重试，原work进入有限失败/等待状态，重开留IM13。

## 可信端口与状态

ObservationAuthority默认拒绝当前许可、材料/声明、baseline归属、语义边界、实际思考入口与结算核验；请求module或正文不生成权限。阶段只在已有合法工作内推进。成功有提案→awaiting_decision；无变更→明确no_change；不足→waiting且带原deadline和待补项。停止/取消/到期不自动唤醒或重新调用，历史事实与可用资格分开。

## 隔离验收

新IM01合成库+现有SQL、真实C0、有限计划，退出停止加锁。验证四类产物、来源报告不升级、0/false/null/unknown、来源/locator/bytes错配、精确baseline/不可比/冲突/无变更、同键/跨键复用、无测量gain、预算累计与额度耗尽、独立干净调用输入/完整输出持久、异常用量未知、F1返回后阻断、提交失败原子回滚、无模型/原工具重做。真实业务接线未验证部分明确报告，不以stub或替身冒称生产模型已接通。

## 实现定型与界限

材料工件采用`TL-OBSERVATION-MATERIAL-1`，保存四类typed Product原件及固定source/baseline token；prepare/material/failure事件分别持久，准备后无材料不得盲重跑，物化已成而主提交失败可按原材料核对，不再调用模型。非processing工作只允许已经完整存在的产品历史复用，不补发/续跑，恢复仍属IM13。预算不足为stopped，定位/必要材料缺失为有限waiting；失败/阻断保留实际进度和用量。

原件、解析view和每份baseline分开逐次计量，已知尺寸超阶段余量前停止读取；成功的完整校验读取才按实际尺寸计bytes，失败或损坏导致无法确认的读取为usage_unknown。elapsed_ms使用本地monotonic观察并上取整毫秒，不用未测零。解析view为unknown/withheld等不能碰巧退回原件；not_applicable view使用原件时仍核已知view_digest。来源显式null保持known/null/source_reported_null。

自动可比要求真实主体Ref、unit、conditions、domain、granularity、时间边界均已知匹配，conditions known/null不是已知无条件。不同类型False与0不等；未知值不会因两边都null而确认。可信比较权威可另给明确可比证据。每条比较保持自己的baseline；只有唯一真实可比目标才建单一existing提案，多目标保留比较并等待明确拆分，不默选第一个。legacy cognition对象与native tl_content映射由IM08明确，不将旧ID直接塞入新FK。

最终fresh packet具有实际thought_requests.id、work_ref、固定source_token、全部已读baseline材料、绑定model/config/provider/process身份，以及deadline和input/output/scan/items/bytes阶段上限（父剩余与请求cap取小）。端口configured_binding及实际返回route必须一致。preflight提供可信输入token计数并承诺可落实output/byte/deadline界限，缺能力默认拒绝；本项隔离数值不是供应方真实消费证明，具体provider硬限制/真实tokenizer由IM11及真实启动门验证。输入/输出JSON字节在本地计量，供应方额外实耗不可按零伪造；部分usage为unknown。

所有含来源材料的准备事件、context、思考输入、返回正文和最终Product物化都在相同gate内先核资格再落盘。响应retention权威、source/全部baseline当前资格及实际响应写入持同一门禁，F1不能夹在check/write之间；删除范围内晚到正文/hash不先落盘再补删，费用/错误类型等允许的事实另记。生产provider未接线；未重做原工具。
