# 账户管理 V0.1：交付与启用

日期：2026-11-14。状态：源码实现与核心验收完成，已在原正式实例安装并部署。

## 已实现

| 类型 | 可读记忆 | 管理权限 |
| --- | --- | --- |
| root | 全部可用域 | 唯一最高权限，维护所有账户与系统配置 |
| admin | 全部可用域 | 管理member/guest、共享与撤回记忆；不能提升管理员或操作系统工具 |
| member | 自己的私有域及共享域 | 自己改密、固定对话 |
| guest | 共享长期记忆 | 自己改密、自己的固定对话与有限对话上下文 |

一个账户一条持久对话。登出、重新登录或换设备不另建对话；多设备并发发送用最后活动版本检查。每次思考仍是干净、独立的模型调用，系统明确组装授权范围内的输入。

旧身份、旧记忆及历史不改写。安装以原controller作为唯一root，把旧聊天映射到root固定对话，旧资料默认root私有。root不自动绑定liwei或“父亲”。人格成长仍未启用。

密码采用独立随机盐和PBKDF2-HMAC-SHA256 600000次；随机登录令牌仅保存摘要，浏览器使用HttpOnly、SameSite=Strict cookie。登录绝对8小时、空闲30分钟失效；改密、禁用和角色修改撤销旧登录。root原有controller.token保留为本机引导/恢复凭据，不可分发给普通账户。

权限检查覆盖HTTP白名单、聊天、记忆、认知、关系、习惯建议、完整思考详情，以及模型发送/采用两道边界。普通账户的历史高权限阶段内容不会在降级后回流为自己的低权限上下文。共享撤回不能追溯收回已交付内容；派生来源权限继续取交集。

## 在现有实例启用

本轮已按下列流程完成首次安装和部署；当前实例不要重复安装。其他实例可参考此流程。

1. 使用CLI停止运行器，并关闭原来执行一键启动的终端/面板服务，确认其进程退出。

```sh
python3 manage.py --data work/primordial00-first-wake stop
python3 manage.py --data work/primordial00-first-wake status
```

若状态仍显示active_process_run_id，不要绕过安装保护或直接删数据库记录。确认对应进程已经退出后，通过现有控制面回收进程登记，再继续。安装脚本会拒绝仍有活动登记的实例。

2. 检查，再备份并安装。默认不安装；必须显式加--install。

```sh
python3 scripts/development/install_accounts.py --data work/primordial00-first-wake
python3 scripts/development/install_accounts.py --data work/primordial00-first-wake --install
```

脚本要求原生schema2/3和停止状态，先将runtime.sqlite、control.sqlite及已有accounts.sqlite一致备份到实例内account-backups/<时间>/，目录0700、文件0600。它只新增账户和映射表，不删除历史、blob或workspace，不启动推理。重复执行不会重建身份或root。schema4受保护实例明确拒绝自动安装。

3. 用既有一键命令部署源码并启动同一个实例，保持终端打开。

```sh
./start-chat.command
```

默认端口18765；在浏览器打开 http://127.0.0.1:18765/ 。启动脚本仍控制是否唤醒，不将部署或唤醒按钮放进面板。启动后真实用户发送消息会按现有模型配置调用模型。

4. 首次直接在面板设置root密码并进入；已有密码时用root与该密码登录。手动token连接入口已移除，刷新页面会自动恢复尚未过期的账户登录。进入“账户管理”分发admin/member/guest；密码不会被写进记忆或发给模型。

5. “交流”只显示当前账户的固定对话。“记忆域”显示可读记忆；root/admin可显式共享或撤回。父来源不允许时，仅修改派生记忆域不会越过来源保护。

## 本轮验证

运行命令：

```sh
PYTHONPATH=.:tests PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_account_management tests.test_chat tests.test_cognition_provenance \
  tests.test_shared_memory tests.test_management
node --check digital_life/web/app.js
```

只用临时SQLite实例与替身模型。覆盖唯一root、管理员越权拒绝、登录/注销、旧令牌撤销、同源保护、跨账户私有数据不进入完整模型输入、认知与关系上下文分域、共享/撤回、降级屏蔽高权限历史、调用途中禁用后结果拒绝、旧身份与历史不改写。CLI检查、安装与幂等重复安装也在临时目录验证。

核心回归42项通过：受限沙箱中41项通过，1项HTTP用例因端口权限受限，在允许本机端口的权限下独立重跑通过。JavaScript语法检查通过。

已备份并迁移原实例、部署新版本，并只读验证root认证和固定聊天。没有调用真实模型，没有做长期压力或浏览器视觉验收。正式root没有默认密码，需要用户首次设置。

## 文件与边界

- 设计：../architecture/account-management-v0.1.md
- 任务进度：../plan/account-management-todo-v0.1.md
- 认证：digital_life/application/accounts/accounts.py；HTTP白名单：account_http.py。
- 域执行：account_scope.py、account_memory.py及核心模块接入。
- 存储：digital_life/resources/accounts.sql、account_runtime.sql。
- 安装：scripts/development/install_accounts.py；核心验收：tests/test_account_management.py。

首版仅适配当前原生运行链路。尚未分域适配的全局人格成长、习惯学习、自主探索、自维护、记忆质量学习或任务循环一旦启用，低权限活动会明确拒绝；不会静默跳过保护。当前关闭的功能不会因安装账户而被开启。

## 正式启用记录

- 实例身份：`cc7b7c0b5115413db2e06cfc3c6eed01`，保持原身份。
- 部署：`d0f84e08e8de48fd984bb59f58bbc95b`，源码与运行版本一致，epoch14。
- 备份：`work/primordial00-first-wake/account-backups/20261113T184755359925Z`，名称使用主机UTC时间。
- 迁移前后均为1项身份、45项活动、85项记忆、44次思考尝试、40项结果。
- root固定对话读取87条消息，可继续发送。未新建生命实例，未额外调用模型。
- 面板：<http://127.0.0.1:18765/>。首次直接在页面设置root密码，以后使用账户登录。
