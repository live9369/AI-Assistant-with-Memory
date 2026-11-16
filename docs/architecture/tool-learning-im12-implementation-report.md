# IM12 实现与隔离验收报告

日期：2026-11-10；版本：V0.1；状态：实现收尾，待冻结源统一验收。最终完成事实以 `outputs/acceptance/tool-learning/im12*.json` 中 source-stable、零失败／错误／skip 的统一记录为准，本报告不预填统一测试数量。

## 已交付

- F2 完整 Envelope／verification／实际 owner 动作／CAS／命令原子提交；分原因、分代、分域，不解除 barrier。不可变 F1 minimum plan 保持原样，实际范围、水位与逐目标证据另存。
- M12 真实 SDK：现有 Bearer 认证、当前实例 controller／policy／control、真实来源 owner 与 work/input、明确 erase_scope、独立有限维护账户；F1→M12 F2→受管 F3 可在新的真实凭据隔离实例完成。未知语义 owner 不一键确认。
- 原 work 过期／halted 不阻止当前合法保护性 F1；旧 work/account/账本不抬限。默认拒绝的独立预算端口只允许实际 M12 proof，普通账户路径不变。tokens/tool=0、真实 finite attempt=1；维护实耗 attempts=0，实际 Engine 入口拒绝普通推理／工具用途。
- 真实 target journal、前置排除记录、artifact tombstone、受限业务行 purge、当前 SQLite secure_delete/checkpoint/VACUUM／主文件验证、独立索引／缓存文件、登记单文件和完整 manifest 备份目录清理。
- 同实例独立来源共享 artifact ID 时不破坏 B；跨实例同根 blob 有任何真实引用不 unlink。路径、symlink、hash、inode、未知提交／中途失败均保守处理。
- 外部排除根/index 实际持久化；当前 control_commands 固定 root identity 与 head，空目录／旧 anchor／缺失记录不变成“空历史”。实际恢复仍须 IM13/16 消费当前控制面记录。
- HTTP material 读取→编码→真实写出处于同根 gate；隔离真实 HTTP 验证 F1 先后顺序和实际 slow-client 有限退出。

## 实际文件

新增：

- `digital_life/application/tool_learning_propagation.py`
- `digital_life/application/tool_learning_maintenance.py`
- `tests/test_tool_learning_propagation.py`
- `docs/architecture/tool-learning-im12-design.md`
- 本报告。

受限扩展：

- `tool_learning_invalidation.py`：默认拒绝 `verify_protective_budget`；真实 M12 独立控制资源分支，原账户行为保持。
- `infrastructure/persistence/tool_learning_store.py`：tl_propagation actual-kind row_revision/generation 技术 token，普通 Ref.known 修订仍严格注册，不造 registry。
- `application/engine.py`：仅控制面 contract discriminator 查询，拒绝两种维护活动进入普通推理／工具入口。
- `entrypoints/http.py`：具名 material dispatch/send 边界与有限 socket timeout；无新增危险清理端点。
- `tool_learning_runtime.py`、`execution.py`、`services/memory.py`、`memory_quality.py`、`management.py`、`privacy.py`、`data_management.py`、`entrypoints/growth.py`：已有真实保护状态下的最小 featureoff legacy 拒绝；无保护 schema3 不改原功能，未声称完整兼容 bridge。

没有修改冻结合同、DDL 或正式实例；没有实际模型、账户、外部工具网络或正式唤醒。真实网络验证仅新隔离 loopback HTTP，不能写成“从未启动任何服务器”。

## 证据与开发过程

已完成的开发验证（均为开发事实，非冻结完成证据）：

- `im12-final-special-04`：69 项（64 IM12＋5架构）通过，25.605s；含 featureoff 下真实F1/F3 pending无旧正文/模型进入、普通无TL schema3真实召回及已合格只读审计。最终源以统一门为准。
- `im12-final-special-03`：较早61项通过，24.568s，含真实本地 HTTP、真实 SQLite／文件清理、真实凭据 SDK及恢复围栏。
- `im12-final-special`：83 项（IM12、受影响 F1、架构）通过，28.641s，开发候选范围。
- `im12-probe19`：较早58项通过，23.228s。
- `im12-genuine04`：11 项真实凭据专项通过，4.606s；从真实 SDK F1 起验证，不用当前 grant 追认 Mechanical F1。
- 较早 probe17 为 47 项／18.177s；后续实际接线与共享保护使范围增加，不能复用为最终源完成证据。

日志同时保留于 `/tmp/im12-*.log`；可归档的开发集合见 `outputs/acceptance/tool-learning/im12-development-probes.json`。早期变化中的完整源快照不可得，明确记录 null，不用当前源伪造旧 source-stable 证据。开发失败没有覆盖或改成通过：probe02 暴露 Budget.max_attempts 最小1与维护账户0冲突，最终真实有限 cap=1但无操作授权；probe06 是字段名 max_scan_count 错，应为冻结 max_scan；probe07 的真实读取超出夹具原请求小 cap，改为在独立维护授权初始就声明相应 caps，不修改已建立账户；probe10 包含复用 F1 command ID 与跨 plan 唯一目标冲突，分别修新命令ID和明确 Conflict；probe11 的 loopback bind 被环境限制，随后经工具许可在隔离本地执行；probe12 错把旧 epoch 的 409 预期为403，改为精确实际旧版本409，并仍断言无源正文。每项实际原因保留，不挑任意 blocked 当语义证明。

专项命令：

```sh
python3 -m unittest tests.test_tool_learning_propagation
```

冻结后唯一统一入口：

```sh
python3 scripts/verify_tool_learning_task.py --task IM12 --complete
```

本项源影响 IM06、IM11；统一门禁覆盖对应既有专项和受影响旧回归，完成后由根绑定追加复验引用，既有完成历史不重写。

## 范围与后续接口

真实认证是当前实例 SDK 的真实 Bearer／policy／scope 链；F1→F3期间当前Control的pending directive防旧head遗漏新变化，独立B的保守inventory目标不自动授予删除权。MechanicalPropagation 等测试端口仍只是机械替身，不是生产授权。真实 SDK F1 当前支持有实际 work/input/trigger 对应的本人／本实例 Signal；其他源种类缺 evidence/owner adapter 时明确拒绝，不按名字推断拥有权。M12 root qualification hold 有实际核验，M04 有实际 withdrawal/group/lease/input 适配；M03/M14 等科学语义重评仍由实际 owner 端口决定，未知保持 pending，不自动产生获益、支持或世界真值。

物理 plan verified 仅指其明确受管目标，不等于九域 F3 完成。`completion` 要求所有必要域真实覆盖；真实 SDK 正例只有 M12 签收时，其余八域仍 pending。独立索引／缓存仅支持已知具体位置，动态未知 adapter 为 not_run；远端／已交付／世界效果 unknown 或不可逆。当前 SQLite 验证不声称 SSD、OS 快照、已删除 inode 取证擦除或模型权重删除。

维护 Scope 必须明确允许需要的最小控制 metadata，尤其 source fingerprints／plan expected hashes；严格禁止现有不可变控制痕迹的范围不能完成。默认不把 hash／摘要当无害数据，也不删根 barrier 伪装完成。

IM13：真实原 plan continuation grant、unknown commit/resource 对账、waiting/review/恢复调度；不同 plan 不重绑原 target，耗尽不会自动续费。IM13/16：从当前协调器可信 Control 读取 root/head，应用全部当前 exclusions 后才能恢复／回退；当前 `restore_constraints` 明确 `restore_authorized=false`，没有宣称既有 restore_bundle 已接线。IM19：最终整体验收再次覆盖最终源。当前实例始终未操作。


## 统一01中断事实

`outputs/acceptance/tool-learning/im12-development-unified-01-interruption.json` 保存一次执行管理失误：统一01尚运行时，后续必要 featureoff 修复继续改变了源，因此它不能成为稳定完成证据。仅已确认的隔离 verify PID36350 收到 SIGINT，exec66806 返回130；只读核查无对应 verify 或 multiprocessing helper 遗留。正式实例未操作。

原始 in-process before 源快照与完成部分测试总数未导出，明确为 null；快照助手另遇 runpy 相对路径错误，未用新源重建旧 snapshot。记录的221文件摘要是中断后当前源，不冒充 before。traceback 日志归档为开发历史。统一02须在公共runner补齐真实PID／before snapshot／live testcase／中断状态记录后，重新冻结再执行；01不登记完成，不覆盖已有历史。
