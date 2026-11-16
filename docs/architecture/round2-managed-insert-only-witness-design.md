# 固定已审 INSERT 的增强必要谓词

状态：设计先行，独立基础实现；仅监视器和基础测试，不改readset或授权。2026-11-11。

## 用途与前提

`insert_only_receipt(receipt, committed=False)` 提供增强的**必要谓词**：真实当前或已提交receipt对象身份、所有authorizer可能写动作为INSERT、没有可能改变主键/匹配语义的不透明历史。它仍不独立证明任何未知SQL/schema都具有保持旧行的性质。应用必须同时核对实际已审plain INSERT、真实catalog的精确schema digest、固定两表以及全部原freshness probes；不可把此bool当授权。

本机实测 `REPLACE INTO r ...` 可以只产生SQLITE_INSERT authorizer事件，不能凭事件名字认证REPLACE不会删除旧行。直接REPLACE/INSERT OR REPLACE不符合本组件固定plain INSERT parser；绑定后加未知trigger或真正schema改变仍使旧contract无证。绑定前的真实schema审批属于可信Store组合入口，不能由一个任意传入的signature字符串冒充。

## 最小能力

- 新增 `insert_only_receipt(receipt, *, committed=False)`：分别调用真实current/committed校验，再检查非空footprint全部SQLITE_INSERT。
- 任何自定义collation配置尝试（包括覆盖BINARY及之后删除）使增强谓词直到该连接关闭都为False。普通tablelevel证书行为不因此放宽或改变；应用可以继续原全部失效路径。
- extension及未知cursor/factory/native binding adapter等不透明状态或已观察历史也不能通过增强谓词。普通已受管clock UDF和私有meter progress保持原窄写足迹契约；其重入写/异常/配置变化仍无证，外部副作用仍由应用全probe检查。
- 不做函数名认证、不查询未计量schema、不改变SQL参数、rowcount、预算或表结构。任意Python改私有内存不在已有安全模型内。

## 验证

当前与正常commit后增强正例、复制/旧receipt反例；自定义collation及删除后的永久拒绝（普通证书仍可用）；BINARY覆盖；unknown row/text factory或原生类型adapter历史；UPDATE/DELETE、直接REPLACE及绑定后未知trigger/schema变化不能冒增强谓词；实际受管clock原样可用。此基础测试不代替应用的精确schema与旧正行保留差分。

## 独立结果

最新50项基础测试全部通过，0失败/错误/跳过，两源文件前后稳定。原43项之外新增7项覆盖增强current/committed身份与实际clock callback、collation删除后的永久强拒绝、BINARY覆盖、原生adapter历史、factory历史、REPLACE语法/新unknown trigger、UPDATE/DELETE。普通tablelevel receipt在collation或factory恢复后的保守强拒绝场景仍可正常验证，应用只能走原清资料路径。

原生REPLACE反例已保存`replace-authorizer-probe.json`：旧行value从old变new，而write action只有SQLITE_INSERT。首次50项扩展运行有1个fixture错误（新trigger先插同一registry主键，随后原trigger正确报唯一冲突）；改为REPLACE独立既有other键后通过，schema guard没有减弱。原错误摘要保留。结果路径：`outputs/acceptance/performance-round2-continuation/managed-sqlite-proof/insert-only-witness-result.json`。
