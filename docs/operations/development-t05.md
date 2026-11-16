# T05 使用与验收说明

版本 V0.1。新功能默认关闭；本轮只在临时隔离实例验证，不部署当前实例。不修改身份、记忆、历史，也不执行正式唤醒。

## 查看任务与复验

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 manage.py roadmap
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 scripts/development/check_task_plan.py
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 scripts/verification/verify_goal_regulation.py
```

验收脚本使用临时实例，运行完整 Python 回归，保存 `outputs/acceptance/development-t05.json`，核对测试期间源码未变，并据结果更新任务状态。面板接口测试需绑定本机临时端口。真实本地模型测试按既有环境开关执行，未开启则明确跳过；不能把替身结果当作真实模型能力验证。

本次另外只读对照了当前实例的身份、运行代次、进程与部署，结果在 `outputs/acceptance/t05-live-guard.json`；不以持续增长中的历史行数或数据库文件哈希判断“未改变”。

## 仅在新隔离目录试配置

以下只准备测试数据和配置，保持唤醒锁，不调用模型。不要将路径替换成当前运行实例。

```sh
python3 -m digital_life --data work/t05-review prepare
python3 -m digital_life --data work/t05-review goal-regulation enable
python3 -m digital_life --data work/t05-review goal-regulation status
python3 -m digital_life --data work/t05-review submit "隔离目标" --key t05-example
```

从提交结果取得 activity ID，再准备一个特征 JSON 文件，例如：

```json
{"importance":0.8,"expectancy":0.6,"cost":0.3,"risk":0.1,"alignment":{}}
```

```sh
python3 -m digital_life --data work/t05-review goal-regulation prioritize --activity ACTIVITY_ID --features path/to/features.json
```

importance 是重要程度；expectancy 是预期收益的可达程度；cost 和 risk 是控制者声明的成本和风险估计。全部为 0—1；空 alignment 使用工程缺省值 .5。已知价值维度 ID 可通过现有价值档案查阅，不能用自造名称替代。参数是可审计估计，不是已验证的心理测量。

启停只能在实例停止、无活动运行进程时操作；配置不会唤醒实例。`enable --min-disk-bytes N` 改最小磁盘余量，默认 64 MiB；`disable` 恢复原有 FIFO。特征只允许在活动尚未准备思考时设置，避免改写已经发生的输入。旧部署运行时，新 CLI 会拒绝写入该部署不支持的功能。

## 如何理解运行结果

启用后，调度先处理原有可执行工作；待思考目标按动机强度排序。强度结合重要性、价值一致性、预期收益、紧迫性、成本、风险、负载与剩余预算。

状态缺失/过期、磁盘不足、数据库异常、恢复未协调、期限到达、预算不足、取消或终态时，不启动新思考。阻断原因保存在竞争事件，队列保留，不把暂缓伪装为完成。期限或预算等永久阻断需显式处理或建立后续活动；本版不自动延长预算、改期限或复活终态。

状态有效期为 30 秒，距过期不足 5 秒时刷新；空队列不额外采集。相同候选和相同阻断原因不重复写竞争事件。健康是工程可观测量，可能有采样延迟；不声称实时诊断所有故障。

已准备请求保持历史快照；在调用模型前再次检查配置代次和状态。失效请求被拒绝，不静默改写旧输入。推理尝试的保守预留仍遵循既有预算规则，未调用不等于自动返还额度。

面板的“思考执行详情”可在完整输入及“动机”中查看 `goal_regulation`：每项贡献、状态及证据、价值档案、预算、动机记录 ID 和配置版本。旧请求没有这个字段会明确显示未进入输入，不反推或补造历史。面板展示不意味着已部署新源码。

## 已验证与未验证

本项验证确定性目标竞争与停止门控、动态预算投入、独立输入、持久化、真实受限工具/审批与 T02 多轮目标核验兼容。系数是工程 V1，未做心理效度或长期适应实验；人格/认知等高维行为概率在 T06；长期公平性、通用目标依赖图、自动目标生成及动机学习不在本次验收范围。
