# ruff: noqa: F821
import numpy as np
import pyne_runtime.ta as batch_ta
NATIVE_RECIPE_EXECUTION_ROUTE = "generic_python_full_history_recompute"
indicator("percentile_missing_sort full-history Python callback", mode="incremental")

def on_bar(ctx,bar):
    history = ctx.state("history", []).value
    history.append(bar.close)
    module = batch_ta.TaModule()
    i = np.arange(len(history))
    source = (i * 7 % 13 - 4).astype(float)
    sources = {'holes': np.where(np.isin(i, [7, 12, 19]), np.nan, source), 'leading': np.where(i < 5, np.nan, source), 'empty': np.full(len(history), np.nan)}
    cases = [(name, 4) for name in sources] + [('holes', 1), ('holes', 2)]
    for name, period in cases:
        percentages = (0, 25, 50, 75, 100) if period == 4 else (50,)
        for pct in percentages:
            ctx.plot('Nearest ' + name + ' ' + str(period) + ' ' + str(pct), module.percentile_nearest_rank(sources[name], period, pct)[-1])
            ctx.plot('Linear ' + name + ' ' + str(period) + ' ' + str(pct), module.percentile_linear_interpolation(sources[name], period, pct)[-1])
