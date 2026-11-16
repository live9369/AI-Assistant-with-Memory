# 原初00版本管理 V0.1 实现报告

2026-11-15。状态：已部署、已启用，真实模型保存版本通过。

## 可用功能

| 工具 | 功能 |
|---|---|
| project_version_status | 查看指定文件状态、当前文件hash及版本head |
| project_version_save | 保存显式文件列表和说明；要求预期head，拒绝过期版本覆盖 |
| project_version_log | 查看最近1—20个版本 |
| project_version_diff | 比较指定历史版本与当前单文件 |
| project_version_restore | 核对当前文件hash和head后恢复历史文件，保留恢复前内容并追加提交，不重写历史 |

普通 project_write/project_edit 在版本保存权限已开启时自动记录修改前后版本，工具回执携带版本号，不增加一次LLM调用。无内容变化则复用当前版本，避免堆积空提交。版本操作沿用原活动预算、目录授权、root账户和审批审计。

底层使用本机 Git bare repository。它位于实例 `project-versions/`，没有在项目新增 `.git`，不覆盖用户已有 Git 配置。使用独立环境和固定 Git 参数，不开放 shell、hook、网络同步、凭据或任意 Git 子命令。

## 基线

442个可读公共源码文件已保存为初始基线，分9批，每批最多50个文件；完成基线版本为 `0501ad44479b3a063c54598a48ac1f8bb886be91`。两份超过单文件读取上限的 evaluation JSON 未纳入。此基线使用既有发布源码收集器，因此不等同项目所有文档和任意输出文件的全量备份。其他允许文件在首次编辑前或显式保存时加入历史。

项目目录仍为 `<PROJECT_ROOT>`，work、config/local、发布记录等排除项保持。恢复只读取当前权限仍允许的历史文件。源码恢复不自动改变当前运行版本；部署、唤醒与运行回退仍由 CLI 及原 Releases/SourceUpdates 管理。

## 验证

12项针对性真实 worker/Git 验证通过（9.297秒），覆盖保存、编辑自动存档、差异、恢复、新旧历史保留、旧head冲突、排除项，以及既有文件工具和任务循环。没有使用假的Git后端，没有调用远端仓库。

正式实例真实 Codex 验收：三次独立思考完成“查询指定测试文件状态 → 保存版本 → 返回版本号”，耗时45.60秒；两次工具执行均成功，活动 completed。新版本：`e4c900a6f42746b74721d23c84a3faf4f6594e04`。文件内容未被改变。恢复功能在临时目录通过真实worker验证，本轮没有回退正式业务源码。

正式测试6条合成记忆已归档，版本记录与专用测试文件保留供审计。身份、原记忆与历史未重建。

## 使用方式

可以对它说：

- “查看 digital_life/application/engine.py 的版本状态。”
- “把这几个文件保存一版，说明是修复某某问题。”
- “看看这个文件相较版本号……改了什么。”
- “把这个文件恢复到版本号……，保留当前内容的版本记录。”

它需要先用状态/历史工具获得真实head、文件hash及版本id，不应编造版本号。每次保存最多50个指定文件，不进行全项目扫描。

## 当前边界

第一版管理UTF-8文本内容。历史恢复目前限已存在、目标历史中也存在、内容不超过20000字节的文件；不恢复删除状态和执行位，不提供分支合并、reset、删除历史或远端同步。裸版本库的存在不等于已扩展现有备份包的覆盖范围；若另做备份，应保存实例 project-versions 目录。

## 证据

- `outputs/project-tools-review/version-tests.log`
- `outputs/project-tools-review/version-initial-baseline.json`
- `outputs/project-tools-review/version-live-8bf1a9d6.json`
- `outputs/project-tools-review/version-final-runtime.json`
- `outputs/project-tools-review/cleanup-423b04fa710b40e2bb211b8e261b7079.json`

设计参考：[Git commit-tree](https://git-scm.com/docs/git-commit-tree)、[Git update-ref](https://git-scm.com/docs/git-update-ref)。
