# macOS候选代码隔离方案调研

2026-11-15。目标：在不开放正式数据、凭据和网络的前提下，运行更新候选的固定业务探针。

## 本机情况

macOS 26.6.2 / arm64，安装了 /usr/bin/sandbox-exec；未发现docker、podman、limactl或Apple container命令。最小原生策略已实测能够执行程序。系统man sandbox-exec明确标记DEPRECATED，不能将它当成长期稳定的唯一接口。

## 方案选择

| 方案 | 适用性 | 本次处理 |
| --- | --- | --- |
| Apple App Sandbox | 官方应用及受签名配置管理的helper体系，工具需继承应用沙箱 | 需要独立应用/helper工程，暂不引入 |
| Apple Virtualization / container | VM提供独立客体系统，适合进一步收紧内存、进程及宿主边界 | 本机未安装，涉及运行时及镜像；作为后续后端，不静默安装 |
| sandbox-exec / Seatbelt | 当前本机具备，可对候选进程树实施文件和网络访问限制 | 首版原生后端，默认拒绝；不可用即停止验证，不回退普通subprocess |

Apple将App Sandbox及工具继承作为官方应用隔离路线：[保护用户数据](https://developer.apple.com/documentation/security/protecting-user-data-with-app-sandbox)。[Virtualization](https://developer.apple.com/documentation/virtualization/running-linux-in-a-virtual-machine)提供Mac运行Linux客体的框架。[Apple container](https://github.com/apple/container)使用轻量Linux虚拟机，当前要求Apple silicon与macOS 26及以上。上述信息用于选择，不声称本机已具备VM后端。

Seatbelt启动需保留系统加载器、公开运行库及少量系统调用；不能把“禁止一切”导致的启动退出误认为业务失败。对照[Codex原生基础策略](https://github.com/openai/codex/blob/main/codex-rs/sandboxing/src/seatbelt_base_policy.sbpl)及[平台读取规则](https://github.com/openai/codex/blob/main/codex-rs/sandboxing/src/seatbelt_read_only_platform_defaults.sbpl)核对操作类别；本项目不复制通用工作台的广泛目录、服务或网络许可，只开放自己的最小运行路径。

## 实现边界

首版提供默认拒绝的文件、网络、外部进程交互限制，并给出CPU、单文件大小、文件句柄、输出和原墙钟超时限制。Python子进程继承策略。没有承诺硬性限制整个子进程树的总内存或进程总量；候选可能故意脱离进程组，正常超时清理不能因此冒称完整资源隔离。这些仍需独立VM或更强的宿主资源管理。

不开放无人值守任意源码部署。CLI继续负责部署；本次只替换候选验证执行后端，正式Runtime和模型调用不进入该离线沙箱。
