# IM12：分域传播、受管清理与恢复排除

版本：V0.1；日期：2026-11-10；状态：已实现／待冻结源统一隔离验收。

## 目标及不变量

实现冻结 F2 `acknowledge_propagation` 与 F3 逐目标清理。F1 已提交的原因屏障始终有效；完成传播或清理不等于恢复权限、不解决科学争议，也不解除用户停止或禁止唤醒。仅管理范围明确、当前 M12 授权且停止、无运行进程的实例可执行物理清理。远端、已交付内容与世界效果分别记录 unknown／不可逆，不冒称撤回。

九域 M01、M03、M04、M12、M13、M14、M17、coordinator、evaluator 独立确认。每域真实 owner 核当前请求、实际动作和验证事实；未配置 owner 默认拒绝。一个域的确认不能代表其余域。各原因、epoch、generation 的记录不得合并覆盖。

## 接口与责任

`ToolLearningPropagation.acknowledge(entry, envelope)` 使用冻结完整请求与响应；校验当前控制版本、barrier、明确 propagation generation、CAS row_revision、原账户、有限 deadline 和当前 owner 权限。读取不可变 F1 minimum plan，并校验 `TL-PROPAGATION-VERIFICATION-1` 中实际目标、边界、水位、逐目标动作与证据。pending→processing→verified 及命令结果同事务；覆盖未知、缺边、环、扫描超限、缺 adapter 保留 blocked／partial。可信 owner 端口必须执行实际域动作及重新验证，调用者 bool 或自行填写 verified 均非凭据。

`renew_generation` 是独立的 M12 当前维护授权操作：明确旧义务、新 maintenance activity/account、原始固定 caps/deadline 与本域 supersedes。保留旧义务，不能改旧行 deadline/account，不能借重试键重领资源；一个域新代不替代其余域。维护活动没有模型或工具机会，不复活普通活动耗尽账本。

`ManagedErasure.prepare/run/status/completion` 先持久化真实 deletion_requests、deletion_effects、tl_erasure_target 与授权计划，再执行非原子的数据库／文件动作；每目标拥有持久状态、恢复定位和实际读回验证。plan 绑定实例、barrier、当前授权、固定版本、允许位置、允许保留字段、路径身份、资源、全部目标与范围水位。失败或提交结果未知不盲重删；重放先核实际状态再继续。

`RestoreExclusions` 将不可撤回排除凭据保存在运行镜像外的受信控制目录；原子创建、校验内容身份、版本及 hash，并在真实清理之前持久化。恢复入口必须查询当前凭据，缺失／无法认证／过旧均拒绝。IM13／IM16 接入恢复；本项提供实际读写及验证端口，不宣称现有恢复已接线。

## 字段和存储映射

保留 `tl_propagation.targets_artifact_id` 中不可变 F1 最低目标集合及 scan_pending。完整实际目标集合写 verification artifact，包括 contract、barrier、generation、domain、source_epoch、minimum_plan、targets、actions、per_target、coverage、boundary、watermark、unresolved；仅换工件名字不能证明扫描已完成。

`tl_propagation.coverage_artifact_id/state/verification_artifact_id/row_revision` 经 CAS 更新。`tl_erasure_target` 固定 barrier/plan/target/location；状态 pending，实际动作后读回验证再 verified，或 blocked/unknown；中途未签收仍 pending，恢复先检查真实状态。verification 记录实际检查。数据库 purge 必须具备现有 deletion_effects + cleaning plan + erase barrier 触发器要求。保留必要不透明 object_registry 身份以维持授权链，不伪造修订。

维护 journal 使用真实 deletion_requests.subject_scope 与明确版本化维护合同；不添加表／DDL。任何新维护账户仅由具名 M12 授权入口创建，初始 caps 一次固定。维护 tokens/tool caps 为零；冻结 Budget.max_attempts 最小为 1，故真实物理账户与维护 caps 均为有限 attempts=1，而本地维护实际 attempts=0。额度不是操作授权：具名维护合同、SDK、普通 Engine 入口均拒绝推理／工具；scan/items/bytes/elapsed 实测累计，未知不释放。停止下保护性操作与普通执行资格严格分离。

## 受管目标与关系

按实际固定版本追踪 support/read/delete，不能把 delete-only 当内容支持。闭包必须涵盖：原件与 view；四 Product 及副本；Decision、C1 内容与修订；C2 representation/head、stage、build-only 正文；普通 context、packet、manifest、proof、provider wire/result、解释；recall item/result event；computed bundle；观察 snapshot event/payload；行为、成长、习惯的派生；日志、索引、缓存；明确登记的备份与外部恢复排除。目标必须对应真实 object/artifact 和 owner；动态未知 owner、legacy 缺边或范围不明只能 partial。

发现的传播目标是保守超集，不等于每个都已语义失效。M03 不重写历史接纳、不自动选世界真值；M04 撤下当前表示、处理组与未完成 lease；M14 保留消耗／效果事实。已交付与在途未知结果仍是历史事实。late output 依旧由 F1 actual-use 门阻断，不因清理使其可再发布。

## 物理安全、并发和恢复

清理只允许明确 managed-local scope。路径必须是计划中根内普通文件，拒绝 symlink、路径逃逸、替换 inode、不明归属。blob 删除前在同根 gate 与数据库排他写边界内检查该 blob 根所有 instance 的 storage_ref；任何引用／查询错误／提交未知都保留。不得以本实例无引用判断共享文件可删。备份只处理登记且身份匹配的快照，不扫描未登记目录。

数据库更新与 blob unlink 无共同原子事务，因此 journal 先行，读取验证在后。数据库残存不可变敏感 hash/Scope 若授权不允许保留，必须报告 blocked／partial；不得删除核心屏障来伪装全删。允许最小控制元数据的 managed-local 范围可单独验证完成；更严格不允许现有不可变元数据的范围明确不能完成。文件已无引用且确实移除、索引查询无残留、缓存实际失效、登记备份已验证后，才可对各面 verified。

## 隔离验收

只创建新的 synthetic fixture；具名真实机械测试端口并非生产权限。反例包括：默认拒绝、跨域／错 epoch／旧 CAS、同键异义、分原因／分代、空计划伪 complete、缺边／环／扫描耗尽、各写点回滚与中途恢复、late 输出、旧 lease、恢复排除缺失及篡改、权限恢复不复活、共享 blob／不同 instance／inode 置换／symlink／未知提交、未知远端／未授权物理面 not_run、允许最小元数据完成与禁止元数据 blocked、stop/lock 下保护性维护且锁不变、维护资源耗尽／未知不重新领额。

专项：`tests/test_tool_learning_propagation.py`；稳定后一次统一 IM12 门禁。IM13 恢复与 IM16 发布回退消费排除凭据，IM19 最终全量再验证。本项不调用真实模型，不触碰正式实例，不提前实现恢复编排。


## 实际认证 SDK 和保护性 F1

实现位于 `tool_learning_maintenance.py`。`ControllerMaintenanceAuthority.configure` 先验证现有真实 Bearer、实例 controller 和当前 policy owner，显式配置有限维护 caps，保留其余 policy scope，并在当前 control.sqlite 的 control_commands 注册外部排除根的 canonical path/device/inode。这是明确的控制面配置，不是 token 自动授予数据权限。

`protective_request → authorize_invalidation → apply_protective` 是实际 F1 SDK。当前支持来源为真实原 work 的本人／本实例 Signal：SourceWork.source_artifact 与原活动 trigger 的实际 artifact 必须一致；未知源种类或外部作者拒绝。当前 source-owner、erase_scope policy owner、policy/configuration/runtime/control 版本、原 work、source revision/epoch、请求及幂等身份全部固定。空 subjects/purposes 的含义在真实授权记录明确为“仅此已授权来源和 affected_scope 内所有主体／用途”，不扩展到无关来源。

保护性 F1 使用当前 M12 授权的新真实维护活动／账户和 `TL-PROTECTIVE-F1-BUDGET-1`，保留原 work_ref。旧来源 work 已过期／halted 不阻止有效保护操作；其账本、caps、deadline 完全不抬限。IM06 新 `verify_protective_budget` 默认拒绝；只有真实 M12 proof 可走独立账户分支，原账户 F1 路径不变。新账户零 token/tool、有限 attempt1，没有普通执行机会。请求／事件／账户／caps 映射核验，entered/unknown 持久；原 change ID 重试复用同一账户／deadline，未知结果不能重新领取。绝不伪造 retrieval_run 或调用普通 IM05 reserve 绕过 stop。

独立账户的活动保留来源 release 谱系；SDK 是控制面代码，不冒称新的正式部署／生命进程。没有自动创建新模型任务、解除停止或禁止唤醒。

## 当前维护授权、owner 行为和 F2

`authorize` 只认可实际已提交的真实 SDK F1：preparation／controller authorization／tl_command／tl_change／barrier 的完整映射。不能用当前 grant 追认 Mechanical 或缺谱系的旧变化。真实 grant 固定完整 plan 指纹、真实来源 owner、原 work、当前 policy/control、deadline、允许 domain 和逐条动作；私有随机 channel handle 在当前进程中绑定实际 domain，JSON module／grant Ref／猜测字符串都不授予身份。授权前实际有限 inventory 读取的测量作为 bootstrap_usage 记入原维护 caps；重放复用该账户与原始测量。

`prepare_acknowledgement` 在同一维护账本里产出真实 domain-hold event 和完整 F2 Envelope；prepare 不是实际签收。F2 在最终事务重新核权限／source／control，使用 LocalOwnerActions 执行，读回实际结果再 CAS。M12 本地资格 hold 可由实际 barrier/epoch/current authority 核验；M04 有实际 representation/head/group/handoff/input 撤下适配。已 published 的交付保留历史事实。M03/M14 等复杂语义复核没有配置可信 owner 时明确拒绝／保留 pending，绝不九域一键 pass，不造科学赢家或正收益。

完整 `TL-PROPAGATION-VERIFICATION-1` 字段：contract、barrier Ref、generation、domain、source_epoch、minimum_plan Ref、targets Ref[]、actions Ref[]、coverage、boundary、watermark、unresolved、per_target。每个 per_target 严格为 target/action/verification 三个真实 Ref，actual owner 必须核事实；最低 F1 targets 不得遗漏。完成签收与命令原子；F2 verified 永不解除 barrier。

## 实际受管适配、账本和物理范围

`ManagedInventory` 以精确版本 TL 关系、真实 artifact FK 和命令／副本反向 FK 枚举；固定查询／节点上限，缺边／环／legacy owner 缺口是 partial/unknown，而非图遍历即全世界 complete。源码中的 PURGE_KINDS 是显式业务表白名单；未知表、未知操作、最小权限／排除根控制记录拒绝清除。数据库 purge 通过真实 cleaning plan/effect/erasure_target 触发器，再读回不存在。

artifact tombstone 前检查全部真实 artifact FK 消费者：闭包外独立来源共享同一 artifact ID 时 blocked，不能先破坏 B 再发现物理 blob 仍被引用。物理 blob unlink 检查同根全部 instance 的 storage_ref，在同一 gate/SQLite 写边界内核真实 inode/hash、删除并验证；共享引用、symlink、换 inode、错误或未知结果不盲删。

数据库当前受管范围是 SQLite 主文件及登记 WAL/journal：secure_delete、checkpoint、VACUUM、freelist=0、完整性/FK、真实主文件读取及空 journal 验证均在原维护资源内。记录持久 compaction 义务，失败不 verified；恢复先核原事实。不是 SSD、OS 快照或已删除 inode 取证擦除。FTS/独立索引必须自己的 adapter，不能 VACUUM 代替语义重建。

已知 memory-quality 独立索引／缓存文件按固定名称、真实 hash/inode 删除并核缺失。备份支持真实 control.backup_manifests 的 canonical managed_root 单文件，以及既有 backup.created + 完整 manifest 目录；仅登记清单的 runtime.sqlite、blob、manifest 逐文件验证／删除。未知文件、逃逸路径、symlink、manifest 变更拒绝；不使用 rmtree，不触未登记备份。动态未知缓存／索引 owner 明确 not_run。

维护 plan 明确 retained_metadata：opaque_ids、control_scope、source_fingerprints、plan_expected_hashes、resource_facts、action_facts；实际 M12 授权须确认。泛 allow_control_metadata 标志不足，严格禁止不可变指纹／Scope 的范围 blocked。最小权限与控制证据保留不是默认“hash 无害”。

`status.state` 是上次维护验证事实，不是新权限或新的全域资格。`completion` 另核固定九域、明确 supersedes 覆盖链和物理计划；单域完成／空 target／物理计划 verified 不等于 F3 完成。当前 rootSDK正例只有 M12 真实 owner 签收时，F3 聚合仍 pending 其余八域。

## 外部排除根与真实发送边界

外部目录独占写 record、fsync，并原子发布 generation/index；缺 record／anchor／未知条目／上限均拒绝。真实 owner 还把 root 注册身份和 index generation/hash/entries append 到当前 control_commands。新空目录、旧目录／旧 anchor 不能因同 Bearer 自动成为当前历史。此控制记录属于当前协调器控制面；IM13/IM16 必须从当前可信 Control 查询根/head，不能从待恢复旧镜像或其 plan 列表定位。现端口 `restore_constraints` 返回 restore_authorized=false；实际恢复消费仍未接线。

HTTP material route 在同 root gate 覆盖当前读取、编码、实际 headers/wfile.write。F1 先到不发送源正文；发送先到则 F1 等实际发送退出，已在途不可撤回。35s 总响应许可加实际 socket 有限发送 timeout，slow-client 释放 gate；静态资产、设备授权等待、保护性 stop 排除。所有新网络测试仅隔离 loopback，无正式服务或外部模型网络。

## 原计划延续边界

`tl_erasure_target` 唯一键为 barrier/target/location 且 plan_ref 不可变。不同 plan 不能重建或重绑已存在 target，返回明确 Conflict。原 plan 的真实已知重试按原账户／caps／deadline，entered/unknown 不自动释放。IM13 continuation 接口必须绑定原 plan、固定 target 集合和当前真实 M12 新授权，保留 target.plan_ref 与旧预算历史；本项未实现“耗尽之后自动续费／恢复”，不宣称跨 plan 是幂等重试。


### F1 与外部排除 head 之间的恢复围栏

真实 SDK 在 F1 实际事务前，先在当前 control_commands 持久 `maintenance.protective_change_pending`，按原 change ID 幂等，保存 opaque source/version、结果 epoch floor、scope digest 和原 work/command 身份。F1 成功而 F3 尚未写新外部记录时，即使目录已有旧 head，当前 restore 读取仍因这条未覆盖 directive 拒绝。只有实际排除 record、index 和当前 control head 成功发布后，才标记对应 directive 已覆盖；constraints 同时返回当前控制面排除事实。失败／未知不自动清除围栏，也不假称已有外部已删事实；IM13 负责当前 M12 证明下的对账／延续。

保守 inventory 是“需要检查的面”，不能直接变成删除权限。真实 SDK 另按固定来源版本闭包和真实 work/frame/outbound artifact 核授权范围；独立 B 仅因同 artifact/hash 被反向扫描发现，不授予对 B 的删除权。已知位置的 expected 字段闭合校验 hash、device/inode 整数（拒绝 bool）、路径和登记清单；未知 adapter 仍 not_run。

物理维护还拒绝有未对账 process_runs.exited_at=NULL 的实例，即使 active_process_run_id 已空；不探测后杀别的 PID。真实 F1 保护性控制可用独立资源，不依赖该物理清理条件；不会因旧来源 work 预算／deadline 耗尽而复活普通执行机会。


### Feature-off 的最小安全兼容边界

`legacy_protection_present` 仅查真实保护元数据：active barrier、不可复活的 erase 历史／target、当前可信控制面保护／排除记录。有这些状态时，关闭 strict flag 不能重新启用未装配的旧 body 读取／思考／执行。Engine.prepare/think/process_one 的旧分支在旧 tick 或模型前拒绝，Executor 实际旧 dispatch、Memory.retrieve、MemoryQuality 原文 span/status、原管理 log/export、旧 backup/Privacy.erase 和 growth CLI 旧材料路径均受限。静态资产、明确 stop、当前 M12 SDK、独立来源的已认证 qualified readonly audit不因这个拒绝获得新权限；不强开 strict。

没有 TL 表／没有新保护状态的 schema3 保留原行为，实际旧 memory retrieval 正例覆盖。此为已存在保护状态的最小拒绝，不是旧接口完整 bridge，IM15 仍须全兼容矩阵。
