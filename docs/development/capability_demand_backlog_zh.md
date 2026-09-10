# Pyne Runtime 能力需求榜

> 本页是 Phase 2 冻结后的选题依据。它不覆盖
> [Current Project Status](../reference/current_status.md) 中的已实现能力，也不把
> Batch-only 名称清单自动升级为实现任务。

## 冻结身份

| 项目 | 值 |
| --- | --- |
| Pine 语料根 | 本机 `Desktop/pine` 目录（104 个 indicator/study 文件，不入库） |
| 文件数 | 104 |
| 字节数 | 1,643,207 |
| 声明 | `indicator` 60，`study` 44 |
| 版本 | Pine v4=20，v5=43，v6=16，未声明=25 |
| 身份摘要 | `02ca3c50ff349fcf4c4adbde787abc9f8d4643bb254086a475b0c6344fc0dc3e` |
| 摘要算法 | 对「文件名 + SHA-256」按文件名排序后的 JSON 做 SHA-256 |
| 审计策略 | `scripts/pine_corpus_audit.py`，不执行、不复制 Pine 源码 |
| 代表性 Pyne 脚本语料 | 仓库内 `examples/*.py`（10 个随包维护的第一方脚本） |

该身份与 [Pine Corpus Compatibility Audit](../reference/pine_corpus_compatibility.md)
记录的 2026-08 快照（104 文件 / 1,643,207 字节）一致。语料更新后必须重新生成
manifest 和本需求榜，不得沿用旧结论。

完整 Pine 逐文件 SHA-256 只保存在本地 `build/capability-completion/`，不提交用户绝对
路径。独立 Runtime 的 Pyne 需求结论以版本控制中的 packaged examples 为准；具体产品
的迁移脚本及采用验收属于其适配仓库。

## 排序规则

稳定字典序，不使用伪精确打分：

1. 是否阻塞已冻结的代表性用户流程；
2. 命中文件数；
3. 是否为 realtime / Incremental 必需；
4. 宿主依赖是否已经准备好；
5. 是否能建立可信外部或确定性证据；
6. 实现风险和后续维护成本。

冻结语料是优先级证据之一，不是新需求的准入名单。独立 CSV、notebook、用户脚本或宿主场景都可提出需求；按真实用例、通用性、确定性验证依据与维护成本评估优先级。小型通用 helper 不要求先冻结完整工作负载。

## 审计结论（相对 Runtime core）

冻结 Pine 语料的 live 分类：

| 桶 | 特征数 | 命中文件 |
| --- | ---: | ---: |
| API analogue available | 356 | 104 |
| Core runtime gap | 0 | 0 |
| Host-owned gap | 10 | 18 |
| Imported Pine-library rewrite | 68 | 9 |
| Required syntax or host-policy rewrite | 8 | 30 |

**没有未解释的 Runtime core gap。** Incremental TA 候选池中，冻结语料只命中
`ta.tsi` 一次（1 个文件）。其余 16 个 Batch-only helper 在该语料中未出现。

已打包的 `examples/*.py` 在 `runtime_mode=incremental` 下 9/10 支持；唯一失败是
`pine_like_semantics.py` 使用 batch-only 的 `strategy.entry_when` /
`strategy.close_when`。这是已声明的 Incremental strategy 边界，不是 TA gap。

外部产品的脚本可以作为通用 Runtime 能力的需求证据；先提取可独立运行的最小 Pyne 用例，再评估是否纳入代表性语料。bridge、workbench 和宿主专用实现仍属于适配仓库；需求来源不改变 Python 语言定位和依赖方向。

## P0

当前没有 Runtime **implement** 的 P0 项。冻结代表性 Pine 语料不被 Batch-only TA
阻塞；已打包 Pyne 示例也不被未实现 Incremental helper 阻塞。

| capability | kind | blocking workload | files touched | modes | owner | evidence plan | risk | decision |
| --- | --- | --- | ---: | --- | --- | --- | --- | --- |
| _(none)_ | — | 冻结 104 文件语料无 core gap；packaged examples 无 Incremental TA blocker | 0 | — | runtime | pine_corpus_audit + pyne inspect examples | — | document |

## P1（外部适配 / 迁移，不进入 Runtime implement）

| capability | kind | blocking workload | files touched | modes | owner | evidence plan | risk | decision |
| --- | --- | --- | ---: | --- | --- | --- | --- | --- |
| `chart.fg_color` / `chart.bg_color` | host | 主题色由图表宿主提供 | 12 / 4 | both | host | host probe；Runtime 保持 fail-closed | host-data | host-first |
| `chart.left_visible_bar_time` / `chart.right_visible_bar_time` | host | 可见范围由图表宿主提供 | 4 / 1 | both | host | host probe | host-data | host-first |
| `request.currency_rate` | request | 1 个 Pine 文件引用；无已批准的数据提供方契约 | 1 | batch | host | 见 Phase 6 启动条件 | host-data | host-first |
| `request.dividends` / `request.splits` / `request.earnings` | request | 各 1 个文件；无宿主数据契约 | 1 | batch | host | 见 Phase 6 启动条件 | host-data | host-first |
| `syminfo.timezone` / `syminfo.volumetype` | host | 元数据已可经 `PyneSettings` 注入；语料中的自动推断仍属宿主 | 1 | both | host | 现有 metadata tests | host-data | document |
| Pine ternary / `:=` / 函数声明 / 循环 | syntax | 92 / 70 / 62 / 50 个文件需 Python 改写 | 92 | batch | runtime | cookbook + inspect 诊断 | lookahead | document |
| `alert(...)` / `alert.freq_*` | host | 17 个文件；信号用 `emit_signal`，调度属宿主 | 17 | both | host | cookbook | host-data | document |
| `array.from` | syntax | 8 个文件；Python 关键字冲突 | 8 | both | runtime | cookbook + validate hint | schema | document |

## Incremental TA 候选池（17 个 Batch-only 名称）

这些名称来自 Batch 已声明、Incremental 未声明的差集。**它们是候选池，不是实现清单。**

| capability | kind | blocking workload | files touched | modes | owner | evidence plan | risk | decision |
| --- | --- | --- | ---: | --- | --- | --- | --- | --- |
| `ctx.ta.tsi` | incremental-ta | `Bjorgum Key Levels` 命中 1 次；无 packaged Incremental 脚本或 realtime 流程证据 | 1 | incremental | runtime | semantic test / TV capture | state | defer |
| `ctx.ta.cmo` | incremental-ta | 冻结语料未命中 | 0 | incremental | runtime | none until workload exists | state | defer |
| `ctx.ta.correlation` | incremental-ta | 冻结语料未命中 | 0 | incremental | runtime | none until workload exists | state | defer |
| `ctx.ta.donchian` | incremental-ta | 冻结语料未命中 | 0 | incremental | runtime | none until workload exists | state | defer |
| `ctx.ta.falling` | incremental-ta | 冻结语料未命中 | 0 | incremental | runtime | none until workload exists | state | defer |
| `ctx.ta.keltner` | incremental-ta | 冻结语料未命中 | 0 | incremental | runtime | none until workload exists | state | defer |
| `ctx.ta.linreg` | incremental-ta | 冻结语料未命中 | 0 | incremental | runtime | none until workload exists | state | defer |
| `ctx.ta.mom` | incremental-ta | 冻结语料未命中 | 0 | incremental | runtime | none until workload exists | state | defer |
| `ctx.ta.nz` | incremental-ta | 冻结语料未命中 | 0 | incremental | runtime | none until workload exists | state | defer |
| `ctx.ta.obv` | incremental-ta | 冻结语料未命中 | 0 | incremental | runtime | none until workload exists | state | defer |
| `ctx.ta.percentile_linear_interpolation` | incremental-ta | 冻结语料未命中 | 0 | incremental | runtime | none until workload exists | state | defer |
| `ctx.ta.percentile_nearest_rank` | incremental-ta | 冻结语料未命中 | 0 | incremental | runtime | none until workload exists | state | defer |
| `ctx.ta.rising` | incremental-ta | 冻结语料未命中 | 0 | incremental | runtime | none until workload exists | state | defer |
| `ctx.ta.roc` | incremental-ta | 冻结语料未命中 | 0 | incremental | runtime | none until workload exists | state | defer |
| `ctx.ta.shift` | incremental-ta | 冻结语料未命中 | 0 | incremental | runtime | none until workload exists | lookahead | defer |
| `ctx.ta.volume_sma` | incremental-ta | 冻结语料未命中 | 0 | incremental | runtime | none until workload exists | state | defer |
| `ctx.ta.wpr` | incremental-ta | 冻结语料未命中 | 0 | incremental | runtime | none until workload exists | state | defer |

`defer` 的含义：Batch 路径保持已支持；Incremental 继续对静态可见调用 fail-closed；
新增 realtime 用例或其他可信需求证据后即可重新评估；实现应附带语义测试，不要求先冻结完整工作负载。

## 外部 Pine library

冻结语料中的未适配成员全部来自第三方或未授权版本，每个 identifier 只命中 1 个文件。
当前只允许已评审的 `TradingView/ta/10` 九个 Batch 成员。未知库继续 fail-closed。

| capability | kind | blocking workload | files touched | modes | owner | evidence plan | risk | decision |
| --- | --- | --- | ---: | --- | --- | --- | --- | --- |
| `TradingView/ta/11#aroon` / `#chandelier` | external-library | 与已 pinned 的 `TradingView/ta/10` 版本不同，禁止静默替换 | 1 | batch | runtime | none；无授权升级 | schema | reject |
| `TradingView/ZigZag/7#*` | external-library | 1 个文件；无 pinned adapter 授权 | 1 | batch | runtime | none | schema | reject |
| `TFlab/*` / `Trendoscope/*` / `Bjorgum/*` / `jdehorty/*` / 其他第三方库 | external-library | 各 1 个文件；版权与实现来源未确认 | 1 | batch | runtime | none | schema | reject |

## Incremental strategy 边界（packaged example）

| capability | kind | blocking workload | files touched | modes | owner | evidence plan | risk | decision |
| --- | --- | --- | ---: | --- | --- | --- | --- | --- |
| `strategy.entry_when` / `strategy.close_when` | strategy | `examples/pine_like_semantics.py` 在 incremental inspect 下 unsupported | 1 | incremental | runtime | 已有 capability contract；Phase 7 启动条件未满足 | schema | document |

Incremental 已支持 `entry` / `close` 等 confirmed-bar API。`*_when` 系列仍是
batch replay 辅助，不因一个演示脚本自动扩展。

## 阶段状态

- **Phase 3**：候选 wheel/sdist 已构建并通过 Twine 与 isolated installed-wheel smoke；产品适配和 lock 不属于本仓库。
- **Phase 4**：完成。无 P0/P1 Incremental TA implement 项；17 个 Batch-only helper 全部 `defer`，Incremental 继续 fail-closed。
- **Phase 5A**：完成（现有 Inspector v2）。目录报告已提供 supported、unsupportedMembers、host、externalLibraries、dynamicAccesses、history hint 与 batch→incremental 迁移；本轮不扩展 schema。
- **Phase 5B**：deferred。第三方/未 pinned 库无授权实现来源。
- **Phase 6**：deferred。`request.currency_rate` / `dividends` / `splits` / `earnings` 各 1 文件命中，但没有已批准的数据提供方契约，core 不得联网。
- **Phase 7**：deferred。无冻结策略缺口；`entry_when` / `close_when` / `order_when` 保持 Incremental 不支持；strategy capture 27/27、0 diff。
- **Phase 8**：deferred。无不可信脚本上传或多实例部署需求；`safe`/`research` 不是多租户沙箱，session 仍为进程内 TTL/LRU。
- **Phase 9**：本地冻结。`check.ps1` 连续两次 881 passed，独立安装 smoke 通过。候选为 **locally accepted**，不是 release-ready（远端 Linux/Windows/macOS CI 未跑，未 push/tag/release）。
- 本仓库的 packaged examples 变化后必须重新跑 `pyne inspect` 并修订本榜；产品迁移语料由适配仓库独立维护。
