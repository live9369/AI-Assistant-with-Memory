# GitHub 首次发布

状态：发布材料已准备，尚未创建远端仓库或上传。当前采用 MIT；不要上传 work、outputs、模型、凭据或私人实例快照。

## 仓库展示

- 建议仓库名：`ai-assistant-with-memory`；展示名：**AI Assistant with Memory · 有记忆的 AI 助手**。
- Description：`Experimental digital life with persistent identity, memory, cognition and independent LLM calls.`
- Topics：`digital-life`、`artificial-life`、`ai-agent`、`llm`、`persistent-memory`、`cognitive-architecture`、`python`、`sqlite`。
- 社交封面：`docs/assets/social-preview.png`，可直接在 Settings 上传；源文件为同目录的 project-overview.svg。
- 首版标题建议：**00 Engineering Preview**。内部软件版本仍为 0.5.0，不用一个新标签隐瞒版本对应关系。

## 本地准备

README.md 是英文首页，README.zh-CN.md 是中文版。MIT 版权署名为 `AI Assistant with Memory contributors`，模型与第三方工具遵守各自条款。

从项目根目录运行只读检查：

```sh
python3 scripts/release/check_public_source.py
```

它检查公开源码候选集，排除私人工作目录，只报告文件位置与问题类别，不打印凭据正文。它是发布前辅助检查，不是保证查出所有秘密的扫描器。若项目已经有 Git 仓库，还会检查实际索引中是否混入排除路径；忽略规则不清除已追踪文件。

源码候选清单包含维护中的研究、冻结设计与合成测试。文档里的 UUID、虚构人物和历史阶段记录应逐项审阅；它们不是分发正式实例数据库的理由。

## 创建仓库和首次提交

在 GitHub 创建一个空的公开仓库，不自动生成 README 或 LICENSE；把下方地址替换成你自己的真实仓库 URL。先审阅文件，再执行命令。本指南不替你运行 push。

若根目录尚无 Git 仓库：

```sh
git init -b main
```

显式选择公开文件，不使用整个本机目录压缩上传：

```sh
git add .gitignore .github README.md README.zh-CN.md LICENSE CONTRIBUTING.md SECURITY.md pyproject.toml setup.py manage.py start-chat.command codegraph.json digital_life primordial00 config/examples config/evaluation config/README.md database docs tests evaluation scripts
git diff --cached --stat
git diff --cached --name-only
python3 scripts/release/check_public_source.py
```

确认没有 `.codegraph/`、`config/local/`、数据库、token、work 或 outputs；复核新增文档和源码差异。若之前有 Git 历史，必须另外检查历史中的私有数据，清理当前文件不能删除旧提交中的内容。

审阅完成后：

```sh
git commit -m "Publish AI Assistant with Memory engineering preview"
git remote add origin https://github.com/YOUR-ACCOUNT/ai-assistant-with-memory.git
git push -u origin main
```

已有 remote 时先核对，不重复添加。不要把 GitHub token 放入 URL。

## 首版验收说明

发布说明可引用：完整发现 2,035 项，分段运行及失败补充复验后 2,032 项通过，3 项显式本地模型测试跳过。不是一次未中断全绿，不代表真实模型／长期生命效果全部通过。完整说明见目录重构修复报告。

先以本机 root 单人使用为范围。普通账户的全局模块适配、严格 Codex 新实例与账户面板的组合、通用容器隔离和长期评测仍列为已知限制。

## 发布后

- 设置 About、Topics、Social preview，并核对首屏排版。
- 启用 GitHub 私密漏洞报告后，再在 Security 页面核对入口。
- 开放 Issues，使用已有模板；按实际复现工作维护少量入门任务，不给未评估任务随意贴 good first issue。
- 分享一段真实演示和具体技术问题，遵守社区发布规则，不刷星或群发。
- 用 Insights → Traffic 看访问、克隆及来源，再调整展示内容。

参考：[仓库主题](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics)、[分享封面](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview)、[MIT 标准文本](https://choosealicense.com/licenses/mit/)。
