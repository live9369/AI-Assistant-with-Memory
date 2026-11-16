# 合并运行契约的下一版数据库

本目录由 `scripts/build_system_schema.py` 生成，保留原完整生命模块表，并合并独立思考、活动修订、动作审批、预算、持久事件、租约与控制面交接所需字段。与 database/runtime.sql 和最小原型数据库均为不同版本。

当前只验证全新建库、结构字段和完整性，尚未编写现有实例的升级迁移，也未将完整 Runtime 服务切换到此模式。禁止直接覆盖 work/primordial00/runtime.sqlite。

- `runtime.sql`：完整模块表加运行增量。
- `supervisor.sql`：独立控制库加唤醒与输入交接表。
- `runtime-field-dictionary.md`、`supervisor-field-dictionary.md`：同源字段字典。

## 当前边界

包含基础外键、类型与枚举、原约束触发器、accepted 思考条件唯一索引和事件去重。新增接口的全部跨行状态机、响应归属、世代检查、发布校验及执行门禁尚未全部强制；后续仍须补充 Repository 与约束测试。建库成功不能等同于运行协议全部实现。

新库目前没有部署到任何生命实例，没有触发模型调用或唤醒工程。
