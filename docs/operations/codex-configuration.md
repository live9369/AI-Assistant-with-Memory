# Codex 设备码授权与独立推理

## 前置条件

适用于本地个人项目。需要官方 Codex CLI，且所选版本支持 `exec --ignore-user-config --ignore-rules --ephemeral --output-schema --json`。当前验收版本为 0.166.0-alpha.6；其他版本先核对帮助与重新验收。使用订阅Codex额度，与API充值余额分开；模型权限、限额和可用性以账户为准。

## 登录

先运行 `codex login status`。已显示 `Logged in using ChatGPT` 时无需再次登录。否则，在ChatGPT安全设置启用设备码登录，再手动运行：

```sh
codex login --device-auth
```

由操作者在官方网页输入一次性代码。不要把auth.json、设备码或访问令牌写入项目配置。项目仅调用官方程序，不提取凭据。登录不是唤醒工程。

## 配置

复制 `config/examples/llm/codex-cli.example.json`，填入 `command -v codex` 得到的绝对路径、账户可用模型名，并按需启用。模板默认禁用。可通过 `prepare --model-config` 创建全新禁止唤醒实例，或对已停止实例使用 `configure-model ... --offline` 版本化保存。只使用新隔离目录，不对正式目录执行这些示例。

```sh
python3 -m digital_life --data work/codex-review prepare --model-config config/local/codex.json
python3 -m digital_life --data work/codex-review model-probe
```

probe只检查订阅登录，不生成、不验证模型额度。不要删除WAKE_DISABLED，不调用resume或运行器。正式实例保持锁定。管理面板可显示Codex配置，但不能在线设置可执行路径；这避免HTTP接口成为任意本机程序执行入口。

## 思考与错误边界

每次generate运行全新临时CLI会话，不使用resume/fork，不传前次历史。只输入系统本次选取的任务、记忆、情境。模型候选仍需项目本地严格校验和既有审批；Codex不执行行为。严格Schema要求`list_files`明确给path；用`.`表示当前目录。

平台指令和CLI固定上下文仍然存在；新会话验证不能证明模型完全没有先验，也不能单凭随机标记测试证明所有情况下无信息串扰。

禁用工具和只读策略与事件审计共同约束执行。新CLI版本可能新增工具；未识别的item会拒绝结果，但事后检测不能代替操作系统隔离。每次升级应重验。超时终止进程组；进程失败、拒绝、错误事件、坏JSON、非法动作或缺少完成事件都失败，不重试、不切换模型。临时日志不会进入数据库；进程运行期临时磁盘增长尚未硬限制。

## 验收产物

`outputs/acceptance/codex-isolated-acceptance.json`记录真实调用、独立会话ID、结构化候选和实际用量。`tests/test_codex_models.py`覆盖无网故障注入。真实调用会消耗订阅额度，测试本身不唤醒实例、不执行候选。

参考：[官方认证](https://learn.chatgpt.com/docs/auth?surface=cli)、[非交互模式](https://learn.chatgpt.com/docs/non-interactive-mode)。

本版本使用开发中的宿主技能发现禁用开关；只在本次进程配置中抑制其特性提示，不修改用户设置。固定平台指令会产生额外输入token，因此CLI用量不等于项目请求正文长度。

## 管理面板增量

现在可在面板编辑模型名、启用状态、超时、预算和授权来源，查看状态、获取/取消设备码并显式测试连接。可执行路径仍由服务端管理。可选auth_home保存实例独立授权目录路径，数据库只存路径、不存令牌。面板细节见[操作指南](management-panel.md)。

## 严格普通思考：调用后核账（2026-11-12）

显式配置 `budget_mode: "post_usage"` 后，严格模式选择真实 Codex 普通思考适配器；学习解释协议不随之开放。每次新CLI进程、独立临时目录、ephemeral，无resume/fork，工具禁用。完整prompt会保存在思考执行详情中。

调用前预留原输入额度全额，不伪称已精确分词；返回后只接受CLI报告的完整真实用量。用量未知或超原额度不采纳结果，并持久停止实例、生成 `MODEL_USAGE_REVIEW_REQUIRED`；不会自动重试。该标记需要控制者核对用量后显式处理，`start` 不会删除它。此为调用后保护，不能保证服务端硬限额或撤销已经发生的消耗。

`max_input_bytes` 在本Codex适配器中是本地完整prompt字节容量，当前配置262144；它不改变活动的输入/输出token额度。新严格实例仍沿用原核心配置的200000输入、200输出token及其余原预算。

本次一条真实聊天已走面板提交→严格核验→Codex→原用量核账→回应保存→面板读取，实际输入59911、输出68，回应为“你好，liwei！很高兴认识你。”。这不是完整回归或长期验收；正式实例没有更新或启动。

## 本地输入容量配置

Codex 配置文件通过 `max_input_bytes` 控制项目完整提示词的 UTF-8 **字节**上限，默认 `262144`（256 KiB），允许范围 `2048`—`262144`。这是本地保护上限，不是模型的 token 窗口；不修改模型服务端容量、活动 token 额度或权限。正文额外预留 1024 字节给提示词。只有超出正文容量时才尝试现有紧凑表示，不截断特征或来源。

```json
{"max_input_bytes": 262144}
```

把该字段写入完整的模型配置（例如 `config/local/codex.json`）。修改文件不会自动改变既有实例；需停止实例后通过 CLI 保存新配置版本：

```sh
python3 manage.py stop
python3 manage.py configure --config config/local/codex.json
```

等待运行进程退出后保存；然后按原有 `start` 流程启动。也可以在停止实例后的面板“模型配置 → 完整输入上限（UTF-8 字节）”保存。配置保存不调用模型，不改写旧思考、身份、记忆或历史。调整容量时保留配置中的其他字段，尤其是 `budget_mode`。

兼容旧 Codex 配置字段 `context_window`（仍按字节解释）。保存模型配置时统一写为 `max_input_bytes`；两字段并存且数值不一致时拒绝保存。其他模型后端的配置不受本次改名影响。
