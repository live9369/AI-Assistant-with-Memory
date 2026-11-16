# 失败后的输入登记进度诊断

状态：先设计、后实施；仅修改隔离scale诊断与小测试，不修改产品或主replay。日期：2026-11-11。

## 目的

连续第二轮已两次在assembly原字节预留停止。旧诊断只留下预算和首轮输出，无法说明第二轮完整包、计划字段和实际登记到哪里。增加只读失败快照，避免靠继续重跑猜测还差多少。

## 边界

- 只在scale异常处理、Engine调用已退出且物理meter已关闭后执行；meter仍活动时返回unknown，不让诊断消耗或规避业务预算。
- 原budget/requests/attempts及raw捕获保持，诊断结果附加在失败快照中。成功路径和主replay不动。
- 不调用prepare、assemble、资格入口或回调；不创建事件、工件、依赖、UUID，不改变世界时间、计费、ledger、状态或事务。只向新的外部诊断输出目录保存已观察材料。
- 原失败与旧输出不覆盖，新harness hash与旧版不同，应明确只增加异常后的诊断；旧三次计时harness不变。

## 能观察到的材料

逐一读取失败activity实际thought_requests（按主库rowid），导出其实际request_artifact字节并验证storage hash/size。查找已完成assembly事件中的实际manifest；若没有完成事件，可读取该次StrictEngine owners.read_opportunities中真实保留的manifest。两种来源均须匹配request.input_manifest_hash，并用实际packet重新validate_manifest；来源和失败原因完整记录。既无持久化manifest又无实际内存材料则标unknown，不从字段模板或固定常量重建。

依赖表只读取当前instance与request：

- tl_dependency：保留真实rowid、全部行字段、metadata原件及其中source token/ref、scope、relation、purpose与field_path。
- tl_input_dependency：保留真实rowid、全部行字段、retention_state、body_digest及source/ref/revision/epoch。
- 按raw field_path汇总两类行数、顺序与retention状态；另按完整manifest原顺序逐项核对预期dependency、非delete输入与实际登记行。

request创建事务已有的`field_path/index`上游链不是assembly的精确`field_path`登记，不可混算为后者完成。匹配dependency须保留实际metadata.expected、scope、relation、用途与路径；输入匹配保留source/revision/epoch/field/digest/用途，其recipient和retention作为实际事实输出。重复manifest期待逐项报告，原始行数另列，不假设一项必然对应一个新行。

## 结论的精度

能报告完整字段/有依赖字段数、已有登记/未开始/部分登记的manifest序号、仍缺的dependency/input期待，以及所有rowid顺序。行存在只证明该行已提交，不是资格、授权或整个assembly成功；没有完成事件时明确assembly_complete=false。manifest缺失时预期总量/剩余量保持unknown，只列真实已有行。

小隔离fixture验证：使用真实临时Store、真实request/packet/manifest和部分登记；快照前后ledger与total_changes不变；packet来自实际原件、进度区别原始上游行；缺失manifest明确unknown；活动meter拒绝诊断。保持原断言，不运行完整思考或真实模型。
