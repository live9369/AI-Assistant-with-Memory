# 配置目录

| 位置 | 用途 |
| --- | --- |
| examples/llm/ollama.example.json | 本地 Ollama 模板 |
| examples/llm/llamacpp.example.json | 本地 llama.cpp 模板 |
| examples/llm/remote-chat.example.json | HTTPS Chat Completions，JSON Schema 输出模板 |
| examples/llm/remote-json-object.example.json | 同一协议的 JSON Object 输出模板 |
| examples/llm/remote.env.example | 环境变量名称示例，不自动加载 |
| local/ | 用户自行建立的实际配置，已加入忽略列表 |

远程模板默认 enabled=false。将模板复制到 local/ 后替换服务地址、模型名及必要参数；密钥只通过 api_key_env 指定的进程环境变量提供，不放入 JSON。

完整用法与供应商兼容边界见[LLM 配置说明](../docs/operations/llm-configuration.md)。应用不会因导入模块、读取模板或本地模型失败而自动调用远程服务。

## 本机使用约定

- Codex 配置与登录见[操作指南](../docs/operations/codex-configuration.md)；登录凭据由官方 CLI 管理，不复制到示例。
- Codex 的 `max_input_bytes` 表示完整输入字节限制，不是 token 上下文窗口；其他后端的字段按各自配置说明解释。
- `evaluation/` 保存带来源校验的评测材料，不随配置清理删除。
- OCI 示例仍为未实现的后续方案，不代表已有 Docker 隔离后端。
