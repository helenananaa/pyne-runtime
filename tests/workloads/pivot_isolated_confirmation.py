# ruff: noqa: F821
import pyne_runtime as _nested_batch_runtime
indicator("Isolated pivot", mode="incremental")


def init(ctx):
    for side in ("high", "low"):
        for name in ("left gap", "right gap", "repeated", "descending" if side == "high" else "ascending", "flat"):
            title = "Pivot " + side + " " + name
            getattr(ctx.ta, "pivot" + side)(title, 2, 0 if name == "flat" else 2)


def on_bar(ctx, bar):
    i = ctx.bar_index
    j = i % 8
    lh = [4., None, 3., 2., 1., 0., 0., 0.][j]
    rh = [1., 2., 3., None, 4., 0., 0., 0.][j]
    ties = [1., 2., 3., 3., 2., 1., 0., 0.][j]
    for side in ("high", "low"):
        values = {"left gap": lh, "right gap": rh,
                  "flat": 5. if side == "high" else -5.}
        for name, value in values.items():
            title = "Pivot " + side + " " + name
            scalar = value if side == "high" or value is None else -value
            ctx.plot(title, getattr(ctx.ta, "pivot" + side)(title).update(scalar))
    ctx.plot("Pivot high descending", ctx.ta.pivothigh("Pivot high descending").update(100. - i))
    ctx.plot("Pivot low ascending", ctx.ta.pivotlow("Pivot low ascending").update(float(i)))
    ctx.plot("Pivot high repeated", ctx.ta.pivothigh("Pivot high repeated").update(ties))
    ctx.plot("Pivot low repeated", ctx.ta.pivotlow("Pivot low repeated").update(-ties))
    _native_missing_outputs(ctx,bar)

NATIVE_RECIPE_EXECUTION_ROUTE = "generic_python_full_history_recompute"
_NATIVE_MISSING_OUTPUTS = ['Rising holes', 'Rising native']
_NATIVE_BATCH_SOURCE = '# ruff: noqa: F821\nimport numpy as np\nindicator("Isolated pivot baseline")\ni = np.arange(len(close))\nj = i % 8\nleft_high = np.array([4,np.nan,3,2,1,0,0,0])[j]\nright_high = np.array([1,2,3,np.nan,4,0,0,0])[j]\nties = np.array([1,2,3,3,2,1,0,0])[j]\nwave = np.array([2,1,2,3,4,3,4,5,6,3,2,1],dtype=float)[i % 12]\nholes = np.where(np.isin(i,[5,17,18]),np.nan,wave)\nplot(ta.pivothigh(left_high,2,2),\'Pivot high left gap\')\nplot(ta.pivothigh(right_high,2,2),\'Pivot high right gap\')\nplot(ta.pivotlow(-left_high,2,2),\'Pivot low left gap\')\nplot(ta.pivotlow(-right_high,2,2),\'Pivot low right gap\')\nplot(ta.pivothigh(ties,2,2),\'Pivot high repeated\')\nplot(ta.pivotlow(-ties,2,2),\'Pivot low repeated\')\nplot(ta.pivothigh(100.0-i,2,2),\'Pivot high descending\')\nplot(ta.pivotlow(i.astype(float),2,2),\'Pivot low ascending\')\nplot(ta.pivothigh(np.full(len(close),5.0),2,0),\'Pivot high flat\')\nplot(ta.pivotlow(np.full(len(close),5.0),2,0),\'Pivot low flat\')\nplot(when(ta.rising(wave,3),1.0,0.0),"Rising native")\nplot(when(ta.rising(holes,3),1.0,0.0),"Rising holes")\n'

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
