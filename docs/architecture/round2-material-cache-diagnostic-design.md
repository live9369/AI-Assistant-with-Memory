# 连续第二轮材料缓存与物理收费诊断

2026-11-12。只增加独立evaluation诊断工具，不改变产品、预算、observer、权限或查询结果。case9强证明152次全部生效，但assembly在216408900字节超过216408843字节（57字节），scan738780低于823167、time232140低于244538ms，仍余18字段；小端口收益不能代表整包。

诊断复用原counter-only Stage与原scale.main，原source/17/两轮参数完整转发，冻结世界后才安装Python包装。只在母进程聚合。SQL语句仅技术shape/query固定标签，不保存绑定值、业务文本或标识；已知nonce尾标记归一只影响诊断标签，绝不改变执行SQL。不安装SQLite trace、row observer或hook，不替换validate_ref/authority身份，不暂停计量或提高cap。

收费从原PhysicalReadMeter.consume的size/scan/items参数直接取得，并在finally统计已经收费的越界行。游标fetch与charge短栈区分SQL行和非SQL原件/产物；不再序列化SQL行。每Stage列出物理SQL top rows/bytes及非SQL分类，用实际计量对账。

PhaseReadSet只做后状态观察：facts精确/complete命中与miss、graph/prepared命中、admission需求与存入；remember成功、重复、callback/observer旁路、reusable关闭、key上限、byte上限、异常。成功size读取原fact_sizes/graph_sizes/prepared_sizes/admission_sizes。拒收次数与主原因全量，拒收size仅每namespace有限样本重算，明确sampled不是总量，避免诊断对百万拒收反复序列化大JSON。bounded producer未调用remember的miss仅报告partial/size/exception未区分，不伪造原因。

高水位分facts query、prepared tag、graph、admission、tracked blobs记录keys/bytes；记录每phase关闭前值、max total与reusable关闭情况。clear/discard/eviction后重建namespace快照，普通hit不遍历缓存；file优先与原4MiB/4096限制完全不变。只输出技术计数，无Ref、Scope或metadata key内容。

小测试验证：已收费失败行仍归属、无额外SQL/原件读取、返回/异常/iterator不变、trace-free原validator身份/known environment保持、实际强证明签发接受提交、cache命中/拒收/高水位有正负例、finally失败落报告。诊断时间含包装开销，不能当最终三次计时样本；唯一一次真实17/两轮只用隔离实例和替身模型，失败原证据保留。依据真实top与饱和证据再定优化，不先改eviction或投影。

## 小端口验证与使用

最终5项小测试通过，约0.62秒，覆盖nonce归一、已收费越界行归属、invalid size原异常、原validator身份/known environment与真实strong证明、cache byte拒收采样/highwater、失败落报告。另实际deep8四模式基线与包装各自业务精确差分通过，scan/items/bytes与strong/UUID/graph计数不变；聚合SQL+非SQL收费3810024字节、13169行，与原meter actual逐项精确对账。CPU单次5.070→5.673秒（约11.9%开销），诊断时间不能替代最终性能样本，也不因此提高预算。

证据：outputs/acceptance/performance-round2/continuation/material-cache-diagnostic-proof-01/result.json、material-report.json、final-tests.log。原产品和scale/replay未修改；工具使用原case参数，仅入口改为evaluation.tool_learning_material_cache_diagnostic，可额外指定--material-output与--rejection-size-samples（0—32，默认8）。默认输出material-cache-diagnostic.json，与continuation-diagnostic.json及原result/failure证据并存。

最终named loader为full443/focused239，未因此新跑完整统一；仅验证新增工具与真实小端口，真实17/两轮由主任务唯一调度。工具全部Python已冻结。
