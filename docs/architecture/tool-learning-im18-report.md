# IM18 独立评测基础设施报告

日期：2026-11-09；版本：V0.1；状态：本项实现及隔离自检完成，待统一验收登记。不更改计划/冻结规范，不代表MECH、DEV或正式实验已经运行。

本项交付十类精确记录校验、唯一权威评测库、显式角色投影、可信确定性替身执行、三级预算与统计聚合。生产主库、当前生命实例和模型适配器均未进入此实现路径。

## 实现与证据

- `evaluation/tool_learning_records.py`：十类§7完整字段，EvalID/同run Ref、Slot、数值/未知、固定协议参数、回调入口、故障终点及区间守卫。
- `evaluation/tool_learning_store.py`：直接使用IM03精确DDL。控制者私有的tle_run/case/query/trial/attempt/label/review/fault/usage/metric十表是唯一权威；`records`仅派生只读视图。角色/工件/生命周期辅助记录不取代精确表。全部测试库由TemporaryDirectory新建。
- `evaluation/tool_learning_runner.py`：可信本地确定性替身、真实本地入口事件、原trial期限、原始/最多一个有据基础设施替代、run/batch/logical_trial三级SQLite原子预留与实际/未知分账。无真实provider transport。
- `evaluation/tool_learning_statistics.py`：由root独立交付的Wilson、固定10000次配对case bootstrap、case内三repeat先均值、TL01—16分类聚合及缺失/失败/成本处理；不自动生成语义真值。

本轮最终运行：`PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest discover -s tests -p 'test_tool_learning_evaluation*.py' -q`，共69项通过（记录/存储/预算/runner44项，统计25项），零失败。统一验收原始证据由root另行封存；本报告不填造独立评审或正式效果结果。

关键反例包括：十类缺键/未知字段/错类型、跨run/孤儿引用、真实Slot未知与零、零分母不pass、固定区间参数、同消费事件变Slot原因/Ref revision重放、reviewer越域读写、evaluator写truth、未登记真实身份、原始/替代分配及预算、独立SQLite连接竞争最后额度、同查询工具不挤占模型唯一机会、账本格式篡改、未知消费阻断、已知超额消费保留后停止、prepared不冒充actual入口、同键异义缓存、旧期限不刷新、晚到返回not_evaluable，以及失败证据脱离临时目录后保留。

## 使用边界

真实DEV/TARGET/RETENTION启动检查始终`blocked_before_start`，会列出材料封存、精确模型能力/路由、价格、货币/账户额度、角色、MECH/G1及授权缺口；即使传入自报条件，也没有真实派发入口。控制者注册身份只能明确标synthetic；不把两个不同字符串冒充真实独立评审已就位。actor仅取learning/query投影，reviewer仅取blind-review材料；知道run/id不能查Trial组别或原真值。

默认导出为控制者审计，剔除Label/Review；完整私有库需显式include_truth。导出目标必须全新且无符号链接，不能覆盖旧证据。runner另提供不可变完整事件/结果JSON，异常机会和actual入口事实保留，临时工作目录关闭后仍能保存。CLI自动归档尚未集成，不把临时自检轨迹冒充IM19封存。

三级预算使用确定性替身计量，报告有明确`real_model_called=false`，不充当供应方账单。已知超额不丢actual：保留违规和消耗、停止run；未知用量保留预留、不补零。基础设施替代必须有原infrastructure_invalid、MECH Fault实际证据及独立评测器角色批准，且共享原分配/预算/期限；普通供应方失败不自动替换。

## 后续义务

IM19仍需绑定并执行IM17真实夹具清单、外层监督受管故障/挂死进程、验证清理及封存全部失败证据。本项同步可信回调只能验证返回后的观察截止及停止后续派发，不能强杀挂死函数；这一边界已由root确认保留，不声称通用进程管理/远端取消。新48并发分支、42写点故障和全G1继承矩阵本轮没有执行。

独立正式材料/双评审、货币额度/价格/账户确认、真实模型先导与正式调用分别属于后续明确授权阶段。当前统计测试和替身通过不证明学习改善、旧能力保持或实际模型可用性。
