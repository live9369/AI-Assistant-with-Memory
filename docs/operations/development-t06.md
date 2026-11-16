# T06 使用与复验说明

V0.1：高维情境行为概率的有界工程版本。功能默认关闭；本轮不部署当前运行实例，不重建身份、记忆或历史。

## 查看进度与复验

```sh
python3 manage.py roadmap
PYTHONDONTWRITEBYTECODE=1 python3 scripts/verification/verify_behavior_policy.py
node scripts/verification/verify_thought_inspection_ui.mjs
```

第一条只读任务状态。第二条在临时实例执行完整 Python 回归，校验源码稳定性并更新 T06 证据和任务状态；HTTP 测试需要本机临时端口。第三条验证思考详情组件：原始响应、概率记录与实际选择分开显示；不是浏览器视觉验收。真实本地模型验收仍依赖既有显式开关，没有开启则明确跳过。

## 只在新隔离目录审阅配置

以下不会启动推理器或唤醒实例，不能将路径改为当前运行的正式实例。

```sh
python3 -m digital_life --data work/t06-review prepare
python3 -m digital_life --data work/t06-review behavior-policy status
python3 -m digital_life --data work/t06-review behavior-policy enable \
  --temperature 0.7 --parameters config/examples/behavior-policy.json
python3 -m digital_life --data work/t06-review behavior-policy status
```

`status` 返回配置、代次及支持的特征名；`disable` 关闭并恢复原有确定性流程。启停要求实例已停止且没有活动运行进程；旧运行部署没有此功能时，CLI 拒绝写入。配置是每次从版本化默认值合并所给参数，调用 enable 时需再次传入要保留的定制参数；历史配置不会被删除。

参数文件仅接受 biases（工具到偏置）和 weights（工具到特征到系数）。系数范围 [-20,20]；温度范围 [.05,5]。低温更偏向高分，高温更分散；不是提高模型“聪明程度”。配置只影响系统选择，不改 LLM 供应商的生成温度。模板中的数值是工程先验，不是经验证的人格行为规律。

## 如何看一次决策

面板现有“思考执行详情”中的“行为概率”和完整输入保存 `behavior_policy`：特征值、missing 标记、来源引用、参数及配置代次。

新增“系统实际行为选择”展示候选、合法性、阻断原因、每项贡献、分数、概率、draw、seed、最终索引及决策记录。系统选择与模型原始输出分开保存。例如模型建议写文件，但系统抽中 wait，则本轮进入等待，不会创建原写文件意图。若工具获选，仍按原审批流程继续。没有权限的候选再高分也不会获选。

候选范围目前是模型提出的一个行动，加等待和询问，最多三个；不生成额外文件路径或任意新工具方案。V2 自主探索使用专用核验流程，输入明确记录 bypass，不应用本次普通行为概率策略。

## 记录与重放

`decision_records` 保存策略版本、seed 和最终状态；`decision_candidates` 保存每个候选、分数、合法性、概率和选中标记。`behavior_policy.selected` 事件关联 request，并保存贡献分解和特征快照。使用 `seed / 2**53` 和记录的概率累计采样可重放选择。已接受请求重试不会再抽签，重开数据库不会改变历史概率。

配置更新使已准备旧请求失效，系统拒绝调用/采用，不把旧请求换成新参数。直接召回记忆被撤权或修订时同样拒绝旧特征输入。缺失信任等特征以带 missing 标记的中性零进入计算；首次没有历史召回属于实际空结果，不能伪装成之前已经记得本次刚收到的消息。

## 能力边界

目前验证工程决策路径、因素干预和抽样频率。人格默认仍可能全为零；没有科学根据自动生成独特人格或通过单次交流改变人格。默认部分维度系数为零，控制者可显式配置；零不是该特征在现实中无作用的结论。

记忆直接评分目前只使用授权召回覆盖量，语义内容通过独立思考影响模型候选；认知信号是已有候选接受状态的统计，不能当作真实无知概率；条件信任仅使用触发者 behavior/reliability 域，不能跨域推广。参数在线学习、任意多方案规划、长期人格与习惯成长仍是后续任务。
