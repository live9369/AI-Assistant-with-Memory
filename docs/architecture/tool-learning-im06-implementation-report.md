# IM06 实现子报告

日期：2026-11-09；状态：单一实现者交付，42项专项通过，统一验收与任务状态由root登记。

## 交付

- `tool-learning-im06-design.md`：详细设计及实际端口/扫描边界。
- `application/tool_learning_eligibility.py`：依赖与输入登记、真实引用/修订投影、Scope代次、上游资格、固定请求快照与受门禁保护的同步替身入口。
- `application/tool_learning_invalidation.py`：合法F1原子change/epoch/barrier/九域pending义务与已发现输入资格失效。
- `tests/test_tool_learning_eligibility.py`、`tests/test_tool_learning_invalidation.py`：合成隔离正反例。

未修改冻结规范、SQL/DDL、Runtime、IM04/05代码或当前实例；未派生新的IM任务，也未开始IM07。

## 本次验证

命令：`PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest tests.test_tool_learning_eligibility tests.test_tool_learning_invalidation -q`。最终42项通过（资格23项，F1 19项），没有真实模型、外部工具或网络调用。

初次开发检查出现过一个线程测试夹具错误：工作线程在构造变更请求时误用主线程SQLite连接，导致ProgrammingError。已改为主线程预构造请求、每个worker建立自己的Store连接；root保留的初测失败证据不覆盖。修正后的线程和跨进程实际本地函数入口均通过。不是反复挑选某次竞态成功。

覆盖同键异义/旧epoch/同事件新命令重放、默认权威拒绝、伪造来源修订/证据摘要、C0既有账户/期限绑定、管理F1在stop/lock下仍能保护但不解锁、不主动resolve、多原因独立、九域义务及未知覆盖、F1各表/输入更新故障回滚、提交确认丢失核对、Scope换hash不能绕过、明确recipient不适用、delete-only与support分开、上游循环/版本归属、全部request输入复检、注册用途/consumer/提交权威、调用者字典不能换绑实际输入，以及停止/取消/权威回调后fresh复检。

大量重复同节点边、输入条目、屏障及targets清单都有有限扫描边界。资格超限拒绝；合法F1遇缺计划、暂不可用计划或枚举超限，仍保存根屏障与九域pending扫描义务，coverage如实为unknown/partial，不等待传播准备完成才阻断。

线程/跨进程验证实际入口顺序：F1先提交则回调不进入；回调先进入则外部F1等真实退出后提交；同线程重入F1保留已在途事实并拒绝返回后使用。prepared/预留不作入口证明；不声称远端已收到、即时取消或网络原子性。

## 支持边界

权威端口默认拒绝。来源域真实版本、M12当前授权、Scope语义不相交、主体别名/recipient适用、完整请求许可及实际模型预算接线仍须可信组合根落实。内部机械替身证明规则，不冒充生产权限或独立科学评审。

公开资格check不接管调用者已有事务，避免反锁序；登记内部复用自己持有门禁的事务。callback只接受可信本地同步测试函数，未提供模型/网络适配器，不是恶意同进程代码安全沙箱。

F2/F3确认、物理删除、屏障解除、备份恢复及全量旧运行入口接线不在本项执行；IM11/12/13/19继续承接。已发现输入只标blocked/erase_pending，未伪称已删除正文或清除hash；有限targets超集不是所有对象均已判假。全部迁移、部署、启动、唤醒及正式实例操作均未执行。


## 后续依赖修正（原验收历史保留）

IM07开发正例暴露F1回执的技术Slot错配：合法静态来源已知revision=0可由源所有者核验，但不存在object_revision_registry；先前Response.current沿用known源VersionToken，M17按其规则拒绝回执，导致保护F1回滚。现按root裁定统一使用技术current.not_applicable，真实来源版本/已知零不改写，仍保存在change payload，资格代次在source_epoch/barrier。新增静态perception_signal revision0正例，检查没有伪造版本注册。原IM06验收证据不覆盖，由root追加复验记录；此段是明确问题修正，不以替换为有版本memory夹具掩盖失败。


## 2026-11-10 指定修订依赖修正

IM08草稿发现原资格展开按稳定content查全部历史支持，既会混淆版本，也令新修订登记重复。IM08暂停，先独立修复IM06：native gate选定修订consumer，F1闭包保留owner与精确revision并追踪stable-owner/revision下游关联，输入仅失效相应修订（未知关联保守）。稳定owner自身屏障仍核验，source+Scope epoch冻结语义不变。

新增完整合成反例：同一content r1依赖源A，r2独立依赖静态源B；A撤权后r1和r1表示被阻断、r1输入blocked，r2及其输入仍可用；另直接对stable owner合法F1验证自身屏障仍有效。无真实授权/模型/正式实例操作。此前43项历史及root统一证据保留，由root追加本次复验绑定。

本次专项命令 `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_tool_learning_eligibility tests.test_tool_learning_invalidation -q`：44项通过（12.477秒）。新增修订隔离正反例为真实SQLite表与登记，不是仅mock遍历函数。
