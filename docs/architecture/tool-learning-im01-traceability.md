# IM01 冻结规范追溯表与实现基线核对

日期：2026-11-09（Asia/Shanghai）。状态：IM01静态追溯交付；不表示新闭环已实现或未来用例已通过。

本记录只读取冻结规范、实施计划和代码文件，未访问当前实例、未打开数据库、未调用模型或服务，未修改冻结规范或任务状态。

## 1 基线核对

冻结记录：`docs/architecture/tool-observation-learning-freeze-v0.1.json`，sha256=`770961cb52f9ce8af2534089c7d190781c51f5217d307d9fdae6ea4e771c2f09`。

规范文档3份、Q01—Q11来源11份摘要均匹配；历史代码快照17份，本次漂移无。代码快照是历史对照，后续正常实现会产生漂移；不能据此拒绝所有实现。规范摘要不匹配则须显式修订，不自行更新冻结摘要。

当前runtime.sql未声明这些新TL表；下表“现有落点”只表示可复用局部机制。schema4迁移及桥接/回退属于IM15/IM16，IM01不创建19表、不改变数据库版本。

## 2 十九张规划表

| 追溯ID／对象 | 业务所有者／实施项 | 现有落点（仅复用候选） | 未来落点 | 正反验收义务 |
| --- | --- | --- | --- | --- |
| IM01-TRACE-T01 / tl_command | 操作接收所有者；IM03,IM04 | `digital_life/infrastructure/persistence/sqlite_store.py` | 类型化命令/幂等账本 | IM01-TRACE-T01-P, IM01-TRACE-T01-N |
| IM01-TRACE-T02 / tl_work | M14/协调器；IM03,IM04,IM05 | `digital_life/application/scheduling.py`、`digital_life/application/engine.py` | 有限学习工作及C0活动/预算绑定 | IM01-TRACE-T02-P, IM01-TRACE-T02-N |
| IM01-TRACE-T03 / tl_product | M14；IM03,IM04,IM07 | `digital_life/application/services/learning.py` | 四类类型化学习产物 | IM01-TRACE-T03-P, IM01-TRACE-T03-N |
| IM01-TRACE-T04 / tl_content | M03；IM03,IM04,IM08 | `digital_life/application/services/cognition.py`、`digital_life/application/cognition_experience.py`、`digital_life/application/cognitive_updates.py` | 内容对象及当前版本头 | IM01-TRACE-T04-P, IM01-TRACE-T04-N |
| IM01-TRACE-T05 / tl_content_revision | M03；IM03,IM04,IM08 | `digital_life/application/cognition_experience.py`、`digital_life/infrastructure/persistence/sqlite_store.py` | 不可变内容修订与版本注册 | IM01-TRACE-T05-P, IM01-TRACE-T05-N |
| IM01-TRACE-T06 / tl_decision | M03；IM03,IM04,IM08 | `digital_life/application/services/cognition.py`、`digital_life/application/cognitive_updates.py` | 八层检查与分轮认知决定 | IM01-TRACE-T06-P, IM01-TRACE-T06-N |
| IM01-TRACE-T07 / tl_group | M03创建/M04就绪；IM03,IM04,IM08,IM09 | `digital_life/infrastructure/persistence/sqlite_store.py` | 互依赖内容/表示组 | IM01-TRACE-T07-P, IM01-TRACE-T07-N |
| IM01-TRACE-T08 / tl_handoff | M03创建/M04处理；IM03,IM04,IM09,IM13 | `digital_life/application/scheduling.py`、`digital_life/application/recovery.py` | 持久表示义务、租约与消费确认 | IM01-TRACE-T08-P, IM01-TRACE-T08-N |
| IM01-TRACE-T09 / tl_representation | M04；IM03,IM04,IM09 | `digital_life/application/services/memory.py`、`digital_life/application/memory_quality.py` | 固定内容版本的纯召回表示 | IM01-TRACE-T09-P, IM01-TRACE-T09-N |
| IM01-TRACE-T10 / tl_representation_head | M04；IM03,IM04,IM09 | `digital_life/application/services/memory.py`、`digital_life/application/memory_quality.py` | 稳定表示系列及当前映射 | IM01-TRACE-T10-P, IM01-TRACE-T10-N |
| IM01-TRACE-T11 / tl_dependency | 登记消费者/原所有者核对；IM03,IM04,IM06,IM11,IM12 | `digital_life/application/memory_quality.py`、`digital_life/application/privacy.py` | 支持/读取/删除依赖图 | IM01-TRACE-T11-P, IM01-TRACE-T11-N |
| IM01-TRACE-T12 / tl_source_epoch | 变更权威域/M12；IM03,IM04,IM06 | `digital_life/application/authorization.py`、`digital_life/application/memory_quality.py` | 源scope资格代次 | IM01-TRACE-T12-P, IM01-TRACE-T12-N |
| IM01-TRACE-T13 / tl_barrier | 变更权威域/M12；IM03,IM04,IM06,IM12 | `digital_life/application/authorization.py`、`digital_life/infrastructure/processes/dispatch_gate.py` | 分原因持久资格屏障 | IM01-TRACE-T13-P, IM01-TRACE-T13-N |
| IM01-TRACE-T14 / tl_change | 合法源生产者/M12；IM03,IM04,IM06 | `digital_life/application/authorization.py`、`digital_life/application/memory_quality.py` | 合法变更身份及F1原子结果 | IM01-TRACE-T14-P, IM01-TRACE-T14-N |
| IM01-TRACE-T15 / tl_propagation | 各目标业务所有者；IM03,IM04,IM06,IM12,IM13 | `digital_life/application/privacy.py`、`digital_life/application/recovery.py` | F2分域确认/F3核验 | IM01-TRACE-T15-P, IM01-TRACE-T15-N |
| IM01-TRACE-T16 / tl_erasure_target | M12计划/目标所有者执行；IM03,IM04,IM12 | `digital_life/application/privacy.py`、`digital_life/application/memory_quality.py` | 逐目标受管清理及效果验证 | IM01-TRACE-T16-P, IM01-TRACE-T16-N |
| IM01-TRACE-T17 / tl_input_dependency | 请求装配者/当前资格所有者；IM03,IM04,IM11,IM12 | `digital_life/application/engine.py`、`digital_life/infrastructure/processes/dispatch_gate.py`、`digital_life/application/privacy.py` | 全输入/输出派生门禁清单 | IM01-TRACE-T17-P, IM01-TRACE-T17-N |
| IM01-TRACE-T18 / tl_effect | M14；IM03,IM04,IM14 | `digital_life/application/experience_measurement.py`、`digital_life/application/services/learning.py`、`digital_life/application/cognition_experience.py` | 效果评估及独立测量引用 | IM01-TRACE-T18-P, IM01-TRACE-T18-N |
| IM01-TRACE-T19 / tl_recall_item | M04；IM03,IM04,IM10,IM11 | `digital_life/application/services/memory.py`、`digital_life/application/memory_quality.py` | 新表示与旧文字兼容的检索结果 | IM01-TRACE-T19-P, IM01-TRACE-T19-N |

## 3 十项契约操作

| 追溯ID／对象 | 业务所有者／实施项 | 现有落点（仅复用候选） | 未来落点 | 正反验收义务 |
| --- | --- | --- | --- | --- |
| IM01-TRACE-O01 / admit_observation | M14；IM02,IM07 | `digital_life/application/services/learning.py`、`digital_life/application/scheduling.py` | 观察准入与分层去重 | IM01-TRACE-O01-P, IM01-TRACE-O01-N |
| IM01-TRACE-O02 / assess_observation | M14；IM02,IM07 | `digital_life/application/services/learning.py`、`digital_life/application/cognition_experience.py` | 类型化提取/比较/评估 | IM01-TRACE-O02-P, IM01-TRACE-O02-N |
| IM01-TRACE-O03 / decide_proposal | M03；IM02,IM08 | `digital_life/application/services/cognition.py`、`digital_life/application/cognitive_updates.py` | G01—G08及C1接纳 | IM01-TRACE-O03-P, IM01-TRACE-O03-N |
| IM01-TRACE-O04 / claim_representation | M04；IM02,IM09 | `digital_life/application/scheduling.py` | 短租约领取固定表示输入 | IM01-TRACE-O04-P, IM01-TRACE-O04-N |
| IM01-TRACE-O05 / publish_representation | M04；IM02,IM09 | `digital_life/application/services/memory.py`、`digital_life/infrastructure/persistence/sqlite_store.py` | C2纯表示发布 | IM01-TRACE-O05-P, IM01-TRACE-O05-N |
| IM01-TRACE-O06 / recall | M04；IM02,IM10 | `digital_life/application/services/memory.py`、`digital_life/application/memory_quality.py` | 有用途的返回与有界回退 | IM01-TRACE-O06-P, IM01-TRACE-O06-N |
| IM01-TRACE-O07 / apply_invalidation | 变更权威域/M12；IM02,IM06 | `digital_life/application/authorization.py`、`digital_life/infrastructure/processes/dispatch_gate.py` | F1屏障和义务 | IM01-TRACE-O07-P, IM01-TRACE-O07-N |
| IM01-TRACE-O08 / acknowledge_propagation | 目标业务所有者；IM02,IM12 | `digital_life/application/privacy.py` | F2/F3分域确认 | IM01-TRACE-O08-P, IM01-TRACE-O08-N |
| IM01-TRACE-O09 / resume_work | 原业务所有者/授权恢复入口；IM02,IM13 | `digital_life/application/recovery.py`、`digital_life/application/scheduling.py` | 原工作有限恢复 | IM01-TRACE-O09-P, IM01-TRACE-O09-N |
| IM01-TRACE-O10 / record_effect | M14；IM02,IM14 | `digital_life/application/experience_measurement.py`、`digital_life/application/services/learning.py`、`digital_life/application/cognition_experience.py` | 独立效果产物与shadow兼容 | IM01-TRACE-O10-P, IM01-TRACE-O10-N |

## 4 九组状态轴

| 追溯ID／对象 | 业务所有者／实施项 | 现有落点（仅复用候选） | 未来落点 | 正反验收义务 |
| --- | --- | --- | --- | --- |
| IM01-TRACE-S01 / Work | M14/协调器；IM02,IM05,IM07,IM08,IM09,IM13 | `digital_life/application/scheduling.py`、`digital_life/application/engine.py` | 逻辑工作阶段/终点 | IM01-TRACE-S01-P, IM01-TRACE-S01-N |
| IM01-TRACE-S02 / Handoff | M04；IM02,IM09,IM13 | `digital_life/application/scheduling.py`、`digital_life/application/recovery.py` | 租约表示工作 | IM01-TRACE-S02-P, IM01-TRACE-S02-N |
| IM01-TRACE-S03 / Decision | M03；IM02,IM08 | `digital_life/application/services/cognition.py`、`digital_life/application/cognitive_updates.py` | 分轮不可变认知决定 | IM01-TRACE-S03-P, IM01-TRACE-S03-N |
| IM01-TRACE-S04 / Content | M03；IM02,IM08,IM12 | `digital_life/application/cognition_experience.py`、`digital_life/application/cognitive_updates.py` | 不可变内容与独立使用资格 | IM01-TRACE-S04-P, IM01-TRACE-S04-N |
| IM01-TRACE-S05 / Representation | M04；IM02,IM09,IM10,IM12 | `digital_life/application/services/memory.py`、`digital_life/application/memory_quality.py` | 固定版本表示及当前头 | IM01-TRACE-S05-P, IM01-TRACE-S05-N |
| IM01-TRACE-S06 / Group | M03创建/M04就绪；IM02,IM08,IM09,IM12 | `digital_life/infrastructure/persistence/sqlite_store.py` | 互依赖组完整性 | IM01-TRACE-S06-P, IM01-TRACE-S06-N |
| IM01-TRACE-S07 / Barrier | 变更权威域/M12；IM02,IM06,IM12,IM13 | `digital_life/application/authorization.py`、`digital_life/infrastructure/processes/dispatch_gate.py` | 分原因持久阻断 | IM01-TRACE-S07-P, IM01-TRACE-S07-N |
| IM01-TRACE-S08 / Propagation | 目标业务所有者；IM02,IM12,IM13 | `digital_life/application/privacy.py`、`digital_life/application/recovery.py` | 有限分域传播 | IM01-TRACE-S08-P, IM01-TRACE-S08-N |
| IM01-TRACE-S09 / Erasure | M12计划/对象所有者；IM02,IM12,IM13 | `digital_life/application/privacy.py`、`digital_life/application/memory_quality.py` | 逐目标清理/恢复核对 | IM01-TRACE-S09-P, IM01-TRACE-S09-N |

## 5 正反例验收目录（全部未运行）

以下ID是分配到后续实施项的用例义务，不是现有测试方法名或通过结果。IM19汇合复验；未来Q11 MECH材料须将裁决和实际fixture逐项链接，不能以本表代替实体材料或运行证据。

| ID | 对象／实施项 | 可判定的场景 | 当前状态 |
| --- | --- | --- | --- |
| IM01-TRACE-T01-P | tl_command；IM04,IM19 | 同键同指纹复用同一持久结果 | not_run；evidence=null |
| IM01-TRACE-T01-N | tl_command；IM04,IM19 | 同键异指纹拒绝；未明提交不盲重放 | not_run；evidence=null |
| IM01-TRACE-T02-P | tl_work；IM05,IM19 | 工作/活动/预算/命令结果C0同时持久化 | not_run；evidence=null |
| IM01-TRACE-T02-N | tl_work；IM05,IM19 | 换请求/恢复不得重置预算；学习触发不得冒充控制者话语 | not_run；evidence=null |
| IM01-TRACE-T03-P | tl_product；IM07,IM19 | 产物保留来源/范围/未知及加工身份 | not_run；evidence=null |
| IM01-TRACE-T03-N | tl_product；IM07,IM19 | 缺字段/缺源拒绝，不能让ready代替认知接纳 | not_run；evidence=null |
| IM01-TRACE-T04-P | tl_content；IM08,IM19 | 只由M03建立/切换内容头 | not_run；evidence=null |
| IM01-TRACE-T04-N | tl_content；IM08,IM19 | M14/M04或旧shadow不得自行写当前世界事实 | not_run；evidence=null |
| IM01-TRACE-T05-P | tl_content_revision；IM08,IM19 | 内容/决定/修订注册C1同时提交 | not_run；evidence=null |
| IM01-TRACE-T05-N | tl_content_revision；IM08,IM19 | 修订号冲突或跨内容previous拒绝；不覆盖旧正文 | not_run；evidence=null |
| IM01-TRACE-T06-P | tl_decision；IM08,IM19 | 同一proposal/review_round只有一个权威决定 | not_run；evidence=null |
| IM01-TRACE-T06-N | tl_decision；IM08,IM19 | 旧轮次不可覆盖新决定；缺复核/支持不得accept | not_run；evidence=null |
| IM01-TRACE-T07-P | tl_group；IM08,IM09,IM19 | C1全组接纳且C2所有必需表示齐后才ready | not_run；evidence=null |
| IM01-TRACE-T07-N | tl_group；IM08,IM09,IM19 | 任一必需项失败不得出现半组当前视图 | not_run；evidence=null |
| IM01-TRACE-T08-P | tl_handoff；IM09,IM13,IM19 | C1完成后可按同一义务继续C2 | not_run；evidence=null |
| IM01-TRACE-T08-N | tl_handoff；IM09,IM13,IM19 | 过期租约/旧代次/未知提交不可覆写或重做原动作 | not_run；evidence=null |
| IM01-TRACE-T09-P | tl_representation；IM09,IM19 | 正文/来源/Scope/未知与表示版本共同发布 | not_run；evidence=null |
| IM01-TRACE-T09-N | tl_representation；IM09,IM19 | 纯表示不得添判断；缺blob或错摘要禁止发布 | not_run；evidence=null |
| IM01-TRACE-T10-P | tl_representation_head；IM09,IM19 | 表示修订以series独立注册并CAS切换头 | not_run；evidence=null |
| IM01-TRACE-T10-N | tl_representation_head；IM09,IM19 | 不能与内容修订号碰撞或由旧工作器回退head | not_run；evidence=null |
| IM01-TRACE-T11-P | tl_dependency；IM06,IM11,IM12,IM19 | 消费者及具体field_path/用途/源代次可追溯 | not_run；evidence=null |
| IM01-TRACE-T11-N | tl_dependency；IM06,IM11,IM12,IM19 | 缺边/环/超限明示覆盖不足，不以支持关系替代删除范围 | not_run；evidence=null |
| IM01-TRACE-T12-P | tl_source_epoch；IM06,IM19 | 合法源变更使当前scope epoch加一 | not_run；evidence=null |
| IM01-TRACE-T12-N | tl_source_epoch；IM06,IM19 | 旧epoch或换scope hash绕过已有屏障时拒绝 | not_run；evidence=null |
| IM01-TRACE-T13-P | tl_barrier；IM06,IM12,IM19 | F1提交后通知丢失仍能阻断新使用 | not_run；evidence=null |
| IM01-TRACE-T13-N | tl_barrier；IM06,IM12,IM19 | 解除一个原因不得清掉其他屏障或复活已删除正文 | not_run；evidence=null |
| IM01-TRACE-T14-P | tl_change；IM06,IM19 | change/epoch/barrier/传播义务同事务持久化 | not_run；evidence=null |
| IM01-TRACE-T14-N | tl_change；IM06,IM19 | 同键不同含义、未经授权删除或预期代次不符时拒绝 | not_run；evidence=null |
| IM01-TRACE-T15-P | tl_propagation；IM06,IM12,IM13,IM19 | 仅完整覆盖及未决零的本域结果标verified | not_run；evidence=null |
| IM01-TRACE-T15-N | tl_propagation；IM06,IM12,IM13,IM19 | 本域verified不得冒充权限恢复或全球清理完成 | not_run；evidence=null |
| IM01-TRACE-T16-P | tl_erasure_target；IM12,IM19 | 合成授权目标逐项执行并验证 | not_run；evidence=null |
| IM01-TRACE-T16-N | tl_erasure_target；IM12,IM19 | remote未知、部分清理或无破坏许可不能算已删 | not_run；evidence=null |
| IM01-TRACE-T17-P | tl_input_dependency；IM11,IM12,IM19 | 逐字段登记来源/用途/接收者及保留状态 | not_run；evidence=null |
| IM01-TRACE-T17-N | tl_input_dependency；IM11,IM12,IM19 | 不能仅检查selected_memories；晚到正文不可重存秘密 | not_run；evidence=null |
| IM01-TRACE-T18-P | tl_effect；IM14,IM19 | 合格测量可保留零/负gain并关联原报告 | not_run；evidence=null |
| IM01-TRACE-T18-N | tl_effect；IM14,IM19 | 未测/失效/未知不填零，分类gain不等于内容忠实 | not_run；evidence=null |
| IM01-TRACE-T19-P | tl_recall_item；IM10,IM11,IM19 | 逻辑query按新统一结果计算一次命中 | not_run；evidence=null |
| IM01-TRACE-T19-N | tl_recall_item；IM10,IM11,IM19 | 表示ID不得硬塞旧memory_revision外键或双计命中 | not_run；evidence=null |
| IM01-TRACE-O01-P | admit_observation；IM07,IM19 | 受许可/材料/预算约束创建或复用原work | not_run；evidence=null |
| IM01-TRACE-O01-N | admit_observation；IM07,IM19 | 停止/伪造源/同键异义不得派发或重做工具 | not_run；evidence=null |
| IM01-TRACE-O02-P | assess_observation；IM07,IM19 | 原文、解释、核验及未知分开且模型在主事务外 | not_run；evidence=null |
| IM01-TRACE-O02-N | assess_observation；IM07,IM19 | 来源报告10不能直接成为现实确定10，旧认识不可补成原观察 | not_run；evidence=null |
| IM01-TRACE-O03-P | decide_proposal；IM08,IM19 | 限定范围决定和新版本/义务C1同事务提交 | not_run；evidence=null |
| IM01-TRACE-O03-N | decide_proposal；IM08,IM19 | 无政策/无复核/无支持不得accept，候选不产生当前表示义务 | not_run；evidence=null |
| IM01-TRACE-O04-P | claim_representation；IM09,IM19 | 新有效租约及generation对应原工作/版本 | not_run；evidence=null |
| IM01-TRACE-O04-N | claim_representation；IM09,IM19 | 旧代次、已超deadline或预算耗尽不能续租 | not_run；evidence=null |
| IM01-TRACE-O05-P | publish_representation；IM09,IM19 | 正文/映射/确认/组ready一起提交 | not_run；evidence=null |
| IM01-TRACE-O05-N | publish_representation；IM09,IM19 | 晚到旧工作、缺blob或半组不能发布当前视图 | not_run；evidence=null |
| IM01-TRACE-O06-P | recall；IM10,IM19 | 合法正文与来源/范围/未知整条返回 | not_run；evidence=null |
| IM01-TRACE-O06-N | recall；IM10,IM19 | C2未就绪不能临时直读，audit入口不可生成调用或修复索引 | not_run；evidence=null |
| IM01-TRACE-O07-P | apply_invalidation；IM06,IM19 | 合法变化按当前epoch串行提交屏障 | not_run；evidence=null |
| IM01-TRACE-O07-N | apply_invalidation；IM06,IM19 | 预留不冒充真实派发；旧许可不越过屏障 | not_run；evidence=null |
| IM01-TRACE-O08-P | acknowledge_propagation；IM12,IM19 | 实际动作/覆盖/验证支撑本域完成 | not_run；evidence=null |
| IM01-TRACE-O08-N | acknowledge_propagation；IM12,IM19 | 未决/部分/远端unknown不得报全部verified | not_run；evidence=null |
| IM01-TRACE-O09-P | resume_work；IM13,IM19 | 先核对持久结果，续未完成阶段和原预算 | not_run；evidence=null |
| IM01-TRACE-O09-N | resume_work；IM13,IM19 | failed工作不自动领取，不换ID或重新执行外部动作猜提交 | not_run；evidence=null |
| IM01-TRACE-O10-P | record_effect；IM14,IM19 | 效果报告经既有独立测量入口校验 | not_run；evidence=null |
| IM01-TRACE-O10-N | record_effect；IM14,IM19 | gain/模型信心不能升级内容资格或直接改实际选择 | not_run；evidence=null |
| IM01-TRACE-S01-P | Work；IM05,IM07,IM08,IM09,IM13,IM19 | 纯评估和候选仅在预指定合法终点completed，接受且需表示必须C2 | not_run；evidence=null |
| IM01-TRACE-S01-N | Work；IM05,IM07,IM08,IM09,IM13,IM19 | 已完成阶段不盲重放，等待/恢复不新增机会或预算 | not_run；evidence=null |
| IM01-TRACE-S02-P | Handoff；IM09,IM13,IM19 | 仅原义务和有效generation发布或恢复 | not_run；evidence=null |
| IM01-TRACE-S02-N | Handoff；IM09,IM13,IM19 | 过期/停止/撤权/耗尽不自动续期 | not_run；evidence=null |
| IM01-TRACE-S03-P | Decision；IM08,IM19 | 解除条件后合法新round，旧决定保留 | not_run；evidence=null |
| IM01-TRACE-S03-N | Decision；IM08,IM19 | 旧round不得回写accepted，部分处理不冒充整体接纳 | not_run；evidence=null |
| IM01-TRACE-S04-P | Content；IM08,IM12,IM19 | 新修订保留更正链和当前源/用途屏障 | not_run；evidence=null |
| IM01-TRACE-S04-N | Content；IM08,IM12,IM19 | 不按最大revision选真，恢复不复活已删除正文 | not_run；evidence=null |
| IM01-TRACE-S05-P | Representation；IM09,IM10,IM12,IM19 | 新表示修订/系列/head一致且当前资格可重查 | not_run；evidence=null |
| IM01-TRACE-S05-N | Representation；IM09,IM10,IM12,IM19 | 已发布不等于永远可用，旧租约不得改新映射 | not_run；evidence=null |
| IM01-TRACE-S06-P | Group；IM08,IM09,IM12,IM19 | C1/C2相应必需成员同事务完成 | not_run；evidence=null |
| IM01-TRACE-S06-N | Group；IM08,IM09,IM12,IM19 | 任一缺失/obsolete不得伪装ready | not_run；evidence=null |
| IM01-TRACE-S07-P | Barrier；IM06,IM12,IM13,IM19 | 明确原因解除后仅resolve对应屏障 | not_run；evidence=null |
| IM01-TRACE-S07-N | Barrier；IM06,IM12,IM13,IM19 | 权限重授不得清其他原因或自动恢复执行 | not_run；evidence=null |
| IM01-TRACE-S08-P | Propagation；IM12,IM13,IM19 | 按原计划/当前代次/预算验证全部声明目标 | not_run；evidence=null |
| IM01-TRACE-S08-N | Propagation；IM12,IM13,IM19 | verified不得消除独立屏障，失败不得刷新身份续命 | not_run；evidence=null |
| IM01-TRACE-S09-P | Erasure；IM12,IM13,IM19 | 授权合成受管范围全部验证后才范围内verified | not_run；evidence=null |
| IM01-TRACE-S09-N | Erasure；IM12,IM13,IM19 | 缺覆盖/外部unknown不可说全球删除，不用恢复旧备份复活内容 | not_run；evidence=null |

## 6 关键复用边界及一致性判断

- CognitiveExperience现有shadow版本仍由M03唯一保存，不能把数值投影改名后当自然语言世界事实，也不能绕过接纳政策。
- ExperienceMeasurement已有封存分类测量；旧分类gain不能作为本链内容忠实、迁移或旧能力保持通过证据。
- 原文字记忆路径和旧修订保留。新增表示系列、修订注册与tl_recall_item须正确映射；不能把表示UUID塞进旧memory_revision外键。
- 当前Queue可以领取queued/租约过期工作；failed TL工作须按原业务身份和剩余预算恢复，不能假定自动续跑。
- 已有privacy和G1门禁是复用基础，不是所有新输入/迟到响应/依赖闭包/受管副本都已覆盖的证明。
- 76个正反场景仅追溯义务。IM01只应验收规范绑定和隔离夹具，不提前完成IM02—IM24或宣布TL-EVAL正式评测通过。

当前未发现阻止IM01继续的冻结设计冲突。后续实施如发现新矛盾，保留失败/差异，交主流程明确修订；本记录不修改设计以适配旧代码。

## 7 机器核对约定

配套文件为 `tool-learning-im01-traceability.json`：`table_mappings`精确覆盖19表，`operation_mappings`精确覆盖10操作，`state_mappings`精确覆盖9轴；每项都有模块路径、冻结依据、实施任务与正反验收ID。`acceptance_catalog`定义76个不重复ID，全部为not_run且evidence=null。`source_verification`逐文件保存预期/实际摘要；摘要仅用于读取时点核对，不是运行或安全证明。父流程可据此静态核对覆盖及依赖，不能直接把所有未来场景标通过。
