# 第二轮连续思考：计算后来源检查材料共享设计

状态：已按本设计实现，小端口差分及统一298项故障复验均通过。真实连续两轮及最终冻结验收尚待根协调。范围：PF07剩余连续对话预算问题；2026-11-11。

## 1. 已有失败证据

读取的仅为项目公开合成验收产物，没有打开正式实例。`pf07-continuous-06/result.json`真实第二轮在`register_dependency`提交前的`_check → _upstream_current → _metadata → selected_revision`耗尽assembly原预留：scan 453229/453229、bytes 141060043/143439443；模型第二次调用未发生。独立0历史样例同样在449090行耗尽，因此不能只归因于数据库预置17条历史。

先前两个阶段实际消耗如下，均来自原账本而非估算：

| 第二轮阶段 | 17历史实际scan | 0历史实际scan |
| --- | ---: | ---: |
| calculated-contexts | 704293 | 708980 |
| calculation-live-bindings | 240558 | 244188 |
| assembly（被拒绝） | 453229 | 449090 |

现有`calculate()`本体已经安装有限材料读集，但退出后，对全部唯一token的`before_calculated_material_retention`循环没有独立材料读集；随后live-binding循环也没有读集。两个阶段对共享的第一轮来源反复读修订映射、原件位置和依赖边。它们先消耗原总账户，使后续assembly按原0.5份额得到更小预留。错误栈终点不代表`selected_revision`独自造成全部开销。

## 2. 最小变更

不跨登记写入保留固定事实，不实施此前被否决的“可信写集”草案，不改变任何总上限或阶段份额。

1. **计算结果保留前**：`calculate()`及其内部状态更新全部结束后，在原唯一token检查循环前开启全新的本地材料边界，循环完毕立即关闭，再执行原bundle和依赖写入。不能沿用calculate阶段的旧物料。
2. **live-binding检查**：在原`calculation-live-bindings`实际读账户内开启另一个全新的材料边界，包住原`verify_live`与`SourceSnapshots.capture`循环。capture的原独立事务、递归identity观察、写前后核对全部照旧。每次本连接写入、事务完成或回滚仍按现有规则使材料全失效，不给跨写例外。
3. 复用现有`calculation_read_boundary`的精确LocalEligibility保护，但将说明改为“固定本地计算及计算后检查材料”，并明确用途。整个边界内`source._verified=None`，因此每次source/version/permission authority入口仍真实执行；只允许固定SQL资料和纯结构准备复用，不缓存“允许使用”结论。
4. 两个新入口要求实际`runtime.eligibility.authority`与`owners.source`一致。live入口另要求实际SourceSnapshots实例、其实际authority与owner标记一致且是绑定同owner的精确LocalSnapshots、实际LocalAssembly也绑定同owner，以及snapshot验证使用的`owners.eligibility.authority`一致。单独替换实际authority而保留旧标记，不会误启用本地共享。

这两处调整独立于assembly登记协议；原登记、事务、回调、每消费者顺序和计量单位均不变。实际SQL返回行更少可使剩余资源按原公式增加，不是提高cap。预计收益必须以真实小端口差分证明，不能以原70万或24万读量直接宣称全部可省。

## 3. 不变条件

- 仍原8个模块，所有value、字段、selector、native/snapshot版本、Scope、read/delete路径、记忆及关系来源均保留。
- 主库同连接写入、外连接/进程提交、控制变化、原件/目录变化、嵌套回滚、未知事务结果仍执行原失效/拒绝；不把total_changes差值当安全写集证明。
- 真实/未知row observer继续收到原逻辑行；不借trusted collector suppression省掉领域来源。新边界不安装新的观察器抑制状态。
- 每次verify_live、snapshot source/capture/dependencies/final检查、资格检查和source_access调用仍保留。未知/子类Eligibility不启用本地优化。
- 技术读集仍4096键/4MiB；真实物理SQL/原件读量及原逻辑图预算完整计量；所有异常路径恢复外层owner状态，关闭阶段。

## 4. 验证顺序

1. 以同一合成SQLite备份创建独立可写副本，固定合成时钟/UUID/磁盘探针，替身模型断言禁止调用。分别关闭/只开retention/只开live/两者开启，逐字段比较计算值、live字段、新字段、bundle全部依赖、snapshot的selector/值/native版本、来源与权限调用顺序、业务cap、UUID消耗。分别记录三个实际读阶段的scan/bytes，不把时间剖析混入最终计时。
2. 对新边界验证`_verified=None`、未知authority保守、权限/版本入口次数不变、异常恢复；同连接修改、外连接提交、控制停止仍重新读或拒绝。
3. 通过后由根协调统一故障复验，再在原17历史真实连续负载运行两轮；必须观察两个不同request、两份实际raw输出和独立wire，不能用单轮成功冒充。
4. 连续性达到标准后冻结最终源，再做原harness三次计时及0/17/50/100历史、原11 Memory/关系增长测试；超原cap真实报告，不删输入/提高上限追通过。

## 5. 非目标

不是许可memo、全局RAM缓存、跨阶段长期记忆缓存或事务批量重排。没有实现源码自更新、真实LLM或正式实例唤醒。本设计不证明意识/主观体验或科学效果。

## 6. 实施与小端口实际结果

已在原两个循环安装独立边界。没有可信写集或跨写豁免。

同一真实8模块合成夹具的五档严格比较，全部values、features、fields、live、新字段、bundle依赖、来源/权限调用序列、snapshot selector/value/native版本、cap与UUID数量精确相同（不归一化）。

| 档位 | calculated-contexts scan | live-bindings scan | 合计 |
| --- | ---: | ---: | ---: |
| 全部材料边界关闭 | 35645 | 150597 | 186242 |
| 只有既有calculate边界 | 21799 | 150597 | 172396 |
| 再开retention边界 | 17340 | 150597 | 167937 |
| 再开live边界 | 21799 | 45116 | 66915 |
| 两个新边界均开 | 17340 | 45116 | 62456 |

相比本轮前已共享calculate的基线，实际scan减少109940（约63.77%）。这是小端口计量，不外推为完整第二轮已通过。五档测试共63.231秒，计时含观测，不用于最终性能门槛。补齐实际authority一致性guard后，五档会随统一PF06再次执行。

新增首批9项及既有观察器/分层共26项4.901秒全部通过。负例含capture commit前source revision变化、控制停止、配置原件变化：均拒绝且该次snapshot未提交；另有外连接提交、未知observer、未知snapshot/assembly authority保守回退、异常恢复及同连接写后材料失效。首次夹具误拼blobs路径导致1个FileNotFoundError，仅修正该路径后通过，原日志保留，产品保护和断言没有弱化。随后新增两个实际authority替换反例，随统一298项复验。

证据位于`outputs/acceptance/performance-round2/continuous-boundaries/`：五档全量payload、result及日志，和implementation-validation-summary.json。统一结果将写入`outputs/acceptance/performance-round2/continuation/faults-01/`。均为替身模型及隔离实例。

统一PF06已实际完成：298个唯一测试、145.47645575秒、0失败/错误/跳过、206个源输入前后稳定，exit0。包含新增11项反例、原故障与预算保护、五档完整8模块严格差分。结果`continuation/faults-01/result.json` SHA256为`e07b706178a57b9dbeb924b125104da982cf31964e1b5f18978c81885be65124`。所有CPU进程已退出。此结果不代替连续两轮实测。
