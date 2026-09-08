# SMA／方差／布林带第四批验收

日期：2026-09-07。接续 VWMA 窗口修复，范围为独立运行时的基础统计与组合一致性。

## 修复与证据

上一批 VWMA 已按非缺失观察值窗口计算，但公开 SMA、方差、标准差和 BB 仍要求
最近 period 根 bar 都非缺失。这样 `VWMA` 与公开 `SMA(price*volume)/SMA(volume)`
会出现不同结果。新 Pine v6 捕获确认这些统计函数均采用足量非缺失观察值窗口。

- 最近 period 个非缺失样本齐备后输出；中间缺失保留已建立的窗口结果。
- 前导或全缺失在样本不足时仍缺失；period=1 的样本方差仍缺失。
- BB 的 middle/upper/lower 使用一致的样本集合。
- 增量 `bb` 的 middle/upper/lower 与旧 `boll` 的 upper/middle/lower 顺序均保留。

batch 复用稳健求和及中心化方差内核，在紧缩观察序列上计算后映射回时间轴。
incremental 的 SMA、variance、stdev、BOLL/BB 共享有界窗口和中心化滚动矩；
按周期重设中心，出现严重消减迹象时提前重设，正常流式路径保持均摊 O(1) 更新。

## 明确的 Pine 数值差异

完整 18 行原生日志、Pine 源码和 SHA-256 均保留在 `tests/workloads/rolling_statistics.*`。
有 16 条输出：14 条对照 Pine 数值，**High Stdev、High Variance 两条只作为参考**。

例如非缺失样本 `1e9+1, 1e9+2, 1e9+5`，平移后的总体方差为 `26/9`；Pine 捕获
却为 128，之后若干窗口为 0。这个误差形态符合大数相减造成的消减误差。
原有 Pyne batch 已采用稳定中心化计算，因此保留该数值契约，并修正原增量路径的
不稳定计算。外部 0/128 数值没有被改写，也没有通过放宽公差伪装为相等。

普通数值列按 Pyne 输出协议的 8 位小数比较，同时严格核对时间坐标和缺失点。
两个参考列采用独立中心化 NumPy 算术预期，并在 manifest 中固定其 reference-only
分类。该文件不进入旧 58 个 capture 的零差异统计。

## 验收覆盖

`tests/test_rolling_statistics_external.py` 共 30 项：

| 检查 | 数量 |
| --- | ---: |
| 原始日志、JSON、输入、摘要、数值差异分类 | 1 |
| batch/incremental × 6 个前缀长度 | 12 |
| local/replay/state × 3 个中断点，含 preview 隔离 | 9 |
| 9000 次更新 × 3 个偏移量（0/1e9/1e12）× 2 个周期（3/63） | 6 |
| 公开 SMA 公式复现上一批 VWMA 捕获，两种执行模式 | 2 |

长流式测试独立核对均值、方差、标准差及两种布林带顺序，包含多次窗口滚动与重设
中心；均值/价格带允许一个被测数值量级的 binary64 可表示单位，离散程度独立用
严格的小量级公差验证。既有边界测试还覆盖 infinity 离开窗口后的恢复。

```powershell
.venv\Scripts\python.exe -m pytest tests/test_rolling_statistics_external.py -q
.\scripts\check.ps1
```

## 升级范围

依赖“窗口内任何缺失都输出 na”的脚本会改变结果；增量状态字段也已改变。
升级时从 OHLCV 重建受影响的旧会话，不直接复用旧语义快照。没有新增 public API，
没有改变输出 schema，也没有扩展到宿主代码或宣称所有 Pine 数值行为完全兼容。
未提交、推送或发布版本。

## 完整验证结果

2026-09-07，Windows 仓库 `.venv` 的 `scripts/check.ps1` 退出码 **0**：

| 检查 | 结果 |
| --- | --- |
| 完整 pytest | 1059 passed，含本批 30 项 |
| 既有 Strategy / TA / Request 捕获 | 27 / 10 / 21，均 0 diff、0 runtime error |
| 新统计捕获 | 14 列按 Pine 对照；2 列参考差异按中心化算术验收 |
| 性能及多会话稳定性 smoke | 全部通过 |
| wheel / sdist、Twine、离线隔离安装与包示例 | 通过 |

日志保留在 `build/rolling-statistics/check.log`。pytest 的一个 warning 仍是既存的
`incremental/session.py` 体积提示，本批未改动该模块。
