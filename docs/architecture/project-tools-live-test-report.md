# 项目文件工具真实测试

2026-11-15。结论：真实读取与修改成功，完整自动任务尚未通过。

唯一测试文件：`outputs/project-tools-review/live-probe-243310e0.py`。真实 Codex 模型发出 project_read、project_edit，经正式审批策略和真实 worker 执行，两项均 succeeded。正文从 `before-243310e0` 正确变为 `after-243310e0`。本轮未修改业务源码来制造测试成功。

## 阻断与处理

1. 管理进程在 verify_handshake 读取数据库时遇到锁，未处理的 OperationalError 令 supervise 的 finally 停止运行器。读取动作一度停在队列。已修复：只对明确的 SQLite busy/locked 返回 verification_pending、记录 watchdog-busy.json 并重试；不把待核对状态宣称为验证成功，保持原心跳期限；持续无法验证仍超时回退。非锁错误不吞掉。已部署 `db01c87f0e1840b28276efbb066b2678`，恢复同一实例继续同一任务。两个针对性 watchdog 测试及七个文件工具测试共 9 项通过。
2. 第二次真实思考提出正确的 project_edit，但行为概率选择改为 ask，导致任务停下。没有擅自改变人格或行为概率设计；按原任务通过已有 resume 接口续办一次，第三次思考的编辑实际成功。
3. 第三次思考后触及原 3 轮限制，活动 paused，未生成工具执行后的最终完成回复。因此不能把文件修改成功等同完整自动任务通过。预算和轮数未放宽。

下一步需要决定：对于 root 已明确授权且信息齐全的执行任务，人格概率是否应该仍可随机将可执行步骤替换成 ask；以及如何在原预算内安排工具步骤和最终回复。这两项本轮未修改。

## 证据与清理

- `outputs/project-tools-review/live-result-243310e0.json`：三次真实思考、两次成功工具动作、正文核对及 paused 状态。
- `outputs/project-tools-review/live-repair-tests.log`：9 项相关验证。
- `outputs/project-tools-review/live-cleanup-243310e0.json`：合成测试记忆归档和测试活动清理；审计及专用测试文件保留。
- 约 290 秒为重新接入观察后到结束的时间，包含中断恢复和等待人工续办，不能当作正常工具或模型单次耗时。
