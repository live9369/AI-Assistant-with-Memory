# 资格校验元数据按需列读取设计

状态：设计定稿、实现及局部验证通过；等待统一PF06与完整场景复验。只优化内部校验行，不改变任何生命特征／召回／完整输入／业务cap或assembly份额。

共享04在模型调用前因assembly bytes原预留触界拒绝。查明纯登记／资格路径validate_ref反复SELECT e.*，read_artifact反复SELECT * artifacts，但逻辑只使用极少字段。本轮不更改meter计费定义，而是在SQL实际返回必要列后按原meter真实收费。

## 允许投影的两处

1. snapshot Event：仅event_type、payload_artifact_id、payload_hash。原JOIN object_registry的同instance、id、kind='runtime_events'条件，event的同instance/id/source='tl.source.snapshot'过滤全部保留。原修订映射、事件种类、完整快照正文及hash、origin owner／kind／instance、snapshot revision及value digest核验全部不变。
2. 工件元数据：instance_id、id、hash、size、media_type、storage_ref。完整原件仍O_NOFOLLOW读取，实际size／摘要／location一致性仍核验，fresh模式与原meter继续实际计量。

object_registry／object_revision_registry、领域SELECT *、特征采样、授权／ACL／epoch／barrier、read/delete路径和来源关系不变。没有外部参数可请求省略来源列。

## 计算来源捕获的保护

DomainReadCollector.on_row会检查SQLite返回UUID字段；因此只在实际_ACTIVE meter的row_observer为None时使用投影。只要任意非None observer存在（包括真实collector正处busy状态），两处都执行原e.*／artifacts *，完整行交给原observer和meter。无observer的纯元数据校验没有这个计算来源捕获义务，才能减少未使用的元数据列。该选择由实际运行上下文决定，不由调用者提供布尔开关。

## 等价与验收

在同一个新合成数据库上，以安装真实row observer的原全行路径与无observer投影路径，比较相同输入的完整返回值或原异常类型／消息。覆盖valid、event_type、source、JOIN登记kind、payload_hash、origin owner、revision、缺记录、工件位置／size／hash／媒体类型／字节篡改和symlink。高预算条件下功能判定必须一致；资源边界单列验证原件完整读取和原meter计量，不把节省元数据字节伪称减少模型输入。

另在实际DomainReadCollector.installed入口验证原全行查询与返回UUID集合，不能只用一个空observer代替计算来源证明。此前既有完整字段／源绑定和故障回归继续保留。只做局部验证，不运行完整Engine；后续统一PF06后重跑共享与连续场景。


## 实施与局部结果

产品只改ToolLearningStore内的私有列选择辅助及两处SELECT列表；无外部省列参数。新11项projection与既有72项局部回归合计83项通过（22.827秒），随后补齐origin/revision payload映射和invalid-location／原件预算前检后，新projection全部13项通过（2.615秒）。未运行完整Engine。

同一合成数据库、相同known snapshot Ref：投影和原全行路径均接受同一完整Ref，scan/items同为4；原全行计量3583字节，投影2978字节，实际减少605字节内部元数据。原始快照正文完整读取及摘要校验均执行，没有少报已返回列或截短正文。证据：`outputs/acceptance/performance-round2/validation-projection-equivalence-unit.json`。

负例覆盖event_type、source、JOIN注册缺失、payload_hash、revision／owner、快照正文origin/revision映射、缺工件、工件size／hash、损坏字节、symlink、非法位置、命名JSON媒体类型及正文预算前拒绝；同库全行与投影返回同异常类型／消息。真实DomainReadCollector.installed路径仍收到完整event及artifact行，并捕获原event和payload artifact UUID来源；既有readset的六字段identity查询仍可能出现，未将其误称本次漏投影保护。

真实模型、正式实例、stage份额、总cap、meter定义、领域SELECT*和完整高维输入均未变。
