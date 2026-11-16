# T08 习惯形成与消退使用说明

V0.1，有界工程版。默认关闭；本轮没有更新或唤醒当前运行实例。习惯不是权限，也不代表已经测出了心理自动性。

## 查看进度与复验

```sh
python3 manage.py roadmap
PYTHONDONTWRITEBYTECODE=1 python3 scripts/verification/verify_habit_learning.py
node scripts/verification/verify_thought_inspection_ui.mjs
```

验收脚本使用全新临时实例，完整回归包括临时端口接口测试，保存 T08 证据并更新任务状态。真实模型测试受原有显式开关控制，未启用就跳过。前端脚本是组件夹具检查，不是真实浏览器视觉验收。

## 在新隔离目录审阅登记

```sh
python3 -m digital_life --data work/t08-review prepare
python3 -m digital_life --data work/t08-review habit-learning enable
python3 -m digital_life --data work/t08-review habit-learning enroll \
  --definition config/examples/habit-learning.json --key review-source-v1
python3 -m digital_life --data work/t08-review habit-learning status
```

以上命令只准备和登记，不执行行动、不调用模型、不唤醒实例。不要将路径替换成当前运行实例。配置 enable/disable 必须在停止且没有活动运行进程时执行；旧运行部署缺此模块时 CLI 拒绝写入。

模板包含完整 action 和 cue，例如在 source=user、任务字面包含 review 时，对读取 source.txt 建立联系。登记不代表文件已经存在或读取已获授权。V1 的 source 是精确匹配：聊天来源为 chat:会话ID，任务循环可能为 task-loop；不会自动合并不同会话。task_contains 是大小写敏感子串，不是语义理解。

## 形成需要真实经历与明确反馈

在另行授权的隔离运行中，匹配线索会记录机会。已接受的 wait/ask 或成功且核验 pass 的工具执行形成观测，status.observations 提供 ID 和 evidence_refs。工具待审批、失败或结果未知不会自动变成正/负学习。

取得真实观测与 status.habits 当前 revision 后，反馈形式为：

```sh
python3 -m digital_life --data work/t08-review habit-learning feedback \
  --observation OBSERVATION_ID --outcome 1 --reason "希望在此情境保持此反应" \
  --key UNIQUE_FEEDBACK_KEY --expected-revision CURRENT_REVISION
```

outcome 只能是整数 0 或 1。1 表示控制者希望强化已实际做出的匹配反应；另选反应不能被当作旧反应的正反馈。0 表示控制者在这一情境明确不再强化该倾向；系统不会从没有选它、工具失败或过去了几天自动推断负面意义。

每个联系、每个活动仅消费一次；同活动多轮不能刷强度。每次反馈都产生新 revision，旧 revision 会拒绝新写入。相同 key 重放幂等，换内容复用 key 拒绝。

至少 3 个不同活动的正反馈并达到门槛，状态才由 learning 变为 active。系统默认没有自动奖励评判或无监督习惯发现。

## 如何看形成与消退

status 中 acquisition=A 是获得痕迹，inhibition=I 是抑制痕迹，effective=A×(1-I) 是当前联系倾向；expression 仅在 active 时为 effective，其余状态为零。

正反馈使 A 小幅增长，并逐步减弱 I；负反馈增加 I，保留 A。反复不再强化可进入 extinct；新正反馈可以先回到 learning，再满足形成条件后 active。历史不会被删掉。常数和门槛是工程 V1，不是人的固定习惯学习速度。

非 active 的登记联系只在 habit_learning 审计快照中出现，不进入 habit_suggestions。T06 只在现有候选完全匹配时使用倾向，不创建新工具或参数；即使习惯很强，权限排除的候选仍是零概率，工具仍需审批。

## 抑制与恢复

```sh
python3 -m digital_life --data work/t08-review habit-learning inhibit \
  --association ASSOCIATION_ID --reason "暂时停止这条习惯倾向" \
  --expected-revision CURRENT_REVISION
python3 -m digital_life --data work/t08-review habit-learning resume \
  --association ASSOCIATION_ID --reason "已复核，恢复按痕迹评估" \
  --expected-revision INHIBITED_REVISION
```

抑制立即去掉这条联系的建议，保留 A/I；抑制期间拒绝学习反馈，恢复需显式操作。如果旧请求已带入旧倾向，抑制或更新后它会拒绝调用/采用，不静默改写原输入。

抑制的是指定联系的偏向，不是禁止用户明确要求相同动作，也不会同时改写另一条独立联系。全局工具限制仍用原权限策略。未登记旧习惯保留兼容路径，但其 inhibited/extinct 状态不再产生建议。

## 补偿回退

```sh
python3 -m digital_life --data work/t08-review habit-learning rollback \
  --change LAST_FEEDBACK_CHANGE_ID --evidence EVIDENCE_ID_1 EVIDENCE_ID_2
```

只补偿仍是当前 revision 的最近一次反馈。需要至少两个不同 origin_object_id 的证据，不能用同一来源的两个包装冒充。status.observations 可查看观测证据 ID。回退追加补偿事件，不删原反馈；已消费活动仍然消费，不能重新刷。后面已经有控制或反馈时拒绝覆盖。

## 查看面板与范围

思考详情的“习惯”和完整输入保存当时 habit_learning：配置、联系 revision、A/I、状态及表达；T06 区域保留当时的候选概率与实际选择。旧请求不拿当前值回填。

本版只管理显式登记、字面情境匹配的联系；不自动迁移所有旧习惯，不声称实现通用语义情境、心理自动性测验、全部复燃机制或长期生物消退。下一项 T09 另处理人物与关系认知。
