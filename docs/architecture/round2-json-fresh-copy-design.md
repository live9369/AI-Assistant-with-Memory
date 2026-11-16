# 已有deepcopy端口的exact JSON fresh-copy候选

2026-11-12。只优化复制机制，不改变校验、权限调用、缓存或输入格式。

新source真实64×3共享图单登记code-object profile显示deepcopy282080次exclusive1.312秒、dict copier29395次0.366秒，总parent5.633秒含profile开销；旧_check exclusive主要包含未追踪copy，不应当作for-loop。严格同帧json_value micro省18.31%，但真实320×3四模式只省1.86%，单独不足，不据此启动新全程。

候选仅替换eligibility模块原deepcopy名字绑定，global copy及其他模块不变。exact None/bool/int/float/str原immutable identity返回；exact dict/list每次root独立memo，在递归前登记目标，保共享别名、自环与键/元素顺序。dict键必须exact str，在新dict插入前检查。它不是JSON校验，所有原type/finite/Unicode/source/version/authority校验原顺序照旧。

遇任何unknown/subclass/tuple/非str键或深度超过64，fast walk立即抛私有sentinel，不调用其hook/hash/repr/自定义iteration；丢掉仅由builtin组成的部分结果，离开except后对原root调用标准deepcopy一次，不传部分memo。递归错误也回退标准root。tuple外层暂不优化，保留原跨参数alias。正常已验证JSON无自定义回调，省去通用dispatch、key重复复制与primitive memo/atomic函数调用。每次复制仍fresh，不缓存判决或对象。

严格差分覆盖随机JSON、共享别名/cycle、key顺序、immutable identity、str/int/list/dict子类、unknown值与后段fallback副作用只标准一次、unknown key hash/clone、过深root与标准异常、mutating authority隔离。无profile micro与真实热四模式对比CPU、计费、权限/UUID/来源/异常、真strong证书；收益不足不部署，不放宽cap。
