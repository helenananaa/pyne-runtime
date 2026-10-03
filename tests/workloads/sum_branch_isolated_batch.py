# ruff: noqa: F821
import numpy as np
indicator("sum_branch_isolated batch")
def input_at(i):
    half = 80000000.0 * (10. ** 300)
    return half if i >= 0 else 0.

values = np.asarray([input_at(i) for i in range(len(close))], dtype=np.float64)
plot(ta.sma(values, 2), 'Native2')
plot(math.sum(values, 2), 'Sum2')
