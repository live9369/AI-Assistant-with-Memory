# Codex 管理面板增量设计

版本V0.1；2026-11-08；状态：设计基线／待验证。

## 用户操作

模型配置增加Codex接入方式，可填写模型名、启用开关、超时和输入预算，离线保存为配置新版本。程序路径由服务端发现，浏览器不得指定。授权来源可选择本机已有登录，或此实例独立授权。设备码授权只写入实例独立Codex目录，绝不覆盖本机现有登录；本机来源只用于读取状态和明确的连接测试。用户最终在官方网页完成同意，面板不收密码或令牌。

状态卡展示登录方式、套餐（如有）、是否等待授权及本地有效期。不把已登录当成模型额度或推理可用性证明。显示设备码、官方固定链接与手动刷新/取消按钮，设备码仅存在服务端与浏览器内存，不写数据库、日志或浏览器存储。授权轮询由用户刷新触发，无全局网页定时器。切页清除浏览器显示；服务端待处理会话保留至取消或到期，可手动刷新取回；服务退出清除内存；服务端会话设置5分钟本地上限，实际授权以官方结果为准。

## 服务边界

认证通过官方app-server stdio的initialize/initialized、account/read、account/login/start(type=chatgptDeviceCode)、account/login/cancel与完成通知。只开放固定认证方法，不允许浏览器提交RPC方法。独立授权目录0700，CLI文件凭据由官方管理；禁止复制host auth.json。单一授权会话，重复开始返回同一会话；取消后不接受旧通知。进程失败、超时、过期显示明确状态；重启后不恢复pending。

API沿用现有Bearer、Host、Origin和no-store保护：GET /v1/codex/status?scope=local|instance；POST /v1/codex/authorize；POST /v1/codex/authorize/cancel；POST /v1/codex/test。配置仍使用/v1/model/validate及configuration，新增body字段codex_auth_scope。所有写操作要求停止且无活动运行进程。设备码授权仅在instance来源执行。路径由服务端固定，HTTP不得注入executable/auth_home。

连接测试绑定expected_configuration_id，调用一次固定合成任务，只接受wait候选，使用独立临时Codex推理，不读取系统记忆、不执行动作、不启动运行器。显式提示消耗订阅额度；并发连接测试拒绝，失败不自动重试。结果只回传状态、耗时和实际用量，记录事件只含配置ID和结果分类，无模型正文、账号、设备码或令牌。配置变化后返回结果标记为旧配置，不混入新配置状态。

认证目录可作为可选auth_home进入可信模型配置，后续运行由同一官方CLI直接读取，数据库只保存路径。它包含凭据，不得通过日志、导出或打包共享；不把整实例目录作为交付文件。

## 验证

离线协议与HTTP测试覆盖状态、设备码发起/重复/完成/失败/取消/本地过期、进程退出/超时、认证来源隔离、固定链接、路径注入、配置CAS、并发测试与结果脱敏。真实隔离HTTP实例验证本机登录读取及实际独立生成；独立空白授权目录验证未登录、设备码签发与取消，不代替用户完成网页授权。正式实例逐文件哈希前后相同、禁止唤醒锁保留。前端验证表单、状态、授权和测试反馈，不能用离线fixture冒称真实OAuth完成。

依据：[官方App Server认证协议](https://learn.chatgpt.com/docs/app-server)、[独立CLI推理](https://learn.chatgpt.com/docs/non-interactive-mode)。
