# 项目任务连续执行修复报告

2026-11-15。状态：已部署原实例，真实完整任务通过。

## 已修复

1. 对当前 root/控制者发起、信息完整且目录已自动授权的项目步骤，保留人格、认知、关系、动机等高维特征、评分和候选审计，但将系统自动生成的随机 ask/wait 标为不适用。不修改人格参数。模型自己明确提出澄清时仍可询问；未授权、越界、自主探索和普通聊天不取得此执行约束，真正动作仍需经过原授权与执行检查。
2. 项目任务不再被额外三轮限制打断（含已有 project_task 配置）；旧 file_contains 等任务的轮次规则保持。项目任务使用原 token、工具、总尝试、时间和 deadline 额度。每轮先核对余额，默认预留最多4096 token，剩余1024—4095时只预留余额，少于1024或其他必要额度不足就暂停并记录明确进度；不再调用模型。没有提高任何上限。该额度是既有本地预留账本，不新增对 Codex 服务端硬 token 限制的保证。
3. 写入工具已有读回 hash 核对，输入说明明确无需为同一次写入再增加核对读取。真正独立检查（如 Python 语法）仍有独立回执。
4. 修复外部输入渠道选择：此前无排序取第一个 perception_channel，有时误选 internal；现按 kind=user、state=available 明确查询。旧历史输入不改写。

## 验证

82 项相关回归通过，18.137 秒；补充输入渠道修复后，最终10项核心验证通过，4.883 秒。包括极端随机抽样仍保持明确项目动作、四次完整独立思考、原预算不足时暂停、来源/目录边界、真实 worker 编辑与检查。首次预算测试夹具使用不存在的操作引用触发外键错误，已改为测试实际低额度边界，首次日志保留。

第一次正式尝试 c33f3193 中，模型正确提出 project_read，但因历史错误的渠道分类，执行约束未生效，行为选择仍变成 ask。没有工具执行。该失败保留，取消活动并归档2条合成记忆后，修复输入分类，重新部署再验证。

最终正式任务 7bbfb5ff：

| 思考 | 结果 | 累计时间 |
|---|---|---:|
| 1 | project_read 成功 | 19.2 秒 |
| 2 | project_edit 成功，正文核对一致 | 32.3 秒 |
| 3 | project_check / python_syntax 成功 | 44.4 秒 |
| 4 | 根据真实回执给出最终回复，活动 completed | 58.56 秒 |

没有人工续办，没有提高预算，没有跳过授权或来源检查。四轮均记录 explicit-authorized-project-task-v1 执行约束。各轮预留 token 为4096、4096、4096、3712，总计16000；三次工具执行、四次思考共7次总尝试，均在原额度内。语法检查不执行项目代码或测试套件，不将其冒称完整功能测试。

## 正式状态与证据

部署：`53fb36d4ee834a8fb3fbdf73f332c1c1`，PID 72186。已确认控制状态运行中，部署内6个修改模块与源码一致。身份、原记忆与历史未重建，目录授权配置未扩展，自主探索未开启。

最终任务8条合成记忆已归档，completed 审计和专用测试文件保留，不再作为日常召回材料。

- `outputs/project-tools-review/continuity-live-7bbfb5ff.json`
- `outputs/project-tools-review/continuity-live-c33f3193.json`（第一次失败）
- `outputs/project-tools-review/continuity-tests.log`
- `outputs/project-tools-review/continuity-channel-tests.log`
- `outputs/project-tools-review/cleanup-7c9fb09288b742328a02a49f3f7f1aa6.json`
- `outputs/project-tools-review/continuity-final-runtime.json`

本次为单文件完整真实链路验证，不宣称任意复杂开发任务都能完成；任务超过原预算仍会暂停。
