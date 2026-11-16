# 实际完整流程的低频CPU栈采样

2026-11-12。小端口JSON/copy候选实际仅约5%，不据此合入额外产品或盲目全流程。本轮只增加独立evaluation采样工具，复用原continuation counters-only少量Stage钩子，绝不复用material百万次方法包装。

仅主线程、POSIX SIGPROF/ITIMER_PROF、原handler为默认/忽略且无已运行timer、无SIGPROF屏蔽时启用。未知环境拒装。最终使用20ms process CPU timer；最初5ms微测有8.7%观测开销，故已降频。handler只看frame的code文件/函数/首行/当前行与完整f_back链、Stage ordinal，计数一次完整stack；不看locals/参数/源码、不查DB、不调用source或validator。代码目录、唯一样本stack数和最大帧数有界；超界、无frame、重入和错误明确计数，不伪装完整数据。

这是近似Python-stack CPU采样：timer按进程user+system CPU计，可能包含其他线程；Python handler只主线程，C调用/GIL可延迟/合并信号，不能看C内部。stack祖先inclusive份额不能相加，count×5ms不当精确秒。独立process_time与monotonic和原Stage CPU/wall并存。所有采样开销仍在原meter里，不暂停或提高预算，不能作最终三次计时。

finally先停自有timer，在保留自有noop handler期间屏蔽并排空自有pending SIGPROF，再恢复原mask与handler；拒绝已有timer而非夺用，测试默认handler恢复后不会被自己的迟到信号终止。异常/中断也落JSON并保留原scale业务结果或失败证据。

小测覆盖支持/拒装、handler只读stack和overflow、原handler/timer恢复、原validator身份与真实强证明、异常落报告及确定工作量微测开销。随后唯一实际17/两轮只采样，不改产品。报告用于真实assembly2栈比例定位，再做定向优化。

## 实际小测与降频

必要6项全通过约0.406秒，包含subprocess20次默认handler/timer恢复与异常退出、无active抢占、样本/code/深度边界、真实strong1和原validator身份、setup失败落报告。5ms的40层固定工作量三次观测中位CPU0.455573→0.495211秒（+8.70%），因此不使用5ms实际采样。

按主任务指示改默认20ms，仅一组约0.4秒固定工作量复验：baseline0.446682秒、sampled0.446579秒，20个样本、无loss，观测差异处于噪声（-0.023%），不能宣称负开销。默认值单项delta通过；无需再三次微测或四模式。证据statistical-cpu-proof-01与statistical-cpu-proof-20ms-01。实际长run仍只诊断，不算最终计时。

当前全部Python冻结，named loader full460/focused256仅登记新增6项，未再运行统一。产品、JSON算法、copy端口、SQL监视/nonce与权限均未改变；前面约5% CPU候选仅存研究证据。
