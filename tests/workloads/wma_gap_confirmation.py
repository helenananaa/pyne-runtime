# ruff: noqa: F821
import numpy as np
import pyne_runtime.ta as batch_ta
from pyne_runtime.utils import fixnan
indicator("wma_gap_confirmation generic Python prefix", mode="incremental")
def init(ctx):
    ctx.plot('WMA 3', None)
    ctx.plot('Filled WMA 3', None)
    ctx.plot('WMA 5', None)
    ctx.plot('Filled WMA 5', None)
    ctx.plot('Nested WMA', None)
    ctx.plot('Filled nested WMA', None)
def on_bar(ctx, bar):
    module = batch_ta.TaModule()
    index = np.arange(ctx.bar_index + 1)
    source = (index * 7) % 13 - 4.0
    holes = np.where(np.isin(index, [1, 7, 8, 12, 23]), np.nan, source)
    filled = fixnan(holes)
    w3 = module.wma(holes, 3)
    w5 = module.wma(holes, 5)
    output = {
        "WMA 3": w3,
        "Filled WMA 3": np.where(np.isnan(holes), np.nan, module.wma(filled, 3)),
        "WMA 5": w5,
        "Filled WMA 5": np.where(np.isnan(holes), np.nan, module.wma(filled, 5)),
        "Nested WMA": module.wma(w3, 3),
        "Filled nested WMA": np.where(np.isnan(w3), np.nan, module.wma(fixnan(w3), 3)),
    }
    for title, values in output.items():
        ctx.plot(title, values[-1])
