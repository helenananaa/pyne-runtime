# 请求缓存索引与 preview 遍历优化

基线：`41033bb`，快照语义版本 2。

## 实现边界

1. `_RangeCachingProvider` 为每个 symbol/timeframe 建立排序的时间索引。
   缓存查询从扫描全部 N 条历史改为二分定位并读取区间内 K 条，查找成本
   为 O(log N + K)。自然向后追加仅追加索引；乱序补充排序合并，覆盖区间、
   缓存预算、淘汰、空结果与 provider 访问规则不变。淘汰同时删除行、索引和覆盖。
   新批次先完成时间戳解析与复制，再发布缓存，避免失败留下未索引的部分数据。
2. `_preview_copy_memo` 不再进入精确类型 `IncrementalRequestModule` 的内部图。
   这个运行时对象已有 `__deepcopy__` 返回自身的共享协议，扫描其内部 provider/cache
   不产生复制效果。优化只适用于该精确类型，用户子类没有此捷径；单独暴露的用户
   可变别名仍按原规则复制，未扩大宿主能力或削弱用户状态隔离。

这不改变指标输出、诊断保留契约或可移植状态结构，因此语义版本保持 2。
请求缓存容量预算仍独立于 chart retention；本轮没有缩短缓存以伪造稳定内存。
请求区间本身包含更多数据时，K 仍会增加，不能把索引等同于所有请求恒定耗时。

## 验收方法

新增八项测试检查乱序/重叠/倒序区间、包含端点、空范围缓存、淘汰后重取、重复
时间戳最后值优先、返回值修改不污染缓存、用户别名隔离、精确类型边界，以及
provider 坏数据后继续使用时索引与数据一致，以及小区间读取/追加不枚举旧缓存。
既有完整脚本验收继续运行。

`scripts/compare_request_performance.py` 复用既有基准脚本，分别在独立进程中加载
旧/新源码并断言实际 import 路径；每轮交替执行先后顺序，三个历史年龄各重复三次。
配置保持 history=64/256/1024、retention=64、max_bars=256、32 confirmed/64 preview。
在计时和 tracemalloc 之外计算每个结果的完整输出/元数据摘要，逐对要求旧新一致。
原始样本、内容摘要与失败记录保留在 JSON，不新增绝对耗时门禁。

```powershell
# baseline-src 指向从 git archive 41033bb src 提取的独立源码目录。
.venv\Scripts\python.exe scripts/compare_request_performance.py --baseline-src build/request-index/baseline/src --output build/request-index/paired.json
.venv\Scripts\python.exe -m pytest tests/test_incremental_request_index.py -q
.\scripts\check.ps1
```

## 2026-09-08 配对结果

[完整原始证据](evidence/request_index_paired_20260908.json) 包含九对、18 个独立进程
测量。每对的输出与元数据摘要一致，恢复与延续验收也均通过。

| 历史根数 | preview median ms（旧 → 新） | preview 配对比 | 确认配对比 | 保留 Python KiB（旧 → 新） |
| --- | --- | ---: | ---: | --- |
| 64 | 9.30 → 8.26 | 0.914 | 1.045 | 267.0 → 269.0 |
| 256 | 15.35 → 11.64 | 0.758 | 1.012 | 619.7 → 622.5 |
| 1024 | 29.63 → 13.03 | 0.440 | 0.858 | 1200.9 → 1216.0 |

绝对耗时列是三轮 median 的中位数；配对比是逐对 after/before 后取中位数，
所以不能用绝对列相除替代配对比。1024 根时 preview 约降低 **56.0%**。
确认路径没有呈现稳定的大幅收益；仍需 materialize 的请求区间和 context 构建
占用成本。本机时间有调度波动，三对短窗口样本不构成生产延迟保证。

索引额外消耗内存，1024 根时约增加 **15 KiB** Python 保留分配。总体缓存仍可随
历史增长直至既有预算，因此这是一项查找/preview 优化，不是恒定内存证明。

[跨版本恢复证据](evidence/request_index_snapshot_compat_20260908.json) 使用真正的
旧源码 `41033bb` 生成 64 根 request 工作负载的两种 portable 快照，再由新版恢复。
恢复结果与下一根确认输出均与旧版相同；没有修改快照版本或重写旧预期。
语义版本继续保持 **2**。

## 完整门禁

最终代码的 `scripts/check.ps1` 退出码 **0**：**1111 passed**（新增八项测试），
性能/稳定性 smoke、Strategy/TA/Request 的 27/10/21 项捕获对照、wheel/sdist、
Twine、离线隔离安装与示例均通过。日志为 `build/request-index/check-final.log`。
pytest 唯一 warning 仍为既有 session 模块体积提示。

原始配对报告中的旧/新源码摘要及比较器摘要均已和最终文件核对。仅本地提交，
未推送、发布，也不宣称新的生产容量或内存上限。
