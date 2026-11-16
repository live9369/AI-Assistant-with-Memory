# 新实例严格初始化

`prepare_new_strict(root,name,model_config)` 仅接受尚不存在的新目录及显式模型配置，先原子建立新目录与 WAKE_DISABLED。拒绝已有目录/实例，不提供存量自动迁移。失败保留目录和禁止唤醒锁，不回退删除历史或自动重试采用半成品。

按生产路径 Store.prepare 建立 schema2/身份/原 bootstrap policy → Control 建立停止状态 → 已有 approved migrate(target=3) → 显式 Store.tx 逐完整 SQL statement 安装 tool_learning_v1.sql，记录原文件 SHA256 checksum 的 schema_migrations v4 和 schema.expanded 事件、PRAGMA user_version=4、foreign key检查 → 重开 Store 更新 columns。

新 policy 保留 bootstrap scope，再加入 TL-STRICT-RUNTIME-1 和既定 ordinary caps：200000 input/200 output/8 attempts/8 tools/2M scan/2M items/512MiB/600000ms。启用现有八个生命服务，健康磁盘阈值使用 GoalRegulation 默认64MiB，维护仍默认不自动修复。configure_model(check_available=False) 建立严格 schema4 显式 model_version 路由，不探测、不调用模型。

CLI `prepare --strict --model-config <path>` 选择新路径；原 prepare 不变。不部署、不 resume、不启动 worker。返回仍打开的 Store，由调用者关闭。2个独立 TempDir 测试验证完整 schema/关联/锁/停止/八开关/原scope和cap/真实默认健康阈值/显式模型版本及无probe，已有root拒绝且不修改。
