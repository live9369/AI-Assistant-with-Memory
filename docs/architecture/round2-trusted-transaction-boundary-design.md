# 受信写事务与共享材料生命周期修复

状态：设计、实现及98项局部验证通过，等待统一PF06。仅新建合成夹具，不操作正式实例、调用真实模型或执行fullthink。

## 发现的问题

PF06 named11的4项既有F1验证失败，并非应拒绝的来源：ToolLearningStore.execute通过自己的COMMIT结束真实F1写事务，而新readset在事务内读取时已更新total_changes。COMMIT后observer／WAL变化被误判为外部写，导致合法r2及delete-only路径被拒绝。不能通过猜测“这次看起来像own COMMIT”放宽外部旧snapshot保护。

另外total_changes不会因ROLLBACK减少：在临时写入内验证过的新Ref、依赖行和metadata准备不能在回滚后复活，旧lazy iterator也不能穿越真实事务结束交付旧事实。

## 明确的边界通知

ToolLearningStore.execute在实际BEGIN前checkpoint，只在本adapter确定完成COMMIT或成功ROLLBACK后显式通知transaction_ended；通知位于blob cleanup前，cleanup后仍检查变化。未知commit／failed rollback关闭phase、清对应映射，保留原CommitUnknown与文件保留／原命令协调规则，不自动重试。已有body异常时，通知错误不能覆盖原异常。

Store.tx显式记录rolled_back，outer结束传递真实结果；nested savepoint成功不当作outer结束，nested rollback立即失效其临时材料。原primary data_version、独立observer、数据库／控制库／工件身份变化探针未弱化；foreign连接／进程提交和未知raw COMMIT仍拒绝。

## 回滚、Ref与物料

每次明确outer COMMIT或ROLLBACK都清对应_REFERENCE_BOUNDARY.cache，不靠total_changes推断旧Ref仍有效。COMMIT可保留持续工件身份与hash证明下的原始bytes；ROLLBACK清phase全部facts、graphs、prepared、admissions、metadata、raw bytes与文件跟踪，避免清理删除回滚新文件后误报，或复用未登记物料。清的是优化材料，不改实际meter消费、unknown或任何业务预算。

nested rollback同样清pureRef及全部临时材料，但不更新observer／primary baseline，不重置额度，不清除foreign变化证据。旧phantom dependency／artifact即使作为Python对象仍被持有，也必须重新经过真实登记读取并拒绝。

## lazy读取的独立结束代次

phase有单独transaction_generation，仅明确outer受信结束递增；正常nested snapshot savepoint成功不递增。另有rollback_generation，真实nested rollback也递增。lazy cached／physical row iterator捕获创建时这两个代次，每次尚未消费的row以及absence交付前检查；旧iterator不能在COMMIT／ROLLBACK后复活。

不按每次total_changes粗暴中止迭代，不给trusted busy标记豁免outer事务结束。生产calculation本来持有outer事务，内部技术snapshot属于nested；全8模块严格差分用于确认来源捕获和字段没有被这个边界删减。

## 局部验收

4个既有F1失败case单独恢复通过。新增14项覆盖真实F1 commit合法后续、F1／普通Store rollback新Ref与物料消失且不退款、nested rollback phantom dependency／metadata／iterator拒绝、正常nested成功、unknown commit、failed rollback、foreign pre-BEGIN／post-COMMIT／blob cleanup gap／post-ROLLBACK及原body异常保留。

新增及既有fault／readset／review／collection／configuration-reader／calculation-sharing合计98项通过（54.921秒），0失败／错误。包括完整8模块values、features、fields、live、新字段、依赖、capture uses、permission uses、snapshot、selector／version、UUID序列和caps严格差分；真实计算没有模型调用，未知raw COMMIT仍保守拒绝。

产品改动限readset、ToolLearningStore和Store.tx的边界状态；未改Engine、contexts、meter计费、版本判定、数据选择、stage份额或总cap。此结果不代表完整共享／连续负载已通过，须由统一PF06及后续完整场景再次验证。
