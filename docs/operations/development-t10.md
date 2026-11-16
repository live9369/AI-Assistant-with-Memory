# T10 记忆巩固与质量使用说明

V0.1，有界工程版。默认关闭。本轮只验证临时实例，不更新、不重启当前实例，不修改其身份、记忆与历史。

## 进度与复验

```sh
python3 manage.py roadmap
PYTHONDONTWRITEBYTECODE=1 python3 scripts/verification/verify_memory_quality.py
node scripts/verification/verify_thought_inspection_ui.mjs
```

验收包含完整 Python 回归、万条合成记忆真实检索和受管理删除测试；需要本机临时端口。真实本地模型验收未显式开启会跳过。前端为组件检查，不是真实浏览器视觉验收。验收脚本记录语料装载、冷构建、温查询、单条增量查询与扫描参考，不能只看其中一个耗时。

## 新隔离目录审阅配置

```sh
python3 -m digital_life --data work/t10-review prepare
python3 -m digital_life --data work/t10-review memory-quality enable
python3 -m digital_life --data work/t10-review memory-quality status
```

这些命令不唤醒、不调用模型。不要将路径替换成当前运行实例。启停要求实例停止且没有活动运行进程；旧运行部署没有模块时，CLI 拒绝写入。

## 摘录式巩固：先提案、预览、再采用

从隔离实例现有记忆取得当前 revision ID，准备 JSON 文件（必须换成真实 ID 和有效字符范围）：

```json
[
  {"revision":"CURRENT_REVISION_1","start":0,"end":12},
  {"revision":"CURRENT_REVISION_2","start":0,"end":10}
]
```

start/end 是 Python Unicode 字符下标，不是 UTF-8 字节偏移；end 不包含在摘录中。至少两条不同来源记忆，输出最多 8000 字符，不能直接提交新总结文本。

```sh
python3 -m digital_life --data work/t10-review memory-quality plan \
  --spec path/to/spans.json --key UNIQUE_PLAN_KEY
python3 -m digital_life --data work/t10-review memory-quality preview --plan PLAN_EVENT_ID
python3 -m digital_life --data work/t10-review memory-quality commit --plan PLAN_EVENT_ID
```

plan 只保存来源、范围和哈希；preview 即时返回可审阅内容，不额外持久化摘录副本。commit 重新检查来源、版本、哈希和权限，显式新增摘录派生记忆。原文不删除、不自动归档，新摘要也不是事实认证。

摘要读者取来源交集，之后持续检查。来源被更正、归档、撤权或删除时，旧摘要停止进入新思考；需重新提案，不能通过复制旧权限绕过。状态仍 active 但 available_to_self=false，可能表示来源失效；status --memory ID 返回依赖及可见性。

## 矛盾与更正

```sh
python3 -m digital_life --data work/t10-review memory-quality conflict \
  --left CURRENT_REVISION_1 --right CURRENT_REVISION_2 \
  --evidence EVIDENCE_ID --reason "两份报告不一致，尚未核实" --key UNIQUE_CONFLICT_KEY
```

标注只表示控制者指出了不同陈述，不自动判断谁真谁假。当前双方均可读时，召回会带未解决标记，相关摘要也继承标记；不能借标注泄漏不可读的另一条记忆。旧记录不覆盖。

更正继续使用已有 memory-feedback 提案、隔离评估与采用流程；Memory.revise 追加新版本，默认召回当前版本。旧版本保留用于审计，而不是继续充当新事实。

## 降权、归档、撤回与恢复

```sh
python3 -m digital_life --data work/t10-review memory-quality status --memory MEMORY_ID
python3 -m digital_life --data work/t10-review memory-quality retain \
  --memory MEMORY_ID --retention demote --salience 0.1 \
  --expected-revision RETENTION_REVISION --reason "降低默认召回优先级" --key UNIQUE_RETENTION_KEY
```

expected_revision 使用 status 返回的 retention_revision，不是 memory revision ID。操作有 CAS 与幂等 key，防止用旧状态覆盖后续操作。

retention 可选 demote、archive、retract、restore。demote 仅降低显著度，正文和版本不删；archive/retract 排除默认召回；restore 不能恢复 deleted 正文，也不能修复失效摘要的来源。没有按时间自动删除或自动遗忘人格。

## 检索与质量评估

```sh
python3 -m digital_life --data work/t10-review memory-quality rebuild-index
python3 -m digital_life --data work/t10-review memory-quality evaluate --cases path/to/cases.json --k 5
```

cases 是至少两个不同问题的人工相关性标注：

```json
[
  {"query":"liwei 喜欢什么颜色","relevant":["MEMORY_ID_1"]},
  {"query":"谁研究植物","relevant":["MEMORY_ID_2"]}
]
```

必须替换成当前可读真实记忆 ID。评估使用实际召回，返回 Precision@k、Recall@k、MRR、nDCG、候选数量、耗时、索引增量/重建与截断标记；不调用 LLM、不执行工具、不自动改写记忆。标注错误不等于测出了质量。

派生 SQLite 索引 memory-quality-index.sqlite 只保存哈希词/字组、ID 和内容哈希，不存明文词；它不是加密系统，不能据此承诺防字典推测。普通新增/修订按主库事件水位增量同步，配置变化或回滚导致旧水位失效则全量重建。所有候选再次核对主库版本、状态与动态权限。

查询最多取 2000 个词法候选再加最近 8 条；若截断会明确标记。过长查询或索引故障会记录扫描回退。不保证通用语义召回或无限规模性能。

## 显式删除与范围

以下是不可恢复正文的显式管理操作，仅用于另行决定要删除的隔离测试数据，本轮不对当前实例执行：

```sh
python3 -m digital_life --data work/t10-review memory-quality erase \
  --memory MEMORY_ID --include-registered-backups
```

要求实例停止。复用 Privacy.erase 清理已知派生关系、请求/响应制品与显式纳入的已注册备份/快照，保留审计墓碑。新生成响应在启用后会保守记录本次输入及选中记忆的依赖，因此已登记的转述也能随来源清理。

删除会按已登记输入关联清理对应请求与全部响应制品，包括 stale/未采用响应；有明确来源链接的认知正文和当前 literal 也会清理。删除同时重建既有全文索引，清理其旧词条，并撤去派生哈希索引，再检查受管数据库和制品。删除不保证处理外部导出、未登记副本、未知历史语义转述或 SSD 取证残留。正常开发与修订保留历史；明确擦除正文是另一个操作，不能同时声称保留被要求删除的正文。

## 面板与能力范围

思考详情的“选中记忆”与完整输入显示 memory_quality：选中版本哈希、依赖、未解决冲突、索引模式与截断；来源类型区分原始、生成、更正及摘录派生。派发和接收还会重查来源，不用旧索引或旧摘要继续传入撤去的内容。

没有自动真伪判断、通用矛盾识别、任意摘要语义保证或全部旧历史依赖推断。下一项 T11 将处理承诺与自主探索。
