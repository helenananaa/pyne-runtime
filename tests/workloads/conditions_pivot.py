# ruff: noqa: F821
import pyne_runtime as _nested_batch_runtime
indicator("Condition pivots", mode="incremental")


def init(ctx):
    for side in ("high", "low"):
        for name, left, right in (("ties", 2, 2), ("holes", 2, 2), ("0 2", 0, 2), ("2 0", 2, 0)):
            getattr(ctx.ta, "pivot" + side)("Pivot " + side + " " + name, left, right)


def on_bar(ctx, bar):
    i = ctx.bar_index
    source = float((i * 7) % 13 - 4)
    holes = None if i in (1, 7, 8, 12, 23) else source
    ties = float((i // 2) % 3)
    for side in ("high", "low"):
        for name, value in (("holes", holes), ("0 2", ties), ("2 0", ties)):
            title = "Pivot " + side + " " + name
            ctx.plot(title, getattr(ctx.ta, "pivot" + side)(title).update(value))
    ctx.plot("Pivot high ties", ctx.ta.pivothigh("Pivot high ties").update(ties))
    ctx.plot("Pivot low ties", ctx.ta.pivotlow("Pivot low ties").update(ties))
    _native_missing_outputs(ctx,bar)

NATIVE_RECIPE_EXECUTION_ROUTE = "generic_python_full_history_recompute"
_NATIVE_MISSING_OUTPUTS = ['Falling 1', 'Falling 3', 'Falling holes', 'Rising 1', 'Rising 3', 'Rising holes']
_NATIVE_BATCH_SOURCE = '# ruff: noqa: F821\nimport numpy as np\nindicator("Conditions pivot baseline")\ni = np.arange(len(close))\nsource = ((i * 7) % 13 - 4).astype(float)\nholes = np.where(np.isin(i, [1,7,8,12,23]), np.nan, source)\nties = ((i // 2) % 3).astype(float)\nplot(when(ta.rising(source,1),1.0,0.0),\'Rising 1\')\nplot(when(ta.falling(source,1),1.0,0.0),\'Falling 1\')\nplot(when(ta.rising(source,3),1.0,0.0),\'Rising 3\')\nplot(when(ta.falling(source,3),1.0,0.0),\'Falling 3\')\nplot(when(ta.rising(holes,3),1.0,0.0),\'Rising holes\')\nplot(when(ta.falling(holes,3),1.0,0.0),\'Falling holes\')\nplot(ta.pivothigh(ties,2,2),\'Pivot high ties\')\nplot(ta.pivotlow(ties,2,2),\'Pivot low ties\')\nplot(ta.pivothigh(holes,2,2),\'Pivot high holes\')\nplot(ta.pivotlow(holes,2,2),\'Pivot low holes\')\nplot(ta.pivothigh(ties,0,2),\'Pivot high 0 2\')\nplot(ta.pivotlow(ties,0,2),\'Pivot low 0 2\')\nplot(ta.pivothigh(ties,2,0),\'Pivot high 2 0\')\nplot(ta.pivotlow(ties,2,0),\'Pivot low 2 0\')\n'

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
