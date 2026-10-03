# ruff: noqa: F821
import numpy as np
from pyne_runtime.utils import sum_
indicator("sma_near_edge_discriminator callback", mode="incremental")
NATIVE_RECIPE_EXECUTION_ROUTE = "generic_python_full_history_recompute"

def inputs(i):
    unit = 2. ** 1021
    ulp = 2. ** 969
    vocabulary = (0., ulp, -ulp, unit, -unit, unit - ulp, unit + ulp,
                  -unit + ulp, -unit - ulp, 2. * unit, -2. * unit,
                  4. * unit - 4. * ulp, -4. * unit + 4. * ulp)
    codes = ((2, 6, 6, 10, 9, 7, 5, 2, 6, 9, 5, 9, 4, 4, 8, 0, 0, 2, 9, 1, 4, 5, 12, 8, 6, 2, 11, 6, 6, 5, 4, 1), (11, 3, 3, 1, 0, 6, 7, 11, 6, 0, 6, 2, 9, 0, 5, 7, 1, 7, 9, 10, 3, 12, 4, 6, 11, 8, 10, 6, 7, 6, 7, 11), (5, 8, 9, 4, 7, 12, 2, 5, 4, 2, 4, 9, 11, 9, 9, 11, 9, 4, 6, 5, 4, 2, 10, 12, 0, 6, 4, 7, 3, 9, 11, 12), (11, 6, 3, 3, 0, 5, 9, 10, 1, 12, 8, 2, 10, 10, 12, 12, 10, 8, 10, 1, 11, 7, 10, 9, 6, 8, 3, 8, 6, 11, 12, 11))
    return {f'case{n}': vocabulary[row[i % 32]] for n, row in enumerate(codes)}

def on_bar(ctx, bar):
    for n, period in enumerate((7, 7, 3, 3)):
        name = f'case{n}'
        values = np.asarray([inputs(i)[name] for i in range(ctx.bar_index + 1)], dtype=np.float64)
        ctx.plot('Native ' + name, ctx.ta.sma('Native ' + name, period).update(inputs(ctx.bar_index)[name]))
        ctx.plot('Sum ' + name, sum_(values, period)[-1])
