# 数据库实现基线 V0.1

该目录包含数据库逻辑架构的可执行展开。Runtime 160 张业务表、一个 FTS5 虚拟索引；Supervisor 6 张独立控制表。FTS 自动产生影子表，不计入业务表数量。

## 文件入口

- [Runtime 建表 SQL](runtime.sql)
- [Runtime 完整字段字典](runtime-field-dictionary.md)
- [Supervisor 建表 SQL](supervisor.sql)
- [Supervisor 完整字段字典](supervisor-field-dictionary.md)
- [关联、约束与数据流验证报告](validation-report.md)
- [机器验证结果](validation-results.json)

环境要求为 SQLite >=3.37、STRICT、JSON 函数和 FTS5 均可用；不同编译版本须检查能力。测试版本记录在 validation-results.json。

## 生成与验证

在项目根目录运行：

```sh
python3 scripts/development/build_database_schema.py
python3 scripts/verification/validate_database.py
```

生成器内的明确字段规格是维护源。修改字段、约束或触发器时，修改生成器并重新生成 SQL 与字典，避免三份文件漂移。生成过程不修改实际业务数据库。

SQL 用于创建全新数据库，不是升级现有数据库的迁移脚本，也不提供 IF NOT EXISTS 掩盖结构不一致。Runtime 与 Supervisor 必须连接不同数据库。

每个连接都需要 `PRAGMA foreign_keys=ON`。WAL、busy_timeout、备份和连接线程归属由运行层初始化；SQL 中不把 journal_mode 设成持久部署决策。建表事务执行失败后调用方应回滚并停止初始化。

## 首次初始化与业务事务

外键为延迟校验，允许在单个事务内创建相互引用的对象及版本。首先建立 identity_instances，自引用的 instance_id 等于 id；普通业务行由 AFTER INSERT 触发器自动登记到 object_registry。不要为同一业务行提前重复登记。

需要跨版本的稳定抽象配置对象（例如人格 profile_object_id）先创建 object_registry 根节点，再插入版本。观察、信念、概念、记忆版本及人格／价值／身份锚点版本会自动登记到 object_revision_registry。一般日志和测量不是版本对象。

当前版本初始允许为空以解决创建顺序，Repository 必须在发布为可用对象前补齐。提交前检查所有必需业务条件，不能把“暂时可空”当成完整对象。

目标、意图与承诺初始状态序号为0。状态修改必须插入 transition_no=当前序号+1 的转换记录，触发器核对状态、边界与序号并更新父表。禁止直接 UPDATE 状态绕过历史。

决策先为 draft，写入全部候选，最后 UPDATE 为 finalized。定稿检查概率总和与唯一选择，随后冻结候选；动作意图只能引用已定稿的可执行选中候选。授权有效性和工具实际前置条件仍必须在执行前由权限服务重验。

## 数据清理与授权边界

普通修订追加新版本。确需删除内容时，删除服务验证用户权限后创建 cleaning 状态请求及 operation=redact/purge 的作用记录，再清理内容；FTS 触发器同步移除旧文本。数据库只识别该流程标记，不验证调用者操作系统身份，不能把触发器当安全沙箱。

同意清理不允许改变版本所属对象和序号。仍被引用的版本应优先脱敏而不是物理删除。附件、派生摘要、日志、WAL、备份及向量索引需要删除服务另外处理；通过局部 FTS 删除测试不等于全系统数据已擦除。
