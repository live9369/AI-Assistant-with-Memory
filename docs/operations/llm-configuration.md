# 本地与远程LLM配置

版本 V0.4.0。远程模板和适配器已实现，尚未配置真实远程账号或调用远程供应商。本轮远程协议验收使用内存回复；真实模型验收仍使用本机隔离模型。

V0.5已接入[管理面板](management-panel.md)：可载入模板、离线校验及保存新版本；显式清单检查独立操作，面板不接收真实密钥。下文协议字段继续适用。

## 1 选择模板

| 文件 | 后端 | 输出形式 |
| --- | --- | --- |
| config/examples/llm/ollama.example.json | ollama | 本地Ollama结构化输出 |
| config/examples/llm/llamacpp.example.json | llamacpp | 本地llama.cpp结构化输出 |
| config/examples/llm/remote-chat.example.json | remote_chat | HTTPS Chat Completions + JSON Schema |
| config/examples/llm/remote-json-object.example.json | remote_chat | 同一协议 + JSON Object |

远程模板 enabled=false，读取、验证和离线保存不会发请求。选择远程后，实际思考时会将本次明确构造的任务、所选记忆和情境发送给所配置的服务；不会自动发送整个数据库。

模板面向实现 Chat Completions 兼容协议的服务，不声称适用于所有供应商。Anthropic Messages、Responses或其他原生协议应新增适配器，不能只把URL替换成其端点。[兼容接口与结构化输出参考](https://github.com/ggml-org/llama.cpp/tree/master/tools/server)。

## 2 字段说明

| 字段 | 含义 |
| --- | --- |
| backend | remote_chat 明确选择远程，不会从本地失败自动回退到它 |
| enabled | 必须为布尔值；默认false，实际调用需明确改为true |
| base_url | 例如 https://供应商地址/v1；不包含 /chat/completions，不放凭据、查询或片段 |
| model | 供应商模型标识，替换 REPLACE_WITH_MODEL_ID |
| api_key_env | 读取密钥的环境变量名；配置和数据库只保存名称 |
| timeout | 请求超时秒数；不进行隐式重试 |
| max_output_tokens | 输出上限 |
| context_window | 客户端保守输入预算，按字节预检查，不是精确分词器计数；超预算拒绝而不静默丢记忆 |
| temperature | 显式采样温度；供应商需支持该参数 |
| response_format | json_schema 或 json_object；按供应商实际能力明确选择，不自动降级 |
| token_parameter | max_tokens 或 max_completion_tokens；按供应商文档选择 |
| accepted_response_models | 可选，允许的响应模型名列表；默认只接受model，供应商返回快照名时明确列出允许值 |

两个远程模板都保留项目的本地结构校验、工具白名单和后续审批。JSON Object模板只表示供应商不提供Schema约束，不表示允许任意JSON进入执行层。

## 3 复制并离线审阅

将所选模板复制到 config/local/，替换地址、模型及参数。config/local/ 已加入忽略列表，不自动读取。真实密钥放在进程环境的 DIGITAL_LIFE_LLM_API_KEY，或在 api_key_env 指定另一个名称。remote.env.example 只是命名示例，程序不会自动加载.env文件。

下面仅展示新建、仍锁定的审阅实例，不操作正式实例：

```sh
python3 -m digital_life --data work/config-review prepare --model-config config/examples/llm/remote-chat.example.json
python3 -m digital_life --data work/config-review inspect
```

为已停止的审阅实例保存自己的配置、同时不联网：

```sh
python3 -m digital_life --data work/config-review configure-model config/local/remote.json --offline
```

离线保存会追加配置版本，不能证明供应商可用。原有WAKE_DISABLED不会被移除。修改路由要求控制面停止；已有请求继续保存其原始清单，不通过失败自动选其他供应商。

## 4 显式检查与实际调用

配置 enabled=true、提供进程环境密钥后，model-probe 才能访问所配置服务的 GET /models；它不进行文本生成。一些兼容服务不提供此清单接口，此时探针明确失败，可离线保存配置再使用独立测试验证生成，不自动假装清单检查成功。

实际生成发送 POST /chat/completions，每次构造全新的system与当前user消息，不传history、messages续接输入、thread_id、previous_response_id或conversation_id。响应必须完整结束、满足动作结构且模型名在显式允许范围内。生成只返回候选，工具仍通过权限和执行层。

HTTPS使用标准证书校验，禁止携带认证信息的URL和自动重定向，不继承环境代理；客户端不把Authorization和供应商错误正文写入事件。用量由供应商返回时记录，缺失不伪造。本轮没有执行这些真实远程请求。

## 5 增加其他协议

实现领域Reasoner接口，在 infrastructure/llm/ 增加传输适配器并登记工厂。使用 schemas.py 的项目输出契约，保留独立输入、显式路由、密钥外置、响应校验和用量记录。新增模板及无网络协议测试即可，不需要修改记忆、人格或目标模块。

## Codex订阅接入

新增 `codex_cli` 后端，使用官方CLI持有的ChatGPT登录，每次临时独立会话。它不使用远程API密钥模板；配置和验收见[Codex接入指南](codex-configuration.md)与[设计](../architecture/codex-reasoner-design.md)。
