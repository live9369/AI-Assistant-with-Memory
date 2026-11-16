# 注册表刷新：同一次完整签名复用分类结果

状态：先设计后微测与最小实现。范围仅监视器及独立基础测试，不改任何应用/readset、预算或检查频次。2026-11-12。

## 已测重复

现实现每次`_refresh_registry`先遍历全局adapter字典，为每个key再与8个原生类型逐一身份比较；紧接着`_registry_signature`又读取同一字典并构建完整(type-id, protocol-id, callable-id)三元组。旧profile记录该刷新有7,457,420次、互斥18.75秒，但不能把微测试收益直接当作完整流程收益。

## 等价变更

- `_registry_signature`的返回格式、adapter和converter全部身份字段与排序完全不变，也不缓存全局注册表。
- 一次刷新仍取得一次完整的adapter+converter签名；从该次已取得的adapter三元组首项，以常驻8个原生类型的id集合做精确成员判断，不再另读字典并构造每key的8类型生成器。
- 初始化也从同一次完整签名设置强opaque历史。每次公开native execute/fetch前后、候选INSERT、增强谓词和monitor_state的刷新调用位置及频次不变。
- 原生adapter一经该完整签名观察到，强opaque仍永久保持；converter注册/移除/替换仍使配置代次变化，不能减少探测字段或忽略参数协议身份。不存在TTL、跨调用签名复用或少一次before/after检查。

## 验证

保存原函数源码与微benchmark原值，旧/新在同一进程对同样完整注册表做重复刷新，交替顺序，记录每次耗时、不宣称全流程达到门槛。新增等价测试覆盖全部8类型/自定义非原生类型/协议身份、完整converter变化、sticky历史及每次刷新完整签名调用一次；原基础50项仍完整复验。

## 实际结果

基础54/54通过，0失败/错误/跳过，两源文件前后稳定。新增4项确认：完整签名每字段和原8类型身份分类一致；每次刷新完整读取adapter与converter各一次且无额外adapter字典扫描；execute前后2次、fetch前后2次、monitor_state一次的刷新频次保持；converter替换和Native opaque历史仍生效。

同进程交替旧/新，每组100000次、各3组，完整注册表为2 adapter / 2 converter，状态未改变：

| 版本 | 第1组秒 | 第2组秒 | 第3组秒 | 中位秒 |
| --- | ---: | ---: | ---: | ---: |
| 原函数 | 0.234206041 | 0.231229625 | 0.231072333 | 0.231229625 |
| 新函数 | 0.148380458 | 0.148122791 | 0.148177417 | 0.148177417 |

该微端口中位减少35.9176%；这不是完整思考耗时，也不能据此把18.75秒profile时间直接减去相同比例。修改前独立实测另保存0.229722542/0.228038041/0.230485959秒，原函数源码和各组原始数据均留证。

证据目录：`outputs/acceptance/performance-round2-continuation/managed-sqlite-proof/`，包括 `registry-refresh-old-source.json`、`registry-refresh-before-micro.json`、`registry-refresh-microbenchmark.json`、`registry-refresh-result.json`。没有改变刷新调用点、丢弃converter字段或减少来源/文件probe。
