# 连续思考的互斥耗时诊断

状态：先设计后实现；只新增独立诊断工具与小测试，不改产品、主replay或原scale。日期：2026-11-11。

## 目标与边界

连续17第四次仍在第二轮assembly阶段超时，实际命中receipt未由原scale导出。新工具转发原scale全部选项并调用其`main()`，原结果、完整输入/输出、失败快照与真实账本仍由原scale保存；另写仅含技术聚合的诊断JSON。

禁止SQLite trace、authorizer/progress hook替换、SQL参数观察、业务字段裁切、预算/时钟/顺序修改。方法包装只读Python计数与高精度计时；不调用SQL、不记录参数、ID、原始文本、Scope或异常内容。方法仍恰好调用原方法一次，保持返回对象、异常和上下文管理器的enter/yield/exit顺序。目标是定位原父进程的热点，不是最终性能计时。

## 阶段与方法

包装StrictEngine._read_operation返回的上下文管理器，以原固定技术key划分阶段；未知key只记`other_read_operation`，不输出原字符串。记录每个阶段出现序号，以区分两轮和重复features阶段；阶段外记`outside`，其中包含fixture创建和诊断输出。

固定方法目录：LocalRuntimeOwners.check/control/configuration/principal/source_access、LocalEligibility._already、ToolLearningEligibility._metadata/_upstream/_check、PhaseReadSet.checkpoint/_probe/_sync_monitor、ToolLearningStore.validate_ref/read_artifact、ManagedConnection._run/_authorize/_refresh_registry。

每次进出方法或阶段，用perf_counter结算上一段时间到当前阶段、当前最深方法；因此方法互斥时间加上unattributed恰好分割观测wall，不把inclusive相加。另记录方法次数与inclusive时间，明确inclusive可重叠。阶段开始/结束读process_time，提供父进程CPU时间，区分等待与CPU工作；不在每次方法调用增加CPU系统调用开销。

阶段结束只读取Store._input_certificate_stats中的固定整数键attempted/issued/accepted/fallback/committed，保存前后值与差值。缺失或异常即unknown，不伪填0；不修改计数。原scale仍是业务是否成功、是否两次独立调用、预算是否超限的唯一事实来源。

## 保持原合成世界初始化顺序

原scale先固定datetime/UUID/磁盘探针，再导入产品与fixture。诊断工具不得提前导入产品，否则某些`from datetime import datetime`会绑定真实时间。使用仅持续到固定fixture导入完成的Python import包装，在原scale完成世界固定后、fixture.setUp前安装方法包装，立即恢复import。不改原scale文件，也不改SQLite注册表。

ManagedConnection方法包装安装在新连接创建前，原私有authorizer照原构造路径安装，不调用任何hook设置API。用真实隔离小端口验证receipt仍issued/accepted/committed且无fallback，防止诊断本身使本来要观察的优化失效。所有包装在退出后恢复；已有原生连接可能保留的Python方法引用在观察器关闭后只转发原调用。

## 输出与局限

默认诊断文件为原scale新输出目录中的`continuation-diagnostic.json`，包含原scale hash/工具hash、固定目录、阶段顺序/次数/互斥wall/CPU、方法exclusive/inclusive/count、receipt快照及原main退出状态。原业务结果文件不改。未能安装或方法缺失记录明确状态，不悄悄标全覆盖。

包装有额外Python成本，可能使原时间预留更早耗尽；本次只用于热点诊断，不能加入最终三次无观测计时，也不能据观测值精确预测最终加速比。计时是wall，阶段CPU仅为父进程，不含模型替身子进程CPU。

小测试覆盖嵌套/异常时间守恒、原返回/异常顺序、未知标签不泄露、延迟安装不提前导入产品、真实隔离登记receipt与账本不被包装改变。完成后冻结文件，等待主任务触发，绝不自行运行完整两轮。
