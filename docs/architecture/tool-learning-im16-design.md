# IM16：仅合成隔离目标的迁移与代码回退

日期：2026-11-10。状态：实现完成，等待稳定验收。依赖IM03、IM15已完成；不修改冻结规范，不接正式/current目录，不调用真实模型或安装服务。

## 1. 强制隔离目标

新增`tool_learning_migration.py`：`IsolatedMigrationTarget.create(new_root, source_version)`只接受不存在且不嵌套任何实例的真实目录，创建新合成身份、随机创建凭据、0700目录、锁与Control。进程内封闭创建登记绑定目录/数据库inode、实例与标记，不接受调用者的synthetic布尔值或给既有目录补marker。版本2由保存runtime.sql实际创建；版本3由现有真实2→3扩展得到，绝不修改PRAGMA伪装历史结构。所有迁移/回退接口先验证该能力，再读目标数据；生产迁移授权不在本项开放。

## 2. 发布能力映射补齐

新发布工件必须有顶层`capabilities:["TL-LOOP-0.1"]`及既有真实bridge合同，严格数组/唯一枚举/类型/JSON解析并绑定实际manifest与加载代码。未登记缺数组candidate不得自签。旧IM15已登记release只在当前可信Control的原baseline记录/原manifest/实际barrier_contract均一致时明确投影有效能力，不改旧文件或假称原件含数组；原IM15完成证据保留，16/19门追加依赖复验。

## 3. 迁移接口和事务

`migrate_isolated(target, bearer, forward_deployment, rollback_deployment, fault=None)`：目标能力、当前controller、停止/锁/无未核对进程、真实版本与结构、两个有效bridge记录均须通过。没有可用schema4回退基线拒绝。原2/3旧库不允许混入未经批准的部分TL扩展；已4仅按原迁移记录/校验和/真实结构幂等核对，不重建库或预算。

迁移前完整备份及blob/manifest核对、语义盘点，外部制品单独登记状态。主库用一个BEGIN IMMEDIATE事务：原2先执行V3语句，再逐完整SQL statement执行冻结TL DDL（不用executescript隐式提交）；登记版本/约束、默认关闭新TL学习并保留原policy、完整性与旧行核对后才提交。任何写点失败全回滚到原2或3，预置备份保留并明确标记失败/待核，不盲删。提交结果未知先按持久版本/迁移记录核对，禁止恢复旧备份猜结果。

身份、记忆/历史/证据、有效承诺、旧shadow及原预算逐旧行保持；仅允许新增迁移/备份/策略控制事实与明确policy head投影。旧shadow不生成TL accepted/content/representation，旧pending缺原八维事实仍blocked，绝不补额度。

## 4. 回退与排除

`rollback_code_isolated`只审计记录离线选择（activated=false）；实际启动/失败回退由既有Deployment处理。所选工件必须是当前可信Control仍有效、真实覆盖4并执行同TL门的bridge，保持停止/锁。不得降低user_version、恢复迁移前DB、改原caps、删任何新C1/C2/F1历史或屏障。旧2/3、无能力或篡改build拒绝。较旧镜像恢复仍需IM13当前镜像外排除及pending核对；不创建新的灾难恢复机制，不用旧镜像自带Control当当前来源。

## 5. 验收

新合成真实2→4与3→4；缺bridge/错误目标/marker与inode替换/停止失败拒绝；每类DDL、登记、策略、完整性、提交前后故障；备份缺失/篡改与外部制品状态；身份/记忆/承诺/原caps/旧shadow语义保持；迁移后创建真实C1/C2/F1，再代码回退证明全部历史/排除保留且不新唤醒；原迁移备份不能复活erased来源。专项和统一门稳定后停源交独立IM19。
