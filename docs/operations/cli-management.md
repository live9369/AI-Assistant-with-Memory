# 中文CLI管理入口

在项目目录运行 `python3 manage.py`，进入菜单。默认目标是 `work/primordial00-first-wake`；每次菜单顶部显示完整实例路径。可用 `--data` 指定其他实例。不会默认操作旧的 `work/primordial00`。

## 常用流程

```sh
python3 manage.py
```

也可以直接使用命令：

```sh
python3 manage.py setup-codex
python3 manage.py login-status
python3 manage.py prepare
python3 manage.py check
python3 manage.py status
```

setup-codex自动发现Codex路径并生成config/local/codex.json；已有配置不会覆盖。如未登录，可执行 `python3 manage.py login`，由你在官方网页完成设备码确认。prepare只创建锁定实例，check做数据检查及模型探针，不执行生成。

新生成的 Codex 配置采用 `budget_mode: "post_usage"`，调用返回后按原活动额度核账；用量未知或超限时保护停机，不采纳结果、不继续。`max_input_bytes: 262144` 是完整本地输入字节容量，不提高活动预算。已有配置不会自动修改；如需启用，请先显式编辑配置文件，再在实例停止时执行 `python3 manage.py --data 实例目录 configure --config 配置文件路径`，之后再执行 `start`。这会记录配置版本，保留身份、记忆和历史。

已有实例更换配置：`python3 manage.py configure --config config/local/codex.json`，离线版本化保存，要求实例停止。

输入任务是可选的：

```sh
python3 manage.py submit "请在笔记中写下：第一次唤醒测试。"
```

默认自动生成唯一任务键；需要防重复提交时使用固定 `--key`。输入只保存和入队，不唤醒。无任务时，运行器等待；自主探索是否启用取决于已有实例配置，可先用 `python3 manage.py exploration-status` 查看，本脚本不自动开启。

## 唤醒

### 一键运行实例与面板

最小设计：`start` 是前台命令，先检查既有实例和面板端口，再复用原有 `wake` 流程；管理面板在本命令内运行，运行器由独立进程组承载。实例级会话锁防止重复启动。不会隐式创建、重置、迁移实例或修改身份、记忆和历史，也不在面板新增部署或唤醒入口。

```sh
python3 manage.py --data work/primordial00-first-wake start --open
```

确认显示的实例目录并输入 `WAKE primordial00-first-wake`。终端打印可点击的 `http://127.0.0.1:8765/`；页面使用账户密码登录；仅初始 root 未设密时显示首次设置入口，不需要复制 token。`--open` 可省略，`--port 8766` 可指定其他面板端口。

非交互使用必须明确确认：

```sh
python3 manage.py --data work/primordial00-first-wake start --confirm "WAKE primordial00-first-wake" --open
```

保持终端打开。Ctrl+C 关闭本次面板和本次唤醒的运行器，记录停止并恢复禁止唤醒锁；失败同样清理本次进程。已经运行的实例只增加本次面板，不部署、不重复启动运行器，Ctrl+C 也不会停止它。运行登记已失效或与禁止唤醒锁冲突时明确拒绝，要求先检查并显式停止。已有另一 `start` 会话会拒绝重复启动；端口被占用时不启动运行器、不终止占用端口的进程。

实例存在 `MODEL_USAGE_REVIEW_REQUIRED` 时，`start` 会在检查、面板和子进程启动前拒绝；不会删除该标记或解除保护，必须先完成模型用量复核。

Codex `post_usage` 仅支持严格实例（数据库版本 4）。`start` 会只读检查并拒绝旧版本，不自动迁移、复制或替换旧实例。需要全新严格实例时，显式选择一个尚不存在的新目录：

```sh
python3 -m digital_life --data work/NEW-strict-instance prepare --strict --model-config config/local/codex.json
python3 manage.py --data work/NEW-strict-instance start --open
```

这是新实例准备流程，不会继承或覆盖旧实例的身份、记忆和历史；已有实例升级须另行明确规划，不由 `start` 隐式处理。

```sh
python3 manage.py wake
```

检查显示的目标目录，按提示输入 `WAKE primordial00-first-wake`。脚本依次校验实例、数据和模型登录，准备当前源码版本，再解除该实例唤醒锁、恢复运行许可并启动部署。保持终端打开；Ctrl+C停止。模型探针只证明登录/清单状态，不能保证后续推理或额度始终可用。

脚本不绕过恢复核对、数据库兼容或权限审批。失败或中断后尽力记录停止并恢复禁止唤醒锁；失败不会自动重新唤醒。首次部署没有上一版本可退。旧原型实例需要单独迁移，不要直接改为目标。

非交互脚本必须显式提供 `wake --confirm "WAKE 实例目录名"`，不会通过缺省确认唤醒。

## 停止与查看

```sh
python3 manage.py stop
python3 manage.py lock
python3 manage.py panel --port 8765
```

stop记录停止要求；lock另外加禁止唤醒锁，运行器收到停止后退出。panel只运行管理面板，不启动生命运行器。stage只准备版本，不启动部署。部署、启动和唤醒始终由CLI处理。

## 本次验证

新增7项测试通过，覆盖配置生成与拒绝覆盖、确认失败保留锁、探针失败不解除锁、启动异常和部署失败JSON恢复锁、输入任务键生成，以及临时实例的真实准备/离线配置。实际deploy调用只在测试中模拟，未执行真实唤醒。

## 版本核对

status现在只读显示部署ID、进程登记、停止状态、源码与部署是否一致及变化文件。源码有更新不等于运行器已更新。wake发现仍有运行进程会拒绝继续；部署握手完成后立即向终端打印deployment_started和实际PID。旧终端只显示“正在启动”不能证明新版生效。

## 当前真实聊天快捷入口

macOS 可双击项目中的 `start-chat.command`，或在项目目录执行：

```sh
./start-chat.command
```

默认目标为已有正式实例 `work/primordial00-first-wake`，面板端口 18765。默认允许唤醒；先运行 `./start-chat.command --show-config` 可只查看配置。使用 `DIGITAL_LIFE_WAKE=0 ./start-chat.command` 可只打开面板，不主动唤醒。

脚本复用已有面板，并按所选唤醒配置决定是否启动运行器；不会自动创建、重置或替换身份。面板采用账户密码登录，不复制令牌或修改剪贴板。需由本次命令创建的前台服务应保持终端打开；退出时以 CLI 状态核对结果。详见[一键启动配置](one-click-start-configuration.md)。
