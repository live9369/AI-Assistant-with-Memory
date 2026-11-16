# T11 承诺与自主探索使用说明

V0.1，有界工程版；默认关闭。本次没有部署或重启当前实例，也没有重建身份、记忆或历史。以下示例仅用于新的隔离审阅目录。

## 查看与复验

```sh
python3 manage.py roadmap
PYTHONDONTWRITEBYTECODE=1 python3 scripts/verification/verify_autonomy_agenda.py
node scripts/verification/verify_thought_inspection_ui.mjs
```

验收脚本使用临时实例、固定模型响应和真实受限文件工具；完整回归包含临时本机端口。真实模型接入另行验收，不能把固定响应测试当作真实模型长期能力证明。前端检查为组件交互检查。

## 停止状态下配置

```sh
python3 -m digital_life --data work/t11-review prepare
python3 -m digital_life --data work/t11-review autonomy-agenda enable
python3 -m digital_life --data work/t11-review autonomy-agenda status
```

这些操作不调用模型、不启动生命活动。启用/关闭配置要求停止且没有活动进程；CLI 会拒绝向不含此模块的旧运行部署写入。

## 登记承诺

复制 `config/examples/autonomy-promise.json`，把 start_at / due_at 改为实际 UTC 时间（毫秒、Z 结尾）；开始时间不得晚于截止时间，新登记的截止时间须在未来。内容、目标文件和验证文本须一致。例子中的2030年仅是格式示范。

```sh
python3 -m digital_life --data work/t11-review autonomy-agenda promise \
  --spec config/examples/autonomy-promise.json --key review-promise-1
python3 -m digital_life --data work/t11-review autonomy-agenda status
```

返回 commitment ID。同 key、完全相同参数重复提交返回原记录，变更参数复用 key 会拒绝。开始时才建立唯一目标活动；是否开始仍受用户工作优先、授权运行和资源门控。单次活动最长沿用现有10分钟上限，最多3轮，长期等待不等于长期无限运行。

履约只认独立 file_contains 核验。调用成功不够；未知效果/核验未通过会暂停或有限继续；未按时完成记 violated。截止审计在授权运行循环恢复时进行，不会为了审计自己唤醒。关闭策略不解除已有义务，要释放请显式操作：

```sh
python3 -m digital_life --data work/t11-review autonomy-agenda release --commitment COMMITMENT_ID
```

释放会取消尚未完成的关联工作，保留记录；不能撤销已发生的外部副作用，终态不重写。本版本只承诺向控制者完成本地文件目标，不自动向他人发消息。

## 有限探索与兴趣

沿用现有 exploration 的显式配置和预算，autonomy-agenda 不自行开启它。先有 V2 的真实问题 ID、可读证据以及工作区文件，再按 `config/examples/autonomy-question.json` 登记：

```sh
python3 -m digital_life --data work/t11-review autonomy-agenda question \
  --spec config/examples/autonomy-question.json --key review-interest-1
```

声明兴趣仅改变合法问题排序，不增加权限、预算或轮数；未登记问题沿用原评分。affinity 是控制者声明偏好，不是已测得的人格参数。原认知经验统计维持影子模式，不自动改为学习或兴趣决策。

实际收益仅针对本地事实覆盖：首次核验某路径、目标字符串与文件内容版本记1；重复观察同版本记0；未知/失败/来源变化不能核验记null。目标字符串不存在也是可核验的否定观察。它不表示获得通用知识或心理学习进步。status 可查看 measurements 的证据、内容哈希、布尔结论与测量理由。

## 查看与等待

管理面板既有“思考执行详情”的“探索”组增加 autonomy_agenda，显示该次请求收到的承诺截止、声明兴趣和测量含义；完整输入仍保存在独立请求快照里。当前面板只有将来显式部署新版后才显示新字段。

status 中 next_due / wait_state 是逻辑等待说明，不是物理睡眠保证。未来承诺开始和截止通过已有持久队列参与两阶段休眠交接；就绪任务、未决效果或新输入会阻止/中止交接。部署、进程启动和唤醒仍由现有 CLI 管理，本说明不执行这些操作。
