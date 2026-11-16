# IM18 独立评测记录、替身运行与统计设计

日期：2026-11-09；版本：V0.1；状态：实现设计。规范依据为冻结存储附录§5/§7、Q10及Q11；不改生产库、IM17材料或任务状态。

## 模块与边界

- `evaluation/tool_learning_records.py`：Run/Case/Query/Trial/Attempt/Label/Review/Fault/Usage/Metric十类完整字段、严格类型/未知键、同run引用及局部跨字段校验；只证明结构，不把作者ID/JSON状态当授权或独立评审证明。
- `evaluation/tool_learning_store.py`：只由`EvaluationWorkspace.create()`创建全新临时目录；直接加载IM03的`digital_life/resources/tool_learning_evaluation_v1.sql`，在controller-truth目录建立唯一权威十表SQLite库；`metadata`/`truth`是同一控制者私有连接的兼容名称，`records`仅十表的派生只读视图，无第二套JSON记录表。工件按learning/query/truth/fault/blind/manifest域做显式投影。目录0700/文件0600。全部十表的字段、主键、唯一性、延迟外键及触发器使用IM03原DDL，补充API语义守卫；所有引用限同run；工件先注册再引用。actor只能取得显式learning/query投影，无Label/Review及truth正文。可信评测控制者不受同进程恶意代码/同UID原始SQLite攻击的安全承诺；正式角色必须另行落实独立进程/身份访问控制并提供证据。
- `evaluation/tool_learning_runner.py`：仅确定性本地替身、回调入口事件、预登记任务状态与故障事实；三级run/batch/logical_trial原子额度及同逻辑trial替代预算。没有模型适配器、网络、生产Runtime、进程唤醒或自动启动。运行材料的planned/null handler不能视为已实现执行器。
- `evaluation/tool_learning_statistics.py`由root独立负责：TL01—16规范化事实聚合、Wilson及10000次case配对bootstrap。先case内三repeat均值再等权case，不把repeat当独立样本；失败保留分母、缺失给界限/阻断，不由聚合器猜语义标签。

## 记录与关系

记录API为`validate_record(type_name,value)->value`，精确使用§7全部必需字段和公共TL基础类型。引用的instance_id对应eval run，外部实例身份以已注册评测工件描述而非生产库FK表示。独立库核对Case/Query/Trial/Attempt逻辑关系、原始与最多一个基础设施替代（必须有独立故障证据，供应方错误不适用）、重复身份和来源簇隔离。TARGET三个查询、RETENTION一个，以及正式组别/重复齐全由封存准入整体核对，不把部分数据报完整。

## 预算与真实入口

每逻辑trial最多6次模型尝试，学习最多3次；每次预留32768token、输入上限24000、输出上限8000；4次只读工具、180秒单调用、1200秒trial观察截止。run/batch/trial三级一起预留，任一级不足整体回滚。未知总额不是无限；替代不新建预算身份。实际用量和预留分别记录；未知保持未结清且阻断后续派发。没有真实回调入口的prepared/sent账本不算消费，失败/停止事实不删除。

替身runner输出审计事件及规范化mechanism observations；不制造语义得分或评审标签。确定性替身只是机制夹具，不能被包装成模型执行或真实删除结果。180秒/1200秒为观察/停止新派发边界，不承诺强制撤销远端；当前无远端执行能力。

## 启动门与验收

真实DEV/正式启动需完整材料封存、精确模型能力/路由、已核查价格、货币/账户上限、角色与授权、MECH/G1及相应DEV前置。TARGET/RETENTION还需独立真值、两独立评审/裁决及来源隔离。缺项`blocked_before_start`；当前实现不提供真实模型派发路径，不能通过传入几个bool解锁消费。

隔离测试只创建临时评测库：十类字段正反例、跨run/孤儿引用、truth拒读、原始/替代唯一性、三级竞争额度与回滚、未知成本/停止、actual入口与prepared区别；统计固定夹具独立复算。实际MECH大矩阵执行属IM19，IM18不将材料全部not_run改通过。


## 物理映射与唯一权威

| 精确记录 | 权威表 | 主要额外API守卫 |
| --- | --- | --- |
| Run | tle_run | 参数固定、仅具名生命周期变更，本工具只启动确定性mechanism |
| Case | tle_case | 来源簇不跨DEV/TARGET/RETENTION |
| Query | tle_query | 同case查询类型唯一，RETENTION专属类型 |
| Trial | tle_trial | 原始logical_id=id、最多一个替代、独立评测器损坏证据、同分配/预算 |
| Attempt | tle_attempt | 同run trial/query一致、真实回调入口不以sent推断 |
| Label | tle_label | 控制者真值域、独立作者/复核组；本工具只注册明确synthetic身份 |
| Review | tle_review | 盲化投影，原评分保留，作者独立性、分歧裁决和两评审门 |
| Fault | tle_fault | MECH case实际存在、未运行无轨迹、完成须有终点和实际轨迹 |
| Usage | tle_usage | 稳定reservation+Attempt身份唯一，不能靠Slot原因或revision改写重复计费 |
| Metric | tle_metric | 真实case/trial/partition关联，零分母/缺失不能pass，固定区间协议 |

十类公共字段和全部业务列以原名一一写入上表；dict/list字段编码为JSON，bool写SQLite 0/1且读取复原JSON bool，known零/unknown等Slot原样保留。测试逐表对照PRAGMA列集合与精确字段字典，并对十类记录完整往返核对。`records`视图从这些列构造文档供统一只读查询；插入/更新只进tle_*权威表，派生视图不可写。角色、工件注册及生命周期历史是辅助表，不替代十类权威记录。

导出只由控制者显式发起到全新无符号链接目录，默认导出不含Label/Review的审计JSON及预算快照；若明确include_truth，才另导出完整私有十表库。默认导出不是actor可见运行包，actor仍只能取得learning/query投影。各SQLite文件单独一致备份，不冒充跨数据库原子快照；完整失败runner事件/结果另可转为不可变JSON字符串，临时目录关闭后仍可由调用方保存。未集成CLI自动归档。

## 观察截止的实现边界与IM19义务

本项执行可信同步确定性Python替身。180秒单调用/1200秒trial为观察及禁止后续派发边界；原trial墙钟期限持久化，重建runner不能刷新，时钟倒退也阻断。回调返回后超过边界则not_evaluable并停止新派发；固定时钟测试覆盖181秒晚到返回。本项不声称强杀挂死Python回调、通用进程管理、远端取消或供应方硬token封顶。

IM19必须在外层独立监督受管故障/挂死夹具，验证超时终止、在途事实/费用及清理保留；不能借本项替身通过宣称硬超时已实现。这里没有启动任何挂死测试或真实调用。三级预算的SQLite预留在独立连接间竞争可核对；同步替身最终检查/回调入口门禁使用线程锁加受管文件锁，不替代IM19完整48分支实际轨迹。
