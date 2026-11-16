# IM03：工具观察学习 SQL 结构设计

版本 V0.1；状态：隔离实现，不部署。依据冻结 TL-LOOP-0.1 字段与存储附录。

本次提供独立的19表运行增量资源与10表评测资源。运行增量只在全新临时 schema3 数据库验收，不更新 runtime.sql、user_version、迁移器或正式实例。正式迁移和兼容回退留 IM15/IM16。

运行表统一使用 STRICT、实例复合延迟外键、对象注册触发器、闭合枚举、非负计数、摘要和身份格式约束。内容修订登记在 content.id 下，表示修订登记在 series/head.id 下。内容头与表示头的循环关联使用延迟复合外键；历史表示不绑定可变当前头的 expected revision。更新采用 row_revision 加一约束；不可变身份和载荷不得普通改写，删除仅接受同实例 cleaning 请求、purge effect、明确 tl_erasure_target 数据库目标和 erase 屏障同时匹配的逐目标门槛；普通 UPDATE 没有删除例外。真实授权仍由 IM12 核验。

C1 的决定/修订和 C2 的系列/表示允许前向引用；需要跨表比较的触发器仅检查已存在的另一端，并在反向插入补核对。复合外键保证事务提交时对象确实存在。组成员存不可变工件，SQL只能保证组关联、不能读取工件字节判定整组齐备。

评测表命名为 tle_run、tle_case、tle_query、tle_trial、tle_attempt、tle_label、tle_review、tle_fault、tle_usage、tle_metric。它们位于独立数据库，用 run_id 隔离；明确的行关联使用同 run 复合外键。JSON 字段保存冻结命名结构，SQL保证 json_valid 及确定性索引条件；IM02结构校验仍不可省略。

## 应用服务必须保证

SQL存在性不等于权限、真实性、有效证据或可用工件。工件结构/字节/摘要核对、授权范围、真实调用入口、租约时钟、CAS期望值、预算累计、原始deadline不延长、屏障资格、组全量覆盖、允许恢复原因、接纳强度、科学有效测量和两名真实独立评审均由后续模块核验。评测正式启动前材料齐备、查询集合完整、机制/DEV先决条件及累计费用也不是建表即已验证。

body_digest保留冻结的非空正常表示约束；删除覆盖时不写伪摘要墓碑，而由授权计划清除相应表示行及工件并处理引用。完整删除顺序由后续删除模块验证。删除授权记录仅作为既有清理通道的SQL门槛，不自行授予执行权。

## 本轮验收边界

结构测试覆盖双顺序 C1/C2、独立版本登记、头归属、版本唯一、行 CAS、非法状态转换、原始载荷不可变、注册行存在性、来源修订归属、输入清除摘要、评测分区/分配/替代/尝试上限与启动参数冻结。测试不执行思考、工具、网络或正式实例操作。

SQL标量检查不能替代IM02严格JSON加载与命名类型校验：嵌入JSON的Ref还需同run映射、Slot需要完整字段和未知语义校验；Unicode与有限数值等由结构层校验。时间SQL检查使用IS消除NULL放行，完整公历/UTC语义仍由IM02负责。

## 交付与来源

- `digital_life/resources/tool_learning_v1.sql`：冻结存储附录§1—4、§8的19表及注册、版本、关联、状态触发器；不包含版本升级语句。
- `digital_life/resources/tool_learning_evaluation_v1.sql`：冻结存储附录§5、§7的10表、run内分配/引用、分区隔离、预登记参数冻结与用量事件去重。
- `tests/test_tool_learning_schema.py`：真实schema3锁定合成夹具及独立内存评测库；31项验收通过。运行命令：`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_tool_learning_schema -q`。

设计依赖主契约§操作接口/状态机与字段附录，不修改已冻结文本。运行DDL创建两个基表辅助唯一索引以支持预算活动归属和修订来源归属复合FK；不改原表定义或已有行。新修订行自身也外键指向版本登记表，不能单独删除版本登记造成无版本历史。插入方向反例覆盖决定/修订与系列/表示的延迟循环，包含表示先于候选修订、头尚未存在时的拒绝。

tl_effect没有冻结row_revision列；仅其state可独立变化，原work/product/measurement/metric_contract/payload及身份不可变。invalidated不以状态回写恢复为measured；新测量需要新产物与独立报告。SQL仅约束measured具有measurement引用，真实测量质量由IM14核验；状态本身不绕过源屏障或赋予current资格。
