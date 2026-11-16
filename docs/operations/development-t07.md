# T07 人格成长使用与复验说明

V0.1，受控人格成长工程版。默认关闭，不自动修改长期人格；本轮没有部署或唤醒当前实例，也不重建身份、记忆或历史。

## 进度与复验

```sh
python3 manage.py roadmap
PYTHONDONTWRITEBYTECODE=1 python3 scripts/verification/verify_personality_growth.py
node scripts/verification/verify_thought_inspection_ui.mjs
```

验收在全新临时实例执行，不读取正式实例生活数据；完整回归包含本机临时端口测试。可选的 live-guard 参数只读对照本轮开始保存的身份、运行代次、进程和部署。真实本地模型验收仍受既有显式开关控制，未开启就明确跳过；测试替身不代表真实模型人格效度。

## 新隔离目录只审阅配置

```sh
python3 -m digital_life --data work/t07-review prepare
python3 -m digital_life --data work/t07-review personality-growth enable
python3 -m digital_life --data work/t07-review personality-growth status
```

这些命令不会唤醒实例或调用模型。不要将路径替换成当前运行的正式实例。enable/disable 仅允许在停止、没有活动运行进程时执行；旧运行部署没有此模块时，CLI 拒绝写入。

启用后，在另行授权的隔离运行中，系统为实际接受的 wait/ask 或成功且核验通过的工具结果记录 opportunity。待审批工具、失败或未知结果、V2 专用探索不会成为本模块的成长来源。

## 从真实记录到标注

status 返回机会、标注、evidence_refs、当前人格档案和需要复核的提交。每条标注对应一个机会的某一维表现；数值和可靠度由控制者给出，不是 LLM 自评，也不是科学测验分数。

已有机会 ID 后，才可在隔离实例执行以下形式：

```sh
python3 -m digital_life --data work/t07-review personality-growth observe \
  --opportunity OPPORTUNITY_ID --trait openness --value 0.8 \
  --reliability 0.8 --context work --reason "解释本次判断的依据" --key UNIQUE_REVIEW_KEY
```

五维名称沿用现有人格定义：openness、conscientiousness、extraversion、agreeableness、emotional_stability。value 范围 [-1,1]，reliability 范围 (0,1]；reliability 是控制者对标注质量的声明，不是统计置信概率。情境标签由控制者声明，不能伪装成系统客观证明的跨情境泛化。

同一机会同一维度只能有一个有效标注。更正时先 invalidate --observation ID --reason TEXT，再用新 key 标注；旧记录不会删除。key 重放幂等，换内容复用 key 会拒绝。

## 提案、留出评估与采用

```sh
python3 -m digital_life --data work/t07-review personality-growth propose \
  --trait openness --observations TRAIN_ID_1 TRAIN_ID_2 TRAIN_ID_3
python3 -m digital_life --data work/t07-review personality-growth evaluate \
  --proposal PROPOSAL_ID --heldout TEST_ID_1 TEST_ID_2
python3 -m digital_life --data work/t07-review personality-growth commit \
  --proposal PROPOSAL_ID --evaluation EVALUATION_ID
```

训练至少 3 个不同活动、2 种情境；留出至少 2 个另外活动，并包含训练未见的情境。已经用于采用的活动来源不能再用于同维成长；同一活动的多轮思考也不算多次独立活动。

提案只改一个维度。单次绝对变化最多 .02，同维更新间隔至少 24 小时，最近 30 天累计绝对变化最多 .05。低质量或明显矛盾的训练标注被拒绝。常数是 V1 工程保护值，不是人的成长速度结论。

评估比较两份隔离参数向量对留出标注的加权平方误差，不调用模型、不执行工具、不修改人格；只有改善且没有逐条回归的提案才可采用。这是对控制者标注的有限拟合检验，不代表人格“变好了”。commit 再查来源、配置、版本、冷却、累计额度与测量内容；任何失效都拒绝，不静默重建新提案。

每次调用依赖对应输出中的真实 ID；以上占位符不能直接执行。此流程不会自动开始后续阶段或更新部署。

## 审阅、失效与回退

已采用后，后续思考会使用新档案；旧思考输入保留旧档案。面板“思考执行详情”的“人格”及完整输入中，可查看 personality_growth.profile 和各维不确定性（样本数、离散程度、来源、评估引用），并结合已有 T06 实际概率记录审阅。

若发现标注错误，invalidate 会阻断它继续参与提案/采用。已经采用的提交会出现在 status.invalidated_commits，需要控制者复核，不自动抹掉成长经历。

```sh
python3 -m digital_life --data work/t07-review personality-growth rollback \
  --commit COMMIT_ID --evidence EVIDENCE_ID_1 EVIDENCE_ID_2
```

回退需要至少两个不同 origin_object_id 的证据；status.observations 中提供标注的 evidence_refs。包装同一来源的两个 evidence ID 不算两个来源。只能回退仍为当前档案的成长提交，不能覆盖后来修订。回退追加补偿版本，保留全部历史、原提交及 reversal_of；已消费来源不恢复为可训练。回退可以立即修复，但反向绝对变动仍计入额度并重置冷却。

## 有界能力

没有控制者反馈与采用就没有长期人格更新。现有底层 Personality.replace 仍兼容人工修订与初始化，它不是自动成长通道；不能用它的手工变动证明成长限速已经生效。T07 CLI 不提供大幅人工改写入口。

长期人格有效性、自动行为解释、无监督成长与真实时间长期随访尚未验证。冷却和滚动窗口测试只模拟临时实例方法的时钟，不修改机器时间。人格成长与 T08 的情境习惯学习分开处理。
