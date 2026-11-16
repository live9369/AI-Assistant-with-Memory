# 固定BINDING读取的已知环境必要谓词

状态：先设计后独立基础实现；只改监视器/基础测试，不改应用BINDING或readset。2026-11-12。

`known_read_environment()`只刷新原完整adapter/converter注册表并检查原有受管状态，不执行SQL、不要求事务、pending或receipt。它是应用固定规范化Ref读取可尝试复用BINDING的必要环境条件，不是权限或当前版本结论；应用在生产及命中时都必须调用，并继续原当前Ref投影、phase/freshness和每消费者权限判断。

必要条件：不在SQLite callback动态范围、连接未关闭、无unknown authorizer/trace/公开progress、原生已知row/text factory、无unknown cursor factory、无collation/extension/原生adapter等已观察opaque历史。原私有meter progress和受管clock UDF保留原契约；进入它们的callback期间该谓词仍为False，不能在callback中借旧缓存读取。

明确不查看txn、pending、accepted或账本tainted：这些描述写证书资格，不说明固定读取环境。纯读取的环境合格也不证明源没变；主库、控制、原件变化及回滚仍由应用原probes/generation处理。未知环境返回False走原完整读取，不能为了命中BINDING修改hook或忽略observer。

基础验证覆盖事务前/候选pending/accepted/提交后均不依赖receipt状态、unknown各flag、callback内部拒绝、注册表变化立即拒绝及无额外SQL。应用端另验证创建/命中两入口的fallback及完整同库来源/权限对照。

快速基础58/58通过，0失败/错误/跳过（unittest报告0.017秒），原54项完整保留，新增4项覆盖上述环境状态。为不延迟最终真实两轮，未额外重复全源封存测试；本次快速结果及实际运行后两文件hash见 `outputs/acceptance/performance-round2-continuation/managed-sqlite-proof/known-read-environment-result.json`，最终统一冻结仍待主任务执行。首次测试编辑的缩进启动错误已单独保留，原测试body/finally与断言恢复后通过。
