# ruff: noqa: F821
import numpy as np
import pyne_runtime.ta as batch_ta
NATIVE_RECIPE_EXECUTION_ROUTE = "generic_python_full_history_recompute"
indicator("direction_transition_confirmation full-history Python callback", mode="incremental")

def on_bar(ctx,bar):
    history = ctx.state("history", []).value
    history.append(bar.close)
    module = batch_ta.TaModule()
    i = np.arange(len(history))
    wave = np.array([2, 1, 2, 3, 4, 3, 4, 5, 6, 3, 2, 1], dtype=float)[i % 12]
    sources = {
        "holes": np.where(np.isin(i, [5, 17, 18]), np.nan, wave),
        "empty": np.full(len(history), np.nan),
        "leading": np.where(i < 8, np.nan, wave),
        "alternating": np.where(i % 2 == 0, np.nan, wave),
        "flat": np.where(i % 5 == 2, np.nan, 5.),
        "descending": np.where(np.isin(i % 5, [2, 3]), np.nan, 100. - i),
    }
    for name, period in (("holes", 3), ("empty", 3), ("leading", 3), ("alternating", 3),
                         ("flat", 3), ("descending", 3), ("empty", 1), ("alternating", 1),
                         ("holes", 7), ("leading", 7)):
        ctx.plot("Rising " + name + " " + str(period), float(module.rising(sources[name],period)[-1]))
        ctx.plot("Falling " + name + " " + str(period), float(module.falling(sources[name],period)[-1]))
