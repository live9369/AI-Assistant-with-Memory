# G2材料、真实模型先导与质量评审报告

日期：2026-11-08（Asia/Shanghai）。作者：Codex主agent（/root）。  
任务：推进G2，补齐独立材料、真实模型运行器和质量聚合，开展隔离评测，正式实例继续锁定并保留既有证据。

## 1 用户确认后的范围

用户选择“现有Codex，先做先导”，并要求保留盲审记录、由当前agent根据科学研究评判。本轮建立匿名化证据包并作单评审探索性标注；当前agent参与材料和运行，不能称独立双盲，不能以此宣布正式G2通过。

运行协议AE-RUNTIME-1.1；指标AE-METRICS-1.0；评测AE-EVAL-1.0。正式60case×3次完整组和G3消融不在本轮执行范围。研究依据及固定量表见[评审文档](../research/autonomous-exploration-g2-review-rubric.md)，运行操作见[G2指南](../operations/autonomous-exploration-g2.md)。

## 2 材料与被测版本

新建60个formal-candidate情境，A–F各10，20个预注册主缺口反例机会；另有主题分离的6个development情境。本轮只运行development。公开经历和工作区文件与oracle分开；oracle不进入actor请求。材料来自当前作者，独立材料审核仍pending，不把摘要差异当作统计独立性证明。

当前工作区在V1.1冻结后又修改了engine、memory和CLI；本轮没有覆盖这些变化，而是校验并复制已通过G1的完整运行归档，worker从validated-runtime加载。manifest保留当前工作区G0差异和实际被测归档摘要。G1已通过的代码没有因本次G2装配改变。

## 3 实测结果

先导run：`g2-pilot-20261108T090814Z-f370a18c`。先导6/6完成，无模型／运行时错误、无缺失证据；27次真实模型输出、10次工具尝试，未自动切换模型。F类的一次预注册工具failed回执完整保留，仍进入有效探索分母；“运行完成”不等于每次工具成功。采用配置中的`codex_cli:gpt-6.1-sol`，未调用真实模型的单元测试不计入这些数字。

正式门结论：G0（被测归档）pass，G1继承已验证源码的pass，**G2=not_evaluable**，G3=not_run。原因是开发先导而非60个正式case、没有3次重复、分母不足20个独立case、评审者是当前材料作者而非两名独立盲评者。不能把6/6运行成功表述为质量通过。

制品：

- [调用前manifest](../../outputs/acceptance/ae-g2/g2-pilot-20261108T090814Z-f370a18c/manifest.json)
- [质量聚合](../../outputs/acceptance/ae-g2/g2-pilot-20261108T090814Z-f370a18c/quality-aggregate.json)
- [匿名包1.2](../../outputs/acceptance/ae-g2/g2-pilot-20261108T090814Z-f370a18c/review/packets.json)
- [43项作者单评审原始记录](../../outputs/acceptance/ae-g2/g2-pilot-20261108T090814Z-f370a18c/review/labels-codex-root-single-review-v1.json)
- [正式实例前后检查](../../outputs/acceptance/ae-g2/g2-pilot-20261108T090814Z-f370a18c/formal-instance-guard.json)
- [分析版本封存](../../outputs/acceptance/ae-g2/g2-pilot-20261108T090814Z-f370a18c/analysis-manifest.json)

## 4 探索性质量结果

以下都是单作者标注的先导诊断，不是独立质量结论。宏观值先在case内聚合，再给每case相同权重；原始分子分母同时保留，不能混用。

| 指标 | 原始计数 | case等权值／状态 |
| --- | --- | --- |
| M01自主问题率 | 17/17首次入库文本ID | 100%；6case，insufficient_sample |
| M02可验证问题率 | 15/17 | 88.9%；6case，insufficient_sample |
| M03引用接纳完整率 | 62/62 | 合法性100%，不等于内容真实性 |
| M04有效探索率 | 6/10调查 | 66.7%；6case，insufficient_sample |
| M05反例响应率 | 2/2预登记机会 | 100%；2case，insufficient_sample |
| M06错误结束率 | 作者判为0/9声明 | 0%；6case，insufficient_sample |
| M07预登记可解缺口覆盖 | 4/5 | 80%；5case，insufficient_sample |
| M08语义重复探索率 | 3/10调查 | 25%；6case，insufficient_sample |
| M09真实重启连续性 | 1/1 | 仅1case，insufficient_sample，不与G1的3/3合并 |
| M10／M12／M16 | 无本轮重放分母／无确认接口／无消融 | not_applicable／not_evaluable／not_run |
| M11停止后新派发／M13预算越界 | 0／0 | 从本轮原始证据审计 |
| M14原始消耗 | 模型端口27、工具10、provider回报351385 tokens | 每有效调查4.5个模型端口调用、约58564 tokens；不是账单金额 |
| M15选择条件Brier诊断 | 10个被选择候选 | 0.292；expected_gain并非已校准概率，不作门槛 |

模型墙钟合计约381.43秒；不含当前agent编写、阅读和评审开销。费用／订阅配额未由此证明。全部token值来自provider用量字段，未用4096预留伪造。输入和输出完整保存，超限或失败不会被删掉再算成功率。

M01按首次文本ID计数，包括多个语义改述；高内部来源比率不代表产生了17个独立新思想。M08另行识别重复。M06检查实际声明的有限事实是否正确，不强迫系统回答未选择的问题；M07才检查预登记缺口的覆盖，因此两者可以同时出现“声明未错、缺口未覆盖”。

## 5 主要发现及证据

1. **跨问题复用已有观察不足。** 回声、票据、颜色三个情境都对同一语义问题重新读取相同SHA文件，没有新世界变化或验证方法。第二次声明仍可能正确，但新增信息为0。对应M08三次重复，具体理由和两次回执ID均在原始评审文件。
2. **出现超出感知接口的问题。** 两个候选要求按event/evidence/receipt/result标识取回内部记录，但当前允许的工作区读取／列举工具没有这种检索接口。它们来自自身经历，却不能据现有通道完成验证，M02据此标false。
3. **反例能改变本轮判断。** 票据gold反驳“全是silver”，locker新版本N反驳旧L，均有实际文件内容和明确修正声明。重启后N证据进入后续独立请求。但随后新的发现活动又围绕旧L提问，说明单次重启连续不等于跨问题认识已稳定整合。
4. **有限结论较谨慎，覆盖仍不完整。** 系统没有把缺少日期的tomorrow推成绝对日期，颜色案例也区分数组排列和真实时间顺序。但它没有触及颜色case预登记的“有限不规则样本不能确定下一颜色”主缺口，M07不因措辞谨慎而自动记成功。这个指标测预设缺口覆盖，不是对所有自主兴趣价值的总判决。
5. **材料还有正式化工作。** 本轮F类错误回执中含synthetic／pre-registered描述，可能暴露评测情境；正式运行前应改为中性错误并以新输入版本登记。候选材料的oracle尚由同一作者编写，仍需独立审核，不能直接用本轮高分宣称有效度。

这些发现支持下一步优先研究语义问题去重、共享观察与信念更新、候选验证路径可执行性，再决定是否耗用更大规模正式模型预算。它们没有授权本轮修改生产运行基线。

## 6 评审、统计及分析修订

查阅了三份一手研究，采用证据增益、固定字段、理由引用和偏差披露，详见研究文档。当前agent知道actor并编写了材料，原始记录明确independent=false、material_author=true、actor_operator=true、blind_to_model=false。匿名化只是一种制品处理，不使作者变成真正盲评者；未伪造第二名评审，kappa不适用。

采用10000次case聚类bootstrap、固定seed20261108；重复不当作独立case。六个case下的区间只是样本诊断，某些全同标签出现退化[1,1]／[0,0]区间不能证明总体确定性；样本不足和独立评审门仍阻止正式通过。

真实运行后发现原export依赖数据库自然返回顺序，不能保证先后。保留`review-v1.0-pre-chronology`，修复显式调用顺序形成1.1；再补上实际world_event／restart等H记录形成1.2，保留`review-v1.1-pre-execution-events`。正式43项标签在1.2包上才创建。另在标签前加固第三裁决身份／引用和有效观察引用检查。旧运行源快照、各版包和摘要均保留，未改actor输入输出、原量表或阈值。

`analysis-source-snapshot`和analysis-manifest保存当前分析器及其摘要；另保存与包内指纹逐字节一致的1.2构建器。运行前源快照与运行后分析版本分开，不把后处理修复冒充调用前已封存的代码。

## 7 工具交付和验证

新增`evaluation/exploration/g2/`：材料构建器、公开／oracle分离材料、真实运行装配、匿名评审导入／裁决及质量聚合；新增`run_exploration_g2.py`、`review_exploration_g2.py`、`aggregate_exploration_g2.py`三个入口。运行器提供正式完整组模式，但本轮只执行开发先导，不自动开展180个正式trial或720个含消融trial。

[最终工具测试](../../outputs/acceptance/autonomous-exploration-g2-tooling-tests-final.json)：11/11通过，覆盖单评审不能正式过门、分歧须独立裁决、未填／伪引用拒绝、材料和证据摘要、匿名身份元数据、case而非repeat统计、公开输入及调用预算、时序与裁决身份限制。测试使用夹具，仅证明工具行为；没有混入本轮真实质量数据。

工作区生产源码、SQL、模型配置、原G1基线和已有证据未由本轮修改。正式实例保持锁定，6个文件前后摘要一致。当前工作区自身仍有冻结后改动，下一阶段应明确继续用通过G1的1.1归档，还是审核新变更建立另一个G1基线。

## 8 后续边界

正式G2还需要候选材料独立审核、60case×3次完整组、足够条件分母和两个独立盲评者。作者单评审无论得到多少高分都不能替代它们。若根据先导修改运行机制，要建立新源码基线并重过G1；若修改正式材料或阈值，按契约另建版本，不覆盖本次记录。
