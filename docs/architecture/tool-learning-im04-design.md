# IM04：受所有者约束的存储适配层

版本 V0.1；状态：详细设计／隔离实现。依据冻结 TL-LOOP-0.1 契约及存储附录，不部署、不修改数据库版本。

## 责任边界

新增 `ToolLearningStore` 包装已有、由可信组合根提供的 Store 连接；不打开任意实例目录，不创建/迁移数据库，不导入 application。构造时核对19表、实例身份、外键开启和受支持的资源能力。当前仅在新建锁定schema3合成夹具加载IM03资源后验证，不宣称运行时已支持schema4。

存储层没有 accept/publish/解屏障等批准方法。写入必须通过可信服务入口，并由组合根注入 `StorageAuthority` 实现：服务身份不来自请求中的 module 字符串；验证器接收深复制完整Envelope，在事务开始和提交前核验认证入口、Principal、用途、活动、权限/屏障/停止/预算等当前业务条件，返回受限的 `StorageGrant`（所有者与具体可写表）。默认验证器拒绝全部操作。测试替身只证明机械约束，不证明M12已经实现；没有真实授权核验服务时生产接线保持拒绝。

Python对象边界不是恶意同进程代码的安全沙箱。持有底层连接的可信代码本身可以绕过适配器；后续服务只能获得所需端口，不把数据库句柄或测试授权器暴露给模型、面板或请求数据。构造函数注入是可信组合边界，调用者不得提交布尔 `authorized` 或自报角色来取得写权。

## 接口与事务

`execute(entry, operation, envelope, callback)` 严格校验冻结请求，按冻结§4对逻辑字段(contract/schema/instance/principal/work_ref/expected/payload，处理方法保留在payload中)生成canonical fingerprint，排除command_id/control/budget以及查找键自身，实例/Principal实际Ref核对后，在一个BEGIN IMMEDIATE事务内写command pending、调用受限 `OwnedTransaction`、保存不可变结果工件和command committed。幂等键按(instance,operation,key)；重放必须原fingerprint一致且重新通过当前读取授权，只返回原结果、不重跑业务。callback禁止嵌套命令和事务外使用。失败回滚业务行、登记、命令和映射；磁盘预置但未引用blob是明确孤立制品，不能自动接纳。

`OwnedTransaction.insert` 只可写授权且属于该业务所有者的表；字段白名单来自固定19表声明，不允许插入registry或已有任意业务表。自动注册依赖IM03触发器。`cas_update` 需要非bool非负expected revision，WHERE同时约束实例、ID和row_revision，更新恰好一行且版本加一；拒绝调用者改身份、revision或注入SQL标识符。不可变表不能借CAS改写。`tl_representation`、`tl_effect`没有冻结CAS列，IM04不提供通用无CAS更新；后续拥有者需具名操作和额外版本门禁。

`lookup_command(entry, operation, envelope)` 使用完整请求上下文核验当前读取权限，只读核对原键、原fingerprint、状态和完整结果工件。新command_id或当前control/budget快照不改变逻辑指纹，但每次重放/核对均把当前完整请求传入可信权限服务复验。pending不是可自动重试的证明；COMMIT_UNKNOWN需要重新打开既有可信连接后只读核对，不重新执行callback。SQLite提交异常且无法确定是否持久化时返回专用CommitUnknown，不能伪报失败后盲重试。

## 引用与制品

`validate_ref` 检查命名结构、实例、object_registry真实kind；known修订必须存在于object_revision_registry并核对版本对象归属。支持TL稳定content/series与具体修订ID两种明确关系；其他类型有版本登记才能作为此端口的已核验版本，未登记不能凭编号补造。跨实例外部来源只允许由后续授权服务保存在类型化工件内，不可通过本地FK引用端口伪造。

`read_artifact` 读取已登记工件的实际字节，拒绝缺失、路径穿越、blob目录或末级符号链接、大小/摘要不一致；JSON使用IM02严格解析并按显式命名类型验证。缺失不是空串、空对象或unknown成功。`put_artifact` 在事务内先验证命名结构，写入canonical字节，再回读校验。所有写入行的工件FK均需实际字节验证；具有冻结载荷类型的列必须进行相应类型校验，字段与载荷ID/归属/摘要等数据库可见映射一致性在存储入口核对。科学事实、支持强度、真实许可及外部字节可用性仍不由结构校验宣称成立。

## 隔离验收

新schema3夹具+IM03资源，WAKE_DISABLED且user_stopped全程保持：默认拒绝、入口伪装/越权表拒绝、跨实例/kind/修订归属拒绝、blob缺失/损坏/符号链接/重复键拒绝、原请求幂等一致与异义拒绝、CAS过期、回调及提交失败无半条命令/头映射、未知提交只读核对。无真实模型/网络/正式实例操作。

连接保持既有Store的同线程约束；独立并发服务需要各自连接，由SQLite写事务协调。适配器只回滚本次已成功BEGIN的事务，不接管外部事务。

## 隔离实现报告与后续义务

已实现 `digital_life/infrastructure/persistence/tool_learning_store.py` 和 `tests/test_tool_learning_store.py`。31项定向隔离测试通过，覆盖原子提交/回滚、提交确认丢失后只读核对、默认授权拒绝、原指纹保持、变化快照重放原结果、完整请求授权、历史结果当前可见性投影、实例/kind/版本归属、原始字节缺失/损坏/符号链接/重复键、CAS、所有者字段/表边界、完整Product/Representation映射、reuse旧交接义务、外部来源类型化保留和指标解析关口。命令：`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_tool_learning_store -q`。

可信 `StorageAuthority.verify` 接收深复制完整Envelope，不能修改原请求；`project_response` 接收待返回原Response及result_refs，默认拒绝，真实服务可保守阻断无法全量读取的结果。重放返回第一次命令ID，新的command_id、control和budget快照不产生新写入，也不绕过当前授权/预算核对。

提交前集中核对新增或CAS更新行的完整载荷和实际注册引用：Product生产者/工作/类型/处理指纹；Decision主体/工作/提案/策略/修订及交接；Representation系列/内容版本/决定/正文/摘要/组；RecallItem表示及其内容/系列版本；EffectAssessment与所指Product.body完全一致。未知revision Slot中的basis_refs也递归核对。reuse仅引用原版本原义务，不强迫归属新的reuse决定，不新建交接。已知本地EvidenceRef材料摘要与media_type必须和实读工件一致；视图和视图摘要仍保持独立Slot，不因缺少摘要改写unknown。

SQL NULL只表示没有绑定本地技术ID。完整payload中的合法unknown/not_collected等非known Slot原样保留，尤其未测量报告；known Ref不能丢弃为NULL。外部来源由 `verify_external_ref` 可信解析端口核验，默认拒绝；通过后保留为工件内类型化来源，不伪造本实例registry/FK，不能用外部Ref绑定本地权威字段。

冻结未规定 `tl_effect.metric_contract` TEXT如何对应 `EffectAssessment.metric_definition:Ref`，因此没有擅自使用Ref.id、name或formula_version相等规则。新增可信 `verify_metric_contract` 解析/版本核验关口，默认拒绝；**IM14必须实现该具体映射和真实指标解析，接线前effect写入阻断**。测试替身的解析成功不代表真实指标契约已经绑定。真实M12授权、屏障、受管清除、科学证据与指标有效性仍待后续实现；本报告只确认存储机械边界。

没有修改Store、Runtime、DDL、正式实例或版本；没有执行模型/工具/网络或唤醒操作。失败事务可能留下未引用预置blob，后续只能显式受管回收，不自动接纳。当前连接遵守既有同线程约束。
