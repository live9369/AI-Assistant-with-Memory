# Native与受管SQLite计算阶段读量对照

状态：新对照已实际通过，来源/权限/业务精确相同且阶段scan相同；必要范围统一复验167/167已通过；真实连续第二轮性能待诊断。2026-11-11。

连续17第四次仍未完成第二轮，且calculated-contexts从约181418行/43.6MB增至294936行/75.9MB。首轮完整业务输入与上版逐字段相同，但只在全部模式都使用ManagedConnection的八档测试中，无法发现“受管后端共同退化”。

根及基础agent已实际定位：旧monitor把无写的SAVEPOINT BEGIN/RELEASE同时当configuration变化，导致PhaseReadSet._sync_monitor清空所有材料。保存点本身可能使写证明ledger不安全，必须禁receipt；但不应把没有写入/回滚/配置变更的BEGIN/RELEASE冒充数据改变。基础组件已将两种generation分离，ROLLBACK TO及实际写仍原强失效。

应用/readset不改规则：材料watermark继续仅看configuration/schema_epoch/write_sequence；不把ledger.tainted（证明资格）误作数据变更。原Store嵌套rollback与lazy iterator保护照旧。

新增一个独立全_contexts真实两模式：从同一合成SQLite/控制备份分别创建Native SQLite连接和Managed连接，固定世界时钟/UUID/磁盘探针，所有新材料边界与数据选择均开启。完整比较八模块values、features、fields、live/new_fields、bundle全部依赖、snapshot selector/value/native版本、来源及权限调用序列、cap、UUID；不归一化业务内容。模型调用显式断言禁止。

保留原八档测试，另跑两后端测试，避免每次为此重复全部八档。两种模式逐阶段记录实际scan/items/bytes/elapsed与总墙钟；预期无写保存点不再导致受管读行回退，若仍不等则保留失败并定位，不通过放宽预算或断言掩盖。

实际账本elapsed可能影响记录编码字节长度，不能将少量字节差异当业务字段差异抹除；业务字段必须精确相同，数据阶段scan应逐项对照。时间只作端口观测，不代替最终三次性能验收。

## 实测结果

新两后端测试27.233秒通过，无模型调用。完整两份payload保存在`outputs/acceptance/performance-round2/continuation/native-managed-contexts-01/`，业务差异为空。两者权限source_access调用均4614次、业务UUID均2086次；不靠减少校验或观测来源获得相等。

| 阶段 | Native实际scan | Managed实际scan | Native bytes | Managed bytes |
| --- | ---: | ---: | ---: | ---: |
| calculated-contexts | 16452 | 16452 | 4897899 | 4897917 |
| calculation-live-bindings | 43280 | 43280 | 10068525 | 10068544 |

阶段scan逐项完全一致，当前小端口已消除正常无写savepoint造成的材料全清回退；真实第二轮大负载仍须另跑。18/19字节差属于实际elapsed账本数字长度，不删除实际账本差异。完整业务字段与source/native/selector/Scope/权限/UUID/cap精确同。

端口观测墙钟Native9.942343833秒、Managed13.346808334秒。受管backend仍约34%额外成本，不能用“读量回归已修”冒充性能达标。后续专门诊断会记录实际Python调用exclusive耗时，不以trace或隐藏预算制造成功。

## 必要范围复验

冻结全部Python源码后，`faults-05`实际167项均通过，0失败、0错误、0跳过，65.494425833秒，source_stable=true。范围包含基础38、接入10、保存点/rollback、来源材料/observer、postcalculation边界、Native/Managed全_contexts及诊断工具5项。本轮是必要范围复验，不替代最终完整387项与三次计时/增长验收。

证据：`outputs/acceptance/performance-round2/continuation/faults-05/result.json`，SHA256 `3f9cd5f58cd7a5b9cb524c42cb25fe321137ccc533d6306edd2315596245e7ac`。此后未再修改Python源码，测试进程已退出，由主任务触发真实第二轮诊断。

## 后续exact材料优化对物理行数的明确变化

以上scan相同是无写savepoint回退修复时的历史诊断目标。后续已审exact投影与owner作用域schema原始整数共享仅适用于Managed已知环境，Native保留原SQL，因此最终相同行数不再是预期。新实际两阶段Native16454/43280、Managed15539/36187，全部业务、来源、权限、UUID差分仍为0。测试改为逐阶段Managed不高于Native、总物理scan减少，保留所有语义精确断言；初次旧相等断言失败与修后同源Native1通过均保留在faults-09-exact-material-focused和faults-09-native-delta。此变化不放宽原件、权限或预算，也不等于真实连续验收完成。
