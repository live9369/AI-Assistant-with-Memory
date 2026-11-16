# 前四项开发验证与使用

当前为有界工程第一版，未部署到正在运行的实例。先阅读docs/plan/development-roadmap.md及task-status.json；不要把本指南的写操作指向当前生命目录。

## 查看开发任务

```sh
/usr/bin/python3 manage.py roadmap
/usr/bin/python3 scripts/development/check_task_plan.py
```

检查器核对依赖、设计路径、隔离验收结果与文件哈希。T01到T04通过后下一项为T05；不会自动开始T05，也不会更新生命运行器。

## 分项复验

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 scripts/verification/verify_development_steps.py
```

按T01、T02、T03、T04顺序使用临时实例，更新outputs/acceptance/development-t01.json到development-t04.json及任务状态。任一失败停止后续门控；复验已完成项不需要重新唤醒生命。

## 新隔离目录中的CLI配置示例

以下准备命令只创建禁止唤醒的测试实例，不启动运行器。需要真实模型时另行提供模型配置并走隔离部署流程，不能使用正式实例代替。

```sh
/usr/bin/python3 -m digital_life --data work/growth-review prepare
/usr/bin/python3 -m digital_life --data work/growth-review cognition enable
/usr/bin/python3 -m digital_life --data work/growth-review task-loop start --text "读取材料后写入answer.txt" --path answer.txt --contains done
```

task-loop status通过--activity查看；resume通过--activity和--text提供后续信息。未知外部效果尚未核实、有待审批、已停止或轮次耗尽时不能继续。默认最多3轮，工具仍走原有授权与执行链。

cognition status查看候选及当前版本。confirm需要--revision与--expected-current；只有控制者可以确认。V3提取仅产生解释候选，引用匹配不证明内容为现实真理。计划为草案，预测仍需独立核验；本版不宣称实现任意自动事实判断。

memory-feedback propose需要--memory、--content、--reason；evaluate需要--proposal与--cases文件；commit需要--proposal与--evaluation；rollback需要--commit与至少两个来源不同的--evidence。

评估文件为至少两个不同问题：

```json
[
  {"query":"测试人物偏好的颜色","contains":"绿色","not_contains":"蓝色"},
  {"query":"测试人物喜欢什么颜色","contains":"绿色","not_contains":"蓝色"}
]
```

预期由控制者提供。评估比较两个禁止唤醒的临时数据库副本的真实检索结果；不调用LLM、不执行工具。只证明固定题集的局部检索改进，不代表泛化、人格学习或因果推断已验证。无收益或有回归的提案被拒绝，不能提交；批准采用仍校验目标版本。回退追加修订，旧经历不删除。

## 可观察性和当前实例

思考详情可展开task_loop和cognition_snapshot/cognition_sources，以及V3响应的cognition字段。各次尝试与输出照常持久化。学习过程有独立反馈、评估工件、采用和回退事件；不在通用日志中冒充完整思考。

CLI写入口在已有活动运行器不支持相应模块时拒绝操作。当前实例没有被部署新版，身份和原部署进程保持不变；后续上线必须另获用户授权并使用CLI。
