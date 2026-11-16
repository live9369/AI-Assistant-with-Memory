# IM02 产品、请求与操作校验详细设计

依据TL-LOOP-0.1冻结契约；本项只实现纯领域结构与局部跨字段校验，不接数据库、权限服务、模型或运行实例。JSON自报M03/M14不是授权；来源支持、实际测量合格、当前版本与权限仍由后续业务门禁决定。

`tool_learning_products.validate(name,value)`返回原对象、不填默认值或改写输入；失败抛ContractError。支持Product及其四类body、Comparison、Decision、Representation、Envelope、Response、RecallRequest/Result/Item及基础类型。`loads`先用基础严格JSON解码，再按名称分派。

Envelope没有operation字段，因此裸Envelope仅检查公共结构；`validate_envelope(value,operation)`和`validate('<operation>.request',value)`按九项写操作检查payload；recall例外直接采用RecallRequest，不额外套Envelope，避免给冻结schema擅加字段。操作payload由独立tool_learning_operations模块负责，无IO。

重点不变量：new目标不伪造旧引用，existing目标及预期对象一致；accept的八项G检查均pass，候选/拒绝等不能携带当前表示义务，reuse必须引用既有内容版本；known gain只有measured且有known measurement_ref，0和负数合法。召回候选/历史/shadow不混为当前事实；普通经验请求只能要求accepted_content，audit用途受限且不产生副作用。

校验分层：基础模块维护Ref/Slot/Scope/Check等公用类型；包装层不反向依赖应用或基础层形成循环。指纹只作严格JSON值与有限数值检查，不证明来源独立、内容真实或调用者有权。

验证使用手工构造的封闭数据样例、字段丢失/多余/错类型、分支矛盾、数字边界和输入不可变性。测试不打开任何实例、不调用真实模型，不将纯类型通过当作业务闭环完成。

已知content/memory对象与对应VersionToken.object必须同实例、同ID、同kind；表示版本引用与其稳定系列ID本就不同，不作错误相等比较。reuse允许引用既有表示义务，但是否已存在且当前合法由业务层核对，类型层不创建新义务或把复用当新接纳。
