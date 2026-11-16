# IM09 实现与隔离验证报告

日期：2026-11-10；状态：专项完成，等待统一验收。固定版本表示、可变控制租约与C2，不操作当前实例、模型、外部工具、部署或迁移。

## 文件与接口

- `digital_life/application/tool_learning_representation.py`：冻结claim/publish，确定性build与受控read_built、短租约、固定stage/整组C2、明确依赖。
- `digital_life/infrastructure/persistence/tool_learning_store.py`：tl_handoff VersionToken按真实row_revision/lease_generation解释；Ref.revision及内容/表示版本仍严格registry；M04固定representation.state窄更新。
- `tests/test_tool_learning_representation.py`：新synthetic隔离测试，无生产授权替身冒称。
- `docs/architecture/tool-learning-im09-design.md`：详细设计、字段/状态/资源与后续端口合同。

## 行为与边界

claim真实递增代次/尝试，限原账户/总deadline和短租约；过期需当前重新领取，blocked/terminal不自动复活。publish只消费真正accepted且仍为M03当前head的指定修订，核完整当前支持、Scope与所有屏障；正文按固定TL-TEXT-1原字段呈现，不增加判断/接纳/gain。body摘要和真实字节双重核验。

独立C2同事务写表示/单调series版本/head/消费/命令；组先保存非ready草稿，最后同一C2切全部表示/heads/消费与group ready，任一成员失败无半组。组stage只保存非秘密worker/principal引用，不保存entry；真实通道由可信端口重新认证解析，每成员使用不同实际entry核验，末次主worker不能覆盖他人权限。

build-only正文已有固定修订delete可达性；stage工件consumer保留来源路径和delete/access关系。F1先到即阻断草稿使用/发布，不等物理清理；body共享hash不混成多版本support。受控read_built在使用前核当前来源/保留/租约，内部裸blob API不是外部授权入口。IM12仍须覆盖build/stage/事件/command等全部受管保留面。

C2清空租约后，最终仍核原worker/generation/expiry快照；末次授权跨租约但总期限有效也全回滚。claim末次跨新expiry同样拒绝。技术响应current是可变控制CAS，未伪造registry或将已知零改unknown。

## 验证

专项命令：`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_tool_learning_representation -q`，29项。包括独立claim/build/publish、精确代次/重领/旧worker、默认真实权限/预算/retention拒绝、正文/Scope/更强claims篡改、0/false/null、stop/取消、跨新lease最终回调/后成员回调令先成员跨期/消费代次回执篡改、C2故障回滚、同命令幂等异义、内容head过时、同series新版本、双不可序列化worker组、缺成员deferred无ready、失去首worker权限/首stage过期拒绝、首stage后独立F1阻断全部后续、build-only erase目标可达和受控读取拒绝。

开发初稿发现实际约束错配：通道对象遇旧字符串端口、series映射NOT NULL禁止NULL占位、重领夹具初始attempt cap仅1。已分别以仅瞬时真实通道桥接、同C2循环FK固定映射、C0之前预声明合成源cap=3解决；未修改已有预算。开发失败保留为问题说明，不把调整正式账户或删约束当通过。

嵌套同连接F1测试仅证明事务内非法重入拒绝、无stage，未冒称F1持久成功；真正撤权/删除先后测试是在stage后独立F1，再到末成员发布。没有真实远程到达或取消证明。

## 未接线与后续归属

RepresentationAuthority、当前源/控制/权限、真实worker通道解析、retention和读取预算端口默认拒绝；测试机械权威不是生产认证。IM11须把每次真实读取/构造/重试（包括M17隐式walk读取）绑定实际operation_ref、原work/account/请求指纹与预留，C2内不新预留，外层实耗结算，unknown保留。技术上界不等于已完成真实八维账单。

IM10按用途召回ready当前表示，不能临时直读C1正文；IM12逐目标清理；IM13负责恢复/合法阶段推进，M04不写work。未增加模型适配器，不作真实学习收益或科学真值宣称。
