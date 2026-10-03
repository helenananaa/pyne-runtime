# ruff: noqa: F821
import numpy as np
import pyne_runtime.ta as batch_ta
NATIVE_RECIPE_EXECUTION_ROUTE = "generic_python_full_history_recompute"
indicator("percentile_insertion_matrix full-history Python callback", mode="incremental")

def on_bar(ctx,bar):
    history = ctx.state("history", []).value
    history.append(bar.close)
    module = batch_ta.TaModule()
    i = np.arange(len(history))
    source = (i * 7 % 13 - 4).astype(float)
    sources = {'holes': np.where(np.isin(i, [7, 12, 19]), np.nan, source), 'leading': np.where(i < 5, np.nan, source), 'ties': np.where(np.isin(i, [6, 10, 11, 20]), np.nan, (i // 2 % 3).astype(float)), 'alternating': np.where(np.isin(i % 5, [1, 2]), np.nan, np.where(i % 2 == 0, -5.0, 5.0)), 'multiple': np.where((i < 4) | np.isin(i % 6, [0, 1]), np.nan, source), 'empty': np.full(len(history), np.nan)}
    cases = [(name, period) for name in ('holes', 'ties', 'alternating', 'multiple') for period in (1, 2, 3, 4, 7)] + [('leading', 3), ('leading', 4), ('empty', 4)]
    for name, period in cases:
        for pct in (0, 25, 50, 75, 100):
            ctx.plot('Nearest ' + name + ' ' + str(period) + ' ' + str(pct), module.percentile_nearest_rank(sources[name], period, pct)[-1])
            ctx.plot('Linear ' + name + ' ' + str(period) + ' ' + str(pct), module.percentile_linear_interpolation(sources[name], period, pct)[-1])
