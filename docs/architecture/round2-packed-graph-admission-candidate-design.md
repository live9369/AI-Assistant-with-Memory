# 有界纯图材料压缩与首次完成入场候选

2026-11-12，状态：graph-interleave已最小实施，完整流程性能待验。以下候选段落保留设计与原型历史。actual缓存证据中完整图约2.95MB，在4MiB已占用时无法入场；320×3共享图的小端口原两种登记调度均0 graph hits，调度变更没有收益，不产品化。

本候选仅改变纯graph材料的本地表示与性能入场policy，保持原interleaved登记。TL-DEPENDENCY metadata、字段字典、来源原件、Ref/授权判定、JSON验证、业务read_bytes/scan预算均不压缩、不退款、不缓存判决。完整遍历的逻辑row数量在graph命中时仍按原值逐次扣除；每个root/node的当前资格与权限原调用不变。

## 表示与边界

只有本地原_upstream完整成功后生成的encoded JSON可压缩，原UTF8单项长度不得超过原phase.max_bytes(4MiB)。使用低级zlib无损压缩；压缩体加实际NamedTuple/bytes/raw-size整数对象头按sys.getsizeof计算占用，和原key/logical_rows表示一起计入同一4MiB；entry仍一项且总4096不变。若压缩无益则原字符串，若raw超限拒入，不以压缩后小于限额掩盖超大原图。

解码要求精确Packed类型、exact bytes、exact非bool int原长、原长与压缩体均不超过4MiB；解压最大raw_size+1，长度精确相同、eof为真、无unconsumed_tail/unused_data，UTF8严格解码。坏流、截断、尾随数据/第二流、超长、非法UTF8拒绝，不能交给后续资格用作完整材料。每次命中仍返回完整encoded JSON供原json.loads生成fresh结构，不共享可变返回树。原blob哈希与文件探测完全不变。

## 首次完成入场与腾空间

原二次需求策略只是性能policy；候选只在实际可信_check lease、同phase/meter/深度/代次、known managed、无任何observer/callback的本地路径让graph_admitted首次返回True。只允许完整遍历成功且generation未变后入场，不缓存partial/failed遍历。unknown/native/observer/callback/无lease保留原二次需求policy。

入场前预检完整所需key/bytes；只可回收可再读prepared与冷facts，顺序沿现prepared-first、facts原LRU。不能动tracked blobs、其他graph或admission以制造空间。若最大可回收集合仍不足，一项也不删；若足够，先确定完整victim计划，再无callback地移除并插入。总cache+blob始终不超过原4MiB且entry不超过4096。不新增通用LRU/codec框架，不压缩prepared，不改业务行计费。未知环境不回收。

## test-only门槛

先验证codec坏流/限额/拷贝与首次需求、observer/callback回退、victim预检不破坏原状态/不动blobs。然后同真实SQLite备份的320×3共享图×多字段，比较原interleave、interleave+图候选、batch+图候选，完整业务值/显式UUID映射/权限检查及逻辑预算保持，报告actual graph hits、scan/bytes、无profile直接CPU。batch仍仅test-only，不因候选可行顺带上线。只有真实净收益成立才考虑产品实施。

## 首轮实测与口径

test-only三项codec/首次需求保护通过；独立只读审查未发现raw界限、真实头计账、流边界或victim/blob保护缺口。unknown消费者不会启用首次入场/回收；Packed命中也要求当前可信lease，否则miss。此前已有的原字符串图仍按原graph读取规则共享纯材料，可能包括known-first产生但因无压缩收益保留的raw字符串；这不是授权结果复用，原每node资格不减。若产品要求unknown读取时也绝对保持旧二次需求时点，应显式标记first-produced provenance，不能把此时序口径默认为已证明。

320节点×3共享边×4字段，同一真实持久化备份、无profile直接CPU：

| 调度/图策略 | CPU秒 | scan | bytes | graph命中/查询 |
|---|---:|---:|---:|---:|
| 原interleave | 14.494266 | 23462 | 9435117 | 0/16 |
| 原interleave+图候选 | 13.751286 | 23462 | 9435117 | 7/16 |
| batch+图候选（仍仅test-only） | 13.783791 | 23462 | 9435117 | 7/16 |

原interleave+图候选单次CPU约少5.13%，有实际命中，尚不能外推整包。16次真实first eligibility、9次Packed存入、7次Packed命中；完整生成raw图累计34311645B，实际压缩表示累计1023543B（累计不是同时缓存占用），本口无需回收victim。三端真实4个strong input均accepted/committed，fallback0，UUID13次。输入/依赖/metadata/返回顺序精确一致；热CPU口未开逐函数profile，权限精确序列需再以原函数code-object观察的独立正确性口确认，不伪称热CPU口已记录。

证据：`work/packed-graph-schedule-hot-01`及`work/test_packed_graph_candidate.py`。产品未修改；batch没有额外收益，不考虑部署。

补充正确性口已完成：`work/packed-graph-schedule-oracle-01/exact-interleaved-result.json`通过；真实15次Packed命中，原interleave与候选interleave完整原始全局source/version/registration调用入参及顺序、依赖/输入原始行与ID、返回ID与UUID25次全部精确相同，不需要ID归一化。此口使用原函数code-object观察，不替换authority方法身份，故不是fallback伪阳性。profiled时长不用于CPU结论。

## 批准后的最小产品实施

仅原interleave+graph获准实施；batch不合入。新增独立`tool_learning_graph_material.py`，GraphMaterial同时包装压缩与小型未压缩UTF8体，因此首产raw图也有明确provenance，未知lease读取一律miss，关闭前述候选口径细点。实际类型、bool/int、UTF8/流边界和全部对象头均严格检查/计账。

图资格只复用可信本地检查身份/代次的组织标记，**仍执行原完整_sync_monitor/_monitor_stamp及known环境registry刷新**；文件lease专用不刷新观察不被用于graph。remember前若同步发现generation变化，直接放弃旧计算材料，不把它重标成当前图。原每node资格/Ref/权限/epoch/barrier与逻辑row扣除不变。

Store._graph_material_stats三整数含义：eligible=实际可信首次入场policy决策次数（含已有图的本次需求），stored=成功新存GraphMaterial次数，returned=成功完整解码并返回GraphMaterial次数。小raw与压缩均计入，损坏/未知/失败不伪增returned。技术计数不入DB/packet/权限，供Stage真实前后差分。

新增used技术计数只在原_upstream已选中cached图、逻辑row余量足够且扣除原logical_rows后递增；只解码但余量不足、随后走原失败/重遍历不计used。used可包括原raw图命中，因此不必等于GraphMaterial returned，二者不可混称。

产品无profile320×3/4字段对照：14.538636→13.466550秒（单次约7.37%），scan23462/bytes9435117完全一致，真实eligible16/stored9/returned7。原方法身份正确性口raw全局权限/版本/注册序列、原始行/ID/返回与UUID25精确相同，实际returned15。证据`work/product-graph-schedule-{hot-01,oracle-01}`；used是其后仅技术计数补丁，最终回归另核，不用该补丁冒称重新测过CPU。


## 本轮冻结与必要回归

最终新增graph12例（codec、首次完成、fresh树、逻辑不足不used、unknown/raw与compressed、坏流、预检/blob优先、partial、写/rollback/config、callback/observer），配合reader6、diag13、monitor、真实原函数权限oracle及原foreign/事务/故障等，named narrow **199/199通过**，40.760905833秒，0失败/错误/skip，前后.py源一致。full/focused实际loader分别499/295唯一例；本轮不是完整full回归。

结果：`outputs/acceptance/performance-round2-continuation/faults-15-graph-material-delta/result.json`，SHA256 `8ac3bccdfca778b288b76ba16443b120629020f20c7ed111d567ca33905c0ec0`。全部.py冻结，CPU移交联合完整流程actual15；不单独再开长测，不把小端口7.37%外推为整包达标。
