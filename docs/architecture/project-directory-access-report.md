# 指定目录文件权限实现报告

2026-11-15。状态：文件工具与任务循环已实现、临时目录验证通过；用户已确认建议目录和权限，本次代码已部署，原实例已启用项目目录授权。

## 已实现

沿用既有模型—行为—审批—worker—回执链路。借鉴 OpenCode/Hermes 的工具分工，采用本地小适配层，没有引入另一套 agent 或第三方运行时依赖。

| 工具 | 能力 |
|---|---|
| project_list | 列出授权目录下条目 |
| project_read | 分页读取文本，返回完整文件 sha256 |
| project_search | 目录内有限的字面文本搜索 |
| project_mkdir | 创建子目录 |
| project_write | 新建或按旧 sha256 替换文本文件 |
| project_edit | 按旧 sha256 将唯一旧片段替换为新片段，可修改较大的源码文件 |
| project_check | 对指定 .py 文件做 Python 语法检查；不执行文件或测试套件 |

授权可指定工具子集和排除目录，支持逐次审批或对该明确范围自动允许；修改/撤销授权使旧授权失效。未启用时模型输入不展示项目权限，输出 schema 不提供项目动作。已有 workspace 工具维持原样。

项目动作自动接上 TaskLoop；每个动作结果及差异进入同一任务下一次完整独立思考，最多 3 轮，预算保持原样。能完成“读→改→回复”或“新建→读回→回复”等小任务；更长任务需要显式续办，不宣称完整自主编程系统已完成。结束标记表示模型在已核验的工具回执后报告完成，不是独立证明全部业务意图已满足。

工具执行通过真实 worker 子进程；不让 Codex 推理调用直接操作文件。root 账户可以使用，其他账户不能继承项目文件权限。没有改变人格、身份、记忆或自主探索开关。

## 文件边界与记录

目录授权保存真实根路径、设备/inode 和配置代次。实际操作使用目录 fd 和 O_NOFOLLOW；上跳、链接、隐藏路径、特殊文件及受保护运行数据不可访问。默认排除 work、releases、snapshots、account-backups 等，另可增加排除项。

写入前核对旧 hash；新文件必须使用空旧 hash。记录原内容、差异和写后 hash 到实例的 project-operations 日志，并在正常执行链路保存 action receipt。单文件临时写入后替换；写入可能发生而回执未确认时不声明成功。外部不遵守本系统锁的进程仍存在最后检查后的竞争窗口，不能宣称对任意外部写入者具备原子 CAS。

本版不提供删除、移动、通用 shell 或任意测试命令（具名检查仅含 Python 语法检查），未借“目录授权”自动取得发布和部署权限。编辑源码不等于正在运行的版本已改变，生效仍由 CLI 发布流程处理。

## 验证

- 48 项相关回归通过（8.872 秒），覆盖聊天、行为选择、Codex 结构化调用和既有 workspace 流程。
- 最终新增核心测试单独记录于 `outputs/project-tools-review/final-core-tests.log`，覆盖三次独立思考的真实 worker 读改回流、新建、较大文件片段修改、创建目录、搜索、旧 hash 冲突、越界、链接、显式审批、撤销与工具子集。
- 首次实现测试暴露 think 中引用未定义变量和执行返回结构不匹配，已修复；一次回归命令使用了不存在的 test_codex_cli 模块名，改用实际的 test_codex_models。保留首次日志，不以其冒称通过。
- 所有模型均为替身，文件后端为真实 worker。没有正式模型调用或正式数据写入。

## CLI

先部署包含本功能的源码，再启用目录；CLI 会拒绝向缺少本功能的运行版本写配置。

```sh
python3 -m digital_life --data work/primordial00-first-wake project-access status

# 示例：精确目录由用户确认。省略 --auto-approve 则每次动作需审批。
python3 -m digital_life --data work/primordial00-first-wake project-access enable \
  --root '<PROJECT_ROOT>' --auto-approve

# 只读工具子集
python3 -m digital_life --data work/primordial00-first-wake project-access enable \
  --root '/path/to/project' --tools project_list project_read project_search

python3 -m digital_life --data work/primordial00-first-wake project-access disable
```

项目根目录授权现已实际启用，另排除 config/local。其他路径的示例不代表额外授权。项目根目录包含 work 时，work 排除生效；身份数据库与发布记录仍由专用模块维护。

## 正式启用记录

用户确认“采用建议的项目目录和权限”后，部署 `5dbfab4c08f746c186803116b1380080`，恢复原实例运行，再经 CLI 启用 `<PROJECT_ROOT>`。自动允许工具为列表、语法检查、建目录、片段编辑、读取、搜索和写入；仅 root 可用。

排除 work、releases、snapshots、account-backups、config/local、node_modules、__pycache__，另有执行器对隐藏路径、链接及已知凭据文件的检查。配置代次与部署代码已核对。没有提交新的正式模型测试消息，没有重建身份、记忆或历史。

补充 Python 语法检查后，最终 7 项核心验证通过（3.555 秒）。检查器使用 AST 解析，不导入或执行项目代码；正常语法和错误语法均由真实 worker 验证。命令执行权限没有因本次授权自动变成任意 shell 权限。

证据：`outputs/project-tools-review/enabling-core-tests.log`、`outputs/project-tools-review/formal-enabled.json`。之前的“尚未启用”记录描述当时状态，以本节为准。

## 连续执行更新（2026-11-15）

此前三轮限制和随机询问中断已修复，项目任务现由原活动预算控制；真实四轮读、改、语法检查、最终回复在58.56秒完成。旧测试记录保留，当前结果见 `project-task-continuity-fix-report.md`。
