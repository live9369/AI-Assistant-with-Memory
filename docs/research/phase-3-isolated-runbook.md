# 原初00 V0.3 隔离验收与管理说明

> 本文保留V0.3操作历史。当前目录和模板已调整，请使用 [V0.4隔离说明](../operations/isolated-runbook.md) 与 [LLM配置](../operations/llm-configuration.md)。V0.3结果已归档到 outputs/history/v0.3.0/。

日期：2026-11-08。本文只说明已实现的管理入口和隔离复验，不授权移除正式实例的禁止唤醒标记。

## 1 已有产物

| 位置 | 内容 |
| --- | --- |
| docs/research/phase-3-full-system-progress.md | 本轮实现与验收报告 |
| docs/research/phase-3-metric-dictionary.md | 188项指标／验证协议逐项字典 |
| outputs/isolated-acceptance.json | 90项统一检查、逐项结果和正式实例文件摘要 |
| outputs/local-model-acceptance.json | 真实模型用量、工具及版本运行证据，模型已停止 |
| outputs/distribution-acceptance.json | 脱离源码目录的安装包检查及摘要 |
| work/distributions/primordial_00-0.3.0-py3-none-any.whl | 可安装工程包，不包含模型权重 |
| work/isolated-model/assets.json | 本机56个模型／程序文件及库链接校验清单 |
| config/model.llamacpp.example.json | 已验证后端的配置示例 |

临时测试数据库、临时模型日志及工具输出在测试结束后清理。保存的验收记录不包含正式实例原始内容。

## 2 重新统一检查

在项目根目录执行：

```sh
python3 scripts/verification/verify_isolated.py --real-model
```

需要本机模型程序、权重、回环监听权限和子进程权限。所有运行实例都由 TemporaryDirectory 新建；代码只解除这些临时实例的锁。正式实例只做只读文件摘要比对，不打开其生命活动流程。任一正式文件内容或文件集合变化，或者锁变化，验收不会记录成功。

不运行真实模型时：

```sh
python3 scripts/verification/verify_isolated.py
```

该模式跳过三项真实模型测试，其结果不能代替真实模型验收。默认统一检查也包含旧版最小原型的临时进程回归；这与唤醒正式实例不同。

## 3 单独启动模型服务

以下入口只加载模型，不启动任何生命实例，运行在前台，Ctrl-C 关闭：

```sh
python3 -m digital_life serve-model --assets work/isolated-model/assets.json --logs work/local-model-logs --port 18081
```

服务绑定127.0.0.1，使用显式本地文件、CPU与离线模式，不下载权重，不安装系统服务。若清单、权重、程序或内部库链接校验失败则拒绝启动。不得把示例小模型的接入通过理解为复杂任务质量已达标。

权重来自 [Qwen官方GGUF仓库](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF)，程序来自 [Ollama v0.40.15官方分发](https://github.com/ollama/ollama/releases/tag/v0.40.15) 中的 llama-server。文件摘要保存在清单和实现报告中；重新下载后必须核对，不能跳过校验。

## 4 准备一个仍锁定的新演示实例

下列命令只创建、查询和采集。示例路径不是正式实例：

```sh
python3 -m digital_life --data work/review-instance prepare --model-config config/model.llamacpp.example.json
python3 -m digital_life --data work/review-instance inspect
python3 -m digital_life --data work/review-instance collect-metrics
```

prepare 保留 WAKE_DISABLED 和用户停止状态；采集不调用 LLM。模型服务已单独启动时，可以用 model-probe 检查可用性，它也不推理。configure-model CONFIG_FILE 在控制面停止时追加模型配置版本，不改写旧思考请求。

本文不提供解除正式实例锁的步骤。隔离完整运行已经由统一检查中的临时实例覆盖。

## 5 指标的两个入口

1. 运行期由 Runtime 自动采集，每个已处理任务后及空闲每15秒触发。collect-metrics 是同一采集器的显式管理入口，七维内部状态也会更新。
2. 人格、认知、相关性或长期质量等指标必须有独立评测依据。通过 Metrics.observe 或本机受控 API 的 POST /v1/metrics/observations 提交 metric、record、source、case、dataset，再由统一采集器聚合。

同一数据集同一案例同一指标的重复提交幂等，提交不同结果会冲突；运行探针不能由外部评分覆盖。缺少真值或无适用样本时记录NULL及原因。科学指标没有样本，不影响其采集通道已实现，但不能把它标为科学验收通过。

## 6 版本与停止语义

stage-release 只保存候选，不启动进程。deploy 才会显式启动并前台监视，默认不安装后台任务。新版本需先完成完整性、schema兼容及就绪握手。已实现就绪前失败、激活后失败、退出和心跳过期处理，回退仍受用户停止与禁止唤醒锁约束。

当前批准迁移路径只有schema 2→3的兼容扩展，要求停止运行，记录校验和及迁移前快照。版本回退切换代码，不倒退生命历史。未来不兼容迁移应另行设计，不能借用本轮测试声明支持任意schema回退。

stop 持久记录用户停止。resume 不移除 WAKE_DISABLED，恢复副本还受 RESTORE_RECONCILIATION_REQUIRED 约束。监视器收到用户停止不会自行重启旧版本。

## 7 删除、恢复与学习

memory/delete 为原有删除申请；memory/purge 为显式受管存储清理，要求控制面停止。派生链、制品、显式纳入的已登记备份和含敏感内容的受管快照按范围处理。未登记的外部副本不扫描，不声称SSD取证级擦除。配置保护冲突会阻断，避免隐式破坏身份。删除不撤销已发生的外部工具作用。

学习撤销使用 Learning.rollback，追加新版本和 reversal_of，不覆盖原记录；需要控制者及证据，后续已改变的对象不能被旧撤销强行覆盖。健康报告分维度保留unknown，认知正确性不因程序能回答而自动变为healthy。

## 8 安装包检查

```sh
python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir work/distributions
python3 scripts/release/verify_distribution.py work/distributions/primordial_00-0.3.0-py3-none-any.whl
```

安装包检查在源码目录之外解包、导入和创建临时实例，确认SQL、页面、指标与兼容资源齐全，并验证旧原型的初始化资源可用。它不会启动模型或生命运行进程。
