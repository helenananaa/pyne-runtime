# Supertrend／VWMA／OCA 第三批验收

日期：2026-09-07。接续完整脚本与 EMA/RSI 两批工作；范围仍为独立运行时。

## 结论

- **B3 Supertrend**：原生 Pine v6 在捕获的两个 ATR 周期下首根 line 都为 0、
  direction 为 +1。保留已有行为，关闭“首根 0 必然错误”的疑点。
- **B4 VWMA**：修复缺失样本窗口。分子与分母各自保留最近 period 个非缺失样本，
  不把缺失乘积当零，也不强制按相同时间戳配对。
- **C2 OCA**：捕获中市价 `strategy.order` 没有取消或缩减以后触发的同组 pending
  单；批量路径正确。修复增量路径的误取消/减量，并避免 pending OCA 追溯修改
  已经成交的 sibling。原有市价 `strategy.entry` 路径不在本次改动范围。

## 原始证据

使用已授权 Chrome，在 TradingView 的 OKX:BTCUSDT、15 分钟图上运行第一方脚本。
源代码、原始 Pine Logs 与 JSON 摘要均保留在 `tests/workloads/`：

| 文件组 | 来源与范围 |
| --- | --- |
| `trend_volume.*` | 18 根完整 OHLCV；原生 Supertrend(2,3)/(2,1)、ATR3、原生 VWMA；缺失价格与显式自定义成交量公式 |
| `oca_timing.*` | 20 个模拟订单、4 根日志；每个订单的最终未平仓数量以及总仓位、未平仓笔数 |

测试核对 SHA-256（文本按 LF 规范化）、原始日志与 JSON 一致性、完整行号和时间戳。
图表历史 OHLCV 随日志保存，不在测试时联网取数。测试失败不得通过修改外部预期解决。
这些 pytest 捕获独立于原有 58 个 request/strategy/TA capture 的统计。

## VWMA 的精确定义

分子是 `source * volume` 最近 period 个非缺失观察值之和；分母是 volume 最近
period 个非缺失观察值之和。两者都具备足量观察值后才能输出，非正分母仍按既有
契约输出缺失。当前 bar 缺失价格时，分子窗口不推进，但分母可能推进。

原生 `ta.vwma(holes,3)` 与 Pine 显式 `ta.sma(holes*volume,3)/ta.sma(volume,3)`
的捕获一致。自定义 volume 分支验证的是这个显式公式，没有冒充原生 volume 被改写。
因两个窗口可能落在不同时间戳，结果甚至可能超过最近价格的最大值；不能根据直觉
改成“只保留完整价格/成交量配对”的另一种算法。

实现上，batch 紧缩非缺失观察序列后复用稳健滚动求和，再线性映射回时间轴；incremental
维护两个有界队列和滚动和。两种模式均覆盖初始化、价格缺失、成交量缺失、同时缺失、
零权重及 preview/恢复。通用 SMA 的其他缺失值场景不由本切片扩展兼容性承诺。

## OCA 正负对照

提交 bar 的 high=79392.2，下一根 high=79422。测试 stop=79400/79410 均只能在后一根
触发，避免把不成交误判为取消。这些价位为验收场景事先从冻结数据选定，不是策略信号。

| 场景 | Pine 观察 |
| --- | --- |
| 同 tick 市价 cancel/reduce 兄弟单 | 两笔都按原数量成交 |
| pending 在市价单之前或之后提交 | 市价 `order` 不取消或减量它；后一根仍成交 |
| 无 OCA 对照 | pending 确实在后续 bar 触发 |
| 市价单与立即可触发 stop | 捕获中两笔都成交 |
| pending cancel 正对照 | PC1=1，PC2=0 |
| pending reduce 正对照 | PR1=1，PR2 从 3 减为 2 |

最终总仓位 30、未平仓 19 笔。原增量实现少了 CB=2，且把 RB 从 3 错减为 2；修复后
与 batch/Pine 的数量一致。另修复了 PR2 成交后的 OCA 再次修改已经成交 PR1 的生命周期。

比较对象是触发后的数量、订单身份和生命周期，不声称所有盘中成交价格、回调调度或
broker emulator 路径完全一致。Pine 使用收盘处理市价单，最初日志是在该收盘处理前；
因此数量对照从后一根日志开始。Pyne 在对应冻结 bar 上执行，并在该边界以后比较。

## 测试与升级

新增 36 项：趋势/成交量 23 项，OCA 13 项，覆盖两种执行模式的前缀、原始证据身份、
正负对照及 local/replay/state 快照在触发前后恢复，并验证 preview 不污染提交状态。

```powershell
.venv\Scripts\python.exe -m pytest tests/test_trend_volume_external.py tests/test_oca_external_timing.py -q
.\scripts\check.ps1
```

VWMA 状态结构和相关 OCA 输出发生语义改变；升级时从 OHLCV 重建受影响的旧会话，
不直接复用旧语义快照。未提交、推送或发布版本。

## 本轮完整验证

2026-09-07，Windows 仓库 `.venv` 运行 `scripts/check.ps1`，退出码 **0**：

| 检查 | 结果 |
| --- | --- |
| 完整 pytest | 1029 passed，含本批 36 项 |
| 既有 Strategy / TA / Request 捕获 | 27 / 10 / 21，均 0 diff、0 runtime error |
| 性能、多会话稳定性 smoke | 全部通过 |
| wheel / sdist 构建与 Twine | 通过 |
| 离线隔离安装、CLI、schema/能力与示例 | 通过 |

完整日志：`build/trend-volume-oca/check.log`。pytest 的一个 warning 仍为既存的
`incremental/session.py` 体积提示；本批没有改动该模块。
