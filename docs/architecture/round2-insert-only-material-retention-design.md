# 固定input新增后的正事实与纯材料保留

2026-11-11。目标是连续第二轮scan预算，不改变cap、权限、字段、事务或原件检查。先设计后实施；限定既有受管公开SQLite接口，任意Python修改私有底层不在证明范围。

只有实际受管receipt current/accepted/committed、原固定_INPUT_SQL/列、完整17对象审批摘要、两表足迹恰等于tl_input_dependency/object_registry、足迹每项SQLITE_INSERT，才适用。plain INSERT唯一主键冲突会失败，不会覆盖已有行；精确schema中没有替换/更新触发器。因此已有object_registry正行不变，而“没有此行”的负事实可能被新增打破。未知collation可能改变键比较，须基础组件对存在任何自定义collation禁证；未知写、UPDATE/DELETE、DDL、回滚、配置、外部/控制/文件变化均保留原强失效。

缓存类别穷尽如下：

| 类别 | 实际读取依赖 | 新增后规则 |
|---|---|---|
| source_kind正单行事实 | object_registry(instance,id,kind) | 唯一键plain新增不改变已存在行，保留 |
| source_kind负事实 | object_registry缺行 | 全清；不得猜新增ID |
| 原有固定事实 | revision_registry/policy/config/dependency/epoch/barrier/change/artifacts或白名单owner表 | 按原表集合相交失效，未知query清 |
| prepared metadata | 固定dependency行、不可变artifact原件、正registry Ref、revision投影、Scope结构 | 均未写；保留序列化纯材料，原件每次track/probe |
| prepared graph | dependency全边与metadata、snapshot/revision桥、Scope/path；成功构建所需正Ref | 均未写；保留序列化路径与原逻辑行数，每用仍扣完整max_rows/scan逻辑预算 |
| admission | 是否已观察该图的纯技术需求标记，不含结果 | strong INSERT保留，使跨input需求可累计；其他失效清 |
| Ref映射、LocalEligibility/其他许可/verdict | 当前权限与认定 | 全清，generation继续递增；不得保留 |
| artifact/metadata原始材料 | 原件hash/路径与不可变JSON | 沿既有规则，所有tracked file真实probes不减 |
| iterator | 事务/rollback generation绑定 | 原失效，不跨commit继续消费 |

receipt消费前、commit前、commit后仍完整DB/control/所有文件probes；callback内不命中facts/graph/prepared/Ref/metadata/raw；真实authority/observer继续原每用通知与权限入口。强配置变化与真实schema审批终止规则不变。prepared数据可复用不等于授权结果复用。

先跑实际深图8字段同库Native/legacy/cert登记对照计量，再补正负kind、纯材料保留、负转正、真实UPDATE/DELETE/rollback、customcollation、外部/控制/原件、observer、权限次数与业务精确差分。只有实际receipt真命中计量才有意义，不以fallback通过冒称优化有效。

实施边界进一步收紧：prepared只保留TL-DEPENDENCY-1固定标签，未知prepared材料清；其命中只复用JSON与Scope编码，仍每用执行validate_ref及selected_revision/revision_owner投影核对，避免把结构准备当Ref verdict。graph是_upstream唯一产品生产的纯路径材料，后续_check仍逐路径执行当前来源、epoch、barrier与许可检查；它不含_check结果。

## 第一端口实测

基础50通过后，接入新增4项通过（1.340秒）。实际deep8同库四模式业务、来源、Scope、权限560次、UUID27次、异常全部精确一致。原table证明与strong均实际issued/accepted/committed8，fallback0。实际scan3657→3361（下降8.09%），bytes773554→767378（下降0.80%），graph查找35次相同、命中0→9、需求命中1→17。单次elapsed1356→1272ms仅作端口观察；这个小图结果不代表真实第二轮约15%所需余量已经满足。Native/Managedlegacy scan均4873。证据continuation/insert-only-retention-01/registration-port/deep-8。首次小测试夹具把应清除的未知TL-CONTRACT标签也要求保留，已只修预期且保留初错日志，产品未放宽。

## 连续验收前的强分支技术观测

新增纯内存strong_material_accepted/strong_material_committed整数；只有readset实际通过全部strong条件并执行材料保留分支时递增。普通receipt成功不能推测为strong。原五计数语义不变，不写数据库、输入包、权限或预算。deep四模式断言Native/legacy/weak为0，strong实际8；真实连续测试通过counter-only读取可选计数，避免因不透明历史使strong始终关闭却误判优化已生效。

新增强计数后5项（4小项+四模式deep8）通过，7.576秒。Native/Managedlegacy两值0，weak普通证书8成功但强计数0，strong两计数各8，证明计数来自实际保留分支。scan与图命中同前。证据strong-counter-port/deep-8及strong-counter-port-tests.log；暂无新的完整统一结果。
