# 受管 SQLite 写表足迹：独立基础组件设计

状态：设计先行；初次兼容修复33项、正常savepoint代次分离后38项、query_only明确连接分类后43项、增强必要谓词后50项、注册表重复扫描融合后54项、已知固定读取环境谓词后最新快速58项通过，尚不代表 Store / register_input 业务闭环。最新独立更新2026-11-12。

目标仅是为一次固定参数化 INSERT 证明当前受管连接的**保守可能写表集合**。不是逐行日志，不证明 UDF 整体只读，不产生授权，也不允许跳过 readset 的主库、控制库和已跟踪原件真实检查。

## 明确边界

- 用 composition Connection / Cursor，无 raw 公开透传；cursor.connection 返回受管连接。直接 sqlite3.Connection.execute(proxy, ...) 不成立。
- 私有原生连接从创建时请求 cached_statements=0；本机实测该参数不足以保证重复语句重新 prepare，因此所有公开 execute / cursor 端口还加连接私有 nonce + 单调序号的唯一**尾部** SQL 注释，使缓存键从不复用。前缀版本会使本机 Python3.9 的 DML rowcount=-1，已由真实接入CAS失败发现并修正为尾部。尾部前加换行，原末尾 `--` 注释与分号保持语义；真实重复prepare及Native rowcount/lastrowid/implicit transaction对照均通过。注释不使用业务 UUID，不带参数；受管 trace 转发时仅移除自己的尾部标记，原用户注释保留。authorizer 只积累原始 action / database / table / trigger 名，不在回调内查询数据库。
- 普通未知 SQL、额外写入、DDL、ATTACH、SAVEPOINT、事务异常和不透明端口使证书失效；未知 authorizer / trace、row / text / cursor factory 不发证。普通业务 SQL 仍执行，原异常保留。
- UDF / progress / adapter 不按函数名认证。所有原生 execute / fetch 的动态范围置 callback_active=True：此时调用的 Python 可能是 SQLite callback；上层必须暂停物料、Ref、metadata / raw 缓存，继续文件跟踪。callback 的同连接公开 SQL 重入仍由监视器记录；额外写入不发证。外连接 / 控制 / 文件影响只能由上层真实 probes 排除。
- progress最终分类：公开 `set_progress_handler(non_none, n)` 为未知hook，阻止新证书；私有 `_install_meter_progress_handler` 仅供原资源meter组合入口，仍包在callback_active中，异常/中断/重入写使证书失效。安装/移除一律使旧receipt失效，不按callback名称认证。
- 固定 INSERT 保留参数化语义。候选参数仅 exact str / int / bytes / None；已注册适用的全局 adapter 或窗口前后 registry 改变使证书失效，业务仍走原参数化语句。短暂注册并恢复无法用快照冒称已观察；callback_active 缓存暂停是其安全前提。
- 不防御同进程恶意 Python 读取私有 raw、改监视器内存、替换授权函数；该能力已足以改写任何现有权限判断。所有公开受管 SQLite API 的操作必须被覆盖，不以这个排除项掩盖公开漏口。

## 私有接口

`managed_connection_factory` 供 sqlite3.connect(factory=...) 使用；其他连接默认无证明。

`bind_insert(sql, target, allowed_tables, schema_signature)` 由可信组合入口在已核验 schema 之后创建绑定本连接的固定 INSERT contract；不读取 / 审批 schema。schema_signature 必须由 Store 对真实 catalog 与受审契约核验后传入。后续受管 DDL / 不透明配置变化会使其失效。

`certified_insert(contract, parameters, context_token)` 原样执行一次 INSERT，返回 `(cursor, receipt_or_none)`。receipt 绑定实际连接、contract、phase context token、事务 epoch、写序列、真实 total_changes、schema stamp。它不是业务可复制的 bool；验证用对象身份和连接内部登记。

`receipt_current(receipt)` 在未出现额外写入 / hook / factory / 事务变化时为真。上层在完整 probes 后调用 `accept_receipt(receipt)`，才把该写纳入当前事务账本。COMMIT 必须正常返回且所有写均被已接受 receipt 覆盖，`committed_receipt(receipt)` 才为真；ROLLBACK / SAVEPOINT / 未解释写一律无证明。

`monitor_state()` 不执行SQL，只返回连接/配置/schema/事务/写序列及当前pending、accepted、last_commit对象。它同时刷新全局adapter/converter注册表的身份签名，持久注册表变化使旧receipt失效；上层在物料重用前应把此watermark纳入新鲜度检查。只允许每个原独立事务一个候选INSERT，receipt只可消费一次；新事务使旧对象失效。schema contract不因普通progress/UDF安装永久失效，但真实DDL使已有审批结束，不能以同旧signature原地重绑。

其 `can_certify` 仅作提前保守回退的只读hint：检查事务/未知hooks或factories/opaque端口等，尚未校验具体SQL contract、参数或外部状态；True不是证明。它让未知观察/trace路径无需增加schema或probe SQL就走原路径。backup progress回调也在callback_active范围，且backup本身令旧receipt失效。

执行器不自行发 SQL 查 schema，不制造未计量主库读取。所有额外真实 freshness / schema 核验由已有 Store / readset 的原计量入口负责。组件不修改预算、字段、事务划分或原参数值。

## 独立验证门槛

连接与 cursor 重复准备、trigger 写表上界、UDF / global adapter 重入 SQL、未知 hook / factory、executescript / blob / deserialize / extension 端口、commit / rollback / savepoint、失败原异常、伪造 / 旧 receipt 均测试。基础通过后再由业务接入者验证外部连接、控制文件、原件变化的 probes，不把本组件测试冒称整个 register_input 已可用。

## 独立实施结果与保留失败

- 33项独立临时SQLite测试全部通过；覆盖重复prepare、trigger、cursor.connection、native base方法绕过失败、懒fetch里的SQL重入、参数adapter语义、临时adapter期间缓存暂停、私有meter/public未知progress、factory、hook、异常、回滚、root/nested savepoint、旧/复制receipt、backup/blob端口与唯一注释trace，以及Native INSERT/UPDATE/DELETE/executemany的rowcount/lastrowid/implicit transaction完全同。
- 特别的外部影响反例：未知UDF同时更新另一control数据库和原件文件时，本组件仍可产生“本连接只写inputs/registry”的窄足迹。这是刻意验证其限制；readset若未执行自己的外部/文件probes，不得接受该receipt。没有用组件的True冒称UDF整体无副作用。
- 首次20项运行有1失败4错误：重复prepare暴露本机cache0不足，已通过唯一注释修复；4个夹具在schema审批之后加DDL，正确被保守拒绝，夹具改为完整建schema后首次审批。另补root SAVEPOINT边界（以unsafe初始事务阻断）。这些记录在独立验收目录保存，不覆盖为第一次就通过。
- 后续真实流程发现无写SAVEPOINT/RELEASE不应增加物料configuration，已把仅账本/window的unsafe与物料配置分离；ROLLBACK TO仍强失效。最新独立38项封存见 `round2-managed-savepoint-generations-design.md`，原33项结果仍保留。
- 再次真实审计往返发现`query_only`纯读和ON/OFF不应增加schema代次；仅该明确连接PRAGMA已与schema失效分离，ON/OFF仍configuration强失效，真DDL/schema相关及未知PRAGMA仍保守。最新43项封存见 `round2-managed-query-only-classification-design.md`，历史结果均保留。
- 增强`insert_only_receipt`仅提供真实身份/全部INSERT action/无collation和不透明历史的必要谓词；不能凭事件名认证未知REPLACE。应用仍需完整已审plain SQL、真实schema及两表约束。最新50项见 `round2-managed-insert-only-witness-design.md`；普通tablelevel证书不变。
- 注册表刷新重复扫描已融合为同一次完整签名内的原生type-id集合分类，保留全部adapter/converter字段、刷新频次及opaque历史，基础54项通过；独立微端口减少35.9%不代替完整思考实测。详见 `round2-managed-registry-refresh-design.md`。
- BINDING固定读取新增无SQL/无txn依赖的`known_read_environment()`必要谓词，unknown hooks/factories/callback/opaque状态走原路径，快速58项过；最终统一全源仍由主任务补证。详见 `round2-managed-known-read-environment-design.md`。
