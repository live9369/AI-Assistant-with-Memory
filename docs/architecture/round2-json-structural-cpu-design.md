# JSON结构校验的纯CPU等价候选

2026-11-12。actual12在字节/scan以内但assembly时间超限，剩18字段。先在当前source的真实64节点×3依赖、一次登记端口用sysprofile按原代码对象计数，不替换validator身份，不装SQLite hook、不改cap。总parent CPU5.637秒含profile开销，json_value371582次、exclusive1.663秒，_check exclusive1.410秒，registry/adapter/refresh合计0.734秒，metadata0.199秒、_run0.160秒。它只定位热点，不是最终计时。

候选1严格同帧：保留每个节点原递归、string/number/active/cycle检查，只对内建exact类型减少重复type/tuple分派，未知类型保留原顺序。候选2在container循环内直接执行primitive的同一个string/number检查，None/bool仍接受，未知/containers仍原递归；没有JSON结果缓存、不跳任何节点、不复用权限判定。深容器达到64层后恢复原primitive递归路径，恶意深树仍按原递归拒绝。正常生命输入及错误类别须精确同，极端外部Python调用栈仅可能改变技术RecursionError触发边缘，不作为JSON业务变化；单列测试和说明。

逐项验证type(bool/int/subclass)、Unicode/surrogate、finite、cycles、共享非循环子容器、非string key、tuple/bytes/set、原_active恢复和RecursionError类别。随机valid/invalid旧新差分，fingerprint仍同canonical JSON/SHA；无profile micro与真实登记比较CPU，所有来源、权限、UUID、计费、异常和strong证书不变。无收益不部署，不把profile包裹时间当性能结论。
