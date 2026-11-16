# IM13 实现与隔离验证报告

日期：2026-11-10。状态：实现收尾，专项证据另存；等待根协调统一门禁。未操作正式实例、真实模型、账户、网络提供方或唤醒。

## 交付

- `tool_learning_recovery.py`：闭合核对工件、原work CAS/命令同事务续处理、原阶段/轮次规则、真实停机崩溃分类、原清理计划独立资源续授。
- `tool_learning_runtime_learning.py`：具名原账户恢复读取与真实协调入口。已持久material只发布、不重做推理；候选补真实controller review后同work下一round；C1未发布恢复原handoff；旧租约过期新generation，迟到旧发布拒绝。
- `tool_learning_budget.py`：默认拒绝的recovery/evaluation本次读取scope，精确entry/work/account/run，原控制/未知占用/限额不变。evaluation由独立IM14实际SDK接线。
- `tool_learning_maintenance.py`：当前Bearer全绑定恢复政策、F1持久提交只读查证。原plan续授仍是真实M12，本域不宣称九域完成。
- `data_management.py`：当前权威库驱动的锁定恢复候选，镜像外当前排除消费、精确整库/路径政策、当前来源所有权、受控旧blob补回及真实计量。旧TL镜像通用restore明确拒绝。
- `recovery.py`与CLI：真实认证停机TL核对，旧无TL工作恢复行为保留。

## 已覆盖的实际反例

专项构造真实隔离SDK与受控故障：C1/C2/F1实际提交后丢失确认、真实停止/新进程epoch后续处理、旧租约迟到、完整material已写而Product未提交、原candidate补认证新轮次、旧plan过期后真实续授、旧消费不重置、未知占用不释放、F1 pending不能被旧排除head绕过、私有ACL/单source维护grant/错误目标不授整库复制、备份blobs目录symlink与manifest失败消费事实。通用mechanical authority测试单独标明，不把替身当生产授权。

控制核对scope固定1s/1024行/1MiB，当前policy只能收紧；恢复原work业务读取仍原账户，保护性续授/候选复制有真实独立维护activity/account与进入/结算事实。copy候选不授外部材料读取、并行同身份运行或唤醒。

## 证据与限制

最终专项命令、数量、源摘要与稳定性以`outputs/acceptance/tool-learning/im13-special.json`为准；开发过程失败日志会另存，不能用早期通过数代替最终统一门禁。根须等待IM13/IM14均冻结后顺序运行统一门禁。

支持的真实条件owner限于完整持久Observation stage、当前认证内容review和固定表示义务。没有owner/不确定模型消费/未知外部效果继续blocked，不自动重试原工具或模型。F1核对不解除屏障、不放开pending、不释放unknown。

恢复需要当前权威库及当前镜像外Control仍可信可用；丢失当前库的灾难恢复未实现。不能用旧库回退新历史。未知原来源owner、多身份库、私有来源和不完整排除均拒绝。输出候选永久保持WAKE_DISABLED及RESTORE_RECONCILIATION_REQUIRED，后续IM16/正式控制流程另行验证连续性，仍需授权。物理维护不承诺SSD/OS快照取证擦除、恶意宿主防护或远端服务已取消；本地文件系统/SQLite底层阻塞只能保守保留失败/未知，不虚报远端效果可逆。
