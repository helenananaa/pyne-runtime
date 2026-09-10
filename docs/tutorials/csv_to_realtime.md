# One script: CSV to realtime

These commands are included in **Pyne Runtime 0.4.0**.
Install the [published wheel](../quickstart.md), then run the commands below.
No CandleScope process, chart, broker, Pandas or data service is required.

## Create and calculate

```bash
pyne new trend.py --template trend
pyne inspect trend.py --runtime-mode incremental
pyne run trend.py --ohlcv bars.csv --param Fast=3 --param Slow=5 --format csv --out result.csv
```

`pyne new` creates a normal editable Python script and refuses to overwrite an
existing file. The three packaged templates are `trend` (two EMAs and direction),
`volatility` (mean and two-standard-deviation bands), and `state` (price changes).
They are first-party examples, not evidence of external user adoption.

By default input is UTF-8 (optional BOM), comma-separated, with Unix timestamps
in seconds and headers `time,open,high,low,close,volume`. For a different schema:

```bash
pyne run trend.py --ohlcv exchange.csv --time-unit ms --column time=timestamp --column open=O --column high=H --column low=L --column close=C --column volume=V --format csv --series "Fast EMA" --series "Slow EMA" --out averages.csv
```

Dates must first be converted to numeric Unix timestamps. Output timestamps
are seconds. `--column time_close=end_ms` optionally maps closing time, using
the same input unit. Unknown/duplicate field mappings fail with a structured
error rather than being silently ignored.

CSV output contains `time` followed by selected plot columns in requested order;
without `--series`, it contains all plotted series. Rows use the union of emitted
timestamps, sorted by time. Warmup/missing values are empty cells; timestamps
with no emitted point in any selected series are absent. Plot names must be
unique and distinct from `time`. Quoted names and commas are handled by CSV quoting.
No interpolation or forward fill is applied. Strategy ledgers, drawings and other
structured objects remain available through the default `--format json` output.

Script failures return exit code 1 and JSON diagnostics on stderr in CSV mode;
input/selection failures return 2. Failed calculations do not overwrite an existing
CSV result. A warmup-only successful result may contain just the CSV header.

## Write the logic once

For logic intended for historical and realtime use, start with an incremental
script. `pn.run()` already detects it and processes supplied history through the
same callback used by a live session. This is historical evaluation of the same
incremental script, not translation into the separate vectorized batch language.

```python
indicator("My EMA", mode="incremental", overlay=True)
length = int(params.get("Length", 20))
if length < 1:
    raise ValueError("Length must be >= 1")

def on_bar(ctx, bar):
    ema = ctx.ta.ema("main", length).update(bar.close)
    ctx.plot("EMA", ema)
```

This uses existing lazy initialization; a separate `init()` is optional. A stable
name identifies each stateful helper. Use different names for independent EMA
streams, keep its parameters fixed for the session, and update each helper once
on every bar, before conditional plotting or decisions. Reusing a name twice in
one bar advances its state twice. Supplying a different period to an existing
helper does not reconfigure it: restart the session when parameters change.

Inside `on_bar`, `bar.close` and TA results are scalar values, so normal Python
`if`, `and`, `or` and ternary expressions work. Check for `None` during warmup.
Keep persistent values in `ctx.state()`; do not use global mutation to hold
indicator state. Preview callbacks run on isolated copies of committed state.

Existing vectorized scripts remain supported: `close[1]`, `when()` and series
boolean operators retain their current meaning. Arbitrary vectorized scripts are
not automatically converted to callbacks. Use `pyne inspect --runtime-mode
incremental` to identify unsupported helpers before choosing this form.

## Use the same file with supplied data

```python
from pathlib import Path
import pyne_runtime as pn

source = Path("trend.py").read_text(encoding="utf-8")
data = pn.read_ohlcv("bars.csv")
params = {"Fast": 3, "Slow": 5}
result = pn.run(source, data, params=params)
if not result.ok:
    raise RuntimeError(f"{result.code}: {result.error}; {result.hint}")
print(result.latest("Fast EMA"))
print(result.get_series("Slow EMA"))
# Optional Pandas: result.to_frame().to_csv("indicators.csv", index=False)
```

For realtime operation the host supplies the bars. It uses the same source and
parameters, with no chart dependency in this code:

```python
session = pn.PyneIncrementalSession(script=source, params=params, retention_bars=1000)
bars = data.to_ohlcv()
session.seed(bars[:-1])
preview = session.on_bar_updated(bars[-1])
if not preview.ok:
    raise RuntimeError(preview.error)
confirmed = session.on_bar_closed(bars[-1])
if not confirmed.ok:
    raise RuntimeError(confirmed.error)
checkpoint = session.snapshot_portable_state()
restored = pn.PyneIncrementalSession.from_portable_snapshot(checkpoint, script=source)
```

Persist checkpoint bytes using your own storage. Send only genuinely new bars
after restore. Restored output retains the configured chart history, while state
continues the full processed history. Retention is not a rolling reset of an EMA.
Historical/live parity assumes the same confirmed input and no dependence on
intrabar-only visits or realtime flags. See [session recovery](session_recovery.md).

## Diagnose a writing mistake

A batch expression such as `if close > open:` operates on a series, not a scalar.
`pyne inspect script.py` reports the migration hint; `pyne validate script.py`
checks script validity and `pyne run` reports execution errors. In a callback,
write `if bar.close > bar.open:`. For a vectorized script, use `when()` or a series
mask instead. Diagnostics are advisory where they cannot statically prove a failure.

Verification for these templates lives in `tests/test_authoring_workflows.py`:
independent EMA/band/state arithmetic, historical evaluation, repeated preview,
rolling retention, typed-state restore before/after warmup, CSV column mapping,
parameter failures and a faulty-to-corrected authoring exercise. The installed
wheel gate also generates, inspects and exports every template outside the checkout.
