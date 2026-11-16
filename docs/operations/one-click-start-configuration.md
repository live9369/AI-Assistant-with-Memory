# 一键启动配置

`./start-chat.command` 会先显示实例目录、身份、源码版本、数据库版本、当前唤醒状态、本次是否唤醒、模型、接入方式、核账模式和面板地址，不显示令牌或密钥。

- `./start-chat.command --show-config`：只查看配置。
- `./start-chat.command`：打开面板并唤醒现有聊天实例。
- `DIGITAL_LIFE_WAKE=0 ./start-chat.command`：只开面板，不发出唤醒操作，也不停止已运行的实例。
- `./start-chat.command work/已有实例目录`：选择已有实例，不自动新建身份。

默认实例为 `work/primordial00-first-wake`，沿用原身份、记忆和历史；高级学习验证实例不再默认启动。已有面板可复用，面板在线不代表运行器已唤醒。部署、启动和唤醒仍由 CLI 处理。启动终端需保持打开；Ctrl+C 停止本次前台运行。
