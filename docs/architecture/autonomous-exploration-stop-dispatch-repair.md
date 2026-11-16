# 停止／派发协调修复与G1复验报告

日期：2026-11-08（Asia/Shanghai）。作者：Codex主agent（/root）。  
任务：修复停止与派发、建立新基线、重新完整验证G1；保留原失败证据，正式实例保持锁定。  
设计与行为边界见[AE-RUNTIME-1.1](autonomous-exploration-contract-v1.1.md)。状态：V1.1新基线及完整G1复验通过；真实模型质量评测未运行。

## 1 变更

新增实例级dispatch_gate，使用线程重入锁和跨进程文件锁，将停止提交与模型／工具回调互斥。最终许可检查和实际同步回调在同一gate内；停止、恢复、配置切换、活动取消和策略撤销先取得gate再写状态。管理取消入口调整为gate优先的事务顺序。

工具最终检查限定到已消费的那一次授权与attempt，重检撤销、epoch和参数；未实际派发就拒绝时，记录failed／cancelled、零工具用量和dispatch_blocked，不生成虚构unknown结果。模型对应记录dispatched=False；实际在途异常仍保留unknown语义。

当前Engine已存在的Chat上下文没有删除；新版本直接验证当前代码，不再用V1引擎覆盖导入。原冻结V1与105/111通过、6项停止派发失败的[历史报告](autonomous-exploration-g1-report.md)及原始run全部保留。

## 2 重要行为权衡

不同线程／进程的停止提交可能等待整个在途同步回调结束；不承诺即时停止或固定毫秒确认。已进入的同线程回调可重入停止，不等待自己。新调用必须重检停止状态。完整活动硬墙钟截止、独立问题核验、真实模型探索质量及写副作用仍不在本次通过声明范围内。

## 3 结果

正式run：`g1-20261108T084738Z-f4e46c48`，被测协议AE-RUNTIME-1.1，评测AE-EVAL-1.0，范围workspace-read。直接测试当前工作区，未使用冻结Engine覆盖导入。

- G0：通过，39个冻结文件及4组接口签名核对通过；75个运行依赖文件、10个评测输入归档。
- G1：117/117通过，无失败、缺失证据或看门狗超时。原111个trial全部保留，新增6个场景；原来的24个停止矩阵全部通过。
- 停止提交后新派发0；非法引用接纳0；每请求重复accepted 0；只读重复派发0；预算越界0。
- G2/G3：not_run。M12统一停止确认延迟和M14单位有效探索成本仍not_evaluable。

[完整聚合](../../outputs/acceptance/ae-g1/g1-20261108T084738Z-f4e46c48/aggregate.json)、[预封存manifest](../../outputs/acceptance/ae-g1/g1-20261108T084738Z-f4e46c48/manifest.json)、[正式实例摘要保护](../../outputs/acceptance/ae-g1/g1-20261108T084738Z-f4e46c48/formal-instance-guard.json)。

| 工程指标 | 结果 |
| --- | --- |
| M03引用接纳完整率 | 174/174 |
| M09恢复连续率 | 3/3预注册工程场景 |
| M10重复只读派发 | 0/4复放机会；写副作用未评测 |
| M11停止后新派发 | 0，共25个停止提交边界（原矩阵24个，另有未派发账本审计1个） |
| M13预算越界 | 0 |
| 原始attempt成本 | 模型278、工具80；包含发送前被拒绝的预留，不代表真实调用或计费token |

跨进程互斥场景使用真实独立子进程与Control连接，验证停止等待gate后提交；不比较子进程和父进程可能不同原点的时钟。新策略撤销和活动取消窗口分别覆盖模型、工具；账本场景检查未派发attempt失败、无虚构结果、工具用量0。

## 4 完整回归及修复过程

[完整回归结果](../../outputs/acceptance/autonomous-exploration-v1.1-regression.json)：197项，194通过、3项真实模型测试按原开关跳过，零失败与错误。所有运行实例为临时目录；HTTP／进程夹具只使用临时本机端口。真实模型未请求。

首次完整回归发现Privacy._clean在既有事务内调用Engine.cancel，违反新的gate→事务顺序。修复为隐私擦除及各登记备份清理先取得对应gate，管理取消也按此顺序。该失败没有被忽略；完成修复后重新运行全部回归，再冻结本版并运行G1。

新gate测试还覆盖同线程在途停止重入、另一线程停止等待、真实进程互斥、进程死亡释放、锁顺序拒绝，以及全部原停止矩阵。没有通过放宽M11零违规规则获得通过。

## 5 原失败证据与正式实例

原三个失败run均保留，分别有674、869、870个文件；本轮结束重新计算整棵目录摘要，与修复前记录完全一致。原V1基线、冻结引擎副本和历史G1失败报告未重写。摘要记录见[原证据清单](../../outputs/acceptance/autonomous-exploration-v1.1-prior-evidence.json)。

正式实例保持WAKE_DISABLED，6个文件前后摘要一致。未启动、启用、部署或迁移正式实例，也没有在那里创建dispatch.lock。新锁文件只在隔离实例及实际控制操作中创建。

## 6 文件与接续

生产改动：新增`infrastructure/processes/dispatch_gate.py`；修改Engine、Executor、Control、Exploration、Policy、Management和Privacy。保留当前Chat上下文集成，没有替换推理供应商或SQL。

评测改动：新增`scenarios-v1.1.json`和`tests/test_dispatch_gate.py`；Harness在途竞争改为允许停止线程等待回调退出，仍以真实入口时序判定；场景实现新增6项，运行器支持--baseline v1.1并直接测试当前代码。新增V1.1契约、机器基线及独立检查器，原V1文件不覆盖。

复核命令：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify_exploration_contract_v1_1.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_exploration_g1.py --baseline v1.1
PYTHONDONTWRITEBYTECODE=1 python3 scripts/aggregate_exploration_g1.py outputs/acceptance/ae-g1/g1-20261108T084738Z-f4e46c48
```

G1通过只支持上述冻结源码的workspace-read协调机制。后续可按正式契约准备G2真实模型材料登记、独立评审和运行预算；本轮没有执行G2/G3，也没有建立写副作用、无界活动时限或即时停止承诺。
