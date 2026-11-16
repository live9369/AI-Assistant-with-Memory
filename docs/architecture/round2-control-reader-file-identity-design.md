# 控制库文件身份检查合并

将 Store.control_reader 的末级路径软链接检查和随后的身份 stat 合为一次真实 lstat，使用 stat.S_ISLNK 判断末级软链接，再用本次 st_dev/st_ino 继续原连接复用或重开。软链接仍抛原 ContractError；缺失、非目录父组件及权限/循环等 OSError 不被吞掉。真实目录仍交原 SQLite 打开报错，不额外放宽或收紧文件类型。

每次调用都重新 lstat，不缓存授权或停止状态。原 application_id 验证、只读连接参数、LocalRuntimeOwners 检查、assert_execution_allowed 和全部当前停止/process SQL、phase probes 不变。检查后路径替换仍有原有 TOCTOU，不能宣称与 SQLite 打开原子绑定。跨调用 inode 替换仍应关闭旧连接并重开。

验证仅新 TempDir SQLite：正常文件及单次 lstat、各类软链接、缺失/ENOTDIR/权限errno、真实目录失败、inode替换与错误application_id、相同inode每次最新stop/process SQL。还用可控替换边界确认检查前替换被读到，不声称消除检查后竞争。
