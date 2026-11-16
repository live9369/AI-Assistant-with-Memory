# 受管 SQLite：正常 savepoint 与物料配置代次分离

状态：设计先行，最小兼容修复。范围仅监视器和独立基础测试；不改 readset、业务事务、字段、权限或预算。2026-11-11。

## 已发现问题

真实接入中，`BEGIN IMMEDIATE; SAVEPOINT a; RELEASE a` 没有任何表写、`total_changes` 与写序列都不变，却使监视器configuration增加2。原因是authorizer把所有SQLITE_SAVEPOINT标为配置unsafe，而readset按配置变化清除资料。普通nested snapshot复用因而反复冷读。这不是实际数据或配置修改，不能把它的配置代次变化误作必要来源失效。

## 最小修复契约

- 增加仅作用于当前receipt窗口和事务账本的unsafe标记。SAVEPOINT的BEGIN/RELEASE仍阻止当前固定写窗口发证，并taint当前账本，不能借嵌套事务跨越已接受receipt；但不增加物料configuration/schema代次。
- ROLLBACK TO仍保持configuration强失效，即使没有实际数据写也不能复用潜在已回滚的物料；现有Store/readset的rollback_generation逻辑完全不变。
- 实际nested INSERT/UPDATE/DELETE仍由prepare authorizer记录写表和单调write_sequence；没有用savepoint名称推测只读，也没有把total_changes不变当完整写集证明。
- root SAVEPOINT如果启动了事务，也因账本unsafe而不可发证；正常外层BEGIN/COMMIT行为不变。

## 验证

比较正常BEGIN/RELEASE前后configuration、schema、write_sequence、total_changes；验证已接受receipt和protected INSERT窗口遇savepoint仍无证；验证ROLLBACK TO强失效、实际写回滚、原生SQLite rowcount/lastrowid/事务及数据结果相同。基础通过后由接入者重测来源缓存复用和完整两轮，不用本组件结果冒称整体性能恢复。

## 独立结果

38项基础测试全部通过，0失败/错误/跳过，0.012221416秒，两源文件前后稳定。新增5项分别覆盖正常savepoint/RELEASE标记不变、已接受receipt仍失效、protected INSERT中的savepoint无证、ROLLBACK TO强失效及数据恢复、Native DML/事务/结果等价。实际无写样例configuration 0→0、write_sequence 0→0、total_changes 0→0，账本tainted False→True；随后ROLLBACK TO使configuration 0→1。

证据：`outputs/acceptance/performance-round2-continuation/managed-sqlite-proof/savepoint-generations-result.json`，SHA256 `7c72364aaa72d3025f44cf97c15e84d9cbbcab79e4d7bbe35c36db1fa6714502`。原33项封存结果保留，本次没有改写旧证据。
