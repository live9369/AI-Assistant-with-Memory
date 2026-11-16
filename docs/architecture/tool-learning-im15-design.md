# IM15：schema4 兼容桥接与部署保护

日期：2026-11-10。状态：详细设计。依赖IM11、IM12、IM13已完成。仅合成隔离，不迁移正式实例、不调用真实模型、不安装后台服务。

## 1. 两个独立开关语义

`qualified_plane_required(store)`：schema4始终走完整装配、当前来源资格、输入/结果/外部实际使用门；schema2/3仅已启用严格策略时进入。`strict_feature_enabled`保留当前policy的新增TL学习开关，默认false。学习Coordinator的admit/assess/decide/publish等真实业务入口另外核该开关，关闭不撤销F1/F2/F3、保护性维护或已合格只读审计。

schema4 bridge关闭新学习仍能在已授权普通活动原八维额度内使用严格聊天/执行/材料读取。旧pending活动缺真实八维原账本就blocked，绝不补猜cap、换账户或重置历史。不能借bridge把旧source report/shadow当accepted经验。

## 2. 可信桥接基线，而非声明自证

新`application/tool_learning_bridge.py`定义闭合`TL-SCHEMA4-BRIDGE-1`能力合同，版本声明允许2—4。stage时schema4候选必须与当前已加载、受本项目审核的完整可执行源基线逐文件/摘要匹配，包含包外可执行导入面，拒绝少文件、篡改代码或额外shadow模块。不是任意候选自己写manifest/测试bool就能取得能力。

实际可信stage将build_hash、基线manifest摘要、能力合同/包版本及schema范围绑定到当前Control的不可变幂等记录；verify/compatible/recoverable再次核真实release文件集合、声明、对应当前Control记录。旧2/3版本不能因改一个schema_max或自报handshake在schema4启动/回退。今后新代码须先成为新已审查主程序基线、经过新的隔离验收，不能自动继承旧能力证据。

Runtime准备及running handshake报告真实schema、能力合同/加载文件摘要/部署身份，不固定自报schema_compatible。启动前对当前加载路径和文件集合核验；激活gate前再次核当前Control/声明/数据库兼容。Deployment不只信driver返回bool，schema4必须匹配已验证部署能力。heartbeat解析真实部署/能力/状态，文件mtime只是活性的一项，错误身份、缺失、过期或进程退出均失败停止。

## 3. 激活、失败和回退

沿既有prepare→activate→running状态机；不在IM15做schema迁移。当前库schema4且没有有效桥接候选就拒绝。prepare/activation/运行/heartbeat失败只回退到当前可信Control仍核准、实际可读schema4且执行同TL保护的版本；不降库、不覆盖当前C1/C2/F1/记忆历史。无合格旧版本则失败停止。

用户stop/WAKE_DISABLED/RESTORE_RECONCILIATION_REQUIRED优先：stop不触发自动回退/重启，恢复锁不被部署解除。主库历史只读核对，控制部署状态变化不得改原预算、清屏障或擦除排除记录。已恢复候选的当前外部排除与身份核对仍归IM13/16，不因bridge有效就授唤醒。

## 4. 验收

合成真实release基线stage/验证、实际独立Runtime准备/有限idle运行/heartbeat/停止（无模型任务）、加载声明与能力匹配；篡改/旧2或3/schema4自报假能力拒绝；featureoff实际严格装配/来源屏障生效且新学习拒绝；旧无原cap pending不能进入模型；失败各点、heartbeat错误/过期、用户stop不重启、桥接回退保留原库及屏障。所有子进程属于新临时实例，退出回收；不安装服务。专项冻结后一次统一门禁（含本机loopback时请求所需本机权限），IM15 complete后才展开IM16。

## 5. 实际实现收敛

保护判据也适用于尚未迁移的2/3库：已存在tl_dependency、tl_input_dependency、tl_content_revision、tl_representation、tl_product或tl_recall_item等受管材料，或已有屏障/erase/当前Control排除记录，均不得落入旧读取/输出路径。空TL表且无保护、无严格policy的旧2/3行为保留。存在材料不是读权；实际recipient/source/retention仍由同一资格门核。任何保护探测错误不得按“无保护”降级。

schema4或保护库的真实tl_*表、约束、触发器、索引必须匹配冻结DDL；仅修改PRAGMA版本号不足以取得兼容能力。基线记录位于当前Control，verify/recoverable/实际Runtime加载/准备与running/heartbeat分别校验。实际加载校验核sys.modules的digital_life路径及字节，不能用调用者传一个目标路径字符串代替已加载版本。就绪JSON有大小上限、nofollow及严格解析，schema/布尔/阶段/PID/能力字段均校验；准备/运行不代表推理就绪，model_access_verified=false、inference_ready=unknown。

source_files使用有总节点/文件/字节限制的scandir，进入子目录前剪枝config/local精确前缀、.codex/.agents/.aws等私有控制根、运行目录与构建缓存，不读其内容、不复制、不生成其manifest哈希；公共config/examples保留，未知包外shadow可执行模块仍拒绝。该基线不证明宿主/第三方Python依赖完整性，也不是任意代码的自签证书。

无合格普通活动原八维cap时，桥接Runtime只做有限控制面policy/heartbeat检查，不猜原cap、不读任务正文、不领取模型/工具机会。控制读取有固定1秒/1024行/1MiB上限和实际累计消费事实；不冒称所有控制开销来自活动账。schema4/保护库不做准备时联网probe，实际模型路由在合格原请求用点验证。旧无保护2/3的原probe/采集行为保留。

原SourceUpdates在无保护旧2/3库的变更候选明确收窄到max3、移除桥接能力并留审计，不能继承当前基线的schema4承诺。schema4/保护库的任意新代码仍需新的已审核基线，不能通过“窄化”绕保护。此限制是可信基线边界，不宣称任意自更新已能自动取得新schema4资格。
