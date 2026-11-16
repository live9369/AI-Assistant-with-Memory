# G2真实先导、匿名评审与质量聚合操作

适用运行基线：AE-RUNTIME-1.2（默认；--baseline v1.1 仅在评测依赖仍匹配旧基线时可用，从已通过G1的源码归档加载）；评测及指标协议均为1.0。正式实例不传入任何运行器，保持锁定。

## 1 材料

`evaluation/exploration/g2/materials/`包含：

- development-public/oracle.json：6个独立开发情境，A–F各一；本次先导只用此集。
- formal-candidate-public/oracle.json：60个候选正式情境，A–F各10，20个主缺口反例机会；不在本次先导暴露。

public仅包含记忆、可读文件、预注册世界事件和故障。oracle包含缺口、核验规则、反例和不可解说明，不复制到actor工作区，也不拼入推理请求。材料由当前agent编写，和G1夹具分开；文件不重合、主题不重复不等于已证明统计独立，独立材料审核仍待补足。

构建脚本`build_materials.py`是作者材料的可复核来源，不会运行模型。不要在一次已封存实验中重建或覆盖输入。修改数据应另建版本和run，保留原摘要。

## 2 先导运行

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/development/run_exploration_g2.py --baseline v1.2 --mode pilot --config config/local/codex.json
```

本次用户选择现有Codex配置的真实先导。每case全新临时实例，单次完整组，最多3活动、每活动3轮、6个模型端口调用、300秒墙钟；整个六case上限36个模型端口调用。模型超时取配置上限和剩余墙钟预算较小值。没有额外人工任务、自动远程API回退或模型切换。

没有--data参数，不会对正式实例解锁。运行前检查正式WAKE_DISABLED并记录文件摘要，结束后再次核对。provider登录由既有CLI管理，不复制凭据；只有合成公开材料进入模型。

Codex每次调用使用独立临时会话，禁用模型工具、浏览器、MCP和会话续接；只接受结构化候选，再由既有Engine与Executor执行允许的临时工作区read_file/list_files。评测器拥有本次CLI子进程，正常、异常和SIGTERM时清理；外层watchdog保留失败证据。

token预算是观测后停止后续调用的阈值，不宣称冻结Codex适配器提供硬输出token上限。用量缺失后不再追加未计量调用，未知数保持null，不用预留4096替代实际token。路由不接受付费remote_chat配置；订阅CLI的配额、延迟和别名修订不可由本工具保证。

## 3 G1前置与源码隔离

运行器核对已通过G1的结果指针、aggregate摘要、所选版本基线，以及完整归档运行依赖。每个worker从run内validated-runtime加载生产包，而非当前工作区混合版本。当前工作区engine、memory或CLI后续改动不被覆盖；manifest分别保留工作区G0差异及被测归档G0。

调用前封存manifest、public/oracle、actor-config、全部源码、CLI可执行文件摘要、预算、逻辑时钟及世界事件。每个worker再次校验。源码和材料变化会拒绝后续trial，不临时适配到未验证版本。模型别名无法固定provider内部修订时，记录这一限制。

逻辑时钟只在评测层把调度间隔推进300秒，以免人为等待长达数小时；请求超时、真实模型I/O及watchdog仍用真实时间。E类按预注册事件更新文件并物理重开Store/Engine；F类只注入事先规定的工具失败／未知结果。不是凭模型回答临时改世界。

## 4 匿名评审

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/development/review_exploration_g2.py outputs/acceptance/ae-g2/<run_id>
```

导出review/packets.json、private-unit-map.json、labels-template.json及review-manifest校验链。actor／arm／repeat元数据不出现在评审包，问题、调查、解决、缺口、反例分别生成匿名单位，次序打乱。初始记忆、真实观察、按活动关联的声明和评审oracle保留，不能只给漂亮的结论文本。

拷贝labels-template到新的评审文件后填布尔字段、理由及存在于packet中的引用；不要覆盖模板或既有评审。填空、伪引用、重复身份、不同packet摘要均拒绝。informative=true至少引用真实观察，covered=true至少存在实际解决声明。

本轮按用户要求，由参与材料和运行的当前agent作研究支持的单评审。即使包已匿名，也不能声称该作者不知道actor身份；independent=false等身份字段必须如实填写。量表、研究来源和独立性限制见[评审依据](../research/autonomous-exploration-g2-review-rubric.md)。正式契约仍要求两个独立盲评者，分歧第三方裁决；当前单评审不会使G2通过。

## 5 聚合

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/development/aggregate_exploration_g2.py outputs/acceptance/ae-g2/<run_id> --review <review-file.json>
```

可重复传--review；有独立分歧时用--adjudication。每份原始评审保留，结果记录来源摘要、一致率和Cohen's kappa；单评审不计算虚假的一致性。

M01/M02/M04/M05/M06/M07/M08按评审单位计算原始分子分母、trial和case等权宏观值，按case聚类bootstrap10000次（seed20261108），报告分层及样本数。不同repeat不膨胀为独立case。质量分母不足20时标insufficient_sample，缺标签标missing，零分母标not_applicable；不补零、不伪造通过。

M03、M11、M13从原始运行证据审计；M14保留原始用量和有效探索分母、M15为选中候选的诊断。M12仍无统一确认接口；G3未运行，不计算因果增益。先导或缺少独立双评审时，正式G2结论为not_evaluable，并列出全部阻塞项，程序退出码2。

## 6 正式阶段入口与范围

运行器也提供--mode full：60候选case×3次，只有完整组；不是包含G3消融的720trial总方案。该模式在本轮没有授权执行，后续需审核候选材料、评审安排及可能显著增加的真实调用预算，再登记新manifest。绝不能把本次开发先导当作正式集完成。

本版运行机制修复见 [1.2契约](../architecture/autonomous-exploration-contract-v1.2.md)；原基线和证据保留。质量聚合另报原始候选、过滤原因及证据复用次数，避免只见接纳分母而忽略筛选。正式实例和历史证据应在每次运行前后保持可核验。
