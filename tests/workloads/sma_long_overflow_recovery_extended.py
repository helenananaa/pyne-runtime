# ruff: noqa: F821
import numpy as np
from pyne_runtime.ta import TaModule
from pyne_runtime.utils import sum_
indicator("sma_long_overflow_recovery_extended full-prefix callback", mode="incremental")
NATIVE_RECIPE_EXECUTION_ROUTE = "generic_python_full_history_recompute"
SAMPLE_INDICES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 31, 63, 127, 255, 511, 1023, 2047, 3071, 4080, 4081, 4082, 4083, 4084, 4085, 4086, 4087, 4088, 4089, 4090, 4091, 4092, 4093, 4094, 4095, 4096, 4097, 4098, 4099, 4100, 4101, 4102, 4103, 4104, 4105, 4106, 4107, 4108, 4109, 4110, 4111, 4998, 4999, 5000, 5001, 5002, 5003, 8190, 8191, 8192, 8193, 9998, 9999, 10000, 10001, 16382, 16383, 16384, 16385, 24998, 24999, 25000, 25001]

def input_at(i):
    large = 160000000.0 * (10. ** 300)
    return large if i < 6 else float((i * 11) % 17 - 6) * .25

def on_bar(ctx, bar):
    actual_index = SAMPLE_INDICES[ctx.bar_index]
    values = np.asarray([input_at(i) for i in range(actual_index+1)], dtype=np.float64)
    module = TaModule()
    ctx.plot('Native2', module.sma(values, 2)[-1])
    ctx.plot('Sum2', sum_(values, 2)[-1])
    ctx.plot('Native3', module.sma(values, 3)[-1])
    ctx.plot('Sum3', sum_(values, 3)[-1])
