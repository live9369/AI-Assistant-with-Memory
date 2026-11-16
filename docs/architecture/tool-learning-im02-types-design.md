# IM02 基础类型与内存定位校验实现说明

2026-11-09；依据冻结TL-LOOP-0.1。纯领域模块 `digital_life/domain/tool_learning_types.py`，不导入应用或基础设施，不访问文件、数据库、网络、实例或模型。

提供严格JSON读取、参考Python编码指纹和基础类型校验；校验返回输入原对象，不补缺键、不归一化文本、不修改调用者载荷。拒绝未知字段、缺必需键、重复JSON键、非法Unicode代理、NaN/Infinity、bool冒充整数及未知契约类型。仅对规范明文限制的字段设置长度/数值边界。

Slot按冻结字段完整校验：非known值为null且reason非空；reason_code属于冻结枚举，不增加规范未写的逐状态Reason映射。known/null仅在调用者声明字段允许JSON null且reason_code=source_reported_null时接受。结构合法不证明来源真实、内容正确、权限存在或M03已接纳。

Ref.kind是非空类型名，注册性和跨实例授权由后续M12/IM04核对。EvidenceRef对工具来源强制已知原结果/回执；非工具对应字段not_applicable。视图引用与摘要独立保留Slot未知/未采集状态；结构校验不强制同时known，也不从单项已知推出可用。真实视图/摘要匹配与处理准备度留给IM04/IM07/接纳门，它不证明artifact实际可读或摘要正确。

Locator分结构校验与 `resolve_locator(locator, view)`：后者只处理给定内存字节/Unicode文本/JSON对象，核对半开区间和quote、RFC6901转义/键/数组位置。whole_artifact可原样返回调用者明确提供的bytes，不解析任意媒体；它不会隐形解析嵌套JSON字符串，调用者须明确构造新视图。只定位不授予whole_artifact主张或任何新执行许可。

Product及操作包装层由另一模块负责，基础validate仅派发基础命名类型，避免循环导入。针对性测试覆盖合法/非法/未知值、引用关联、JSON与Unicode、时间格式、定位边界及输入不变。
