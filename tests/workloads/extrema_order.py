# ruff: noqa: F821
import pyne_runtime as _nested_batch_runtime
indicator("Extrema boundaries", mode="incremental")

def init(ctx):
    ctx.ta.highest('Highest holes', 3)
    ctx.ta.lowest('Lowest holes', 3)
    ctx.ta.highestbars('Highestbars holes', 3)
    ctx.ta.lowestbars('Lowestbars holes', 3)
    ctx.ta.highest('Highest ties', 3)
    ctx.ta.lowest('Lowest ties', 3)
    ctx.ta.highestbars('Highestbars ties', 3)
    ctx.ta.lowestbars('Lowestbars ties', 3)
    ctx.ta.highest('Highest leading', 3)
    ctx.ta.lowest('Lowest leading', 3)

def on_bar(ctx, bar):
    i = ctx.bar_index
    source = float((i * 7) % 13 - 4)
    holes = None if i in (1, 7, 8, 12) or 23 <= i <= 27 else source
    ties = float((i // 2) % 3)
    leading = None if i < 5 else source
    ctx.plot('Highest holes', ctx.ta.highest('Highest holes').update(holes))
    ctx.plot('Lowest holes', ctx.ta.lowest('Lowest holes').update(holes))
    ctx.plot('Highestbars holes', ctx.ta.highestbars('Highestbars holes').update(holes))
    ctx.plot('Lowestbars holes', ctx.ta.lowestbars('Lowestbars holes').update(holes))
    ctx.plot('Highest ties', ctx.ta.highest('Highest ties').update(ties))
    ctx.plot('Lowest ties', ctx.ta.lowest('Lowest ties').update(ties))
    ctx.plot('Highestbars ties', ctx.ta.highestbars('Highestbars ties').update(ties))
    ctx.plot('Lowestbars ties', ctx.ta.lowestbars('Lowestbars ties').update(ties))
    ctx.plot('Highest leading', ctx.ta.highest('Highest leading').update(leading))
    ctx.plot('Lowest leading', ctx.ta.lowest('Lowest leading').update(leading))
    _native_missing_outputs(ctx,bar)

NATIVE_RECIPE_EXECUTION_ROUTE = "generic_python_full_history_recompute"
_NATIVE_MISSING_OUTPUTS = ['Linear holes', 'Linreg holes', 'Nearest holes']
_NATIVE_BATCH_SOURCE = '# ruff: noqa: F821\nimport numpy as np\nindicator("Extrema boundaries batch")\ni = np.arange(len(close))\nsource = ((i * 7) % 13 - 4).astype(float)\nholes = np.where(np.isin(i, [1, 7, 8, 12]) | ((i >= 23) & (i <= 27)), np.nan, source)\nties = ((i // 2) % 3).astype(float)\nleading = np.where(i < 5, np.nan, source)\nplot(highest(holes, 3), \'Highest holes\')\nplot(lowest(holes, 3), \'Lowest holes\')\nplot(highestbars(holes, 3), \'Highestbars holes\')\nplot(lowestbars(holes, 3), \'Lowestbars holes\')\nplot(highest(ties, 3), \'Highest ties\')\nplot(lowest(ties, 3), \'Lowest ties\')\nplot(highestbars(ties, 3), \'Highestbars ties\')\nplot(lowestbars(ties, 3), \'Lowestbars ties\')\nplot(highest(leading, 3), \'Highest leading\')\nplot(lowest(leading, 3), \'Lowest leading\')\nplot(ta.linreg(holes, 3, 0), "Linreg holes")\nplot(ta.percentile_nearest_rank(holes, 3, 50), "Nearest holes")\nplot(ta.percentile_linear_interpolation(holes, 3, 50), "Linear holes")\n'

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
