# IM16 隔离迁移与兼容回退实现报告

日期：2026-11-10。范围：仅新建合成命名空间；不读取或迁移正式实例，不调用真实模型，不安装后台服务。

## 实现与授权

`tool_learning_migration.py`提供封闭创建能力。已有路径、实例嵌套、symlink祖先、替换marker/inode、运行中实例和缺唤醒锁均不能成为迁移目标。真实版本2由项目保存DDL创建；版本3必须经原2→3迁移，且校验记录及实际三项历史DDL一致，不能修改PRAGMA伪装。操作须真实当前Bearer、当前controller、停止且无未核对进程，以及已核schema4前进/回退发布工件。

迁移备份先生成独立SQLite快照和包含所有登记blob的ZIP，按真实page_size和有限scan/bytes/time计量、逐blob及ZIP回读核验后才登记为完成备份；发生中途失败，Control命令保留本次独有的两个路径与真实失败/消费事实，不把残件称完整或自动删除。备份不是旧库恢复许可。

一个主库事务逐statement执行V3与冻结TL DDL，记录迁移、复制原policy但默认关闭新学习、校验真实布局/完整性和全部旧行。身份、原记忆/证据/历史、未来承诺/审批、shadow、原账户不改写；不为旧活动补八维额度，不把shadow采纳为事实。提交后确认丢失会保留真实已提交状态，下一次只按持久版本/校验和/布局幂等核对，绝不恢复旧库。

`rollback_code_isolated`是停止状态的具名离线发布选择审计，明确`activated=false`，不冒称已启动。实际运行与失败回退继续使用现有`Deployment`：专项包含迁移后真实前台idle Runtime启动、心跳、用户停止；另用明确确定性driver注入replacement失败，核真实Deployment状态机重新选择已核bridge且主库字节不变。这些不是两个不同生产代码版本的认证，也不构成正式部署验收。

## 发布字段依赖修正

新release顶层精确数组`capabilities:["TL-LOOP-0.1"]`补齐冻结字段；拒绝bool、unknown、重复及额外能力。旧IM15工件只有当前Control原baseline记录、原manifest和真实barrier合同精确一致时才能投影有效能力，原工件不改写，未登记缺数组candidate不能使用该兼容投影。旧无保护2/3 source update缩小能力时同步移除数组。IM15原完成证据保留，由本项及IM19追加受影响复验。

## 真实链与边界

迁移同一个目标中用真实原账户建立C0、四Product、真实Bearer控制者复核C1和C2；随后通过明确mechanical authority构造F1，验证新历史/屏障/epoch/九域义务和原账户在离线代码选择及拒绝旧库恢复后原样保留。C1/C2走具名现有owner；F1机械端口仅验证迁移后持久保护，不冒称新增M12真实授权（真实M12授权已由IM12/13专项覆盖）。无实际LLM调用。

原迁移备份恢复入口明确拒绝，不以早期快照绕过后来撤回/擦除。真正恢复仍须现有IM13当前Control和镜像外当前可信排除；本项没有在旧快照上重建新的权限或排除历史。

## 验证记录

专项：`PYTHONPYCACHEPREFIX=/tmp/im16-pycache python3 -m unittest tests.test_tool_learning_migration -v`。统一验收：`python3 scripts/verify_tool_learning_task.py --task IM16 --complete`。最终实际数量、耗时、源稳定和完整命令以不可变验收JSON为准。

开发中保留日志：最小2→4首次通过；语义夹具曾引用不存在的`budget_accounts`，改为真实`activity_budget_accounts`；native链先后遗漏合成解锁和激活前置、误用方法名，均保留实际失败日志，按真实前置补齐；历史工件篡改反例最初期待了错误异常类别，改为精确`release integrity failure`。这些开发日志不冒称稳定完成证据。

实际文件：新增本设计/本报告、`application/tool_learning_migration.py`与`tests/test_tool_learning_migration.py`；依赖修改`application/tool_learning_bridge.py`、`application/control_plane.py`、`application/source_updates.py`、`resources/release.json`及`tests/test_tool_learning_bridge.py`。未改冻结DDL、规范、原账户上限或正式目录。
