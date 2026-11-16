# 候选资源隔离：Docker/OCI通用路线

2026-11-15。状态：已记录用户偏好；本项暂缓，不安装或切换后端。

用户最新决定：先跳过Apple Container，优先Docker等通用容器。已停止Apple安装包下载并清除本轮不完整文件；没有安装运行时、启动服务或拉取镜像。当前正式实例及已部署的候选检查保护不变。

## 后续方向

以Docker兼容接口和OCI镜像为基础，不把Apple专用CLI、安装器或VM接口写成项目依赖。先支持实际Docker Engine，再评估Podman；不能仅因命令相似就宣布所有运行时都兼容。

配置模板：config/examples/candidate-isolation-oci.json。它是尚未启用的计划，不是当前实例配置。

后续实现保留以下要求：固定镜像digest、无网络、非root、丢弃能力、禁止提权、只读根目录与源码、不挂载宿主可写目录或Docker socket。CPU、总内存与PID数量由容器资源限制控制；临时写入用有界tmpfs，产物通过独立有界通道回收，不放宽日志或LLM预算。

Docker提供cpus、memory、memory-swap、pids-limit、read-only、network、security-opt、tmpfs等相关接口；实际使用仍需核对引擎与cgroup能力并验证生效，不以命令行参数存在替代验收。[Docker官方运行接口](https://docs.docker.com/reference/cli/docker/container/run/)

Linux Engine的容器与宿主共享内核，macOS/Windows的Linux容器通常经虚拟化运行。通用的是镜像和接入接口，不应把各平台都描述成每容器独立VM。远程Docker上下文的挂载路径也不能按本机路径处理；首版应要求明确的本地引擎。

## 恢复实施时的顺序

1. 确认要使用的Docker兼容运行时与安装范围，再准备镜像。
2. 实现启动、资源核验、只读输入、产物传输与按本次容器ID清理。
3. 使用合成数据做必要边界和资源验证，不调用真实模型或故障注入正式实例。
4. 验收后明确切换候选检查后端；部署继续由CLI控制。

本轮不继续安装、下载镜像、实现或部署该后端。Apple原生方案的历史研究保留，但不再作为优先实施路线。
