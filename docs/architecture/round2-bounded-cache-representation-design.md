# 同4MiB与4096项内的材料表示和分配

2026-11-12。已选择并实施仅facts-LRU；A/B/C比较保留为研究历史，codec、ordered key与graph优先均未部署。最终保护与同源范围验证进行中。

实际17-10 assembly2（原row_observer=None，SQL分类可用）SQL收费180773976B/665307行：consumer_dependency_materials70595941B/182651行，artifact_location55673807B/192644行，activities27277425B/2272行。phase29达到4096keys和4194304B但reusable仍True；prepared binding峰值981项/3229177B，graph单项最多929593B。prepared byte拒收78420、位置事实byte拒收100853，source_barriers小事实byte拒收149038。图43次byte拒收样本需约2.95—3.04MB。瓶颈已证明是firstcome满后拒收，不是所有材料变更或强证明关闭。

候选A：依赖row cache key的精确有序表示。只对已知完整schema行或内部固定投影行用明确版本/布局tag及按固定列顺序的全部values，省去每key重复字段名。未知/多列/缺列保留旧完整sorted-items形式，所有业务/技术值都参与key；布局tag互不混淆，row身份、scope、原件identity与首次完整核验不变。它不能单独解决4096项上限。

候选B：仅本地prepared/graph已序列化纯材料用UTF8无损压缩，绝不压缩SQL返回行或退还实际输入/逻辑预算。压缩门槛与最小节省明确，按实际存储bytes加固定codec元数据和原有完整key/scope记账，逐条仍算一个entry，不合并记录绕keycap。原编码/解码API返回相同完整新字符串/JSON树；单条原始长度不超过原max_bytes，解压用显式输出上限且要求完整eof/无尾数据，坏压缩、长度错、无效UTF8 fail closed。所有原文件、schema、变化失效与observer/callback保护保持。

实际失败保存的320份metadata，原compact UTF8共828950B；zlib level1为243685B（29.40%），编码CPU0.00406秒、解码0.00112秒，逐字节完全相同。此只表明表示可缩，不是整流程提速；要在真实小登记图及受压fixture比较CPU/收费/强证明/来源。

候选C：同bound内替换可再生材料，不改tracked blobs。只在原本要因key/byte拒收时考虑：小固定facts可淘汰部分prepared/admission；已经出现第二次需求的纯graph可按现LIFO淘汰部分prepared以容纳，单项和blob合计不可能容纳或淘汰全部允许victim仍不够时，事先拒收、不先破坏热cache。不同entry逐项删除，原尺寸逐项扣除，绝不提高4096/4MiB或打包虚拟记录。单一小图不能证明优先级适合全包。

先test-only比较A、B和C的最简单版本。受压fixture用真实持久化metadata完整核验后预热，加真实负registry事实达到相同4MiB/4096（不抬上限）；热登记仍真实register_dependency→register_input，核对权限/UUID/输出/异常/逻辑遍历预算，记录命中、拒收、物理SQL/字节、CPU与缓存上限。禁止用任意未核验“许可”填充。根据结果仅落地最简单有效方案，不同时合并无收益策略。

诊断旁路修正：原17-10 calc在SQL row observer内重入artifact/produced时存在分类混记，assembly无observer可用。新工具显式material_stack优先，6个小测试通过，其中嵌套SQL3B、artifact5B、produced7B总15B与原meter一致；不为此重跑全诊断。

## 最终选择：仅facts的最小LRU替换

受压端口04在真实64个热artifact节点、每节点3条依赖、1000份真实核验冷metadata与真实negative registry事实填充下，原4MiB/4096不变。baseline strong scan14724/B7428692；仅facts-LRU scan7368/B5513876，减少49.96%行、25.78%字节。整四模式CPU单次17.257→16.105秒。组合ordered/压缩/graph-priority/LRU收费仍7368/5513876、CPU16.182秒，没有额外实际收费收益，因此不部署codec、ordered key或graph优先，候选及坏流5项仅留研究证据。

case11首次产品只改facts替换：实际managed/known read environment、匹配meter/current phase、无任何observer/callback时，exact或complete-prefix命中将对应完整facts entry移到最近使用端，返回原immutable rows与原generation/iterator检查。新facts原本因keys/bytes拒收时，先算全部可回收facts/prepared是否足以满足同一原限额；不够则不删任何热项，仍拒收。最初可容纳时先删最冷facts、耗尽后才回收prepared；后续真实整包证明这一victim顺序仍让prepared长期挤占空间，最终已改为prepared先让位，见后节。graph/admission不回收，tracked blobs永远不回收，单条太大不先破坏旧cache。每次删除按原fact_sizes/prepared_sizes准确扣减，再按原size记新项。没有虚拟entry打包，也不提升4096或4MiB。

file tracking仍原先保证优先入场：admission→prepared→graph→facts；到facts阶段在已知环境采用最冷事实，未知环境保留原逻辑。未知/native/observer/callback不进行新的LRU回收或触碰。DB、文件、control、epoch、rollback、generation、Ref与权限memo失效规则、逻辑遍历预算完全不变。LRU只替换可重读数据，不缓存判决。

压力入口使用原同库业务差分helper，但其原两条“strong总比legacy省”的性能断言只在此专用入口改为记录实际值，原产品test未更改；baseline受压时该假设恰好为false，证据保留。所有业务/source/authority/UUID/异常assertEqual不变。不能从小端口直接推断整包或最终三次计时达标。

最终产品受压四模式复验同样得到strong scan7368/B5513876，权限、UUID、来源与异常精确一致；总key峰4096、表示bytes峰4191243，均不超原限额。8个LRU保护及7个诊断小测试共15项通过，3.089秒。产品只进入facts-LRU；codec坏流等5项仅测试原型，不引入产品。

## 已知未扩大的边界

bounded consume在积累真实行时仍以原self.bytes+blob_bytes+pending_size判断是否继续retain，空间满时可能在remember前放弃缓存，所以本轮LRU不保证消除所有consumer_dependency_materials重复读。它仍返回每一条原始消费行，不预读更多、不把partial记complete、不改变逻辑budget。若完整实测仍证明必要，下一步再研究受guard的pending reservation与冷fact回收，不能偷偷扩大cache+pending总表示。本轮冻结后明确不改此处，先以actual11验证最小变更是否足够。

诊断工具另修正显式material_stack优先于外层SQL charge，以及inline LRU接受新项后的namespace reconcile；实际phase总key/bytes高水位始终来自产品，不受namespace旧统计偏差影响。原17-10 assembly无observer可用于本结论，calc细分类别可能混记，未据此推导优化收益，也不为此重跑全诊断。

## 最终必要范围门槛

冻结全部Python后，focused249/249通过，0失败/错误/跳过，84.280338792秒，source_stable=true。覆盖原差分、预算、authority、foreign/rollback/observer、Native/Managed全上下文及新LRU/诊断保护。证据faults-11-cache-replacement-focused/result.json，SHA256 add6b6eedbad58e34a767afc4bfaee32fa1dd8d7ace355da81101adfa6057fd0。全部Python保持冻结，CPU移交actual11；完整named453、最终三次计时/增长尚未因此宣称完成。

## case11实证后的最终victim顺序

case11仍在第二轮assembly字节超限，剩23字段；首次facts-first使prepared长期保有约3.23MB，hot facts互换，小端口04不代表真实热working set。新端口移除冷filler/人为negative填充，用真实320个artifact节点、每节点3条依赖的960份热metadata反复遍历、真实1字段登记，四模式业务/source/authority/UUID/异常仍精确一致。

只交换remember的victim顺序后，strong scan20697→10438（减少49.57%），字节8952375→5588128（减少37.58%）；权限2268、UUID6、graph lookup7/hit0、真实strong1不变。单次strong elapsed8165→7998ms，整四模式CPU34.762→34.462秒，仅作观察。证据prepared-first-real-graph-01，baseline强比legacy更贵的记录完整保留，原产品test未覆盖或放宽。

最终策略仅在原预检已确认可容纳时，先逐项回收可再核验prepared末项，再回收最冷facts。没有跨namespace新索引，没有codec/ordered key/graph优先，没有pending/reservation新状态；所有旧guard、原限额、file优先及bounded producer边界不变。新增hotfact不被prepared挤占保护后，替换9+诊断7+真实接入12共28项通过，13.559870542秒，source_stable=true。源审计相对249范围恰为readset顺序交换、新test、runner计数三文件。

证据faults-12-prepared-first-delta/result.json，SHA256 f5d0c0543c07120248668c67576b9ea1da22575ed523bc3b153f00cb34cd153c。全部Python再次冻结，CPU移交actual12；当前named454/focused250，只做28项delta，未称新全量完成。真实第二轮与最终三次计时/增长仍需主任务完成。
