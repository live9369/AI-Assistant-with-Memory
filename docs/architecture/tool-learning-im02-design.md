# IM02 实现说明：冻结契约的纯类型校验

2026-11-09；TL-LOOP-0.1。依赖IM01已验收；用户实施授权只覆盖普通实现与隔离验证，不覆盖真实模型、正式评测、迁移或当前实例。

## 文件分工

- tool_learning_types：严格JSON、基本标量、Slot/Ref/来源定位、Scope/Claim、控制/预算等基础结构。
- tool_learning_products与可选operations：四类M14产物、决定/表示、请求/响应/召回及十项操作的payload结构与局部交叉字段约束。
- tool_learning_contract：统一公开入口，拒绝未知类型/版本，不将结构结果转换为业务资格或授权。
- 对应纯测试使用构造JSON、固定有效字段和正反例；测试不打开任何实例、不运行推理或工具。

先设计后实现，公共validate返回原对象且不修改；loads严格解析重复键、非有限值和非法Unicode；规范指纹与现有JSON序列化完全一致。只应用冻结文档明示约束，不凭实现方便擅自添加“任意长度”等限制。

## 核验范围

强制必需字段、封闭枚举、精确类型（bool不是int）、UTC日期/精度、ID、摘要、有限数、定位区间，保留0/false/已知空与不同缺失原因。Slot的known/null只在允许原始null的字段及理由下成立；其他字段不凭null装作未测。

new目标无旧对象/预期版本，existing必须有匹配对象/版本；Product类型/owner、Decision状态与引用、Representation系列及版本、Recall用途/版本/字段、measured gain及下游资格轴不能靠互相推导。具体业务状态变迁仍交后续所有者实现。

## 不是本项的通过声明

校验Principal.module、Ref格式、source_check或Decision=accept，只证明形状/局部语义正确，不证明实际身份、权限、原文存在、证据支持、FK/CAS/事务、停止/预算剩余或真实评测通过。这些核对保持IM04—IM19责任。使用方不得因validate成功就写数据库或派发模型。

不修改旧domain.contracts的兼容行为，不更改冻结文件。若发现无法从规范解决的实质冲突，先记录/裁决，不在代码中暗改政策。
