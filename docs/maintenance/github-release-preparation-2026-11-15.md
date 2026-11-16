# GitHub 发布准备记录

日期：2026-11-15。状态：本地材料准备完成，尚未创建远端仓库、初始化根目录 Git、提交或推送。

## 交付物

- README.md、README.zh-CN.md：双语公开首页，区分工程能力、研究假设和待验证范围。
- LICENSE：用户选择 MIT；版权行采用 Primordial00 contributors。pyproject.toml 和 setup.py 同步许可与 README 元数据。
- CONTRIBUTING.md、SECURITY.md、.github/ISSUE_TEMPLATE/ 与 PR 模板：贡献及反馈入口，不填虚构联系方式。
- public-first-run.md：独立、锁定、无模型的面板预览，再按需使用操作者自己的模型。
- public-demo.md：虚构信息演示分镜，不假装已有真实视频或对话截图。
- docs/assets/：SVG 架构示意与 1280 × 640、约 59 KB 的分享封面 PNG。
- docs/releases/00-engineering-preview.md：可供首次 Release 使用的说明草稿，未实际发布。
- github-release.md：仓库名称、简介、Topics、人工审阅、显式 git add 与 push 步骤。
- scripts/release/check_public_source.py：只读公开候选清单与有限的凭据／本机路径检查；有 Git 索引时另核对被排除路径，不能代替完整秘密扫描或历史审计。

三份工程报告中的个人本机源码目录已改为 PROJECT_ROOT 占位说明；实现与验收结论保留。维护中的 CLI 说明同步使用 max_input_bytes 名称。没有修改运行层或正式实例。

## 验证

- 临时实例走通 prepare、账户安装、完整性检查，以及停止状态下的认知／人物模块配置；root 需要首次设密、唤醒锁保留、思考请求为 0。临时目录随后自动删除。
- 33 项架构、聊天、Codex 用量和冻结材料检查通过，没有重跑长期或全量测试。
- 新 wheel 构建及源码目录外执行检查通过；元数据声明 MIT，许可文件已包含。
- 发布检查工具的私有目录排除、脱敏报告、符号链接及已追踪私有路径检查在临时 Git 仓库验证通过。
- 公开候选扫描未发现当前规则匹配项，私有 work、outputs、config/local 等未被读入候选集。实际没有根目录 Git 索引，因此不声称已经审查了真实待提交内容或 Git 历史。
- 新入口链接核对通过；PNG 文件尺寸核对并实际查看，图中内容明确为概念示意。

详细证据在 outputs/github-release-preparation/，不进入公开源码提交。

## 待操作者完成

1. 在 GitHub 创建自己的仓库，复核完整待提交清单及需要公开的历史报告。
2. 按实际仓库地址设置 remote 并推送，再配置 About、Topics、分享封面及私密漏洞报告入口。
3. 若需要视频或实际聊天截图，使用独立演示实例和虚构信息真实录制。模型访问与预算由操作者选择，不使用正式实例记忆作为宣传素材。

本轮没有上传任何文件或使用模型额度。MIT 标准文本来源：https://choosealicense.com/licenses/mit/ 。
