# 自持思考 V2 首版设计

## 运行与责任
每次唤醒检查变化或可推进方向，选择一个方向或等待。一轮一个活动、一个干净模型请求；方向可跨活动延续。原工具审批与预算不变，严格 schema4 实例暂不开放新版，旧 V2 探索协议不变。新配置显式 mode=continuous 才使用新循环。

## 持久化
复用 SQLite runtime_events 与不可变 artifacts，事件为 continuous.direction（方向快照）、continuous.selection（因素、概率与抽样）、continuous.step（理解、下一步、进展性质与决策）、continuous.tool_result（真实回执）、continuous.discovery（已处理经历窗口）。引用原 request/activity/result，不复制身份。读取必须沿用记忆权限及来源撤回检查。

方向状态为 ready、waiting_tool、paused、finished。继续/分支保留 ready；换向使当前方向短暂冷却；暂存必须记录重新开启条件；结束仅表明该轮探索目标已结束，不自动认定事实。无新来源且重复相同理解/方法，不计进展；模型提出的新理解标为自评，实际工具结果另外记录。相同方向按规范化文本及字符重叠初步合并；语义重复检测首版仍为启发式，不能宣称完备。

## 选择
先过滤来源不可读、暂存、结束和等待工具的方向。当前人格、状态、动机、已有认知和关系共同构造可记录的特征；用 softmax 概率抽样，同时保留等待选项。最近连续无进展扣分并冷却，切换不等于删除方向。概率参数均是工程初值，未经心理学实证。

## 协议
V4 输出保留 action/explanation，新增 reflection：directions（最多4个新方向）、decision（continue/branch/switch/pause/finish）、understanding、next_step、reason、reopen_condition、evidence_refs。新方向有 title、kind、next_step、expected_gain、cost、evidence_refs。kind 为 reflect/explore/create/relate/maintain。所有引用必须来自当轮输入；权限不由模型输出授予。模型 finish 也不提升认知为已确认。

## 首版边界
探索深度不再由树层数或访问两次决定；单活动和全局预算仍限制实际消耗。暂存/结束不能凭下一次随机调用自动重开，后续需新经历与明确理由。先人工重开入口，不自动猜测复杂条件。源代码自修改、人格成长不属于本次范围。完整模型用量与状态仍由原运行器负责。

## 真实链路修订：步骤与方向分离（2026-11-14）

V5 输出在 V4 基础上增加 inquiry：prediction（本步预期）、observation（实际看到了什么）、revision（理解如何改变）、remaining_questions（最多四项）、next_attempts（最多四项）、direction_status（ready/paused/finished）及 finish_basis。完成一次回复不再直接结束整个方向。有尚待处理的问题及后续尝试时保留方向；受阻则暂停，避免为了继续而空转。自由文本仍是模型报告，不冒充独立验证。

每步输入回放该方向最近四份真实工具回执，便于比较先前观察。生成方向与推进方向明确分开：生成阶段仅等待；推进阶段可提出结构化工具行动，由现有审批及执行链执行，模型不能自行调用工具。收到工具回执后，再由下一次独立调用更新理解。

新增 scripts/run_continuous_system_trial.py，将限定次数、限定时长的合成任务接入既有正式运行器和模型。预期答案仅保存在评价文件，不放入模型输入。验收只批准两份指定、哈希未变的合成文件读取；不扩大权限，不发送提醒。观察程序结束时关闭自主探索，聊天及健康维护保留。
