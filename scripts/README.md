# 辅助脚本

均从项目根目录执行。日常实例启停使用 `manage.py` 或 `start-chat.command`，不要用历史诊断脚本替代。

| 目录 | 用途 | 示例 |
| --- | --- | --- |
| development/ | 配置、结构生成与开发辅助 | `python3 scripts/development/check_task_plan.py` |
| verification/ | 功能验收、材料校验与界面检查 | `node scripts/verification/verify_thought_inspection_ui.mjs` |
| release/ | 安装包与交付检查 | `python3 scripts/release/verify_distribution.py work/distributions/ai_assistant_with_memory-0.5.0-py3-none-any.whl` |

脚本名含 `real`、`trial`、`run` 或模型测试的，不应直接作为无副作用检查运行；按其参数和对应操作指南确认目标、模型与预算。`development/` 中也有真实模型评测入口，目录名不代表离线或无副作用。

完整自动化回归使用正常模块入口，避免多进程无法重新载入标准输入脚本：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
```

本机临时端口与子进程需要正常运行权限。默认真实模型验收测试保持跳过，不代表真实模型已经验收。测试结果保存到 `outputs/`，不得直接随源码公开分发。
