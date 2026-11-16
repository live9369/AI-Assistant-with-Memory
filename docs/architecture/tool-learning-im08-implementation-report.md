# IM08 实现与隔离验证报告

日期：2026-11-10；状态：专项完成，等待统一验收。仅新合成数据库、确定性机械权威端口，无模型/网络/真实工具副作用、无迁移或当前实例操作。

实现为 `digital_life/application/tool_learning_acceptance.py`，专项为 `tests/test_tool_learning_acceptance.py`，详细合同在同目录IM08设计。入口保持冻结decide_proposal；未改冻结规范、SQL、Runtime或当前实例。

## 已落地

- M03真实授权入口、八门Check所有者/真实Ref与当前source资格、typed policy和独立controller review，默认权威拒绝；缺材料不能accept，blocked/fail不被incomplete降级。
- 六类Decision：accept/candidate/defer/reject/conflict/reuse；每proposal每round唯一，异义拒绝；candidate默认等待补复核的协调投影，不直接终结或冒用M14写work。
- C1内新Decision、内容修订、真实head CAS、固定handoff/组和命令原子提交；每组成员独立完整权限/来源/预算上下文，重复native目标预拒，任一失败无半接纳。
- 每修订来源依赖与闭合桥接metadata；旧认知对象和native独立身份、当前双基线绑定，旧legacy1→明确legacy2可再评估；new候选已有native时也须review绑定真实head。
- CAS读取技术head不等于使用旧正文。A旧head来源撤回后，独立B加明确expected和当前review可以修复；沿用A、reuse或preserved旧内容仍走完整资格。reuse不增版本/义务/收益。
- 真实字节定位、视图与digest核验、source_report类别限制、0/false/null精确保留；source report不冒称world truth。字节/claims/证据/依赖/bridge/review/policy有上界。

## 专项验证

`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_tool_learning_acceptance -q`：35项通过。覆盖候选→同work合法新round→accept、原生CAS与reuse、旧对象新版双基线、组全接纳/不完整/第二成员故障/逐成员权限/重复target、默认拒绝与伪gate/复核错绑定、最终权限撤回全回滚、来源A失效后独立B修复、拒绝继续A支持、局部locator覆盖、真实类型和值、stop及读取预算端口。

开发中出现过夹具问题：新proposal未更换processing_identity触发唯一约束，以及停止测试调用不存在的Store方法；已修为新独立产品身份和真实RuntimeControl.stop。首次从其他模块直接导入TestCase令unittest重复发现其39项，已改模块引用，最终35项为本项独立计数。开发失败不冒称业务通过；正式结果以统一证据为准。

## 未接线边界及归属

全部真实AcceptanceAuthority、EligibilityAuthority默认拒绝。机械替身不是认证controller授权、科学事实审查或真实预算计量。

IM11必须接通认证review authoring、实际M03/M12/来源域判据、CAS-only元数据权限、真正分阶段read机会与原work/account上的actual operation_ref预留/消费/结算。每个read_context唯一且绑定请求指纹、work/account、当前剩余额度与deadline；不能把阶段名宽泛授予当预算。C1内不新预留，commit重复读取也计，未知用量保留/停止。本项技术有界读取和预算端口不等于已执行真实累计八维账单。

工作阶段推进由实际M14/协调器读取持久projection后执行；IM13承接合法新round和崩溃核对，本项测试仅以隔离fixture推进round，不实现恢复。表示发布归IM09；传播/物理清理由IM12；真实provider/当前实例/部署唤醒均未触碰。不将任何端口存在冒称生产系统已完成接线。


## 统一验收后自查补正

首次统一验收424项、0失败/错误、源稳定；原`outputs/acceptance/tool-learning/im08.json`保留。该次通过后继续自查发现桥接仅标签核验和最后权威回调跨期两个边界，不能据初次通过声称无缺口。现桥接复用IM06闭合_metadata真实映射校验；最终回调后fresh stop/deadline核验。新增consumer/source错投影和末次G08跨精确工作deadline（policy/review仍有效）全回滚反例，专项35项通过；再执行追加统一复验，不覆盖原证据，由root绑定revalidation_refs。
