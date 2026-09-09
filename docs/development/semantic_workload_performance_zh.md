# 完整脚本性能基线

> 后续状态：诊断历史增长已在[请求诊断保留切片](request_diagnostic_retention_zh.md)
> 修复并复测；本页保留修复前基线及当时的结论。

本轮测量独立 Python 包的实际组合负载，不新增运行时能力或宿主适配。
入口：`scripts/semantic_workload_benchmark.py`。

## 方法

- 复用五类第一方验收脚本，增加每 12 根 bar 重复交易的 `strategy_cycles` 对照。
  原策略在第 9 根后空闲，不能代表持续交易成本。循环策略每周期净亏损 5、手续费 3，
  有独立算术检查；没有把这个变体声明为新增 TradingView 捕获。
- 默认历史年龄 64/256/1024 根，各三轮，交替执行顺序；每个场景/轮次独立 Python
  子进程，初始化 16 根后逐根确认推进。固定输出 retention=64、max_bars=256。
- 每个年龄测 32 次确认和 64 次 preview（每根两次不同临时报价），保留全部原始
  毫秒样本、median、nearest-rank p95 和最大值。GC 正常启用，trace 关闭。
- 分别测 local/state/replay 快照生成和恢复，各三次；计时外检查恢复结果及下一根
  确认结果相等，并检查首个被测 preview 不污染已提交输出。
- 记录 portable 编码字节数。local 快照是对象图，不伪造序列化大小；超出 max_bars
  的 replay 明确报告不可用，不能当成零耗时。state 快照继续接受恢复验收。
- 内存在独立的无计时 pass 用 tracemalloc 测量；报告活会话保留的 Python 分配与
  初始化/推进峰值。输入和合成 provider 在 tracing 前创建，不计入这些值。
  这不是 RSS、进程峰值或完整原生内存，也不是内存上限保证。
- request 使用验收中的算术数据公式与稀疏 LTF 规则，扩展到被测时间范围，并仅生成
  查询区间；计时包含此 provider 调用成本，不包含网络、真实行情获取或数据库。
- JSON 保留代码摘要、工作区状态、Python/平台和完整配置。失败保留不完整结果与
  错误；不生成虚假的 PASS，也不把本机绝对耗时升级成跨平台 CI 门槛。

```powershell
.venv\Scripts\python.exe scripts/semantic_workload_benchmark.py --output build/semantic-performance/baseline.json
```

当前阶段先建立证据；运行时优化需要从稳定的热点及其语义回归风险出发。

## 2026-09-08 本机结果

运行时代码为 `62ff49c`，Windows、Python 3.12.7，三个重复共 **54 个独立子进程场景**
全部完成，恢复与延续结果校验全部通过。原始样本及源文件摘要见
[baseline JSON](evidence/semantic_workload_baseline_20260908.json)。
基准脚本和循环策略当时尚未提交，JSON 如实记录工作区状态及它们的内容摘要。

下表是三轮 median 的中位数；箭头表示历史年龄从 64 增至 1024 根，retention 一直为 64。

| 工作负载 | preview ms | 确认 ms | state 恢复 ms | state KiB | 保留 Python KiB |
| --- | --- | --- | --- | --- | --- |
| TA 组合 | 4.34 → 4.05 | 0.204 → 0.180 | 5.48 → 5.20 | 36.3 → 38.0 | 138 → 126 |
| 多周期请求 | 8.74 → 35.11 | 4.09 → 27.54 | 7.70 → 81.34 | 63.0 → 475.7 | 304 → 1900 |
| 状态/缓存 | 5.53 → 4.56 | 0.329 → 0.220 | 6.22 → 5.78 | 37.3 → 38.3 | 141 → 127 |
| 绘图 | 4.59 → 4.81 | 0.345 → 0.359 | 11.90 → 11.92 | 95.1 → 96.8 | 239 → 225 |
| 空闲策略 | 4.41 → 4.25 | 0.230 → 0.202 | 5.93 → 4.72 | 33.5 → 31.9 | 128 → 107 |
| 循环交易 | 4.86 → 4.71 | 0.429 → 0.389 | 6.51 → 6.22 | 43.0 → 43.7 | 146 → 131 |

其他负载在年龄 256 的内存较高，部分原因是仍保存完整 replay 历史；超过 max_bars 后
运行时清空这份历史并禁用 replay，因此不能把 1024 比 256 小误称为随时间自动优化。
state 模式不依赖完整 replay 历史。

主机存在测量波动：request 1024 的三轮确认 median 为 17.76–27.64 ms；应优先看
跨年龄趋势、确定的记录数量和快照字节数。p95 保留于原始数据，是每个短窗口的描述统计，
不能推导生产 SLA。本机单会话 inline 测量不代表多租户并发、宿主进程通信或真实行情性能。

## 已定位的下一项优化

[请求剖析证据](evidence/semantic_request_profile_20260908.json) 在同配置下，分别从
64/1024 根历史开始，对 16 次 preview 和 16 次确认进行 cProfile。剖析带额外开销，
不能用其绝对耗时替换上面的无 tracing 基线。

两种年龄下 `retainedBars` 和实际 request chart bars 都为 **64**，但 request diagnostics
从 **128 增至 2048**，state 快照从 **64530 增至 487105 字节**。对应代码路径：

- `IncrementalContext.record_request_diagnostics()` 持续追加诊断；
- `prune_before_time()` 裁剪图表历史和策略记录，但未裁剪诊断列表；
- `to_result()` 深拷贝完整诊断列表，列表也进入 typed-state 图；
- 剖析同时显示 `deepcopy`、preview 全局扫描与 request context 构建成本较高，
  因而不能把全部耗时增长都归因于单一函数。

下一开发切片应先定义诊断的保留/截断契约，确保当前请求的错误与警告仍可见，再限制
历史诊断增长，并用本基线做同条件前后对照。该变化会影响输出及快照语义，需要遵循
仓库的 semantics version 升级规则。本轮没有修改运行时或悄悄丢弃历史诊断，
也不能据此宣布长期多周期会话已获得稳定资源上限。

## 验证记录

基准工具的四项测试覆盖循环交易独立盈亏、replay 不可用分类、恢复错误不能被计时
掩盖、以及延长的 provider 时间边界。另核对全部 54 个场景无重复、原始样本统计
可重算，且脚本内容摘要与被测版本一致。

首次完整门禁 pytest **1088 passed**，随后既有 `pivot_time_growth` 比值
**3.110 > 3.000**，门禁退出码 1；其他性能项通过。失败日志保留在
`build/semantic-performance/check.log`。本轮未改该路径，原阈值保持不变，
完整门禁按原配置复测；不能把第一次执行描述为通过。

复测 `scripts/check.ps1` 退出码 **0**：1088 项测试、性能/稳定性、58 项既有捕获
对照、wheel/sdist、Twine 和离线隔离安装全部通过；pivot 比值 **2.260 < 3.000**。
日志：`build/semantic-performance/check-rerun.log`。pytest 仍只有既有 session 模块
体积提示。复测没有重现第一次的 pivot 超限；这不等于证明所有主机时序波动的原因。
本轮仅本地交付测量工具与证据，不涉及推送、发布或运行时语义升级。
