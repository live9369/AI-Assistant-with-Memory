# 候选虚拟机隔离设计 V0.1

2026-11-15。状态：用户要求跳过Apple专用路线，已暂缓；未安装运行时、未启动服务、未切换正式实例。改为后续采用Docker/OCI通用容器接口，见candidate-container-portability-plan.md。本文件仅保留调研记录，不作为待执行安装计划。

## 目标与选型

补齐原生进程沙箱尚未覆盖的整组内存、进程数量与脱离进程组后的清理。使用Apple Container 1.7.1，每次检查创建独立Linux VM。系统要求Apple silicon/macOS26，本机符合；当前没有container命令。

选型依据：[官方发布](https://github.com/apple/container/releases/tag/1.7.1)、[虚拟机架构](https://github.com/apple/container/blob/1.7.1/docs/technical-overview.md)、[对应版本CLI](https://github.com/apple/container/blob/1.7.1/docs/command-reference.md)。不借用Docker专有参数；所有命令以实际安装版本help及运行结果再次核对。

## 计划限制

- 1个虚拟CPU、512MiB客体内存；这不是包括宿主服务和虚拟化开销的总RSS承诺。
- 候选以专用非root UID/GID 65532运行，丢弃Linux能力，并在导入候选前设置no_new_privileges。
- nproc=64作为该专用客体UID的进程/线程上限。它不是可直接照搬到宿主用户的全局限制，且不能在root或具有相应能力时冒称有效。实际内核生效需验证。
- 256个文件句柄、单文件64MiB、core=0、CPU时间沿用探针时限；墙钟时限继续取原检查参数，不提高活动预算。
- 网络none，不转发端口、socket、SSH、DNS或主机凭据。
- 根文件系统与候选源码只读。仅挂载候选副本和宿主生成的检查脚本，均为只读；不挂载真实HOME、正式实例或任何宿主可写目录。
- probe使用64MiB tmpfs，另有16MiB临时目录和16MiB共享内存；这些计入客体内存，不生成可无限增长的宿主写入卷。

[官方ulimit说明](https://github.com/apple/container/blob/1.7.1/docs/ulimits.md)与[Linux限制语义](https://man7.org/linux/man-pages/man2/getrlimit.2.html)说明，nproc按真实UID计算，root及相应能力可能豁免；本设计因此必须验证非root、能力清空及禁止提权，不能只检查命令里出现了一个数字。[tmpfs说明](https://github.com/apple/container/blob/1.7.1/docs/volumes.md)用于限制客体临时写入。

## 产物与清理

不能把宿主probe目录可写挂载进VM，否则客体仍可能耗尽宿主磁盘。候选完成后，通过单独的有界工件通道取回SQLite与blob。计划最多16MiB、限定相对路径和普通文件，拒绝绝对路径、..、符号链接、硬链接与特殊设备；校验大小/hash后由宿主原有逻辑验收。

该通道是检查产物传输，不是LLM上下文，也不放宽原128KiB日志上限或活动token预算。不能使用未经检查的tar直接解包到宿主。实际container cp要求运行中的容器，不能假设停止后仍可直接复制。

宿主通过唯一的本次VM ID执行停止和删除，不按宿主Python进程组推断客体已清理，不使用--all。超时、内存耗尽、进程超量、产物过大、后端不可用或清理结果无法确认，都不能标记验证通过。运行时若不支持某项限制则拒绝该后端，不自动降级到Seatbelt。

## 安装与本机影响

官方签名包：container-1.7.1-installer-signed.pkg，发布页标为162MB。
SHA256：b6739caf3d47ca53a78f1a7edf32521420a75c7941838c3cefa75f30b80f5a97。

安装会向/usr/local放置工具/辅助程序；container system start会启动当前用户的管理服务。首次使用还需内核、初始化镜像及Python镜像，具体下载量以清单为准，不能把162MB冒称全部占用。为准备和缓存计划预留约2GB，不是已测占用。检查后停止并删除本次VM；管理服务与镜像缓存另有明确停止/清理命令，不批量删除用户其他容器或镜像。

镜像必须固定为拉取后验证的digest；配置中的image:null不是可执行配置，不自动使用可变标签。未获安装/启动服务授权前，不安装、不拉镜像、不启动管理服务。

## 实施顺序

- [x] 调研官方版本、资源与网络/挂载接口，准备配置模板。
- [ ] 已取消：下载并核对Apple安装包；未完成下载与签名校验，不用于安装。
- [ ] 已取消：安装Apple运行时、启动服务并固定镜像digest。
- [ ] 实现VM启动、产物传输与清理后端，再接入SourceUpdates。
- [ ] 只做正常探针、内存/进程限制、网络/文件边界和清理的必要合成验证。
- [ ] 验收通过后再明确切换正式候选检查；原实例在此之前保持现有已通过的Seatbelt版本。

不启用人格成长，不开放无人值守部署。独立于可编辑源码的控制器仍是后续单独事项，安装VM运行时本身不会自动完成该项。
