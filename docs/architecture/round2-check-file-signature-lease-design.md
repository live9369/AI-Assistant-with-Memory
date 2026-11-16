# 同一可信只读检查内的已追踪文件签名复用

2026-11-12，先设计后实现。实际sampling13 assembly2为11717样本：lstat约39.17%，track_location祖先约24.44%，_probe祖先仅4.68%。JSON/copy小候选不产品化。本次只去掉同一已界定_check内对入口已经追踪文件的重复stat，不缓存资格或授权。

原_check入口full checkpoint完整检查DB/control/ALL tracked files后才mint lease；只允许实际exact LocalEligibility/LocalRuntimeOwners、实际同Store/owner/eligibility/artifact aliases、原函数绑定及RuntimeIdentity。方法稳定性仅mint审定一次，不在每条track扫描。unknown/subclass/实例方法替换不mint；每个nested_check都安装自己lease或None，finally恢复。

lease绑定phase identity、当前线程、check_depth、generation、txgen、rollbackgen、managed配置/schema/write sequence，以及入口已追踪path集合。每次track轻检查实际meter/phase/source/owner别名、无任何observer/callback、相同depth/代次，窄observed_material_revision只读取已观察的configuration/schema/write/closed四元组（不发SQL/不刷新全局registry；mint仍完整known环境检查，所有SQL/facts/cached_artifact与原检查起终仍保留原registry刷新）。无SQLite调用时，全局adapter注册自身不能改变此已追踪path；后续任意SQLite调用及出口仍观察并失效。此观察不得用于Ref/metadata/facts/权限/写证书。。只有入口已追踪且当前仍在blobs的path可以跳过track_location内lstat。新path仍每次真实stat，原open/no-follow/size/hash/media/JSON流程不变。fresh=True显式旁路，仍真实stat与hash。standalone/native/unknown/callback走原stat。

_check正常返回前的原full checkpoint不变，_probe永远直接调用真实_signature，不用lease。外部中途改文件/foreign DB/control变化必须在返回qualified前被出口真实probe拒绝；没有允许动作的中途回调，未知回调不进入该优化。已存权限/Ref/graph/generation/写证明和commit/model前后阶段probe完全不变。任何同连接write、rollback、配置/模式变化、clear、关闭即不再匹配lease；不跨未知write解释变化。

威胁范围沿现受管公开API：任意Python恶意替换私有授权函数或同进程破坏模块对象不在安全模型。实际可配置authority/owner替换在mint回退，native callback内每use仍原stat；控制与原件更改仍真实全边界核验。

验证：入口/出口实际stat计数不减，新path/fresh/unknown/nested/callback逐次stat，文件中途变化（含已有body缓存）/foreign/zero-row写/rollback/config失效，返回异常/代次恢复；再做原oracle精确差分与无profile直接真实热图计数/CPU。原oracle若用未知方法包装会保守回退，必须单列真实fast路径stat下降，不能用fallback冒称成功。不增加budget/cache上限，不改变LLM上下文或模型调用。

## 候选实测与当前结论

原方法身份不替换的四模式登记差分使用sys.setprofile仅记录实际source_access/verify_version/verify_registration入参，所有业务行、来源metadata、权限调用序列、UUID、预算、异常逐项一致，并断言strong模式确有签名复用命中。无profile的320节点×3共享边真实持久化登记端口，baseline与候选同样mint；baseline仅关闭私有签名短路。

- 每次登记原_signature次数27870→20130，实际复用7740次；scan=7820、bytes=4811487完全一致，普通/strong证书各1且fallback0。
- 保留registry刷新的轻stamp，交替三对CPU中位4.236958→4.241843秒，无净收益。
- 仅此file-lease使用不刷新的observed_material_revision，交替三对4.283222→4.265629秒，约0.41%，属于噪声级，不能宣称性能目标已达成。
- 最终原方法权限差分与12项入口/出口、file/foreign、配置/zero-write/rollback、unknown/subclass/nested/fresh/callback/copied-context保护合计13例通过，6.938秒。早期失败是未保证可达metadata或WAL设置污染受管配置的测试夹具，原失败日志保留。

证据：`outputs/acceptance/performance-round2-continuation/check-file-signature-candidate/`。此阶段只证明实际stat减少和正确性，尚未建立完整流程CPU收益；不以本地小图百分比推断整包，不触发新的完整连续测量。

### 已验证location的最前短路候选

旧候选仍在每次64hex逐字符检查及Path连接之后才复用stat。下一窄候选在mint时一次建立入口已追踪path的location→原Path映射；track入口只对exact str、相同可信lease与此精确集合成员启用，集合成员自身已经证明格式，不重复格式扫描/Path连接。新location、未知类型、fresh、未知环境仍完整原流程。映射值仍须在blobs中，generation/线程/depth/配置连续性不变；_probe真实stat不变。仅新增Store内存minted/hits技术整数，不影响packet/DB/权限/预算。

最前location短路实测交替三对CPU中位4.258779→4.196521秒，约1.46%；真实7740次复用、scan/bytes/业务精确不变。13项保护/原权限函数差分通过。此增益仍远低于完整流程所需余量，不能据此宣布整体达标。

## 本轮冻结门槛

最终最窄实施采用入口validated-location最前短路、仅file lease读取observed_material_revision；所有原SQL/facts/资格入口出口的registry刷新保留。Store._file_signature_stats仅实际minted/hits，独立诊断Stage按原值可选采集，不加每次调用包装。新增早期location反例证明非法格式、str子类、未在入口追踪的新原件仍走原完整检查。

`faults-14-file-signatures-delta`：179/179通过，38.099847291秒，0失败/错误/skip，测试前后源一致。范围含monitor61、file13、certified13（含原函数身份fastpath权限差分）、architecture、readset、owned事务及foreign/rollback故障、诊断11。现full/focused runner loader分别479/275唯一例；本轮未重复整full，也未将179误称完整回归。

结果SHA256：`b3fb8fdd636448497925058dd7808d4d9bbfdd2e3b273b844625708dbbaaeb9e`。CPU已移交完整隔离流程，以实际规模结果决定去留；不将1.46%小端口外推为整体达标。
