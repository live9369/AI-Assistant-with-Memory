# 经验回流首版交付报告

日期：2026-11-14。状态：实现、必要隔离验证及最小真实模型验收完成，已更新既有正式实例。

## 交付结果

1. 聊天V3与探索V6进入同一CognitiveUpdates接纳入口。探索的learning.claims最多4条，可留空；区分来源陈述、推断和方法。所有模型提案仍为held，不自动成为现实真值。有效时间与记录时间分开。
2. M03认知修订与M04可召回表示同事务发布，引用原认知版本、原文及来源性质。重复发布同一修订复用已有表示，不建立另一个权威事实库。确认和更正保留历史；默认召回排除被替代的旧表示，明确询问历史时标记旧版本。历史来源仍有效时可继续作历史依据，不能把“旧版本”误当成“无权读取”。
3. 原始来源归档、权限撤回或版本失效后，派生内容不能继续被当成可用来源。账户域与父来源读者交集保留，私有推断不能靠总结跨账户公开。增加循环/深度防护。
4. 已确认的方法可接受明确的控制者反馈。同方法同反馈来源幂等，unknown不计成功，可撤销。只有方向引用该方法表示且匹配适用线索时，才加入有界经验因素；保留原人格、动机、状态、概率与权限。模型自评和工具成功不自动计为方法有效。
5. 原问题与停止规则保留；发布经验不额外要求继续探索，无新增内容时空提案是正常结果。

本次是当前native链路升级，未迁移schema4，也不声称已完成TL-LOOP的全部保证。

## 必要验证

最终相关核心组合45项通过，约16.6秒，日志见 outputs/experience-return-real/core-tests.log。包含：V6探索到统一认知及记忆、新活动召回、幂等发布、更正和确认后的当前/历史分离、原来源归档阻断、账户隔离、精确引文拒绝、方法因素进入实际方向评分、反馈去重、适用范围和撤销，以及原聊天、来源和探索生命周期相关回归。没有运行无关全量或长时间测试。

真实模型验收使用一个新建且仅含合成资料的隔离实例，沿用当前已配置模型；不发送正式身份、私有记忆或历史。通过实际Engine队列、原权限审批、工作目录工具执行和接收链路，完成3次独立请求：

| 调用 | 实际行为 | 结果 |
| --- | --- | --- |
| 1／V6 | 提出读取learning-case.txt，经核对指定文件后批准执行 | 实际工具回执成功；调用前输入没有测试代号 |
| 2／V6 | 根据真实正文提交有引文的学习提案并结束该方向 | 发布1条可召回的认知候选表示 |
| 3／V3 | 固定账户会话的首次提问，没有会话前文 | 取回该认知表示并答对代号，说明合成来源及未核实状态 |

三次提供方会话标识互不相同，均为fresh_request。问题只含测试对象，不含代号；答案来自前一步实际读取及保存。验收后隔离实例设置停止与禁止唤醒标记，未把这些合成内容写入正式实例。

证据：outputs/experience-return-real/result.json、input-1.json至input-3.json、output-1.json至output-3.json。复现入口为 scripts/verify_experience_return_real.py；它新建合成目录，不唤醒正式实例，运行前仍应明确授权真实调用，避免无意义重复。

## 正式部署

既有实例：work/primordial00-first-wake。部署编号：c41bec4ca62a426395e17f87db2914ef。

部署前确认无待处理队列工作。经原CLI停止、部署和启动后，核对身份与锚点、人格配置未变，原244条记忆仍存在，42条测试记忆仍归档。自主探索关闭，聊天和健康维护保留；没有开启人格成长、习惯学习或自动事实确认，没有批量回填旧候选。

正式实例本次没有额外真实聊天验收，真实调用只在合成实例完成。正式部署与状态对照见 outputs/experience-return-real/formal-before.json、formal-after.json。

## 使用与边界

日常聊天的新认知候选自动发布带状态的表示。下一次显式启用连续探索时，新绑定在认知功能开启的情况下使用V6；旧绑定协议和旧记录保留。它们不是隐藏的提供方上下文。

控制者仍可用CLI确认认知及评价方法：

```sh
python3 -m digital_life --data work/primordial00-first-wake cognition status
python3 -m digital_life --data work/primordial00-first-wake cognition confirm --revision CANDIDATE_ID --expected-current CURRENT_ID
python3 -m digital_life --data work/primordial00-first-wake cognition method-feedback --revision ACCEPTED_METHOD_ID --source USER_SIGNAL_ID --outcome success --reason '该方法在这次任务中有效'
python3 -m digital_life --data work/primordial00-first-wake cognition retract-method-feedback --feedback FEEDBACK_EVENT_ID --reason '撤回这条评价'
```

反馈来源必须是真实记录的控制者外部输入信号，不能引用模型自己生成的评价冒充用户反馈。确认及评分不改变来源性质，也不赋予现实身份或关系已获外部验证的含义。

以下边界继续保留：

- 精确引文检查证明引用存在，不自动证明语义支持或现实真值；不充分的模型判断仍是候选。
- 历史问法与方法适用线索使用有限文本规则，不是通用语义检索或时间推理；未展开检索性能专项。
- 方法效果目前是控制者明确评价驱动的有界方向偏置，尚未实现任意任务的自动效果归因，也没有训练模型参数或校准长期因果收益。
- 首版方法影响方向选择；普通工具候选仍沿用既有策略，不宣称已比较所有实施方案。
- 人格成长、习惯学习和后续自我能力模型不在本次启用范围。全局学习背景下普通账户的其他既有限制没有扩大解除。

## 修改位置

- digital_life/application/cognitive_updates.py：统一提案、来源检查、认知修订及确认发布。
- digital_life/application/cognition_memory.py：认知表示、当前/历史区别和依赖检查。
- digital_life/application/method_experience.py：显式反馈、撤销及有界方向效果。
- digital_life/application/engine.py、continuous_exploration.py：接受顺序、V6输入及方向评分接线。
- digital_life/application/services/memory.py：召回表示性质、历史标记与动态来源检查。
- digital_life/infrastructure/llm/schemas.py、entrypoints/growth.py：严格协议与CLI。

设计与任务清单见 experience-return-v1-design.md；调研依据见 ../research/experience-return-solution-review.md。
