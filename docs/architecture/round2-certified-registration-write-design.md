# PF04/05：登记写入后保留未变事实的最窄设计（待审查）

状态：本文件保留早期设计草案；其受管监视前提后来已经实现并验证，当前具体契约及结果见 [受管输入接入设计](round2-certified-input-integration-design.md)。下文“当前连接不足”等描述对应草案当时的裸连接，不代表后续接入状态。2026-11-11。范围仅 `register_input`，不改变业务检查顺序、事务划分、预算份额或总上限。

## 1. 问题与结论

`assemble` 按字段逐项执行 `register_dependency` 和 `register_input`。两者均有独立事务，并在写前、写后重做资格检查。现有 `PhaseReadSet.read` 遇到本连接 `total_changes` 变化即清除全部固定事实；受信事务结束又清除一次。因而一个没有改变源图的输入登记，也使下一次上溯重新读取原件位置、版本映射和依赖边。纯 JSON 缓存还在，不能消除这些主库读取。此行为与共享样例、连续第二轮在原 assembly 扫描份额耗尽的栈一致；这不是许可判断可以省略的理由。

最窄优化是：只证明一个确切 `tl_input_dependency` INSERT 的保守写表集合，保留读表与该集合不相交的固定事实。所有许可、源资格、版本 owner、主体、用途、接收者、epoch、barrier、控制面判断照原顺序重新执行。只要不能证明写集合完整，就退回现有全部失效。

**当前连接机制尚不足以发放这个证明。** 裸 `sqlite3.Connection`、方法名、`total_changes` 差值、SQL 文本白名单，均不能单独证明触发器和重入写入的范围。不得先加“这是内部写”开关再补保护。

## 2. SQLite 机制约束与可实施前提

SQLite authorizer 在语句准备时调用，不是实际逐行写日志；已准备语句再次执行不一定调用它。只有一个 authorizer，替换会覆盖旧 hook，Python 没有读取原 hook 的接口。回调不能再修改本连接。因此不能临时装一个 authorizer 并将其回调集合冒称实际写集合。[SQLite 官方说明](https://www.sqlite.org/c3ref/set_authorizer.html)

trace 能表明执行过哪些语句，但展开参数可能敏感，触发器 trace 也可能重复外层语句。不能解析 trace 猜测实际目标表，也不能保存完整展开值作为普通日志。

首版需要 Store 创建连接时拥有一个专用执行监视边界，覆盖 connection/cursor 的 execute、executemany、executescript、游标迭代期间重入以及 prepare/reprepare。它只为确切固定 INSERT 建立**保守可能写表集合**；这比逐行日志弱，但对“不相交读表”保留足够。

建议实现条件如下，缺任一项则禁用证书：

1. 连接从创建时由 Store 管理监视器；已有或后来外部替换的 authorizer/trace、替换连接、未受管游标均禁用。不能悄悄覆盖第三方 hook。当前测试/工具自行替换连接时默认禁用，另用受管 factory 才启用。
2. 证书窗口只包一次固定 INSERT，不跨资格 callback。窗口前完整新鲜度检查；无证书的写入仍原全部失效。
3. 必须确保窗口语句被重新准备，不能靠“本机 SQLite 看起来会过期缓存”作为永久契约。可为受管连接关闭 SQLite statement cache，或使用可靠独立准备接口；两者都有性能/兼容影响，需要先单独测量。若选择全连接 `cached_statements=0`，需先证明不会造成更大回归；本设计不直接批准该全局改动。
4. authorizer 只积累 table/op/database/trigger-origin 的保守足迹，不做 SQL/DB 操作；精确触发器定义及 schema 版本必须匹配受审目录。所有 UPDATE/DELETE/REPLACE、DDL、ATTACH、未知 PRAGMA、未知触发器/虚表、额外 SQL、用户 SQL 函数或重入 callback 均使证书失效。普通 SQLite 内置函数按已核验固定语句依赖处理；同名 Python UDF 不能按函数名字认证。
5. 原固定 INSERT 的参数、显式新 ID、实例与执行状态由受管调用记录。authorizer 证明允许的写表上界；正常返回且已核验 SQL/trigger 证明语义。不得用 `total_changes==2` 代替完整监视。
6. 未知/外部 callback 入口先丢弃证书并原全部失效，返回后做真实新鲜度检查；不能把“返回 None”当只读证明。固定 Local owner 仍真实执行；它的检查只在独立受监视只读段内成立，任何写入即原失效。不跨 callback 持有尚未确认的写证明。

受管执行监视属于必要基础设施而非小型缓存补丁。若不能完整覆盖上述入口，结论是本轮不能安全认证该优化；不得以部分 trace + changes 差值替代。

## 3. 首版确切写集合

唯一候选是 `LocalEligibility.register_input` 的新行分支，位于现有 begin 检查与 commit 检查之间，保留所有原步骤。

- 原 INSERT：`tl_input_dependency` 完整固定字段（包括 request/source/revision/path/purpose/recipient/digest/retention/row_revision）。
- 原 `tl_input_dependency_register` AFTER INSERT：向 `object_registry` 插入相同 id/instance、kind=`tl_input_dependency`。
- 约束触发器允许读取/拒绝，不允许增加其它写表；完整递归 trigger 足迹必须由监视器核对。
- 保守写表集合：`{main.tl_input_dependency, main.object_registry}`。未知新 trigger 即禁用，不能仅核对已知 trigger 仍存在。
- 已存在旧行分支不写；不需伪造 INSERT 证书，仍执行全部 commit 检查。
- `register_dependency` 不在首版范围。它改变 `tl_dependency` 消费者边，可能新建 artifacts 与 registry；不能说旧图天然不变。它照原全失效。

不做按新增 ID 推断旧正查询不变的行级优化。即使 INSERT 只加一个 registry ID，首版仍丢弃全部 source_kind 与相关准备证明，避免负查询/复用 ID/触发器间接影响的复杂性。

## 4. 保留/失效矩阵

| 共享材料 | 查询读取表 | register_input 受证写后的处理 |
|---|---|---|
| artifact_location | artifacts | 保留；完整 blob 身份/文件持续检查仍执行 |
| revision_mapping_by_object/by_id、revision_owner、selected_revision、snapshot_bridge、registered_revision_presence | object_revision_registry | 保留，包括 absence；前提完整写表证明 |
| consumer_dependencies（含 complete/prefix） | tl_dependency | 保留；顺序、LIMIT、逐消费者逻辑预算原样 |
| source_epoch | tl_source_epoch | 保留；每消费者实际 epoch 判定仍执行 |
| source_barriers | tl_barrier + tl_change | 保留事实；barrier 判定不缓存 |
| control_policy_epochs/latest_configuration/active_barrier | policy_epochs/configuration_versions/tl_barrier | 保留固定主库事实；Control DB/process/pid/stop、实际 PRAGMA user_version 不共享 |
| source_kind | object_registry | 全部失效，不做“不同新 ID 所以安全”推断 |
| whole-root graphs、prepared metadata 动态投影 proof | 混合 registry/图读取 | 全部失效；首版不追踪细粒度依赖 |
| Ref 映射 memo、资格/版本/授权 memo | 证明而非裸材料 | 全部失效，generation 改变，重新判断 |
| 已核验 raw bytes/纯 JSON | 完整 artifact identity + 已 hash 原件 | 沿用现有持续 file proof；不提升为许可 |
| tl_input_dependency 行 | 新写表 | 不纳入共享目录；原直接 SQL |

所有共享条目仍计入同一 4MiB/4096keys，不新增免计量区域。物理 SQL 真实少读才少收费；cached facts 仍懒通知 logical observer，完整 domain capture 路径不丢字段、UUID 或来源顺序。

## 5. 拟议接口与文件分工

仅为审查契约，不表示已落地。

- `sqlite_store.py`：拥有连接执行监视器；提供私有 `certified_input_insert(fields)`。它执行原 INSERT，返回不可由业务构造的 receipt 或 None。receipt 绑定实际 connection、phase stamp、transaction identity、schema/trigger 指纹、监视器写序列、保守影响表；不用业务 UUID 生成技术 token。
- `tool_learning_readset.py`：`accept_registration_write(receipt)`。立即在 INSERT 返回后、任何 commit 检查前验证 receipt/真实外部探针，按表依赖失效缓存；更新本连接已解释写序列，但不重基线 foreign primary data_version、Control DB 或 blob 变化。不接受任意表名/用户传入 booleans。
- `tool_learning_eligibility.py`（由 read_boundary agent 独占）：仅新行 INSERT 调用受管接口并立即提交 receipt；原 `_registration(commit)` 和 `_check(commit)` 完整保留。未知 authority/reader/callback 条件直接原 insert 与全失效，不给部分证书。
- `tool_learning_store.py`：不扩大 validate_ref 共享范围；若注册统一入口需要，最多接私有 receipt 转发，不改原校验语义。
- outer 事务结束：始终递增 transaction_generation，旧 iterator 失效、Ref/许可 memo 清除。只有所有写均已解释且 commit 正常、原外部/文件/控制探针全过，才保留不相交固定事实。rollback/unknown outcome/full callback/未解释写/外部提交一律现有全失效或关闭。
- nested rollback：仍清全部物料，不退款。正常 nested success 不放宽现规则。不能凭 receipt 重建已失效材料。

当前 `transaction_ended` 无 receipt ledger；必须让 ledger 从窗口前延续至真实 COMMIT，否则 INSERT 后再次未知 SQL 可以被最终“自有提交”掩盖。任何不连续监视都使整个 ledger 失效。外部提交仍由现有主连接 data_version 与 observer 双探针阻断，旧读事务不能被自有 COMMIT 洗白。

## 6. 验证门槛

先实现独立监视器证明能力的小测试，未过不接业务。

1. prepared-cache 重执行、cursor/connection 各入口、trigger 增加间接 UPDATE/DELETE、未知 UDF 重入 SQL、未知 hook/替换 connection 均不错误发证；原约束错误位置和类别保持。
2. 同库原路径对照新输入/已有输入/重复摘要/错 epoch/错用途/错 recipient/删除屏障；persisted rows、ID 序列、事件/输出完全相同。
3. 保留每个 positive/negative 固定材料；随后同连接修改对应任一源表必须重新读/拒绝。foreign write 含旧 snapshot、gap race 与 child process 仍拒绝。
4. outer/nested rollback phantom facts、Ref、JSON、artifact 不复活；未知 raw COMMIT 仍保守拒绝；异常不吞原业务错误；旧 iterator 过 outer commit 不可继续消费。
5. 未知 authority callback 在 begin/commit 修改 policy/barrier/artifact/依赖边必须被原保护发现，不能因 receipt 获得任何免检。observer 真/未知/替换情况下完整来源序列与原 SELECT* 分支保持。
6. 实际 register_input 端口重复登记，记录原与新真实 SQL/扫描/字节、permission-use 序列、逻辑预算，不 mock owner。不更改 meter 定义/上限/样例。
7. 既有故障集与全八模块 `_contexts` 严格差分；之后协调统一 PF06，再原 11 Memory shared 与连续二轮。

预计收益只可说：每个 input 新行写后及其事务结束后的两个冷材料窗口有机会复用不相交事实；register_dependency 仍冷，source_kind/prepared/graph 仍清。不能由此宣称能省 20 万扫描或已足够通过 assembly；需真实端口计数证明。

## 7. 审查决策点

当前可安全实施的是先验证受管连接监视完整性，不能立即加 selective clear。若为此必须全连接禁用 statement cache、接管现有 hooks 或允许任意 UDF，则成本与风险可能超过收益，应明确停止此方案，而不是降低证明标准。批量改变事务/检查顺序另有行为影响，本次不选。后续应以小端口实际重复量决定是否值得继续；不存在已获授权的 cap/份额扩大方案。
