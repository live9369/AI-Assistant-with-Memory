# 受管输入登记写证明接入设计

状态：基础监视器33项、完整375项及单调收紧后43项定向复验通过；实际连续两轮及最终性能尚待根验证。不改原预算、事务或校验次数。2026-11-11。

## 证明边界

沿用`round2-certified-registration-write-design.md`。新composition监视器提供受管Connection/Cursor、每条SQL的新prepare、authorizer保守可能写表足迹、事务ledger和一次性receipt；它不是权限判断，也不是实际逐行日志。公开Store/ManagedConnection接口内的重入SQL、hooks/factory/DDL/事务变化受监视；任意Python改私有native handle、授权函数或内存不在安全模型中。Python factory/cache参数与SQLite authorizer机制依据[Python文档](https://docs.python.org/3/library/sqlite3.html)及[SQLite文档](https://www.sqlite.org/c3ref/set_authorizer.html)；authorizer只在compile/reprepare阶段运行，故组件每次新prepare并持续覆盖执行/取行。

## 最窄执行路径

1. Store创建主连接时采用ManagedConnection factory；meter外包层仍真实计量。只解包精确已知meter代理，不信任任意actual属性。其他旧/替换连接按原路径运行，无证明。
2. 仅精确LocalEligibility且实际owner/store一致的`register_input`新行分支调用私有固定input写入口。原ID生成位置/次数、字段顺序、参数化SQL和所有begin/commit资格检查不改。任何observer存在时走原INSERT，避免新增证明SQL改变其观察序列。
3. 实际审批main中`tl_input_dependency/object_registry`全部17项table/index/trigger完整定义及不存在对应TEMP影子。与代码中按可信DDL生成的静态digest精确比较；未知表/trigger/index/临时影子不发证。缓存schema审批只在监视器schema/config watermark及实际主连接data_version不变时使用，外部提交或本连接DDL须失效。proof SQL也真实计量。
4. 对固定原INSERT建立InsertContract，allowed tables仅`main.tl_input_dependency/main.object_registry`。执行返回receipt后，在任何commit资格检查前消费。无receipt不猜测total_changes，仍原全失效。

## 材料及事务ledger

PhaseReadSet记录监视器configuration/schema/write_sequence watermark。任何未解释write/配置/DDL，即使0受影响行、total_changes未变，也清全部材料及proof。读取/缓存命中都核对该watermark。

接受receipt前先检查真实connection/phase token/当前事务/receipt唯一身份，做完整主库data_version、主/控制文件与全部已跟踪blob探针。只有receipt current且仅覆盖固定两表时，一次消费并按query实际read-table集合保留不相交固定事实。source_kind及任何object_registry材料失效；graphs/prepared/admissions、Ref和资格memo全部失效，generation递增。原4MiB/4096key记账准确减去丢弃项，完整owner行与逻辑通知不变。

Store.tx正常COMMIT前做完整探针；成功后transaction_ended再完整探针，然后仅在committed_receipt仍成立、同事务所有写均已解释且无配置/回滚变化时保留不相交facts。transaction_generation始终递增，旧iterator不能跨提交。rollback/nested rollback/unknown outcome/unknown commit一律原全清或关闭。主连接data_version锚不因自有commit重基线，防外部提交被observer rebase洗白。

## SQLite callback缓存隔离

组件`callback_active()`覆盖native execute/fetch内部运行的Python（UDF/progress/adapter/row/text factory等）；meter外层charge的领域通知在该scope外。此scope内禁用facts、graph/prepared、Ref、owner许可和request-input memo、raw/metadata缓存命中与新增，不禁file tracking，原件必须真实读取/hash校验。预建缓存iterator不允许在callback中消费。返回后receipt接受和正常COMMIT前后仍全探针。

保留参数化SQL语义。自定义native-type adapter或registry/config变化无证；临时callback查询不能读旧缓存或污染返回后cache。不会把strftime函数名当信任；harness的普通memory-clock UDF只在受管无额外变更时可得到窄写证明。

## 验证

- 真实`register_dependency→register_input`同一合成SQLite备份旧/新对照，无SQL trace hook。逐字段比较所有持久行/Ref/metadata、权限调用顺序、UUID/cap/异常；技术issued/accepted/fallback计数证明真命中。
- 更换trigger/schema/连接/authority、unknown callbacks、source/control/blob变化、0行write、嵌套rollback/旧iterator/重复receipt和COMMIT间隙外效不能跨过保留。
- callback内facts/Ref/raw/metadata不得命中，仍真实计量/hash/文件追踪。
- 基础monitor及接入端口通过后统一原故障与全8模块差分，再原连续17两轮，最后同源三次计时及增长测试。不先宣称完成。

## 实际实现与结果

Store主连接已接composition factory。源码静态审批digest为`1690f9bffed11b05738e491a621da4a50913e41694e846b4c7895878145d007d`，来自可信runtime.sql及tool_learning_v1.sql在空SQLite中实际生成的17项完整table/index/trigger定义；任何同目标TEMP影子或额外定义均原INSERT无证。主库未迁移，原文件未操作。

实际使用基础组件`bind_insert/certified_insert/receipt_current/accept_receipt/committed_receipt/monitor_state`，上下文token绑定phase.stamp。最后额外单调收紧：receipt.tables必须恰为已审批的两张表，缺任一表也不接受。真实低层单表footprint反例已经验证，非伪造receipt identity。

`_probe`及transaction_ended均先执行SQLite版本探针，再采目录、控制及全部已跟踪文件签名，之后不再执行可调用callback的SQL。COMMIT前后两次实际探针。post-COMMIT外效拒绝只保证cache关闭及后续不使用旧许可，**不声称已提交技术登记行回滚**；实测该行可能已存在，模型未调用。

meter安装进度检查采用基础组件私有`_install_meter_progress_handler`；公开非None progress不发证。callback中facts/graph/prepared/Ref、owner和request许可memo、raw/metadata命中及新增均暂停，文件追踪和实际原件hash读取保留。零行UPDATE亦通过monitor write watermark使材料失效，不依赖total_changes猜测。

### 真实三模式端口

同一合成SQLite/控制库备份，固定世界时钟、UUID，保留原parameterized SQL及真实活动账户；Native legacy、Managed legacy（禁用receipt）、真正certified三种模式的完整tl_dependency/input行、Ref、metadata、权限/version/registration调用顺序、UUID、cap及重复/错digest异常逐字段精确一致。资源实际账本差异原样保留，不归一化。

| 深共享12新增节点/8字段，小端口首次完整比较 | Native legacy | Managed legacy | Certified |
| --- | ---: | ---: | ---: |
| scan/items | 4873 | 4873 | 3657 |
| 实际bytes | 1196118 | 1196118 | 773554 |
| 实际elapsed_ms（单次） | 1536 | 1874 | 1649 |
| issued/accepted/committed | 0 | 0 | 各8 |
| fallback | 0 | 0 | 0 |

读量减少约25%、字节减少约35%；但相较Native该单次仍慢约7.4%，不能只报相较Managed更快而掩盖监视器重prepare成本。后续43项复验同业务结果及实际scan/bytes再次一致，elapsed分别1768/1842/1709毫秒，反映单次波动，未挑数作为最终性能结论。

4字段浅图也实际真命中各4，841→721scan、223676→180568字节；浅图时间有波动，不推断全部系统净提速。

### 故障及封存

- 接入初31项曾出现14个CAS错误，定位为Python3.9对前缀注释DML返回rowcount=-1；基础组件已改尾部唯一技术注释，原生INSERT/UPDATE/DELETE/executemany rowcount、lastrowid、事务及重复prepare/trace对照通过。原错误保留。随后31项全部通过，10.832秒。
- 接入端口初9项前的post-COMMIT测试正确收到关闭phase的Conflict，退出时又拒绝，旧断言未覆盖两次拒绝；修正测试作用域后通过，产品保护未放宽。
- 完整375项：419.102708042秒，0失败/错误/跳过，213份公开Python输入前后稳定。结果`outputs/acceptance/performance-round2/continuation/faults-04/result.json` SHA256 `8e974e52c6f8586ce23620ba85de0f4e5ad1bb36ddeb5d7ddf0f5d0a091b71f3`。
- 之后仅产品一行tables相等收紧、1项真实缺表反例及runner计数376改动；只复验基础33+接入10，共43项通过，12.519秒，213份输入稳定，其余源码逐hash不变。`faults-04-delta/result.json` SHA256 `8329ddc58b6e13eb47cbd6d5f5370064504d37fad0aaa71413a94123cd19a346`。**不是新的单次376全过**；最终全量回归仍由根后续执行。

深/浅三模式完整payload与实际账本在`certified-input-port-03/`、`certified-input-unified-port-01/`、`certified-input-delta-port-01/`，此前所有失败日志保留。所有Python文件已冻结，全部CPU退出。当前结果只允许进入真实连续17验收，不能代称其已完成。
