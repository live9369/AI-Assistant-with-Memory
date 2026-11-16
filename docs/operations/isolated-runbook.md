# V0.5隔离复验

当前版本130项后端及系统检查、21项真实浏览器检查通过，包含管理面板、架构、远程内存协议、本地模型、临时版本进程、指标、回退及安装包。面板用法见[操作说明](management-panel.md)。

## 完整检查

```sh
python3 scripts/release/verify_management_release.py
```

真实模型程序及权重使用本机已有 work/isolated-model/assets.json。模型只监听临时回环端口，运行数据写入临时目录，结束关闭；正式实例只做只读摘要比对，禁止唤醒标记必须保持。远程测试使用内存回复，不访问真实供应商，不需要真实密钥。

使用 --skip-real-model 会跳过三项真实本地模型检查，不能等同于完整验收。只验证后端可另用 scripts/verification/verify_isolated.py --real-model；单独浏览器复验可用 node scripts/verification/verify_dashboard_browser.mjs。浏览器使用新的临时Chrome资料目录，不使用用户登录信息。

## 安装包检查

```sh
python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir work/distributions
python3 scripts/release/verify_distribution.py work/distributions/ai_assistant_with_memory-0.5.0-py3-none-any.whl
```

检查在源码目录外的临时解包位置运行，验证新分层包、SQL、指标与页面资源，不启动正式实例。

## 证据与模板

- outputs/acceptance/isolated-acceptance.json：当前逐项结果、版本、正式实例摘要比对。
- outputs/acceptance/management-release-acceptance.json：后端、浏览器、构建与分发检查汇总。
- outputs/acceptance/dashboard-browser-acceptance.json：21项浏览器交互、关闭状态及无面板执行证明。
- outputs/acceptance/screenshots/：五页与移动端截图。
- outputs/acceptance/local-model-acceptance.json：真实本地模型闭环证据及关闭状态。
- outputs/acceptance/distribution-acceptance.json：安装包摘要和独立运行结果。
- outputs/history/：V0.3与V0.4历史证据，保留原样。
- config/examples/llm/：当前模板；具体用法见[LLM配置](llm-configuration.md)。

本轮未移动 work/primordial00，未安装常驻任务，不提供解除正式实例禁止唤醒标记的命令。当前目录和更新边界见[工程结构](../architecture/project-structure.md)。
