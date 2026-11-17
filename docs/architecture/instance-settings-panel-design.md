# 实例配置面板设计 V0.1

日期：2026-11-16。先设计、后实现；只用临时实例与替身验证，不改变现有实例配置。

后续变更：2026-11-17按用户要求增加显式默认不限累计预算模式，参见[聊天核心修复](chat-core-fixes-v0.2.md)。本文件其他历史默认值不自动重写旧活动。

## 目标与页面

新增仅root可用的“实例配置”。沿用浅色现代工作台、现有字体与青绿色；标题与表单左对齐，内容最大宽度约1000px。窄屏分组横向滚动、字段单列，标签和错误可读，不用大段JSON作为配置编辑器。左侧或顶部按身份、人格、价值、预算、对话与记忆、学习、行为、探索、维护、目录权限、恢复设置分组，默认只展开所选组。每组独立保存，展示修改前后、原因、版本和生效条件，离开未保存页面需提醒。

只开放已有明确语义的控制，不把内部数据库ID、来源校验、停止保护或冻结研究常数做成任意配置。账户、记忆域、模型参数与授权继续由现有页面承担，在配置页提供入口。审批与人工学习提案是工作流程，不伪装成开关。

## 可调范围与实际接入

| 分组 | 参数 | 实际落点 |
| --- | --- | --- |
| 身份 | 实例称呼、补充交流偏好 | 新configuration_versions与identity_anchors；不换instance_id、self_actor或账户 |
| 人格 | 五维−1..1 | Personality.replace；人工配置依据与确认分别保存，明确不是测评或成长效果 |
| 价值 | 各维相对权重 | Values.replace，归一化后保存；标记人工配置 |
| 任务预算 | 总token、工具次数、总尝试数、时长、单次思考预留、单请求尝试数、请求期限 | runtime设置；Engine.submit、Budget.create、TaskLoop.thought_tokens、Engine.prepare真实读取；只影响新活动 |
| 对话与召回 | 近期消息条数、近期材料字节上限、普通/探索召回条数、root/其他来源权重 | Chat.context、Engine.prepare、cognitive_influence；root权重必须高于其他来源 |
| 认知 | 候选记录开关 | CognitiveUpdates.configure |
| 人格成长 | 开关 | PersonalityGrowth.configure；现有人工标注/评估/提交规则不变 |
| 习惯 | 候选收集开关、已审阅习惯学习开关 | HabitCandidates、HabitLearning；不自动确认候选 |
| 经验 | 自反馈影子记录、受控经验测量开关 | SelfFeedback、ExperienceMeasurement；保存不运行评测或真实模型 |
| 记忆质量、人物关系、自主安排 | 各模块开关 | 各自configure；不自动确认关系或生成承诺 |
| 动机 | 开关、最低磁盘余量 | GoalRegulation.configure |
| 行为概率 | 开关、温度、各行为偏置与所有已有特征系数 | BehaviorPolicy.configure；表格编辑，不改变合法候选过滤 |
| 探索 | 开关、模式、间隔、活动数、轮数、有效时长 | Exploration.configure；保存不开运行器、不解除WAKE_DISABLED |
| 维护 | 开关、自动修复、最多修复数 | SelfMaintenance.configure；只保留既有受限修复能力 |
| 项目目录 | 授权开关、目录、工具子集、额外排除、自动审批 | ProjectAccess.configure；强制排除仍不可删，源代码与部署权分开 |
| 恢复 | 检查点开关、新版本独立思考验收、验收超时 | ProcessCheckpoints.configure及现有控制记录；不启动、部署、恢复或回退 |

首版不接入受保护schema4的原生设置写入口：明确返回不支持，不绕过既有保护。模型的输入字节容量与token额度继续分开，Codex能力不因页面可编辑就获得硬限额保证。

## 接口、版本与保存

GET /v1/instance/settings 返回分组、类型、范围、字段提示、当前值、组revision、是否可编辑与原因，GET不写入、不探测模型。POST /v1/instance/settings/{group} 接收完整values、expected_revision、reason、confirmed=true。服务端拒绝未知字段、非有限数、类型伪装、越界、非root与运行中修改。

所有设置统一要求持久停止且active_process_run_id为空，在实例dispatch_gate内再次检查。不要由网页偷偷停止、重启或唤醒。使用组状态与实际配置版本生成revision；防止旧页面覆盖CLI或另一窗口的更新。组内保存为事务并记录修改前后与操作者；恢复配置复用现有文件原子替换与控制库审计。配置文件的写入不与运行账本合并为虚假的跨库原子事务。

新runtime参数在活动创建时冻结到budget_json，调用与后续轮读取该快照。旧活动不补额度、不换预算、不延长期限，严格学习路径继续使用原预算。默认值沿用旧行为。对话/召回参数默认8条历史消息、8000字节、8/3条召回；新增信息不允许绕过权限。

## 核心验收

只验证临时实例：root与普通账户权限差异、运行中拒写、旧revision冲突、每组参数实际保存、非法参数回滚、人格与身份不变、旧活动预算不变、新活动使用新预算、来源撤回仍拒绝、页面字段和未保存提示、宽窄屏布局。保存过程不得调用模型、启动运行器或改正式实例。更新正式面板另走CLI发布流程。
