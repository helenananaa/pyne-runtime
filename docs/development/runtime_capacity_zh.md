# 独立运行时长时间会话容量测量

本工具测量 standalone `pyne-runtime` 在持续 preview/确认下的资源与正确性窗口，不新增运行时能力，也不给出绝对性能门槛或优化结论。

入口：`scripts/runtime_capacity.py`。

## 方法

- 复用 `scripts/semantic_workload_benchmark.py` 的 bar 公式与 `Provider`（导入该脚本的辅助函数），工作负载为第一方 `requests`、`strategy_cycles`、`ta_chain`。没有用空转或 idle 脚本替换真实组合语义。
- 一次子进程内按 round-robin **顺序**推进多个会话，会话工作负载按上述三者循环分配。这是单进程顺序推进，**不是**并行 CPU 吞吐。
- 每个 `--sessions` 取值是一个独立 case，父进程拉起全新子进程，避免上一 case 的 RSS 残留。
- 默认确认 4096 根、每根 4 次 preview、每 256 根一个窗口；`retention=64`、`max_bars=256`。`--cache-bars` 默认 2048，写入 `PyneSettings.max_output_points`（请求 range cache 的 `max_cached_bars` 与输出点预算共用该字段）。若 `retention * 32` 更大，则上调输出预算以免绘图/策略点先被打满；报告同时记录请求值与实际 `appliedMaxOutputPoints`。
- 输入 bar 按序号即时生成，不保留增长中的 OHLCV 数组。原始 preview/确认耗时在计时结束后写入 JSONL；内存中只保留**当前窗口**样本。RSS 在窗口内、事件计时之外、typed-state 编码之前采样。
- 当前 RSS：Windows 为 `GetProcessMemoryInfo` 的 `WorkingSetSize`；Linux 为 `/proc/self/statm` 常驻页 × 页大小。其他平台明确 `unsupported`。**不会**把 `ru_maxrss` 标成当前 RSS。进程 RSS 包含 Python、harness、provider 与会话；报告同时给出创建会话前的 harness 基线。不是 tracemalloc。
- 窗口检查 typed-state（`snapshot_portable(mode="state")`）字节与编码/恢复耗时；恢复后的已提交输出与独立 clone 的下一根确认延续相对照，**不推进被测会话**，也不把当前运行时重算当作外部 oracle。
- 请求 cache 通过 `IncrementalRequestModule.cache_stats` 的私有探测读取（仅测量用，见下）。只在观察到缓存 bar 下降且 fetches 增加时记录 eviction；不会因为设置了 `--cache-bars` 就声称发生了淘汰。
- 循环策略的完整周期盈亏按既有基准测试的独立算术：每 12 根 net −5、commission 3，不把当前运行时回放当 oracle。持仓按 `bar_index % 12` 的已知生命周期检查，用于证明不是空转策略。
- 有限墙钟：`--timeout-seconds`（worker 循环）与 `--process-timeout-seconds`（父进程杀子进程）。循环上界为 `--bars`，没有无限循环。中断时 `completed=false`，已完成窗口留在 JSON 里。

```powershell
H:\program\pyne-runtime\.venv\Scripts\python.exe scripts/runtime_capacity.py `
  --sessions 1 4 8 --bars 4096 --previews-per-bar 4 --sample-every 256 `
  --retention 64 --max-bars 256 --cache-bars 2048 `
  --output build/runtime-capacity/qualification.json
```

本地冒烟（本页交付时执行）：

```powershell
H:\program\pyne-runtime\.venv\Scripts\python.exe scripts/runtime_capacity.py `
  --sessions 3 --bars 48 --previews-per-bar 2 --sample-every 24 `
  --output build/runtime-capacity/smoke.json
```

长时资格跑由维护者执行；本工具不把本机耗时升级成 CI 门槛。

## 声明的不变量

每个窗口、每个会话单独记录 `passed`，不把“全部通过”写成笼统 PASS：

| 名称 | 含义 |
| --- | --- |
| `confirmed_prefix_retention` | `retainedBars == min(retention, totalCommittedBars)`，时间窗口边界符合保留配置，且每窗口首个实际提交的旧绘图点重叠部分值不变 |
| `preview_isolation` | 每窗口首根实际计时 bar 的 preview 不改变已提交输出；不额外喂入 preview 预热缓存 |
| `typed_state_restore_committed` | 恢复会话的已提交 lines/output/retention 与被测会话一致。比较排除 `trace`：harness 关闭 `trace_enabled` |
| `typed_state_continuation_clone_vs_control` | typed-state 恢复体的下一根确认输出，对照随后被测原会话的真实确认；末尾另做一根非计时探针 |
| `measured_subject_not_advanced` | 检查后被测会话 committed 输出未变 |
| `retained_bars_bounded` | 保留根数不超过 retention |
| `request_cache_stats_observed` | 读到 `series/bars/coveredRanges/fetches` |
| `strategy_cycle_arithmetic` | 仅 `strategy_cycles` 且 `committedBars % 12 == 0`：net/commission/equity 符合已知周期算术 |
| `strategy_active_position` | 仅 `strategy_cycles`：持仓符合该周期的开/减/平，非零区间证明在交易 |

请求 cache 的私有路径：`session._globals["request"].cache_stats()`，对应 `IncrementalRequestModule.cache_stats`。脚本侧 `cache_stats()` 是公开的 session cache 统计，一并记录。二者都只用于测量。

## 输出

- 主 JSON：`schema=pyne.runtime-capacity/1`，Python/平台/CPU、git HEAD/status、harness/workload/runtime 摘要、完整 CLI、每个 case 的窗口。
- 每 case 另有 `*.s{N}.json` 与 `*.s{N}.events.jsonl`。JSONL 一行一个 preview 或 confirmed 事件（`utc/session/workload/barIndex/kind/ms`）。
- 子进程非零退出或超时：父报告 `completed=false`，写入 `failure`，并保留已落盘的部分窗口。

## 冒烟与测试

`tests/test_runtime_capacity.py` 覆盖：Windows 上当前 RSS 为正且来源为 WorkingSetSize；非法参数拒绝；父进程记录部分失败并保留窗口；短 worker 的 JSON/JSONL 完整性。

本轮不修改运行时、既有夹具、依赖或版本，也不提交。

## 维护者审核修正

原稿的续算对照使用同一 typed-state payload 恢复两次，无法发现恢复特有缺陷；现改为
恢复体与尚未恢复的被测会话下一次真实确认对照，末窗口追加一根非计时确认。比较续算
时排除 request diagnostics（冷恢复与已热缓存的诊断不同）；已提交恢复检查仍比较它们。
每个窗口的续算检查在下一次实际提交前标为 pending，不能当作已通过。

原稿窗口摘要保留 samplesMs，会使测量自身的原始数组增长；现仅保留汇总统计，逐事件
原始样本只写 JSONL。窗口报告仍占少量随窗口数增长的内存，RSS 包含该开销，不声称为
纯 runtime RSS。测试注入“只在恢复对象下一步改变数值”的故障，确认续算验收能失败。

维护者复跑：5 tests passed、Ruff passed；3 会话/96 根/每根2次 preview 的 review-smoke
完成。证据 build/runtime-capacity/review-smoke.json；这是工具冒烟，长测尚未验收。
