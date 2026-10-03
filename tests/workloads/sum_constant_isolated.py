# ruff: noqa: F821
import numpy as np
from pyne_runtime.utils import sum_
indicator("sum_constant_isolated callback", mode="incremental")
NATIVE_RECIPE_EXECUTION_ROUTE = "generic_python_full_history_recompute"
def input_at(i):
    half = 80000000.0 * (10. ** 300)
    return half

def on_bar(ctx, bar):
    values = np.asarray([input_at(i) for i in range(ctx.bar_index+1)], dtype=np.float64)
    ctx.plot('Native2', ctx.ta.sma('Native2', 2).update(input_at(ctx.bar_index)))
    ctx.plot('Sum2', sum_(values, 2)[-1])
