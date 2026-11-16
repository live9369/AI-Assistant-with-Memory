# 数字生命第一阶段研究文档

当前专项：[认知—经验归属V0.2](../architecture/cognitive-experience-ownership-v0.2.md)。已同步生命工程的状态所有权、系统接口与影子实现；真实收益测量及实际选择接入仍待后续。

## 当前状态

完整系统工程已开始，正式唤醒被用户禁止；见[完整工程实现进度](phase-3-full-system-progress.md)。新增本地模型适配器和 system-v2 数据库定义尚未全部接入正式服务，不标记整体完成。

第三阶段已命名为“原初00唤醒”，首个标准库 CLI 原型已实现，使用测试推理器，见[阶段实现报告](phase-3-primordial00.md)与[运行入口](../../README.md)。当前精简数据库与全量架构库分离；全量增量合并、真实LLM和完整恢复协议仍待实现。

> **第一阶段完成：概念基线完成 / 待系统工程与实证验证。**

第一阶段已完成生命定义、组成量化、完整运行闭环、身份连续性、数字健康和五项最低验收原则。第二阶段将进行系统架构、数据模型、运行机制和实验设计。

第二阶段当前状态：系统架构、数据库增量和模块接口字段设计已补全；新增字段尚未同步到 SQL，运行框架尚未编码。后续按授权进入实现与验证。OpenClaw、Hermes 仅为执行能力参考。

## 推荐阅读顺序

最新审查：[第二阶段架构一致性复审](phase-2-architecture-consistency-review.md)。列明12项交接与字段问题及设计修正；本轮不开始框架编码、不改SQL。

当前统一入口：[第二阶段工程架构设计基线 V1.0](phase-2-architecture-design-baseline.md)。新增详细产物：[数据库增量字段设计](phase-2-database-increments.md)、[各模块接口字段字典](phase-2-module-interface-dictionary.md)。

最新工程闭环入口：[系统运行契约 V1.0](phase-2-system-contracts.md)。覆盖独立思考、一次接受、授权、取消、唤醒、初始化和部署交接，明确待同步的数据库增量。

数据库可执行设计：[SQL、完整字段字典与验证入口](../../database/README.md)。Runtime 160张业务表、Supervisor 6张控制表，已完成 SQLite 存储约束和合成数据流测试；服务层功能验证仍待实现。

数据库设计入口：[数据库架构设计报告 V1.0](phase-2-database-architecture.md)。按生命模块定义特征存储，覆盖逐表核心字段、科学依据、关联约束、更新事务与指标验证；状态为逻辑架构基线，尚待 DDL 和程序实现。

第二阶段计算机系统实现入口：[实现层系统架构 V0.2](phase-2-implementation-architecture.md)，包含技术栈、进程部署、代码目录、数据库、API、任务队列、外部执行一致性和版本回退。

第二阶段架构入口：[模块架构设计 V0.1](phase-2-modular-architecture.md)。初版采用模块化单体与独立生命周期管理器，按生命功能划分状态所有权、输入输出和验证责任。

第二阶段已启动，第一步为[生命指标数字可实现性核验](phase-2-feasibility-review.md)，状态为进行中。该核验分别记录可表示性、可测量性、功能效度和实际测试结果。

1. [`phase-1-complete-report.md`](phase-1-complete-report.md)：第一阶段完整报告；
2. [`digital-life-definition.md`](digital-life-definition.md)：生命定义与概念基线；
3. [`digital-life-quantification-audit.md`](digital-life-quantification-audit.md)：完整性与自洽审计；
4. 按需要阅读下列专题研究。

最新设计：[自反馈闭环设计 V0.1](../architecture/self-feedback-loop-design-v0.1.md)。已明确人格→意图→信息→学习→下一次选择的数据、概率与模块改造；尚未编码或行为验证。

最新专题补充：[自反馈学习：本身意图、信息获取与学习](self-feedback-learning.md)。本轮为文献与架构研究，尚未实现人格驱动、学习收益影响下次意图的闭环。

## 专题研究索引

| 主题 | 文档 | 状态 |
| --- | --- | --- |
| 人格 | [`personality-quantification.md`](personality-quantification.md) | 初步量化完成 / 待实证 |
| 认知与思考 | [`cognition-quantification.md`](cognition-quantification.md) | 初步量化完成 / 待实证 |
| 感知 | [`perception-and-cognition.md`](perception-and-cognition.md) | 概念完成 / 工程待设计 |
| 记忆 | [`memory-quantification.md`](memory-quantification.md) | 初步量化完成 / 待实证 |
| 行为 | [`behavior-probability-model.md`](behavior-probability-model.md) | 初步量化完成 / 待实证 |
| 动机、状态、反馈与自我 | [`supplementary-components-quantification.md`](supplementary-components-quantification.md) | 初步量化完成 / 待实证 |
| 目标、价值、习惯、关系与承诺 | [`dynamic-goals-values-commitments.md`](dynamic-goals-values-commitments.md) | 初步量化完成 / 待实证 |
| 适应标准 | [`adaptive-criteria.md`](adaptive-criteria.md) | 概念完成 / 工程待设计 |
| 身份连续性 | [`identity-continuity-and-branching.md`](identity-continuity-and-branching.md) | 概念完成 / 工程待设计 |
| 数字健康与自我维护 | [`digital-life-health-and-self-maintenance.md`](digital-life-health-and-self-maintenance.md) | 概念完成 / 工程待设计 |
| 五项判据验收 | [`five-criteria-minimum-acceptance.md`](five-criteria-minimum-acceptance.md) | 原则完成 / 阈值待实验 |

## 阶段边界

第一阶段产物是概念和量化基线，不宣称实际系统已经被实现为生命，也不证明意识或主观体验。具体软件设计、SQLite 数据结构、模型选择、事件协议、生命周期管理、健康监测、版本部署、自动回退和实证校准属于第二阶段。

