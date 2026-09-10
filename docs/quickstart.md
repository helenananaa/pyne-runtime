# Quickstart

Install the published **0.4.0** wheel on Python 3.11–3.13:

```bash
python -m pip install "https://github.com/helenananaa/pyne-runtime/releases/download/v0.4.0/pyne_runtime-0.4.0-py3-none-any.whl"
```

Standalone execution uses full Python in the caller process without default
computation quotas. No development dependencies or source checkout are needed.

Create an editable script from the installed package:

```bash
pyne new trend.py --template trend
pyne inspect trend.py --runtime-mode incremental
pyne run trend.py --ohlcv bars.csv --format csv --out indicators.csv
```

`bars.csv` is your data, with `time,open,high,low,close,volume` columns by default.
This same `trend.py` can run in a realtime session; no second indicator implementation
is needed. Templates `volatility` and `state` cover rolling bands and explicit state.

Run a script from Python:

```python
import pyne_runtime as pn

data = [
    {"time": 1, "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 100},
    {"time": 2, "open": 1.5, "high": 2.5, "low": 1.4, "close": 2.0, "volume": 120},
    {"time": 3, "open": 2.0, "high": 2.4, "low": 1.9, "close": 2.2, "volume": 150},
]

result = pn.run("""
indicator("Close", overlay=True)
plot(close, "Close", color=color.orange)
""", data)

print(result.ok)
print(result.series_names)
print(result.latest("Close"))
```

Run a script from the command line:

```bash
pyne run examples/ma_cross.py --ohlcv examples/sample_ohlcv.csv --out result.json
```

Override script inputs from the command line:

```bash
pyne run examples/ma_cross.py --ohlcv examples/sample_ohlcv.csv --param Length=20
```

Validate a script:

```bash
pyne validate examples/ma_cross.py
```

Inspect package metadata and schema:

```bash
pyne --version
python -m pyne_runtime --version
pyne schema
```
