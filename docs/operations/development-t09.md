# T09 人物与关系认知使用说明

V0.1，有界工程版。默认关闭；本轮不更新或唤醒当前实例，不重建身份、记忆或历史。

## 进度与复验

```sh
python3 manage.py roadmap
PYTHONDONTWRITEBYTECODE=1 python3 scripts/verification/verify_people_relations.py
node scripts/verification/verify_thought_inspection_ui.mjs
```

验收脚本使用临时实例，完整回归包含本机临时端口测试。真实模型验收受既有显式开关控制，未启用则跳过。组件脚本检查原始快照展示，不是实际浏览器视觉验收。可选 live-guard 仅只读核对本轮开始保存的身份、运行代次、进程和部署。

## 在新隔离目录只审阅配置

```sh
python3 -m digital_life --data work/t09-review prepare
python3 -m digital_life --data work/t09-review people-relations enable
python3 -m digital_life --data work/t09-review people-relations status
```

这些命令不调用模型、不运行行为、不唤醒实例。不要把路径替换成当前运行实例。启停需实例停止且没有活动运行进程；旧运行部署没有模块时，CLI 拒绝写入。

status 返回配置、revision、人物候选、关系称谓、条件信任及证据 ID。register 不从同名去重；一个名字出现两个人时，保留两个 actor/entity。controller 与 self_actor 为受保护的实际 ID，名称、别名和亲属称谓都不改变认证和权限。

## 人物、别名与称谓

需先在隔离实例中取得已有证据 ID。证据必须有实际 origin 对象或不可变制品；本模块不会替用户生成不存在的身份验证材料。

```sh
python3 -m digital_life --data work/t09-review people-relations register \
  --name "陈明" --evidence EVIDENCE_ID --key PERSON_REVIEW_KEY
python3 -m digital_life --data work/t09-review people-relations alias \
  --person ACTOR_ID --alias "小陈" --scope user \
  --evidence SOURCE_ID_1 SOURCE_ID_2 --key ALIAS_REVIEW_KEY
python3 -m digital_life --data work/t09-review people-relations resolve \
  --name "小陈" --scope user
python3 -m digital_life --data work/t09-review people-relations relate \
  --person ACTOR_ID --label "朋友" \
  --evidence SOURCE_ID_1 SOURCE_ID_2 --key RELATION_REVIEW_KEY
```

以上 ID 是占位符，不能直接执行。别名与称谓需要至少两个不同来源；同一 origin 的两个包装、或无 origin 时相同制品哈希不算不同来源。来源数不证明统计独立或事实真实。

scope 默认为 global。具体 scope 有经审阅别名时优先使用具体候选，否则用全局姓名/别名；聊天 scope 可为 chat:会话ID。一个别名同一 scope 指向多人时继续 ambiguous。unique_candidate 只表示本地候选唯一，不代表现实身份鉴定。

T03 启用时，只有明确经审阅别名绑定且无歧义，陈述才引用该本地 entity。单凭姓名唯一仍不会归并新陈述；未知或歧义标签在当前活动局部保存。旧实体、旧信念不被自动合并或改归属。称为“父亲”也不会变成控制者或获得工具授权。

## 条件信任

```sh
python3 -m digital_life --data work/t09-review people-relations trust \
  --person ACTOR_ID --domain behavior --dimension reliability \
  --condition config/examples/relationship-condition.json --outcome 1 \
  --evidence EVIDENCE_ID --reason "这次观察的解释" --key TRUST_REVIEW_KEY \
  --expected-revision CURRENT_REGISTRY_REVISION
```

outcome 只能是整数 0 或 1，由控制者标注；不自动从模型自称、工具成功或人名推断信任。维度支持 reliability、ability、benevolence、integrity。domain 与 condition 独立；condition 仅允许 source 与 task_contains，省略文件表示该域无额外条件。

expected_revision 来自 status，是保守的模块全局代次，任何人物、别名或关系写入都可能使它失效。初次 revision 为 null 时传字符串 none。key 重放幂等，不允许换内容重复 key。一个格子中相同来源不能换包装重复计数，失效后也不允许重新刷次数。

有观察时使用 α=1+正次数、β=1+负次数，estimate=α/(α+β)。没有有效观察时标 missing，不把 .5 先验当作已测信任。这是控制者标注的平滑频率，不是心理量表或成功率预测。

T06 只使用实际触发 actor 的 behavior/reliability，并挑当前情境最具体的匹配格子。输入提到某人，不代表请求由那个人发出；其他人的信任或其他领域不能代替。旧标量估计保留，不能倒推出不存在的正负次数。

## 有证据修复与更正

负观察使相关格子有未解决分歧。之后两条新正观察也不会自动宣布修复，需要显式操作：

```sh
python3 -m digital_life --data work/t09-review people-relations repair \
  --person ACTOR_ID --domain behavior --dimension reliability \
  --condition config/examples/relationship-condition.json \
  --reason "已审阅两次新的补救表现" --key REPAIR_REVIEW_KEY \
  --expected-revision CURRENT_REGISTRY_REVISION
```

必须同一格子最近负观察之后有两条不同来源的有效正观察。修复事件关联这些来源，旧负观察仍在次数中，不重置为满信任。其他格子仍未解决时整体继续 disputed；ended/dormant 关系不擅自重开。修复支持失效或新负观察会重新显示分歧。

```sh
python3 -m digital_life --data work/t09-review people-relations invalidate \
  --target ASSERTION_EVENT_ID --reason "原登记或陈述有误" --key CORRECTION_KEY
```

target 是 register/alias/relate/trust/repair 返回的事件 ID。失效追加记录，不删旧行或旧证据。更正不是独立修复证明；撤去直接记忆读取权限或擦除来源后，当前投影也不继续使用相应陈述。

## 思考详情与范围

面板“思考执行详情”的“关系”与完整输入中，可看当时的 relationships：配置/登记代次、实际触发者、人物歧义、别名及称谓来源、条件信任、样本数和分歧。旧请求不按当前图谱回填；登记或来源变化后旧快照会拒绝调用或采用。

关闭功能恢复既有读取路径，同时排除本模块的 assessment 行，避免管理投影泄漏回旧路径。未自动迁移全部旧人物和旧信任，没有现实身份认证、任意自然语言人名识别/代词消解、欺骗检测或法律亲属认定。下一项 T10 将继续记忆巩固与质量。
