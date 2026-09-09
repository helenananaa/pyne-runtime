# 请求诊断有界保留

基线：`46538e4`。上一轮多周期负载在固定 64 根 retention 下仍累积
128 → 2048 条诊断，typed-state 从约 63 → 476 KiB。

本批将增量诊断限定为当前 bar，进入下一根时丢弃此前条目。当前 bar 的每次请求
诊断仍完整保留，没有增加任意条数门槛；单 bar 调用量仍由原有执行控制负责。
新元数据 `requestDiagnosticsInfo` 披露 scope、barTime、retained、dropped、truncated。
dropped 累计统计先前诊断条目，包含成功请求，不是漏掉的错误数量。

没有请求的 bar 清空旧列表并披露累计截断信息；从未请求的会话不增加元数据。
preview 只继承已提交计数，丢弃先前已确认诊断后产生自身条目，不回写已提交状态。
未处理的 provider 异常行为不变；batch 的完整请求诊断与 opt-in trace 未改变。
宿主需要完整历史时应收集每根确认结果。

这是可观察的输出/状态语义变化，快照语义版本由 1 升为 2。格式和包版本不变；
真实历史 `46538e4` 生成的 replay/state 快照在构造会话前拒绝，旧会话从 OHLCV
重建。相关 fixtures、原始字节摘要与来源位于 `tests/golden/snapshot_semantics_v1`。

## 验收

`tests/test_request_diagnostic_retention.py` 覆盖 512 根持续会话、每根全部诊断、
忽略非法 symbol 的诊断可见性、无请求 bar、反复 preview、三种恢复及下一根延续、
300 次单 bar 请求不截断、batch 不变。既有完整脚本验收继续比较输出与恢复一致性。

性能复测复用原基准脚本与默认配置，只选择 requests：64/256/1024 根历史、
retention=64、max_bars=256、三轮、每轮 32 确认及 64 preview。原始数值和主机波动
仍需区分；Python 分配不是 RSS，provider 的缓存与完整盘中历史不是本批保留保证。

```powershell
.venv\Scripts\python.exe scripts/semantic_workload_benchmark.py --workloads requests --output build/request-diagnostic-retention/after.json
.venv\Scripts\python.exe -m pytest tests/test_request_diagnostic_retention.py tests/test_snapshot_semantics.py -q
.\scripts\check.ps1
```

## 2026-09-08 性能复测

[原始复测数据](evidence/request_diagnostics_after_20260908.json) 的九个独立进程场景
全部完成，恢复结果及下一根确认结果检查通过。以下为三轮 median 的中位数：

| 历史根数 | state 字节数 | state 恢复 ms | 确认 ms | preview ms | 保留 Python KiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| 64 | 37519 | 5.52 | 4.07 | 10.39 | 267 |
| 256 | 38262 | 6.20 | 9.17 | 19.15 | 619 |
| 1024 | 38428 | 7.39 | 8.86 | 26.74 | 1199 |

对比[历史基线](evidence/semantic_workload_baseline_20260908.json)，1024 根时 state
从 487105 字节降至 38428 字节（约 **92.1%**），恢复 median 从 81.34 ms 降至
7.39 ms，确认从 27.54 ms 降至 8.86 ms。快照在三个历史年龄下现在约 37–38 KiB，
仅剩时间坐标与累计计数等少量增长，不再保存全部历史诊断。

这是相同配置、相同基准脚本的历史对照，不是交替运行旧/新版本的配对 A/B。
主机调度波动可影响耗时，不能将全部差异严格归因于本补丁；未调整任何性能阈值。

仍有明确剩余项：请求场景的 Python 保留分配随历史增加，preview 也仍较重。
provider 范围缓存的保留预算独立于 chart retention，已有剖析还显示 preview 全局
扫描和 request context 构建成本。当前证据只关闭诊断列表持续增长问题，不能声称
整个请求运行时达到恒定内存或恒定延迟；后续优化需分别测量这些路径。

## 完整门禁

2026-09-08，Windows / 仓库 `.venv` 的 `scripts/check.ps1` 退出码 **0**：

| 检查 | 结果 |
| --- | --- |
| 完整 pytest | 1103 passed（比上一提交新增 15 个参数化实例） |
| 性能及多会话稳定性 smoke | 通过，阈值未修改 |
| Strategy / TA / Request 捕获 | 27 / 10 / 21，全部 0 diff、0 runtime error |
| wheel/sdist、Twine、离线隔离安装及包示例 | 通过 |

日志：`build/request-diagnostic-retention/check.log`。唯一 pytest warning 仍为既有
session 模块体积提示。本轮仅本地提交，未推送或发布。
