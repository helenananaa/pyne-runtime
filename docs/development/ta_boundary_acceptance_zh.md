# EMA／MACD／RSI 外部语义修复与验收

> 2026-09-09 独立复核：维护者在 Chrome 的新指标中逐字输入本页同一 Pine 源码，
> 编辑器剪贴板回读与文件一致；重新取得的 18 行、15 列与原结构化捕获全部相同，
> 包括缺失位置。新[原始日志](evidence/ema_rsi_reverification_20260909.txt)及
> [比较记录](evidence/ema_rsi_reverification_20260909.json)单独保留，未覆盖旧证据。

日期：2026-09-07。接续第一批完整脚本验收；独立运行时范围，不包含宿主接入。

## 外部证据

在用户授权的 Chrome 中运行两份第一方 Pine v6 脚本，直接读取 TradingView
Pine Logs。第一份 18 根合成 bar 覆盖 12 条输出，第二份 18 根覆盖 2 条组合输出。
输入序列为 `1,4,2,5,3,6,2,4` 循环；leading 分支前 3 个值为 `na`，holes 分支
在索引 1、7、12 为 `na`。价格、时区和真实市场走势不参与计算。

- `tests/workloads/ema_rsi.pine`：三种 EMA、MACD 三元组，以及六种 RSI 输入。
- `tests/workloads/smoothing.pine`：`EMA(RSI(holes))` 和 `TSI(holes,2,3)`。
- 相邻 `.tradingview.txt` 保留原始日志，`.tradingview.json` 保留来源、抓取时间、
  SHA-256、列名和逐行数值。测试验证原始日志与 JSON 一致及行号完整性。

这些证据单独由 pytest 验收，不改变既有 58 个 request/strategy/TA capture 的计数。
旧外部预期没有改写。Pine 日志保留 10 位小数；比较时按 Pyne plot 协议舍入至 8 位，
同时严格比较缺失位置的时间坐标。

## 确认的语义及修复

| 边界 | 原行为 | Pine v6 实测及现在的行为 |
| --- | --- | --- |
| EMA 中间缺失的种子窗 | 第 period 根用不完整样本均值播种 | 收到 period 个非缺失样本才播种 |
| EMA 开头连续缺失 | batch 可能永不恢复；incremental 可能过早播种 | 等到足够非缺失样本，两种模式一致 |
| EMA/MACD 已建立后缺失 | 输出旧值，掩盖缺失位置 | 缺失位置输出 na，内部平滑状态保留 |
| 横盘 RSI | 0 | warmup 后为 100；单边上涨 100，单边下跌 0 |
| RSI 源值缺失及后一根 | 输出旧 RSI | 两个无有效相邻变化量的位置输出 na，Wilder 状态不推进 |

例如 period=3 的 EMA 输入 `1,na,2,5`，外部结果为 `na,na,na,8/3`。
`RSI(holes)` 在索引 7、8 和 12、13 都为 na；下一次有效相邻变化量再更新。
这些规则来自捕获，未采用原审查中“平盘应为 50”等未经证实的推断。

batch 的公开 EMA、MACD signal、TSI 内部平滑复用 `_ema_skip_leading_na`。
该历史函数名保留，但实现现在按非缺失样本计数，使用单次索引扫描及线性递推。
增量 EMA 保留现有状态字段，以相同规则推进。增量 TSI 没有新增。

## 验收

`tests/test_ta_external_boundaries.py` 有 27 项：

- 来源、摘要、原始日志、18 根输入身份一致性；
- batch/incremental × 6 个截断长度，按外部预期检查全部输出和缺失位置；
- local/replay/state × 4 个中断点，覆盖未完成播种、已有输出、刚经历缺失；
- 先做多个 preview，再恢复并继续，确认临时更新没有污染已提交状态；
- 两种模式的 RSI→EMA 组合，以及 batch TSI 的外部对照。

原有两个内部测试随已确认的行为修正：缺失后的 step 返回值预期，以及强制要求
EMA 调用某个滑窗实现的测试。后者改为验证 5000 周期、无连续完整窗口的稀疏输入
仍能正确播种和恢复，不再绑定内部算法选择。

复现：

```powershell
.venv\Scripts\python.exe -m pytest tests/test_ta_external_boundaries.py -q
.\scripts\check.ps1
```

## 升级与剩余工作

这是可观察语义修复。依赖早播种、缺失位置前向填充或横盘 RSI=0 的脚本会改变输出。
采用新代码时，应从 OHLCV 重建受影响的会话；不支持直接复用按旧语义计算的快照。
同一新语义版本内的恢复已通过上述测试。API 名称和输出 schema 未改变。

本轮关闭历史审查 B1/B2；B3 Supertrend、B4 VWMA 和 C2 OCA 时序仍需各自的外部捕获。
未提交、推送或发布版本。

## 本轮结果

2026-09-07，Windows 仓库 `.venv` 的完整 `scripts/check.ps1` 退出码为 **0**：

| 检查 | 结果 |
| --- | --- |
| pytest | 993 passed，含本轮 27 项 |
| 既有 Strategy / TA / Request 捕获 | 27 / 10 / 21，均 0 diff、0 runtime error |
| 新增两份 Pine v6 捕获 | 各 18 根完整原始日志，边界和组合对照通过 |
| 性能与多会话稳定性 smoke | 全部通过 |
| wheel / sdist / Twine | 通过 |
| 离线隔离安装、CLI、schema/能力与包示例 | 通过 |

生成日志保留在 `build/ta-boundaries/check.log`。pytest 的一个 warning 仍是既存的
`incremental/session.py` 模块体积提示，本轮没有改动该模块。
