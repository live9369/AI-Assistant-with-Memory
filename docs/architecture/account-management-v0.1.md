# 独立账户、固定对话与记忆域 V0.1

日期：2026-11-14  
状态：已实现，核心验证通过；已安装并部署到原实例。

## 用户已确认的权限

| 类型 | 账户管理 | 记忆域 | 系统操作 |
| --- | --- | --- | --- |
| root | 唯一，最高权限，管理所有账户 | 全部 | 保留原CLI及管理权限 |
| admin | 创建、维护普通/访客账户，不增设root或提升自身 | 全部 | 不配置模型、唤醒、审批或执行系统工具 |
| member | 维护自己的凭据 | 本账户私有域与共享域 | 对话，不执行系统工具 |
| guest | 维护自己的凭据 | 仅检索共享长期记忆 | 对话，不执行系统工具 |

历史数据先归初始root，不公开。管理员可读全部可用记忆域，但删除、撤回、失效来源不会因此恢复。root是系统账户，不自动绑定liwei或父亲关系。人格仍属于同一个数字生命，不按账户复制生命。

## 一个账户一条持久对话

账户UUID决定固定thread_id，角色变更、登出、重新登录、换设备均不新建对话。登录会话与对话线程是两回事；多个设备可登录同一账户，但发言用expected_last_activity_id做并发检查。前端删除会话选择器/新建会话按钮，后端拒绝账户任意指定别人的会话或新建线程。

历史聊天通过映射表并入root的固定对话视图，原活动、原thread_id、身份、记忆和历史不改写。只保留有限最近上下文及按权限检索，LLM仍每次独立调用，不恢复供应方会话。访客可以查看自己的对话上下文，但长期记忆检索仅共享域。

## 存储与事务

认证独立存于 accounts.sqlite（权限0600），含settings、accounts、sessions、login_attempts、audit。绑定instance_id；不向LLM、日志接口或记忆域暴露密码摘要和登录令牌。

accounts：id、username（唯一，root保留）、display_name、role（root/admin/member/guest）、status（provisioning/active/disabled）、password_hash、revision、created_at。root角色部分唯一索引，且API禁止禁用/降级root。密码带独立随机盐，PBKDF2-HMAC-SHA256 600000次，不保存明文。账户创建先provisioning，再在运行库创建actor与固定对话投影，最后active；半成品不能登录，可按相同账户配置恢复。

sessions：token_hash、account_id、account_revision、created_at、last_seen、expires_at、revoked。令牌随机256位，只保存摘要；绝对8小时、空闲30分钟；角色/密码/状态变更增加revision并撤销旧登录。失败登录按用户名与全局窗口限流，未知用户名执行同类密码计算并返回统一错误。

运行库增量表：acct_activity_owners（活动归属及生成时权限层级）、acct_conversation_turns（账户固定对话的有序活动映射）、acct_memory_domains（记忆共享/私有域及来源权限层级）、acct_object_owners（认知等派生对象归属）、acct_policy_state（域权限修订）。沿用SQLite，不降级或跳过严格学习存储保护。首版明确只在原生schema2/3安装，受保护schema4拒绝自动安装。

## 域在输入链路上生效

账户私有域private:<account_id>，共享域shared。账户类型给默认读权限；未标记的历史对象归root私有且按旧高权限数据处理。管理员/root可读全部域，普通账户不能互读同类型账户的私有记忆；访客不能检索私有记忆。共享只通过管理员/root显式操作，不因对话提到“公开”就自动发布。

活动发言者是已认证账户对应的social_actor，不再把所有人记成controller。用户提交的account_id、actor_id、domain_id或角色字段不作为授权来源。每轮输入的账户信息来自服务端记录，不包含凭据；账号认证不等于现实身份或亲属关系验证。

记忆召回、派生记忆来源、认知快照及时间来源、关系/习惯上下文、思考详情和历史查询均检查当前账户范围。生命周期自身对来源的撤回权限与受众权限同时成立才可入模。派生记录继承实际来源/活动归属，回填旧回复不能误归当前检索者。

角色降级不能让旧高权限模型回复通过“自己的历史/记忆”再次进入低权限输入：记录生成时权限层级；普通账户不重新读取高权限阶段内容，除非经过显式共享。禁用账户、域授权撤回或账户修订改变时，在模型发送前及结果采用前重新检查；已发给模型的数据无法被追溯撤回。

全局已批准的生命身份、人格与价值参数为共同核心；账户私有资料不自动训练全局人格。首版对尚未完成域适配的自主探索、人格成长、习惯学习、自维护/记忆质量等已启用模块，对低权限账户默认拒绝，不以删掉校验来绕过。当前正式实例这些模块保持关闭。高权限账户继续沿用完整链路。

## 接口与页面

- POST /v1/auth/login、/logout，GET /v1/auth/me：账户登录、登出、当前账户。
- GET/POST /v1/accounts，POST /v1/accounts/<id>、/v1/accounts/<id>/password：按类型管理账户。
- POST /v1/account/password：自己改密；初始root无默认密码；只有root未设密且账户总数为1时，才允许本机首次设置并自动登录，之后禁止重复初始化。
- GET/POST /v1/conversation：当前账户唯一对话。
- GET /v1/activities/<id>/thoughts、/v1/thoughts/<id>：按活动归属与当前权限检查。
- GET /v1/account/memories、POST /v1/account/memories/domain：授权范围内的记忆与显式共享。

普通账户无法进入旧管理API或借旧多会话接口绕过限制。root保留管理总览、审批、模型配置与健康日志；admin仅账户/记忆管理及对话。浏览器登录用HttpOnly、SameSite=Strict cookie，沿用本机Host/Origin限制，不把会话令牌存localStorage。继续绑定127.0.0.1，不因增加账户自动开放公网。

## 迁移与验收

先写代码及完成必要的账户/域测试，正式启用时再停止原实例、备份数据库、显式安装、部署同一身份。安装脚本备份runtime/control/accounts数据库；原始blob和workspace不改写。本轮已通过CLI停止、备份、安装并部署同一个原实例；没有提交真实模型测试消息。原控制令牌仅作为root的引导/恢复凭据保留，不作为普通账户凭据分发。初始root没有默认密码，通过面板设置。根账户唯一性、登录/撤销、角色越权、同类私有域隔离、共享撤回、派生来源、完整入模请求无串域、固定会话并发及旧数据保留是本模块的必要验收。先不调用真实模型或开展长期/增长测试。

## 依据

逐请求授权、默认拒绝与对象级校验参考[OWASP Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)。会话在服务端验证、超时与撤销参考[OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)。独立盐与慢密码摘要参数参考[OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)。上述账户类型及记忆域是本项目的产品设计，不冒称这些文档规定了数字生命的账户结构。

## 首版明确边界

共享撤回会阻止后续直接召回并使已准备输入在发送/采用前失效；已经展示或已经由账户获知的内容无法收回。模型回复记忆保留所选记忆的父来源依赖，即使记忆质量学习未启用；派生来源撤回仍会阻止召回。历史对话保留曾经合法送达的内容，不能把域撤回理解为所有历史内容的追溯删除。共享派生记忆的域标签不自动扩大其父来源权限。

本轮未进行真实模型调用、长期验收、全量压力测试或浏览器视觉验收；账户HTTP、完整替身模型输入、核心旧链路回归和JavaScript语法已验证。

登录简化：GET /v1/auth/status仅公开是否需要首次设置；POST /v1/auth/setup仅进行一次root设密。面板不再提供手动token连接，自动恢复未过期cookie。见../operations/account-login-simplification-2026-11-14.md。
