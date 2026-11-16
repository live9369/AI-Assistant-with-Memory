# T13 联合与长期验收操作说明

V0.1；T13保持validating，短时工程测试不等于长期验收完成。所有示例新建隔离身份，不能指向当前实例；不复制当前身份、记忆或历史。

## 短时联合实验

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/development/run_life_acceptance.py \
  --output outputs/acceptance/t13-review-NEW \
  --duration-seconds 30 --interval-seconds 1
```

输出目录必须不存在；实验期间保持前台终端。程序使用固定推理器、真实受限文件工具、实际子进程和控制者实验反馈，不调用远端模型。每周期保持同一实验身份、记忆、未来承诺，核对睡眠交接并进行真实环境交互。第3、7周期破坏派生索引并核验恢复；不会破坏权威记忆。

适应性实验不固定随机采样，最多12次训练机会：只有实际匹配行为才能得到正反馈。报告保留机会分母、训练前后概率、未训练相似情境、无关情境和回退值。它证明受控习惯机制的局部变化，不代表真实LLM理解能力已经改善。

模型配置、身份或源代码在实验中变化、子进程失败、源记忆前缀变化、证据缺失均不能通过。失败或中断保留失败信息，实验实例停止并写禁止唤醒锁。实验输出用于审阅，不作为正式生命实例使用。

## 核对证据

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/development/run_life_acceptance.py \
  --verify outputs/acceptance/t13-review-NEW
```

校验协议、检查点哈希链、身份与历史记忆、真实进程记录、睡眠交接、环境文件和最终停止锁，不接受单独把passed改成true。普通哈希不是第三方签名或可信时间戳，不主张抵抗能同时改写所有本地证据的攻击者。

report.json分开记录engineering_passed和long_horizon_passed；最终passed只有长期门槛达到才可能为true。固定模型与受控本地环境始终保留范围限制，不表示意识或主观体验。

## 24小时受控长期实验

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/development/run_life_acceptance.py \
  --output outputs/acceptance/t13-24h-NEW \
  --duration-seconds 86400 --interval-seconds 30
```

本轮没有启动该长期任务。它需要保持终端和设备可用，实际经过至少24小时、至少100周期、检查点间隔不超过300秒、至少两次核验修复及多次实际进程续接。阈值是项目工程标准，不是科学界“生命标准”。程序不会安装后台服务、自动部署、清除正式实例停止锁或调用真实LLM。

同时核对单调时间和UTC检查点，设备休眠造成的观测空档也不能略过。设备休眠、终端关闭或人为停止可能使本轮不满足条件；如实记录，不补造经历，不将循环次数转换成经过的时间。计划内等待与真正的控制交接有独立记录。默认固定模型实验与真实LLM长期实验必须分栏，真实模型接入不能靠改报告字段完成。

## 全量验收门控

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/verification/verify_life_acceptance.py \
  --joint outputs/acceptance/t13-review-NEW
```

该命令运行全部隔离回归，需要本机临时端口和子进程。工程测试通过但长期门槛不足时，退出可成功、engineering_passed=true，但T13仍为validating、passed=false，不将TODO标完成。若以后使用真实长期结果，应先复核协议、源码版本、隔离条件和完整证据，再重跑门控。

正式实例的部署、启动和唤醒仍只由既有CLI管理。本项不改变它。未经支持的任意磁盘克隆、全局身份唯一性、机器迁移、开放世界与真实模型长期可靠性仍需单独验证。

## 自洽复核后的证据修订号2

当前检查器要求新的 evidence_revision=2，逐项校验实际请求、回执、修复、身份和睡眠代次。旧修订号保留为历史，不能用于当前版本完成门控。本轮最新短时实验为 `outputs/acceptance/t13-review-joint`，最新复核报告为 `docs/architecture/development-t13-consistency-review.md`。异常退出先停止并锁定实例，再尝试打开运行数据；证据损坏会更新失败结论。
