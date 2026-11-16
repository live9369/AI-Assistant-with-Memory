# Codex 订阅推理接入设计

版本 V0.1；状态：设计基线／待验证；2026-11-08。

## 范围与授权

本地个人项目通过官方 Codex CLI 使用 ChatGPT 订阅登录。设备码是登录方式，不是 API Key，也不代表 API 充值余额。登录由操作者执行 `codex login --device-auth`，CLI 自行管理凭据与刷新；项目不读取、复制或存储令牌。已有 ChatGPT 登录可复用，不主动注销或重新授权。面板不接受设备授权令牌。

## 接口与独立思考

新增 `codex_cli` Reasoner，沿用领域输入与 action JSON 契约。每次 generate 创建新的临时工作目录，以 stdin 提交一次完整输入，启动全新的 `codex exec --ephemeral`；禁止 resume、fork 和历史字段。忽略用户配置、项目文档，跳过宿主技能发现并禁用技能搜索、记忆、MCP/apps、浏览器、shell 等能力，不把项目目录交给模型。系统记忆只能来自本次明确构造的请求。Codex 自身平台指令仍存在，不能称为没有任何系统上下文。

`--output-schema` 约束输出，项目再次执行严格契约校验。最终只返回候选，绝不将 Codex 作为行为执行框架。禁用工具、read-only 与 never 审批共同限制执行；事件流一旦出现命令、文件改动或外部工具事件，本次结果作废。该事件检测属于事后拒绝，不等于操作系统级零工具证明，部署需固定并复核 CLI 版本。

## 配置与运行

字段：backend=codex_cli、model（明确模型名）、enabled（默认false）、executable（绝对路径）、timeout（1–600秒）、context_window（保守字节预算）。不伪装支持采样温度或精确输出token上限。路由配置版本化，不改写既有思考请求；不修改数据库结构。probe 仅检查CLI和ChatGPT登录，不做推理，不证明模型权限或额度充足。

CLI 是可执行信任边界，路径由本机操作者配置，HTTP管理面板不允许指定任意可执行文件。本轮通过CLI配置接口接入，面板仅展示配置；后续再设计专用登录管理界面。

## 异常处理

禁用、输入超预算、历史字段、缺失CLI、未登录、进程失败、超时、拒绝、事件失败、缺少完成事件、工具事件、无效JSON及动作越权全部明确失败，不自动重试或降级。超时终止整个进程组并回收。错误只记录稳定分类，不持久化CLI原始stderr或授权内容。stdout/stderr落临时文件，读取受限；临时目录结束即删除。超时前临时磁盘增长仍是剩余限制。用量仅采用CLI完成事件实际报告，不推算缺失值。

## 验证计划

先做离线传输与故障注入测试，再创建独立全schema实例，保持WAKE_DISABLED和停止状态，直接调用推理适配器（不启动生命运行器）。两次真实调用使用不同随机标记；第二次不得包含或复述第一次标记；同时核验不同thread ID、结构合法、零工具事件。行为候选不执行。正式实例前后逐文件SHA256完全一致。断网、超时、坏输出等由隔离故障注入覆盖，真实额度耗尽不主动制造。

## 官方依据

- [认证与设备码登录](https://learn.chatgpt.com/docs/auth?surface=cli)
- [非交互模式、临时会话与结构化输出](https://learn.chatgpt.com/docs/non-interactive-mode)
- [配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)
- [App Server适用范围](https://learn.chatgpt.com/docs/app-server)：本地／开源集成与商业托管范围应区别处理。

## 版本约束

当前CLI的`skip_host_skill_discovery`为开发中特性。适配器在单次调用配置中启用它，并只抑制该类不稳定特性提示，不修改用户配置；真正的错误事件仍一律失败。该特性需要随CLI升级重新验收。不把独立会话等同于精确的裸模型调用；CLI固定上下文可能带来额外输入token。适配器自身不重试；CLI内部传输恢复行为仍受总超时约束。

## 面板增量

后续已补充[Codex面板设计](codex-panel-design.md)，允许通过面板配置模型与授权来源，但可执行路径及授权目录仍由服务端固定。新增可选auth_home字段，用于官方CLI持有的实例独立授权；项目不提取令牌。
