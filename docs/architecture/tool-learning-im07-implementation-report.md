# IM07 实现子报告

日期：2026-11-09；状态：实现者交付39项专项通过，root统一验收和任务登记为准。

## 交付与范围

主设计`tool-learning-im07-design.md`；实现`application/tool_learning_observation.py`；专项`tests/test_tool_learning_observation.py`。本项未改冻结规范、DDL、Runtime、计划或当前实例，也未提前实施IM08。IM06依赖修正已由root单独复验、追加证据后才恢复本项。

实现确定性源定位/提取、固定版本typed baseline比较、四类Product、有限等待/停止/失败、跨键原工作产品复用、typed原件及完整思考输入/输出/状态持久化。生成的是source_report及M03提案，不创建Decision/content/head/表示；EffectAssessment为not_measured，gain保持unknown，不预造收益。0、false和来源明确null按真实JSON值保留。

自动比较不把相同unknown Scope、同名label、False与0、known/null条件或未知值当相等事实；唯一可比目标按实际comparison选择，保留所有反证。多目标等待明确拆分，旧cognition对象到native tl_content的接受映射留IM08。

## 思考、计量与保护

只在固定计划要求独立解释时调用`ObservationThoughtPort.generate_fresh`。每次完整输入无session/history，request_id等实际审计行ID，model/config/provider与调用端配置及reported route均核对；packet含父剩余和阶段cap的input/output/bytes/deadline等界限。模型输出只能提供有标识的解释文字/局限/缺项，不能直接写可接受的world facts或gain。

preflight是可信计数/限制能力接口，不代表本轮验证了供应方真实tokenizer或硬限；实际provider和Runtime连接属IM11，当前默认拒绝。隔离仅确定性新鲜端口，未调用真实LLM、网络或原工具。

原件/view/baseline逐份读，读前查可知尺寸，成功完整性校验后累计scan/items/bytes；无法确认实耗为unknown，不二次结算覆盖已知事实。本地elapsed使用monotonic实测。模型真实本地入口与预留分离；usage全维齐备才known，未知保留占用，已知超额存事实并停止，错误route不当合格输出。

IM06资格在含源材料写入前与返回后检查；retention和响应原件写入持同一dispatch_gate，F1先到或回调内erase时不新存受禁正文/hash。合法已写响应先于竞争F1提交的顺序有线程实测，后续使用仍查当前资格。

## 测试与开发中发现的问题

`PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest tests.test_tool_learning_observation -q`：最终39项通过。覆盖四类产物、已知零/false/null、unknown和真实比较目标、无变更/冲突、有限缺项、large view预限、第二baseline失败累计计量、缺失工件unknown、完整fresh输入输出与真实ID/limits、配置/route不一致、input/bytes预限、部分usage/超额、运输异常、无隐式历史、F1先到/在途/retention并发、准备/主提交幂等与非processing禁止补发。

开发反例发现静态source合法revision0与IM06 F1 Response.current known Token的M17版本登记要求冲突（两个新增用例失败）。按root指令暂停IM07，单独修正IM06技术结果Slot并新增静态来源正例；root保留原历史并以192项追加复验SHA绑定后，才恢复IM07。这里未用memory夹具替换掩盖失败，IM07仍有静态source0的真实正反例，且没有伪造版本登记。

当前业务只适用于明确准入的本地来源、固定计划和可信域解析；真实来源/M12/比较/retention权威均默认拒绝，不把测试授权当生产许可。未完成provider真实调用、旧全链门禁、M03接纳、表示发布或完整恢复；后项仍需逐项工程与隔离验收。
