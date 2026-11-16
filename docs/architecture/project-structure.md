# 项目目录与维护规则

更新：2026-11-15。当前源码与正式实例的已部署版本分开管理；修改源码不会自动更新实例。

## 目录职责

```text
项目/
├── README.md                 项目介绍与日常入口
├── manage.py                 CLI 管理入口
├── start-chat.command        本机一键启动
├── pyproject.toml            包元数据
├── setup.py                  兼容旧 setuptools 的构建入口
├── codegraph.json            CodeGraph 项目配置
├── digital_life/             主系统可安装包
│   ├── domain/               公共契约与核心规则
│   ├── application/
│   │   ├── runtime/          思考循环、调度、执行和配置
│   │   ├── chat/             聊天与公开回复组织
│   │   ├── accounts/         账户、权限、记忆域和来源影响
│   │   ├── cognition/        认知更新、依据与经验表示
│   │   ├── memory/           记忆质量和数据管理
│   │   ├── behavior/         人格、目标、关系和习惯
│   │   ├── learning/         工具观察、学习及其受控流程
│   │   ├── autonomy/         自主探索、方向和任务推进
│   │   ├── lifecycle/        健康、部署、版本和恢复
│   │   ├── monitoring/       查询、执行详情与任务检查
│   │   ├── services/         生命模块的基础服务接口
│   │   └── telemetry/        指标采集
│   ├── infrastructure/       模型、SQLite、进程和工具适配
│   ├── entrypoints/          CLI、HTTP 和子进程入口
│   ├── resources/            随包 SQL 与机器字典
│   └── web/                  管理面板资源
├── primordial00/             旧原型兼容与历史回归对象
├── config/
│   ├── examples/             不含凭据的配置示例
│   ├── evaluation/           评测材料与协议
│   └── local/                私有本机配置，不提交
├── database/                 数据库设计与生成资料
├── docs/
│   ├── research/             概念定义与研究基线
│   ├── architecture/         设计、契约和交付报告
│   ├── operations/           操作指南
│   ├── plan/                 TODO 与机器任务状态
│   └── maintenance/          维护及当前验收记录
├── tests/                    自动化功能与集成测试
├── evaluation/               研究评测实现
├── scripts/
│   ├── development/          生成、配置和开发辅助
│   ├── verification/         验收与检查
│   └── release/              构建交付检查
├── work/                     私有实例、模型、备份和构建产物
└── outputs/                  私有诊断、验收数据与证据
```

## 依赖与变更

- domain 不依赖 application、infrastructure、entrypoints 或旧原型。
- infrastructure 不依赖 application 或 entrypoints；应用层负责装配业务流程。
- 原有 services 与 telemetry 保持职责，不为了目录对称而复制实现。
- 迁移源码时同步导入、脚本根路径、资源引用和打包检查；历史冻结材料按自己的修订与校验规则维护。
- 数据库生成 SQL、随包 SQL 与字段字典必须同步。建表 SQL 不能替代实例升级流程。
- 旧原型仍用于兼容和回归，不直接删除，也不增加第二套主框架。

## 私有数据边界

当前正式实例仍为 `work/primordial00-first-wake/`。`work/primordial00/`、备份及进程快照保留原路径；迁移它们需要完整快照和恢复核对，不随源码整理移动。

`work/` 与 `outputs/` 可能包含身份、完整对话、模型输入、凭据及恢复资料，均不进入源码交付包。Git 忽略规则不代替权限保护，也不会自动取消已追踪文件。

## 维护入口

- [日常操作](../operations/cli-management.md)
- [模型配置](../operations/llm-configuration.md)
- [目录重构记录](../maintenance/directory-refactor-2026-11-15.md)
- [回归修复与最终结果](../maintenance/directory-refactor-fixes-2026-11-15.md)
