# ruff: noqa: F821
import numpy as np
from pyne_runtime.utils import sum_
indicator("sma_overflow_discriminator callback", mode="incremental")
NATIVE_RECIPE_EXECUTION_ROUTE = "generic_python_full_history_recompute"

def input_at(i):
    coefficients = (0, -2, 0, 4, -3, 3, 0, 0, None, -2, 0, 4, 2, 3, -3, None, -1, 3, 4, -3, None, -2, -1, -4, 0, -3, -3, None, -3, -1, -2, None)
    small = {8: .25, 15: .25, 20: -.5, 27: -.5, 31: -.5}
    index = i % 32
    return small[index] if index in small else coefficients[index] * (2. ** 1021)

def on_bar(ctx, bar):
    values = np.asarray([input_at(i) for i in range(ctx.bar_index + 1)], dtype=np.float64)
    ctx.plot('Native7', ctx.ta.sma('Native7', 7).update(input_at(ctx.bar_index)))
    ctx.plot('Sum7', sum_(values, 7)[-1])
