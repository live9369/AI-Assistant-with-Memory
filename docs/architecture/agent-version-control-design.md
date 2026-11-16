# 原初00版本管理 V0.1

2026-11-15，实施设计。

采用宿主 Git 的对象、提交、引用机制；模型只见受控版本工具，不获得 Git shell。每个已授权项目根有独立 bare repository，存于实例 project-versions，项目目录没有新增 .git，不干扰用户已有仓库。Git 使用独立配置环境，无远端、hook、过滤器或凭据调用。

工具：project_version_status（指定文件的工作状态与当前版本）、project_version_save（显式文件列表增量保存及说明）、project_version_log（有限历史）、project_version_diff（单文件历史与当前差异）、project_version_restore（按旧hash恢复单文件，并追加历史）。所有工具沿用项目授权、root限制、动作审批和审计、工具预算与独立思考闭环。

保存/恢复必须携带预期 head（首次为空），以 update-ref 的旧值核对防止覆盖其他提交。版本读取只允许该项目主历史可达的完整提交id，恢复文件继续经过当前目录排除项与文件权限。恢复不 reset 历史，也不触发部署。支持UTF-8文本和存在于目标版本中的文件；本版不提供历史缺失状态的删除、分支合并、网络同步。

保存仅采集显式列出的文件，不扫描全部项目，不自动把 work、凭据或巨大 outputs 纳入历史。首次文件编辑前后自动存档只在版本工具已明确授权时启用，避免另用模型调用；写前快照失败则不修改，写后版本记录失败则返回未确认状态，不冒称整个操作成功。

参考：[git commit-tree](https://git-scm.com/docs/git-commit-tree)、[git update-ref](https://git-scm.com/docs/git-update-ref)。Git提交不等于发布；现有 Releases/SourceUpdates 负责运行版本及回退，继续保留。

验收只覆盖真实 worker 保存、修改差异、历史恢复及新提交、旧 head 冲突、当前权限排除、持久化重开；不做长期或远端测试。通过后部署原实例，在现有授权范围增加版本工具，建立初始源码基线。
