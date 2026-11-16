# IM15 兼容桥接实现报告

日期：2026-11-10。状态：源码与报告收尾，统一门禁结果以独立证据为准。范围仅新合成实例/临时release、有限前台Runtime及本机库存替身；未操作正式实例、调用真实模型/账户或安装后台服务。

## 实现

新增`tool_learning_bridge.py`，绑定实际完整公开可执行源集合、当前Control基线记录、版本/能力/加载路径/实际模块字节与真实保护DDL。篡改、额外shadow模块、自报schema4声明、无基线记录和bool-only readiness均不能取得桥接资格。私有配置与控制目录在递归前剪枝，公共配置样例保留。

`control_plane.py`、`deployment.py`与实际`entrypoints/runtime.py`接线：prepare→activate→running分别核部署身份和能力，heartbeat核真实阶段/PID/能力/时效，失败只回退到仍合格的桥接代码，不降库或回写原历史。用户stop/恢复锁优先，不自动重启或解除锁。schema4/受保护库的准备只证明存储/控制/门禁，不联网查模型；模型与额度未验证明确保留unknown。缺普通原cap时只有有界控制面读取。

`engine.py`、`execution.py`、HTTP材料接口、配置版本、实际LocalRuntimeOwners与StrictEngine选择`qualified_plane_required`，与默认false的新TL学习开关分离。受管材料存在时也保留资格门，不必等F1后才保护；关闭学习时普通已授权严格活动仍使用原账户，旧pending缺原八维账本拒绝。Native Coordinator在admit/assess/decide/publish/project/resume及stage入口前检查学习开关，不能先消耗机会/写stage再拒绝。

`source_updates.py`仅无保护旧2/3变更候选收窄max3并移除bridge承诺、记录审计；schema4和已有保护状态不得这样绕过新基线审核。`resources/release.json`与实际包版本相符，范围2—4并声明闭合桥接能力。

## 开发验证与最终证据

已进行针对性合成验证：实际独立Runtime无模型空队列准备/激活/heartbeat/用户停止；受注入的prepare/running/heartbeat失败与回退；旧2/3、自报声明、篡改和无保护DDL拒绝；当前真实F1停锁只读审计；学习关闭后普通fake模型完整严格思考、旧pending不追认cap；受管schema3也继续保护；私有目录哨兵无遍历/读取/manifest记录；真实旧源码更新本机回归和显式能力收窄；当前IM14真实sealed报告到shadow采用正例保留。

开发中曾有测试漏传既有prepare/Memory.retrieve参数及scandir哨兵未兼容shutil目录fd，属于夹具错误，已按真实接口修正；失败日志保留。此前effect开发回归30项198.817秒自然完成，精确停止前PID已退出，因此未发送信号；该过程有后续源码修订，不能作最终稳定证据。普通fake聊天一轮约95秒，属于实际性能限制，不宣称日常性能充分。

最终固定源统一结果、源摘要、运行PID/进度与完整测试数以`outputs/acceptance/tool-learning/im15*.json`及唯一runs目录记录为准；不将多次开发通过数相加冒称独立完成数。loopback测试需要本机临时HTTP权限，禁止真实模型和正式操作。

## 限制与后续

当前基线是受信当前程序的完整公开可执行源匹配与隔离验证，不是任意新源码的签名或自动科学正确性证明。新schema4变更须重新成为已审核基线；旧无保护2/3自更新路径保持。桥接不会修复旧活动缺失的原始八维计量事实，不会把旧shadow提升为世界事实，不授新的来源权限或解除erase。

本项不执行迁移。IM16随后验证2→4/3→4、新历史保留、失败回滚与当前镜像外排除消费。恢复候选仍保持双锁，不把桥接就绪当迁移/正式部署/唤醒授权。模型真实路由仍须可信计数/硬限等实际能力；本轮无真实模型验证。宿主恶意修改、OS/SSD取证擦除及远端取消不在本桥接证明内。

## 统一01与定点修正记录

统一01实际756项、源稳定，仅旧featureoff测试1项失败：已进入qualified分支后，未提供live process的夹具先被真实身份/epoch拒绝，原正则仍期待旧legacy拒绝文字。保留该失败证据；测试现明确区分身份拒绝与独立真实Bearer审计的`audit source barrier`拒绝，仍保留零模型/零召回/零导出断言。

同轮结束后修正Runtime读取顺序：ordinary_ready/真实原cap检查在transfer_inbound之前。缺cap时不触及待转正文、保持控制队列pending与进程alive；旧无保护schema3正常转入并幂等ack保持。真实腐坏inbound哨兵与旧正常transfer、明确F1审计等5个目标案例通过（3.732秒）。不将旧身份拒绝冒称F1实证，不覆写统一01快照；最终统一02覆盖本次修改。

统一02实际758项、源稳定，仅恢复symlink夹具1个error：夹具无序选择非signal artifact时可能删到当前认证配置，尚未到达预期路径门。生产恢复逻辑未改。现精确选取既有独立合成inventory正文，断言不被任何configuration_versions引用，保留symlink拒绝与failed settlement断言；该单例5次新临时夹具重复验证通过（2.398秒），不作5个独立科学样本。统一02证据保留，最终统一03另行记录。
