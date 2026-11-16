# 部署独立思考验收实现报告

2026-11-15。状态：已部署、原实例已启用、真实模型验收通过。

## 部署成功新增判据

进程启动并完成原存储、来源和版本身份检查后，先运行一次独立思考，再正式放行普通任务。此时进程物理状态可以是running，但未获得admitted门前不转入普通任务执行循环。

通过要求：

1. 使用当前配置的实际推理器，走正常 Engine 输入准备、独立请求、输出验证、结果接受与持久化链路。
2. 应用层推理调用恰好一次，thought_attempts也必须恰好一次；不自动重试。
3. 结构化输出只能是wait，reason和explanation必须精确回显宿主为这次部署产生的随机nonce。
4. 不允许工具动作、认知候选、预测、计划或学习提案；不创建action_intents。高维特征评分保留，验收的随机ask替代标为不适用；不推进人格/习惯成长。
5. 实际thought_result必须accepted且valid，活动completed。CLI管理进程再次核对真实数据库、请求与结果工件hash、nonce、deployment和当前process_run/epoch后才写入admitted门。

模型错误、超时、非法输出、错nonce、未接受的结果或核对失败，均使新部署失败并进入原检查点回退。门超时默认180秒，可配置1—600秒，未增加普通活动预算。应用层只调用一次，不声称能控制服务提供方内部网络重试。

## 回退策略

用户明确选择：上一已知可用版本回退启动时不再调用模型做验收。管理器记录skipped-known-good-rollback，不把它冒称新一次模型验证成功。旧版仍经过原代码完整性、schema兼容和启动检查；用户停止与禁止唤醒锁优先。

这避免模型服务临时不可用时，新旧两个版本都被同一外部故障阻断。没有移除原进程/心跳/状态监控。该模型验证结论是本次启动时的事实，不保证后续网络和额度一直可用。

## 记录与清理

- runtime_events：deployment.thought_started / passed / failed，以及原有推理请求、结果和失败日志。
- control_commands：process.deployment_thought，记录验收成功的部署、nonce、request、result和调用次数。
- launches 下ready.json保留deployment_acceptance阶段、耗时及证据标识；新状态inference_ready=verified、model_readiness=independent-thought-verified。
- 验收输入和回复的记忆自动归档，不进入日常召回；原始审计保留。不进入账户聊天记录。

本版验收仍限native路径；受保护schema4需要相应合格适配器，不绕过其来源/预算与桥接约束。

## 验证结果

核心4项通过（0.349秒），覆盖单次调用、实际Engine接受、归档、错nonce/错动作拒绝和不产生工具意图。

真实Runtime进程加本机HTTP模型替身的2项验证通过（8.302秒）：成功后才admitted；HTTP模型服务503时，新版失败、旧版恢复，实际模型HTTP调用总数为1。没有故障注入正式实例。

43项相关回归通过（5.923秒），覆盖验收、普通聊天、行为概率和Codex适配器。

正式实例：部署 `8edacf712ca44984bc6b748bccbf5228`，PID 18617，普通任务已放行。实际Codex独立会话 `01a1dd73-f12c-7aa1-9920-cd83358eca4d`，调用次数1，accepted结果持久化并经管理进程复核；工具意图0。验收阶段耗时40.572秒，包含输入准备、模型调用及接受处理，不是纯模型计时。

身份、原记忆、历史及目录权限不变；没有另建正式生命实例。

## 配置命令

```sh
# 修改配置前先正常停止并等待原进程退出
python3 manage.py stop
python3 -m digital_life --data work/primordial00-first-wake process-manager enable \
  --verify-thought --thought-timeout 180
# 随后通过既有start/wake正常部署

# 如需关闭独立思考验收而保留进程检查点功能，同样先停止
python3 -m digital_life --data work/primordial00-first-wake process-manager enable \
  --no-verify-thought
```

## 证据

- `outputs/project-tools-review/deployment-thought-core-tests.log`
- `outputs/project-tools-review/deployment-thought-process-tests.log`
- `outputs/project-tools-review/deployment-thought-regression.log`
- `outputs/project-tools-review/deployment-thought-formal.json`
