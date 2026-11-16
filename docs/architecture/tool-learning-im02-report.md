# IM02 实施与纯契约验收报告

2026-11-09。状态：完成；不是TL业务链已打通。冻结规范未改动，当前实例未被打开、更新或唤醒。

三路并行：基础类型/JSON/内存定位器；Product/请求与操作包装；独立只读复核。主agent负责统一API、请求操作适配、门控与证据。

## 已实现

- 严格JSON拒重复键、非有限数、Unicode代理；规范指纹与sha(dumps(value))一致，不做Unicode归一化，大整数不暗转float。
- Slot保留实际0/false/空值与缺测，已知null仅用于明确允许的JSON原始null；字段缺失不是unknown。对view/digest独立缺测不过度收紧为结构非法。
- 精确引用、版本/依赖局部一致性、UTC及已知时间边界；resolve_locator仅处理给定内存视图，不读文件/DB、不隐形解析嵌套JSON字符串。
- 四类Product、Comparison、Decision、Representation、Envelope/Response及Recall封闭字段与局部条件。candidate/reject等不能伪造当前表示义务；measured/known gain需要相应引用，0与负数保留。
- 九项写请求使用Envelope，recall为独立只读RecallRequest。表示记录ID与系列ID分开；复用已有义务不冒充创建新义务；独立项允许group_ready不适用，真实组条件仍留后续模块核对。
- 公共入口tool_learning_contract.validate/loads/fingerprint/resolve_locator/validate_request，不修改旧domain.contracts行为，不修改模型提示、数据库或实际选择。

## 验证及范围

首次统一81项通过；随后补Envelope与resume_work/record_effect.payload.work、admit用途的局部一致性反例，独立复验82项通过。全部无失败/错误/跳过；相关源码在验证期间稳定。证据：outputs/acceptance/tool-learning/im02.json及同目录im02-recheck-*.json，历史证明保留。

结果只证明纯结构与可由给定值判定的局部矛盾检查，不证明Ref实际注册、授权真实、来源可读、摘要匹配原制品、语义支持、C1/C2/FK/CAS、预算剩余或当前资格。下游仍须按IM04—IM19实际核验，不能因validate成功派发模型或写业务状态。

IM03与IM17依赖门已解锁并开始独立准备/实现；真实模型、正式标签/盲评、正式组和当前实例操作授权没有因此打开。
