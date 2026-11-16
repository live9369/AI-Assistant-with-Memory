# IM10 实现与隔离验证报告

日期：2026-11-10；状态：实现收齐，等待统一验收。新合成隔离数据库与确定性端口；无真实模型、网络、工具副作用、迁移、部署或当前实例操作。

## 交付

`digital_life/application/tool_learning_recall.py`、`tests/test_tool_learning_recall.py`及IM10详细设计。本项未改冻结合同/DDL/Runtime。保持冻结RecallRequest/Result/Item，另有固定trace admission begin及独立输入登记helper，不授予业务写回调。

用途隔离：普通经验只真实C1 accepted+C2当前表示/整组当前ready；旧文字/原来源保留真实memory revision及原始性质，不升级shadow。独立candidate/原件无合法映射只能controller_audit临时投影。as_of选实际时点版本、specified精确Ref登记；未知Scope不自动匹配，false/0/null/unknown不混同。

controller_audit在stop/WAKE_DISABLED仍可授权查看，SQLite query_only强制只读，不建run/item/event/访问、不写共享账户、不登记模型inputs。正常执行必须真activity/context/account、八维原账本和本run已entered的真实预留；本人slice不因全局remaining扣减而变0，不能借其他run或重用一次机会。每次实际read_entry独立保留，主trace失败不抹掉已进入事实；后续须结算/核对并取得新机会，不能刷新预算。

受控reader覆盖资格/metadata/屏障/Scope/语义端口和原件的实际逻辑字节读取，资格与登记共用scan，回调后重核期限。整项预算不裁掉限定。只有同次已验不可变材料缓存，权限/epoch/head/组始终当前检查，结束清空。公开有限覆盖不泄漏隐藏存在/数量，空结果不是世界否定。

source_refs真实tokens、typed访问/删除关系及组其他成员当前依赖进入trace与输入。完整item与body字段分别有正确摘要，F1可阻断本源、旧文字原source或组其他成员。delete-only普通撤权不当支持失效，erase仍阻断保留元数据。最终retention回调后再核全部来源，再作无回调控制/期限检查；重放不永久复用权限或旧current head。

## 验证

专项为42项；本次预统一运行41项通过，唯一错误为测试耗尽原账户后仍拿旧已消费机会，已改清空旧机会并另证实新1字节预留被真实原账本拒绝，该目标复验通过。最终全部42项以统一门禁case清单为准，不把局部重跑当总体验收。

覆盖：正常真实trace；完全零写停机审计；无真context/run/原account拒绝；C1无C2不直读；旧文字原版本与原source A单独F1后replay/input callback拒绝；深依赖scan1、大metadata/语义回调同reader字节上界、资格回调跨期；整项token/k/scan/byte边界；无关近期不填充；无回退许可不修复；retention撤回前不存正文/不回缓存；as_of真实早版本及不重复历史；组ready仍在但另一成员F1时拒绝；未知/false/0/null；双库隐藏/不存在公开projection相同；全量输入预检与部分失败默认无派发许可；delete-only与erase；本人全剩余预留可用一次/他人预留与无slice拒绝；原账本耗尽不重置。

开发历史保留：`outputs/acceptance/tool-learning/im10-development-probe-01.json`记录早期fixture已有input而误断言总数0，原源码快照未知，不重建。另曾把runtime_event的object与artifact同时设为非空，触发现有互斥约束，已撤回该优化，未改DDL。引入真实预留后重放需要更多真实读取，相关fixture在C0前预声明足够原始300000字节（组500000、scan512）并实际reserve/entry/计量settle，未放大任何已建立账户。小预算拒绝与原cap耗尽正反例保留，不跳过末次检查。

## 必须承接的接口与限制

所有真实RecallAuthority/EligibilityAuthority默认拒绝。IM11必须接真实M04/来源/Scope/recipient/retention、索引与受控reader、可信tokenizer/上界、原account的真实run预留/实际物理读取/known与unknown结算。测试使用真实IM05账本的确定性本地读取与机械身份，不冒称生产授权、模型输入或真实供应方账单。隐藏枚举量不作公开coverage，内部实际用量由可信meter记录。

legacy普通活动没有初始八维账本时明确拒绝新TL执行，不能猜预算；IM11为新schema4活动在原account按真实初始授权一次绑定，旧路径兼容归IM15/16。本项不临时造新活动/预算去掩盖限制。

输入helper只做全量预检和逐条持久登记，没有assembly完成许可；失败可留部分事实。IM11须绑定完整packet/字段/来源manifest和target hash/revision，持久化成功标记，全部登记前/部分失败后禁止actual callback，派发与返回使用重查所有实际inputs。仅查询或prepared不构成进入模型证明。

IM12清理须覆盖item/完整结果event及payload、原run/活动管理轨迹、输入包和相应摘要；read_entry只保留允许的最小管理事实，不将其永久豁免删除范围。未经接纳的原件、格式或分类本身不是世界真值/学习收益。本项未操作正式生命实例。
