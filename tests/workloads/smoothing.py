# ruff: noqa: F821
import pyne_runtime as _nested_batch_runtime
indicator("Smoothing composition", mode="incremental")


def init(ctx):
    ctx.ta.rsi("rsi", 3)
    ctx.ta.ema("ema", 3)


def on_bar(ctx, bar):
    holes = None if ctx.bar_index in (1, 7, 12) else bar.close
    rsi = ctx.ta.rsi("rsi").update(holes)
    ctx.plot("Smoothed RSI", ctx.ta.ema("ema").update(rsi))
    _native_missing_outputs(ctx,bar)

NATIVE_RECIPE_EXECUTION_ROUTE = "generic_python_full_history_recompute"
_NATIVE_MISSING_OUTPUTS = ['TSI']
_NATIVE_BATCH_SOURCE = '# ruff: noqa: F821\nindicator("Smoothing composition")\nholes = when((bar_index == 1) | (bar_index == 7) | (bar_index == 12), na, close)\nplot(ta.ema(ta.rsi(holes, 3), 3), "Smoothed RSI")\nplot(ta.tsi(holes, 2, 3), "TSI")\n'

def _native_missing_outputs(ctx,bar):
    history = ctx.state("_native_batch_ohlcv_history",[]).value
    history.append(dict(time=bar.time,open=bar.open,high=bar.high,low=bar.low,
                        close=bar.close,volume=bar.volume))
    result = _nested_batch_runtime.run(_NATIVE_BATCH_SOURCE,history,executor_mode="inline")
    if not result.ok:
        raise ValueError("Nested batch native recipe failed: "+str(result.error))
    values = {line["name"]:next((p["value"] for p in reversed(line["data"])
                               if p["time"]==bar.time),None) for line in result.lines}
    for title in _NATIVE_MISSING_OUTPUTS:
        ctx.plot(title,values.get(title))
