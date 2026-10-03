# ruff: noqa: F821
import numpy as np
import pyne_runtime.ta as batch_ta
NATIVE_RECIPE_EXECUTION_ROUTE = "generic_python_full_history_recompute"
indicator("percentile_confirmation full-history Python callback", mode="incremental")

def on_bar(ctx,bar):
    history = ctx.state("history", []).value
    history.append(bar.close)
    module = batch_ta.TaModule()
    i = np.arange(len(history))
    source = (i * 7 % 13 - 4).astype(float)
    holes = np.where(np.isin(i, [7, 12, 19]), np.nan, source)
    for pct in (0, 25, 50, 75, 100):
        ctx.plot('Nearest ' + str(pct), module.percentile_nearest_rank(source, 4, pct)[-1])
        ctx.plot('Linear ' + str(pct), module.percentile_linear_interpolation(source, 4, pct)[-1])
    for pct in (25, 50, 75):
        ctx.plot('Nearest holes ' + str(pct), module.percentile_nearest_rank(holes, 4, pct)[-1])
        ctx.plot('Linear holes ' + str(pct), module.percentile_linear_interpolation(holes, 4, pct)[-1])
