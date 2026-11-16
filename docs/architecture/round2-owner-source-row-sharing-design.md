# 本地来源完整行材料共享设计

状态：已按本设计实施，小端口11项及统一309项（含六档全8模块差分）通过。原真实连续第二轮须由根协调复验。2026-11-11。

## 问题与已有计量

计算后两个独立材料边界及统一298项已通过，但原17历史真实连续样例第二轮仍在assembly读取字节处拒绝：197062692超过原197062656字节，scan670070低于782577。计算及live阶段已分别降至208487、77667行，不能据此声称第二轮已通过。

`LocalRuntimeOwners.source_access`每次先执行真实`owner.check`，然后`Store.row(kind,id)`返回完整来源行。相同来源在多个字段/依赖路径中被反复读取，调用入口和权限判断都必须保留，但完整行是阶段内可共享的数据库材料。

现有全8模块小端口真实记录4614次source_access、93种kind/id对象；重复最多为state_definitions784次、value_dimensions416次、personality_dimensions395次、identity_instances383次。该记录只能证明重复需求存在，不能直接推定所有可共享或节省字节数：写入仍会清空材料，首次物理读和完整领域来源观察均保留。收益以新旧小端口实际PhysicalReadMeter为准。

## 固定目录及返回契约

- 基础设施层定义严格完整表名白名单，覆盖既有LocalRuntimeOwners支持的snapshot/native/static来源和memory/cognition根；不接受任意调用者表名拼SQL，不导入application。
- 为每个固定表构造独立固定query名，SQL仍`SELECT * FROM table WHERE id=? AND instance_id=?`，参数仍为实际来源id和当前store.instance_id；全部列、完整sqlite.Row及原id/instance谓词保留。
- 仅在`source_access`的来源材料读取处调用新私有owner helper。不存在表目录的种类走原`Store.row`，原未知owner拒绝路径不变。未命中行保持原ContractError类别及含表名的缺失消息。
- 每次返回新的`dict(row)`，不能把可变字典直接缓存或返回给后续消费者。不会裁列或改变source_access返回API。
- memory来源额外读取memory_items以判断state时也走同一固定完整行helper；`Memory.readers`仍每次真实读取ACL，actor/recipient判断继续执行。

## 权限、观察与变化边界

不缓存source_access判断。每次调用首先仍原`owner.check`，完整核对活进程、控制代次、策略、实际principal、用途和接收者；然后使用完整材料逐项执行原memory retention/ACL、perception source actor等谓词。

复用现有PhaseReadSet，无阶段时执行原SQL。技术账户仍4096key/4MiB。物理首读通过原meter真实收费，cache hit仅按现有逻辑行接口通知真实/未知row observer完整行，不假装发生物理读，不创建新的观察抑制边界。未知observer收到的行列和调用顺序与原路径相同。

本连接写入、COMMIT/ROLLBACK、嵌套回滚、外连接/进程提交、控制/原件变化保持现有全失效或拒绝。owner.check已在每次入口进行fresh检查；不跨写保留，不创建可信写集豁免，不提高cap或份额。

## 验证

1. 单来源重复source_access：完整返回值/列和对象独立性一致，source_access、owner.check、Memory.readers及ACL谓词次数不减，实际来源SELECT/返回字节减少。
2. 真实/未知observer分别捕获完整行序列；不同来源id、实例、缺失、未知kind不能串用。修改returned dict不影响后续。
3. 同连接改变memory retention或配置来源actor、ACL撤权、source表内容变化立即重新读/拒绝；外连接提交、控制停止、回滚及文件变化使用原保护并负例验证。
4. 同一全8模块五档小端口、原连续17完整负载验证；全部业务值、fields、live、来源/权限调用、snapshot selector/value/native版本、cap/UUID精确一致。最终由根协调统一故障、连续第二轮及最终冻结3次/增长测试。

本设计只减少来源完整行的重复物理读取，不修改科学特征、授权或输入选择，也不直接宣称197MB边界已解决。

## 已完成的小端口计量

同一合成来源连续访问4次，每次仍真实owner.check。原4次完整来源SELECT/26实际行/3484字节；新1次来源SELECT/23实际行/2143字节，实际节省3行/1341字节。完整返回内容逐字段相同且每次新dict；4次owner.check没有减少。

新增11项2.483秒通过，包含未知observer完整行与完整序列精确对照、返回dict修改、observer重入写后下一次fresh、memory每用ACL与retention、memory policy撤权、同连接写/回滚、外连接旧读事务、控制停止、配置blob修改、固定目录和无phase不缓存。

首次负例给configuration.compatibility写入非JSON，被原schema的json_valid约束拒绝，3个夹具错误记录保留。仅把测试写值改成合法JSON后通过；没有改产品约束或放宽断言。两轮日志将保存在continuation下。

统一复验新增`source_rows_off`档，在全部原边界开启时仅切换完整来源行读法，与新`both`档严格比较全部计算值、field、live、snapshot、来源与权限调用、cap、UUID；不按字段数量冒充内容一致。

## 最终统一结果

309个唯一测试实际全部通过，166.4174375秒，0失败/错误/跳过，207个源输入前后稳定，exit0。新增11项和既有故障/权限/预算保护均保留。全部CPU已退出，产品与工具Python冻结。

六档全8模块真实差分无任何语义差异。只切完整来源行读取方式，两阶段合计实际scan 62458→59734、bytes 17233683→15895693，节省1337990字节；不是裁列或缩短payload。全部来源/权限调用、snapshot selector/value/native版本、完整计算与live字段、cap及UUID精确一致。

证据：`outputs/acceptance/performance-round2/continuation/source-row-six-way-01/`全量六档payload与对照；`source-row-validation-summary.json`；统一`faults-02/result.json` SHA256 `156f7cc8f53f0604ac1a3644e692f376ada504eefda0ff50832efe66d67f2c58`。完整连续第二轮仍未在此结果中验证，不提前代过。
