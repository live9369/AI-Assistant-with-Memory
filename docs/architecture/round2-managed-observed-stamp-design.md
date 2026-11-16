# 小型受管连接观察戳

状态：窄 CPU 去重设计。`observed_stamp()` 返回 `(configuration, schema_epoch, write_sequence, closed)`，专供已受约束的材料签名租用检查。每次仍调用 `_refresh_registry()`，保留全部全局 adapter/converter 变化检测；不创建完整 monitor_state 字典，不访问事务/账本和 native 属性，不执行 SQL。

它是观察值，不是证明，不替代 known_read_environment、完整 checkpoint、文件/控制探针、来源核对或权限检查。原 monitor_state、唯一 SQL nonce、写表证明、receipt 和预算均不变。只省略消费端不使用的完整观察字段构造；不得据此把未知环境认证为安全。

独立内存 SQLite 测试比较该元组与 monitor_state 对应字段，覆盖普通写、未知 trace 配置、实际 DDL、关闭连接和全局 adapter 登记/恢复；trace 确认观察操作不执行 SQL。

补充两个明确入口：`material_revision()` 与 `observed_stamp()` 一样刷新 registry；`observed_material_revision()` 只返回已经观察到的四字段，不刷新。后者仅允许已约束的文件边界 lease 使用，因为单纯全局 adapter 注册不修改文件；下一次实际 SQL、facts、cached_artifact 和完整边界仍须保留原刷新。公开 hook/factory 配置立即改变 configuration，关闭立即改变 closed。无刷新入口不得用于 Ref、metadata、facts、权限、receipt 或已知环境认证。测试明确展示 adapter 注册时无刷新戳保持原值，而刷新入口立即发现变化，防止两种 API 语义混淆。
