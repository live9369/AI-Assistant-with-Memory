# 本地组装的依赖登记与输入登记分阶段候选

2026-11-12，状态：可行性与测试原型设计，尚未修改产品。

## 实际问题

actual14第二轮真实签名复用674333次，仍在154个输入时耗尽原时间份额，尚余16字段。继续微调stat没有足够收益。现ToolLearningRuntime.assemble在manifest顺序中逐条执行`register_dependency → 非delete时register_input`。每次dependency登记都写tl_dependency、artifact、registry，合理地使所有材料失效；紧接input登记的严格INSERT证书仅保住这一小段材料，下一字段再次清空。

候选只更改受审本地组装的调度：先按原manifest字段/依赖顺序执行全部register_dependency，并保存与原field digest对应的已登记ID；随后按同一顺序执行原先需要的非delete register_input。不改任何单项函数、事务、授权、来源检查和逻辑遍历；不把依赖登记当成可消费许可。不新增总预算、阶段份额或特征裁剪。

## 必须公开承认的语义变化

这不是全局执行顺序严格等价的纯缓存优化。原序列为D1,I1,D2,I2…；候选为D1,D2…Dk,I1,I2…In。每项D/I自身的begin/commit、原检查次序与数量保留；跨字段D/I顺序改变，UUID分配先后、recorded_at、部分失败留下的技术审计行可能不同。不能把生成UUID差异用不明归一化隐藏，也不能声称全局权限调用序列完全相同。

- 正常完成：按稳定业务键比对每个依赖/输入及immutable metadata含义，输入proof仍按原manifest顺序；UUID总分配次数应相同，但其分配对象会换位。测试另列明确ID双射及原始差异。
- 依赖阶段失败：可能比旧流程多留下已提交依赖、少留下输入；没有完整proof，不能进入模型。
- 输入阶段失败：全部依赖可能已登记，只有输入前缀已提交；仍没有完整proof，不能进入模型。重试沿原幂等检查，不假装组装整体原子化。
- 时间或撤销发生在调度间隙：失败位置与已提交前缀可变；每次输入自身重新核验epoch/barrier/owner/Ref/权限，末尾assembly/retention/qualify与模型前后原边界完整保留，失效材料绝不能变成可消费proof。

## 拟定启用范围与回退

只考虑实际exact ToolLearningRuntime、LocalAssembly、LocalEligibility/_LocalInputEligibility、LocalRuntimeOwners、同Store/owner/authority/artifacts aliases、受管连接known环境、原方法绑定的已封存本地manifest。unknown authority、subclass、实例替换、observer/callback、未知连接/工厂/钩子保持原interleaving。单靠`deduplicate_identical_fields=True`或类名字不足以授权新顺序。方法稳定性与实际别名需要在调度选择时证明；若期间进入未知回调，原单项权限检查仍真实执行，不缓存其结论。

调度选择不得增加隐藏SQL扫描来证明图互不相交。已有来源图若可能经过当前request，提前加入后续dependency会改变某些输入检查可见的图；最终原qualify本来已要求整张图有效，但成功/失败时点可能变化。测试必须覆盖self/cycle与当前request关联；若存在新旧完整完成结果不一致，应收紧为可证明非当前request来源的原本地manifest，或放弃候选，不能忽略此差异。

## 不变边界

assemble入口深拷贝/Ref/Principal/manifest/packet hash校验、prepare assembly/retention、before_assembly_retention qualify、已有proof检查保持位置。所有D/I仍独立事务，原注册身份/版本/scope/metadata/digest/recipient检查保持。delete依赖仍不产生input；其他关系仍按原register_input契约处理，不新增关系强制转换。尾部commit assembly/retention、assembly_complete qualify、proof事件及其来源边、invoke实际入模和结果使用检查保持原样。缓存失效与证书契约不变；只让原已证明强INSERT区域自然延长。

## 最小测试原型及验收

先只在隔离测试调度原型中比较交错与两阶段，不改产品：同一真实SQLite备份、固定时钟和UUID序列，调用原register_dependency/register_input，使用真实共享深图、重复来源、read/delete、多scope与digest。保留原始行/权限序列/UUID；再按显式D/I业务键与生成ID双射比较完整值，检查每项内部权限顺序/数量相同以及总调用数量不减。计量真实scan/bytes/CPU、graph/fact命中、issued/accepted/committed/fallback，不能靠关闭校验取得收益。

然后设计完整assemble级别的失败/幂等/撤销/最终proof/model阻断对照，含未知authority严格旧顺序。只有可解释的调度差异和足够真实收益通过，才申请产品实施与实际完整连续验证；目前不编码产品、不运行新的完整17/2。

## 有界计划与当前request闭包证明（评审补充）

不得仅凭manifest直连sourceID排除当前request。候选需一份调用级、不持久化的完整性说明，由原`before_assembly_retention`真实资格遍历顺带记录：已完整核读的根canonical VersionToken+Scope、实际访问的全部root/upstream对象ID，以及该调用是否完整结束。来源只允许已存在的原遍历结果，不额外查询图、不新增walk、不按UUID/时间戳猜先后。无记录、未知方法/authority、异常、超限或未完整遍历均回旧调度。

调度选择前必须确认每个依赖根（包括delete-only）均被该次实际核读根覆盖。原_qualify跳过delete，因此只有delete根与已核读根完全相同且scope/token相同才可覆盖；未覆盖delete根一律回退，不额外资格查询凑证。若任何已访问ID为当前request，回退交错，包含间接祖先和循环；完整记录必须包含所有关系路径，不因delete不成为content而丢其图身份。说明绑定实际phase/store/meter、manifest/request/principal及调度选择时的generation/transaction/rollback/monitor观察。必须来自同一仍持续的可信阶段；新阶段或不确定变化不得洗白旧说明。说明不是授权缓存，全部D/I及最终资格原调用仍执行。

计划先只读计数manifest依赖，超过4096 descriptors立即选择原调度，不拒绝原可处理输入、不截断字段。待处理结构只保留原field/scope/digest对象引用、依赖下标与已返回ID，不复制高维特征树；至多4096项，并预先按确切容器/tuple/新增ID表示核定有限本地字节界，超界整个调用走旧调度。不能把计划拆成虚拟包绕4096，也不能增加现材料缓存4MiB/4096；计划是有界调用控制状态，不能充当未计量来源缓存。重复dependencyID、旧行幂等命中、重复input返回仍逐条按原调用办理。

科学/冻结设计审阅结论：IM06要求已登记read绑定与每次begin/commit；IM11要求全部成功后才有complete proof，未要求跨字段交错。改变调度必须更新本性能设计的顺序契约和失败审计说明，不得继续引用旧“所有顺序严格相同”的声明。

## 已完成的测试原型与止步条件

`work/probe_local_assembly_registration_schedule.py`只调度原低层登记函数，未修改产品assemble。两份同库SQLite备份使用固定时钟/UUID；原始表、权限事件顺序和生成ID双射均保存，不将跨操作顺序变化隐藏。12节点共享图×8字段的原方法身份sys.setprofile正确性对照通过；按每项D/I业务键保序比较权限、版本、注册检查序列，以及归一生成ID后的依赖/输入/immutable metadata/返回顺序/UUID总数均一致。25次UUID各自分配对象不同的原始差异仍保存。此仅证明普通隔离低层路径，不等于完整LocalAssembly/失败/闭包证明已实现。

- 小图：两调度scan=1988、bytes=634031；graph命中7→14（共32次查询），未减少实际物理读。profiled时长不作CPU收益声明。
- 更贴近受压规模的320节点×3共享边×4字段、无profile直接对照：两调度scan=23462、bytes=9435117；graph命中均0/16次，大图未能入缓存。CPU交错14.460641秒，两阶段14.863816秒，反而约慢2.8%。两端4个input均真实strong accepted/committed，fallback0。真实签名复用38703→42591亦未形成净收益。
- 两份原型业务比较均通过，证据分别在`work/local-assembly-registration-schedule-01`与`work/local-assembly-registration-schedule-hot-01`；原型显式标记不是完整assemble实现。

因此当前不推荐部署此调度变更，也不据此发起新的完整17/2测量。需先有更贴实际字段/来源构成的收益证据，才能值得承担UUID、权限跨字段时序、失败审计与闭包证明的新设计面。产品仍保留原interleaving。

补充：若以后继续，两pass必须保留manifest flatten后的每一出现，不得用depID集合/字典去重。重复read依赖可能返回同DID/IID，原proof.inputs的重复位置和每次检查必须保留。
