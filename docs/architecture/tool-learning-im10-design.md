# IM10 M04用途限定召回、只读审计与输入依赖设计

日期：2026-11-10；V0.1。冻结依据TL-LOOP-0.1 §6、Q08、storage §119；前项IM09统一455项通过。只合成隔离库，不调用模型/真实工具，不操作当前实例。

## 入口与控制边界

`ToolLearningRecall.recall(entry, RecallRequest)`返回冻结RecallResult。execution与controller_audit显式分支，不复用会prepare/编码公开回复/修复索引的旧Memory.retrieve。默认RecallAuthority拒绝实际入口、用途/recipient、Scope匹配、原来源材料、预算机会和retention。

execution必须绑定真正activity_ref/context_ref及其原account，受stop/lock/cancel/Control/总deadline和共享预算约束；不每retrieval新建额度。controller_audit必须实际controller、限定history_audit/verify_source/evaluate，允许停机/唤醒锁下只读检查，仍核当前权限/Scope/erase等来源屏障。审计仅请求给定有限上限，无账户写入、模型派发、输入登记、run/item/event/访问/索引修复或其他业务写入。

## 用途和材料

recall_experience只返回真实accepted、当前M03 head/精确C2表示head、ready且整组ready、用途及recipient当前合格的accepted_content。C1正文不作临时普通表示；旧cognition shadow不是TL经验替代。recall_episode走原有真实memory_revision原文字/经历，verify_source可读合法原记忆承载来源，保留原始性质，不伪造M03引用。evaluate/history_audit可在明确权限内查看candidate/history/shadow，但不得usage_state=current。

原memory.kind/revision、权限、Scope与来源由实际M04/源所有者核验，不能用相似标签猜类型/身份。已知false、0、null与unknown/withheld/conflicted完整保存。索引端口不可用时，仅明确授权index_fallback=bounded_primary才有限主库回退；不修索引、不拿近期无关项凑数。相关性是确定性词/汉字片段或精确Ref匹配，不是事实概率。

版本current/specified/as_of按真实内容与表示版本、时间界限处理；不凭写入时间伪造世界新旧。Scope匹配由可信语义端口确认，未知不合并主体或单位。每项正文/来源性质/Scope/未知/局限/证据整体打包并计byte/token上界，装不下整项去掉并报partial，不能裁掉限制。k=budget.max_items，scan/bytes/time及token计数均有上界；无相关结果保留限定覆盖/空原因，不声称世界不存在。

## 持久化映射与只读审计裁定

冻结tl_recall_item只接受真正memory_revision或tl_representation目标，memory_retrieval_runs要求真正activity/context。execution对合法映射写真实run+tl_recall_item、固定依赖；旧memory路径保留类型正确的retrieval_result/access轨迹，不将表示UUID塞旧外键，不重复计算命中/独立证据。

无memory/representation映射的独立原件、未发布candidate或旧shadow只能在授权controller_audit临时投影，retrieval_run=NA、临时条目ID不冒称持久化；审计绝不写runtime_event。execution遇该缺口明确覆盖不足/not_ready/unavailable并按权限公开，不返回无消费轨迹却可送模型的正文，不造wrapper、记忆或context。此为本版支持范围边界，不改冻结/DDL。

正常召回的固定技术审计写入口只写run/item/旧文字访问及派生依赖，无任意回调或业务表grant，不走M17禁止的generic execute(recall)。材料持久化前同gate重新核当前资格/retention；任何失败无半次trace。公开诊断不泄漏隐藏ID/正文/精确数量，默认公共覆盖仅计可公开条目，内部扫描/实际用量由可信计量记录。

## 当前资格与实际输入

execution沿IM06实际source token、指定native修订支持路径、所有active屏障和recipient用途核验。audit用独立默认拒绝的audit authority，读取同一受限依赖图、真实版本和全部相关屏障，但不调用普通执行停止检查；不能借审计绕过erase/Scope未知。

`register_inputs(entry, recall_request, result, target_request, final_principal, field_prefix)`是独立正常受授权装配入口，审计结果禁止登记。对每个完整返回项重新核真实持久tl_recall_item/原run、精确source token/Scope，实际final purpose/recipient再次授权，再登记TL-DEPENDENCY-1 read边及tl_input_dependency。仅召回返回不等于模型上下文已使用；IM11在实际独立LLM调用入口/返回使用仍必须IM06 callback检查所有实际inputs，部分登记失败不得派发。

## 验收及后续

隔离验证真实C2普通命中、C1未ready不得直读、组未齐/withdrawn/过时版本、用途/recipient/Scope/源F1、旧memory合法类型及不升级shadow、停机审计完全无写、无真实context执行拒绝、scan/k/byte/token/time整项边界、空/partial/故障区分、audit禁止输入登记、实际input依赖登记后F1阻断callback。真实索引、来源/Scope/审计权限、tokenizer与共享预算实际meter默认拒绝，IM11接线；本项不声称模型已使用/答对/学习收益。


## 实现定型：真实机会、读取和装配

正常执行增加固定技术`begin(entry,request)`：在真实activity/context下保存real memory_retrieval_run及请求指纹，不产生认知、模型或学习活动。IM11必须用此真实run在原work/account预留八维retrieval机会并记录实际本地入口，再调用recall。`execution_reservation`默认拒绝且必须返回原账本中的known ID；服务核kind=retrieval、同实际run/account/work、仍reserved且entry已知，读取cap取**本次自己已持有slice**，不将post-reserve全局remaining=0误判为无权使用自己的额度，更不返还他人的占用。每次实际查询的read_entry用独立短事务保留，后续查询回滚也不消失；同一次entered机会禁止再次读，重放也须新真实机会、沿原账户结算。该控制事件不是检索完成或模型上下文进入证明。

目前无tl_work的legacy normal activity没有真实八维读取账本，正常新召回明确拒绝，不凭request猜额度。IM11只能在新schema4普通activity创建时按真实初始policy/caps一次绑定原account读取账本；旧活动欠缺scan/bytes等不得补0、猜额度、换account或每query建cap，兼容旧路径交IM15/16明确处理。audit不受此账本依赖，仍完全只读。

同一调用的artifact reader统一覆盖M17、资格metadata、屏障payload/Scope、legacy原件和语义端口；受控row reader对固定允许表先核逻辑UTF-8字段字节再读取。所有资格检查（含输入登记内部检查）共用请求剩余scan，所有实际artifact读取扣byte；回调/读取前后核deadline/单调耗时。元数据按当前授权读一次后可缓存同次不可变Scope/固定组清单/已验正文，缓存不替代任何权限、epoch、head或group.state检查，结束即清空。公开不报告隐藏扫描量，逻辑字节上界不冒称OS页读数或供应方费用。

公开查询统一报告有限partial覆盖，scanned仅为可披露条目数，truncated仅指已获资格的完整输出项因打包上限被移除；隐藏对象/拒绝次数/索引枚举截断不改变公开completion、coverage、gaps或empty_reason。不存在Ref与无权Ref同样不公开。仅明确获对象元数据权限后才能说明C1未ready/材料损坏等。空结果不证明库或世界不存在。

as_of按实际accepted/recorded/published持久时轴选时点前正确版本，同series不把全历史凑多项；不是世界发生时间。specified已知Ref.revision必须实际登记匹配。重放仍核真实当前head/类型/Scope及retention，不能让旧current永久有效。组的固定清单、每成员当前M03与表示head、当前资格逐一受同meter核验，group.state=ready不是永久许可。其他成员当前tokens进入选择项依赖并保留其实际Scope，F1即使F2尚未改组标志也能阻断输入。

旧文字的全部source_refs tokens和访问依赖进入RecallItem/trace/input，不能只留memory token。delete-only保留为relations及派生删除路径，普通unavailable/revoke不当作事实支持失效，erase仍阻断拷贝元数据。实际input同时登记完整tl_recall_item为source的whole-item字段与各实际读来源，完整项摘要与body摘要分别精确绑定；保留删除路径不将delete改read。

输入装配全量预检后才开始逐项登记，target必须是该活动当前prepared thought_request。具名binding端口得到field_prefix、target hash/state revision、全部item/source清单和manifest指纹，实际Owner核完整字段。部分登记失败可留追踪事实，绝不返回装配成功/可派发证明；IM11必须另持久化完整assembly完成标记并在实际callback/结果使用处核对全部实际inputs，prepared或部分登记不能派发。查询返回也不冒称已进上下文。
