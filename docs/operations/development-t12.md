# T12 健康维护与自更新操作说明

V0.1，有界工程版。当前实例本轮不更新、不重启、不重建身份、记忆与历史。以下命令用于隔离审阅目录，不能直接替换成正在运行的正式实例路径。

## 查看任务与复验

```sh
python3 manage.py roadmap
PYTHONDONTWRITEBYTECODE=1 python3 scripts/verification/verify_self_maintenance.py
node scripts/verification/verify_thought_inspection_ui.mjs
```

验收使用临时目录、固定模型适配器、真实受限工具、本机模型清单替身及临时运行进程，验证后清理。不会调用真实LLM，也不会唤醒正式实例。完整测试需要本机临时端口；真实模型验收另行显式开启。

## 建立隔离审阅目录

```sh
python3 -m digital_life --data work/t12-review prepare
python3 -m digital_life --data work/t12-review maintenance enable --max-repairs 3
python3 -m digital_life --data work/t12-review maintenance diagnose
python3 -m digital_life --data work/t12-review maintenance status
```

这些命令不启动推理或生命进程。status 是当前配置、剩余次数、诊断与提案历史；diagnose 会记录一次带时间的健康观察。unknown 表示没有独立证据，不应解读为健康。

启用/关闭配置要求已停止且没有运行进程。每次显式重新配置产生新预算代次，最多3次修复；不会为了持续修复自动续期。自动修复还须显式指定：

```sh
python3 -m digital_life --data work/t12-review maintenance enable --auto-repair --max-repairs 3
```

该命令仍不唤醒。只有未来通过既有CLI启动、且允许执行的运行进程才会维护；每30秒最多一次检查，每次最多一项修复。

## 有限修复：先计划，再执行

白名单只有 restore_workspace 和 rebuild_index。前者只创建缺失的空工作目录，不恢复丢失文件；后者重建可再生索引，不改写原始记忆。健康目标未满足、路径是符号链接/普通文件、核心存储或身份异常、存在未知外部效果时，不擅自修复。

当对应故障实际存在时：

```sh
python3 -m digital_life --data work/t12-review maintenance plan \
  --kind restore_workspace --key repair-workspace-1
python3 -m digital_life --data work/t12-review maintenance repair --plan PLAN_ID
```

将 PLAN_ID 替换成返回的计划ID。重建索引改用 `--kind rebuild_index`，前提是记忆质量索引功能已启用且确有缺失或损坏。一般索引水位落后沿用原增量同步，不报为重大故障。

计划绑定当前故障事实、配置与记忆源水位，5分钟过期；变化后拒绝执行。尝试记录先持久化，成功或失败均消耗一次；崩溃后也不自动重放。每次执行有前后诊断与目标核验，同一计划重复调用返回已有结果。手动执行要求停止；自动执行仍须运行授权与自动修复开关。

## 源码提案、构建和验证

要求一个已通过既有CLI部署过、现在已停止的隔离实例。若没有active部署，不编造base ID；自动验收脚本会为测试夹具建立基线。可用 status 的 source_updates.active_deployment 查看真实部署ID。

复制 `config/examples/maintenance-update.json`，将 base_deployment 替换为真实当前部署ID，填写 reason 与 changes（包内相对路径→UTF-8全文）。最多5个文件、单文件64KB、总计128KB。不能删除文件、装依赖、执行shell补丁或自动迁移生产数据库。

```sh
python3 -m digital_life --data work/t12-review maintenance propose \
  --spec config/examples/maintenance-update.json --key source-proposal-1
python3 -m digital_life --data work/t12-review maintenance build --proposal PROPOSAL_ID
python3 -m digital_life --data work/t12-review maintenance validate \
  --proposal PROPOSAL_ID --timeout 30
```

构建复制已核对完整性的旧发布版本并应用提案，不修改宿主项目或运行版本。验证在临时目录运行固定探针，检查模块导入、schema初始化、真实文件工具、独立目标核验与两次独立调用；父进程另行检查临时文件和SQLite记录。验证结果绑定候选hash、原部署、当前schema与探针版本；失败或基线变化不能当作通过。

以上都不部署、不启动正式实例。对于该流程生成的新候选，后续既有CLI deploy会检查独立验证证据；普通stage-release流程保留原有人工管理方式。不要因为验证通过就误以为已升级。

## 系统自身如何提出改进

启用后，每次独立思考可收到维护摘要、剩余修复次数、当前base_deployment和提案边界。系统可用既有write_note行为写 `maintenance/update-KEY.json`，内容字段为 base_deployment、reason、changes。仍受write_note的16000字符上限限制。

普通权限模式需要工具审批，open模式沿用已有授权。只有真实成功写入回执、哈希和已接受思考来源匹配时才记录提案；来源含请求、思考结果、意图、动作结果和证据引用。写入提案不等于部署代码。无效提案会单独标拒绝，不篡改已经成功写笔记的事实。

## 更新、回退与观察

部署、启动和唤醒继续通过既有CLI处理，不新增面板生命周期入口。本轮没有执行当前实例的这些操作。

旧机制仍检查prepared/running双握手和heartbeat；新版准备、激活后或运行期间失败会尝试恢复旧版本。现在还检查发布文件集合、内容hash及数据库兼容范围；无法安全恢复时保持失败/降级，不伪造恢复成功。程序回退不恢复旧数据库，不抹去新记忆、历史或已发生的动作；自动数据库迁移不在本项范围。

用户停止优先：停止后不自动修复、不为恢复而清除停止锁，也不在启动握手被停止时回退重启。面板“思考执行详情→健康”增加self_maintenance快照，展示该次输入中的诊断不确定性、预算和CLI权限边界；当前旧实例须以后显式部署新版才会出现该字段。

## 验证限度

临时目录和清理后的子进程环境不是操作系统安全沙箱；执行候选代码需要信任其代码。固定探针不能证明任意源码安全、复杂任务改善或长期自愈可靠性。真实LLM改进质量、长期恢复率和五项生命判据留待明确实验与T13验收。
