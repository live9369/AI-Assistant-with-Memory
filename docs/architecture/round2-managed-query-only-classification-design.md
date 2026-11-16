# query_only：连接只读状态与 schema 代次分离

状态：先设计后最小基础修复。范围仅受管SQLite监视器和独立基础测试，不改controller、Store、readset、权限或预算。2026-11-11。

## 实际复现

一次固定INSERT已发证并提交后，`PRAGMA query_only=ON/OFF`把configuration 1→2→3，同时错误地把schema_epoch 1→2→3；数据库catalog实际没有改变，旧signature的重新绑定却报“schema approval ended”。纯读`PRAGMA query_only`也被同一个未知PRAGMA分支错误归为schema修改。两次原版内存复现已分别保存 `query-only-before-fix.json`、`query-only-read-before-fix.json`。

## 最小分类

- 仅明确加入`query_only`只读PRAGMA目录。无参数纯读不改configuration、schema或写序列。
- 仅明确加入`query_only`连接设置目录。ON/OFF或等价参数仍完整执行原SQLite语句；configuration增加，当前ledger/window无证、缓存失效、旧receipt失效，但schema_epoch不增加。
- 不扩大其他PRAGMA的许可。真正DDL以及`writable_schema`、`schema_version`、`user_version`等写参数仍按原保守schema强失效处理，未知PRAGMA仍保守。
- 保留原生query_only只读限制：ON时INSERT仍抛原生SQLite异常，不因候选receipt绕过；OFF后新的干净事务可在同一个未变化的schema审批下发证。schema_signature仍来自实际catalog审批，不把mode切换当新的schema审批。

## 验证

独立临时SQLite比较纯读状态、ON/OFF前后schema/config代次、旧receipt失效、新事务同contract成功、原生SQLite只读错误/事务/数据结果相同，以及真实DDL和schema相关PRAGMA拒绝旧审批。随后由业务接入者另测真实controller审计往返与完整两轮，基础结果不代替系统验收。

## 独立结果

最新43项基础测试全部通过，0失败/错误/跳过，两源文件前后稳定。新增5项覆盖纯读（含大小写）代次不变、ON/OFF后同schema contract可在新事务发证、Native只读异常和数据行为、设置仍使活跃receipt/ledger失效、真实DDL及schema/未知PRAGMA仍拒旧审批。

首次新增43项运行有1失败：SQLite authorizer保留大写`QUERY_ONLY`，固定名字判断需按SQLite自身的大小写无关规则归一化；已修为仅本地固定名分类lowercase，执行SQL与转交foreign authorizer的原参数未变。原失败摘要和两份修改前真实复现均保留。最新结果为 `outputs/acceptance/performance-round2-continuation/managed-sqlite-proof/query-only-classification-result.json`。
