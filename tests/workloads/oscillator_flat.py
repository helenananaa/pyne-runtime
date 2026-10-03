# ruff: noqa: F821
import pyne_runtime as _nested_batch_runtime
import numpy as np
import pyne_runtime.ta as batch_ta

indicator("Oscillator boundaries", mode="incremental")
NATIVE_RECIPE_EXECUTION_ROUTE = "generic_python_full_history_recompute"


def init(ctx):
    ctx.ta.cci("CCI holes", 3)
    ctx.ta.cci("CCI flat", 3)
    ctx.ta.stoch("Stoch flat", 3)
    ctx.ta.stoch("Stoch holes", 3)


def on_bar(ctx, bar):
    history = ctx.state("correlation_history", []).value
    history.append(bar.close)
    i = ctx.bar_index
    source = float((i * 7) % 13 - 4)
    holes = None if i in (1, 7, 8, 12, 23) else source
    ctx.plot("CCI holes", ctx.ta.cci("CCI holes").update(holes))
    ctx.plot("CCI flat", ctx.ta.cci("CCI flat").update(5.0))
    ctx.plot("Stoch flat", ctx.ta.stoch("Stoch flat").update(5.0, 5.0, 5.0))
    ctx.plot("Stoch holes", ctx.ta.stoch("Stoch holes").update(
        holes, None if holes is None else holes + 1, None if holes is None else holes - 1,
    ))
    index = np.arange(len(history))
    values = ((index * 7) % 13 - 4.).astype(float)
    missing = np.where(np.isin(index, [1, 7, 8, 12, 23]), np.nan, values)
    module = batch_ta.TaModule()
    ctx.plot("Correlation holes", float(module.correlation(missing, values, 3)[-1]))
    ctx.plot("Correlation flat", float(module.correlation(np.full(len(history), 5.), values, 3)[-1]))
    _native_missing_outputs(ctx,bar)
_NATIVE_MISSING_OUTPUTS = ['CMO flat', 'CMO holes']
_NATIVE_BATCH_SOURCE = '# ruff: noqa: F821\nindicator("Oscillator boundaries")\nsource = (bar_index * 7) % 13 - 4.0\nholes = when(\n    (bar_index == 1) | (bar_index == 7) | (bar_index == 8)\n    | (bar_index == 12) | (bar_index == 23), na, source,\n)\nflat = source * 0 + 5.0\nplot(ta.cmo(holes, 3), "CMO holes")\nplot(ta.cmo(flat, 3), "CMO flat")\nplot(ta.cci(holes, 3), "CCI holes")\nplot(ta.cci(flat, 3), "CCI flat")\nplot(ta.stoch(flat, flat, flat, 3), "Stoch flat")\nplot(ta.stoch(holes, holes + 1, holes - 1, 3), "Stoch holes")\nplot(ta.correlation(holes, source, 3), "Correlation holes")\nplot(ta.correlation(flat, source, 3), "Correlation flat")\n'

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
