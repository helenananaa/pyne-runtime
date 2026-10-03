# ruff: noqa: F821
import numpy as np
import pyne_runtime.ta as batch_ta
NATIVE_RECIPE_EXECUTION_ROUTE = "generic_python_full_history_recompute"
indicator("percentile_history_context full-history Python callback", mode="incremental")

def on_bar(ctx,bar):
    history = ctx.state("history", []).value
    history.append(bar.close)
    module = batch_ta.TaModule()
    i = np.arange(len(history))
    common = np.asarray([3.0, np.nan, -2.0, 7.0, 1.0, np.nan, 5.0, 0.0])[i % 8]
    sources = {'baseline': common, 'ascending': np.where(i < 16, i, common), 'descending': np.where(i < 16, 16 - i, common), 'leading': np.where(i < 16, np.nan, common)}
    for name, source in sources.items():
        for period in (2, 4, 7):
            for percentage in (0, 25, 50, 75, 100):
                ctx.plot('Nearest ' + name + ' ' + str(period) + ' ' + str(percentage), module.percentile_nearest_rank(source, period, percentage)[-1])
                ctx.plot('Linear ' + name + ' ' + str(period) + ' ' + str(percentage), module.percentile_linear_interpolation(source, period, percentage)[-1])
