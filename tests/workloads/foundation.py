# ruff: noqa: F821
import pyne_runtime as _nested_batch_runtime
indicator("Foundation scalar boundaries", mode="incremental")


def init(ctx):
    ctx.ta.change("Change 1", 1)
    ctx.ta.change("Change holes 3", 3)
    for title in ("Cum source", "Cum holes", "Cum leading", "Cum empty"):
        ctx.ta.cum(title)
    for method, title in (("cross", "Cross source"), ("cross", "Cross holes"),
                          ("crossunder", "Crossunder source"), ("crossunder", "Crossunder holes"),
                          ("crossover", "Crossover holes")):
        getattr(ctx.ta, method)(title)


def on_bar(ctx, bar):
    i = ctx.bar_index
    source = float((i * 7) % 13 - 4)
    holes = None if i in (1, 7, 8, 12, 23) else source
    leading = None if i < 4 else source
    other = float((i * 3) % 7 - 2)
    other_holes = None if i in (2, 7, 13, 23) else other
    ctx.plot("Change 1", ctx.ta.change("Change 1").update(source))
    ctx.plot("Change holes 3", ctx.ta.change("Change holes 3").update(holes))
    for title, value in (("Cum source", source), ("Cum holes", holes), ("Cum leading", leading)):
        ctx.plot(title, ctx.ta.cum(title).update(value))
    ctx.plot("Cum empty", ctx.ta.cum("Cum empty").update(None))
    for method, title, a, b in (("cross", "Cross source", source, other), ("cross", "Cross holes", holes, other_holes),
                               ("crossunder", "Crossunder source", source, other), ("crossunder", "Crossunder holes", holes, other_holes),
                               ("crossover", "Crossover holes", holes, other_holes)):
        ctx.plot(title, float(getattr(ctx.ta, method)(title).update(a, b)))
    _native_missing_outputs(ctx,bar)

NATIVE_RECIPE_EXECUTION_ROUTE = "generic_python_full_history_recompute"
_NATIVE_MISSING_OUTPUTS = ['Momentum holes 3', 'NZ holes', 'NZ leading', 'ROC 1', 'ROC holes 3', 'ROC zeros 3', 'Shift holes 3', 'Shift leading 2']
_NATIVE_BATCH_SOURCE = '# ruff: noqa: F821\nimport numpy as np\nindicator("Foundation missing boundaries")\ni = np.arange(len(close))\nsource = ((i * 7) % 13 - 4).astype(float)\nholes = np.where(np.isin(i, [1, 7, 8, 12, 23]), np.nan, source)\nleading = np.where(i < 4, np.nan, source)\nempty = np.full(len(close), np.nan)\nother = ((i * 3) % 7 - 2).astype(float)\nother_holes = np.where(np.isin(i, [2, 7, 13, 23]), np.nan, other)\nzeros = np.where(i % 5 == 0, 0., source)\nplot(ta.change(source, 1), "Change 1")\nplot(ta.change(holes, 3), "Change holes 3")\nplot(ta.mom(holes, 3), "Momentum holes 3")\nplot(ta.roc(source, 1), "ROC 1")\nplot(ta.roc(holes, 3), "ROC holes 3")\nplot(ta.roc(zeros, 3), "ROC zeros 3")\nplot(ta.cum(source), "Cum source")\nplot(ta.cum(holes), "Cum holes")\nplot(ta.cum(leading), "Cum leading")\nplot(ta.cum(empty), "Cum empty")\nplot(ta.nz(holes), "NZ holes")\nplot(ta.nz(leading, 7), "NZ leading")\nplot(ta.shift(holes, 3), "Shift holes 3")\nplot(ta.shift(leading, 2), "Shift leading 2")\nplot(when(ta.cross(source, other), 1., 0.), "Cross source")\nplot(when(ta.cross(holes, other_holes), 1., 0.), "Cross holes")\nplot(when(ta.crossunder(source, other), 1., 0.), "Crossunder source")\nplot(when(ta.crossunder(holes, other_holes), 1., 0.), "Crossunder holes")\nplot(when(ta.crossover(holes, other_holes), 1., 0.), "Crossover holes")\n'

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
