# 真实 ADX/DI 脚本迁移验收

本案例迁移用户现有 Pine 语料中的 BeikabuOyaji
[ADX and DI](https://www.tradingview.com/script/VTPMMOrx-ADX-and-DI/)，不是按 API 名称
推测可迁移。原文件有 MPL-2.0 声明；原始本机字节 SHA-256 为
`4bff7f7d020c876fefaee2d3d173b892156af915fc6713caa8974645284d87cc`。

衍生脚本、捕获源和完整 MPL 许可证位于
[tests/migrations/adx_di](../../tests/migrations/adx_di/README.md)。这些文件保留作者与
MPL 声明，不按包的 MIT 许可证重新授权，不放入运行时或 wheel 的 `src` 包。
源码分发若包含这些文件，也必须保留该目录的许可证。

## 用户流程与迁移取舍

1. `naive.py` 保留直接翻译时常见的 Python series 条件错误。`pn.validate()` 给出
   `PYNE_MIGRATION_HINT`，包含位置、原因和替代写法；执行实际失败。
2. `batch.py` 明确逐根计算三个递归和，再以 `ta.sma` 平滑 DX；`incremental.py`
   用 `ctx.state` 和 `ctx.ta.sma` 保留同一递推。它们没有偷换为内置 ADX/DMI。
3. 增量命名空间没有 batch 的 `input/nz/na`。第一版迁移执行因此失败，随后改为
   `params`、显式初始化/缺失值处理，未扩展运行时 API。长度默认 14、阈值默认 20。
4. 增量没有 `hline`，因此阈值用 `Threshold` 常量 plot 表达；保留参考值和参数，
   不声称对象类型或线型与 Pine hline 相同。另有参数 27 的输出验证，避免静默丢失。

直接使用同版本源码中的案例：

```python
from pathlib import Path
import json
import pyne_runtime as pn

case = Path("tests/migrations/adx_di")
capture = json.loads((case / "tradingview.json").read_text(encoding="utf-8"))
bars = [dict(time=row["time"], **dict(zip(capture["ohlcvColumns"], row["ohlcv"])))
        for row in capture["rows"]]
diagnostics = pn.validate(case / "naive.py")
result = pn.run(case / "incremental.py", bars, params={"len": 14, "th": 20},
                executor_mode="inline", timeframe="15")
assert result.ok, result.error
```

这是一项实际脚本迁移验收，不是所有 Pine 脚本的成功率，也不是直接运行 `.pine`。
输入范围是合法非缺失 OHLCV；极端缺失行情和所有参数取值没有外部捕获覆盖。

## 外部证据

2026-09-09 04:34:18 UTC，维护者操作 Chrome，在独立布局
`https://www.tradingview.com/chart/Dah3Glm9/` 运行 `capture.pine`。
源文件从原 v4 脚本做声明/input/math/ta 命名空间的 v5 适配，并增加日志；自定义
递推未替换。此证据比较该 v5 适配源，不额外声称运行了原 v4 源码。

- BINANCE:BTCUSDT，15 分钟，bar_index 0–79：2026-02-01 00:00 至 19:45 UTC。
- 每行同时记录 time、OHLCV、DI+、DI-、ADX；保留原 Pine Logs 文本和结构化数据。
- 第一行 DI+=100、DI-=0、ADX 缺失；ADX 首个有效值位于 index 13，不能丢掉预热
  时间坐标后再比较。所有 80 根来自同一计算起点，不使用后半段数据假装完整 seed。
- 原文保留十位小数；包绘图协议八位小数。比较时将捕获值转为八位，绝对容差 1e-9、
  相对容差 0。未改写标准输出或扩大容差以通过迁移。
- JSON 记录捕获源和原始日志的 LF 规范化摘要，测试核对原文与解析数值逐行一致。
  本机现场截图为 `build/stable-delivery/adx-capture.png`，原始数值证据已入测试目录。

## 验收结果

维护者运行：

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_adx_capture.py tests/test_adx_migration.py
.venv\Scripts\python.exe -m ruff check tests/test_adx_capture.py tests/test_adx_migration.py tests/migrations/adx_di
```

18 passed（2.20s），Ruff 通过。覆盖两模式的 1/14/40/80 根外部前缀、原始证据身份、
24 根滚动保留、逐根两次 preview、预热/稳定阶段 state-v2 恢复与继续、阈值参数，
以及两种长度的独立合成算术对照。合成对照不计为新增 TradingView 捕获。

本轮还发现 Inspector 的能力报告没有暴露 validate 已有的迁移建议。现已复用原检测器，
在 Inspector v2 的 `migration.diagnostics` 添加建议（包括语法失败时可用的迁移提示）。
不改变 `compatibility.supported` 或模式迁移资格；合法标量可能与 series 同名，启发式
建议不是强制拒绝规则。修复后初译稿的 validate/inspect 建议一致且实际执行失败，
两份修正版没有建议且成功匹配捕获。不能把 `compatibility.supported=true` 当作一定可运行。
