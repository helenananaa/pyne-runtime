# ruff: noqa: F821
import numpy as np
import pyne_runtime.ta as batch_ta
from pyne_runtime.utils import sum_
indicator("oscillator_formula generic Python prefix", mode="incremental")
def init(ctx):
    ctx.plot('Highest', None)
    ctx.plot('Lowest', None)
    ctx.plot('Stoch formula', None)
    ctx.plot('Stoch native', None)
    ctx.plot('Stoch source only', None)
    ctx.plot('Momentum', None)
    ctx.plot('Up', None)
    ctx.plot('Down', None)
    ctx.plot('Up sum', None)
    ctx.plot('Down sum', None)
    ctx.plot('CMO formula', None)
    ctx.plot('CMO native', None)
def on_bar(ctx, bar):
    module = batch_ta.TaModule()
    index = np.arange(ctx.bar_index + 1)
    source = (index * 7) % 13 - 4.0
    holes = np.where(np.isin(index, [1, 7, 8, 12, 23]), np.nan, source)
    hh = module.highest(holes + 1, 3)
    ll = module.lowest(holes - 1, 3)
    momentum = module.change(holes)
    up = np.where(momentum >= 0, momentum, 0.0)
    down = np.where(momentum >= 0, 0.0, -momentum)
    us = sum_(up, 3)
    ds = sum_(down, 3)
    with np.errstate(divide="ignore", invalid="ignore"):
        stoch_formula = 100 * (holes - ll) / (hh - ll)
        cmo_formula = 100 * (us - ds) / (us + ds)
    output = {
        "Highest": hh, "Lowest": ll, "Stoch formula": stoch_formula,
        "Stoch native": module.stoch(holes, holes + 1, holes - 1, 3),
        "Stoch source only": module.stoch(holes, source + 1, source - 1, 3),
        "Momentum": momentum, "Up": up, "Down": down,
        "Up sum": us, "Down sum": ds, "CMO formula": cmo_formula,
        "CMO native": module.cmo(holes, 3),
    }
    for title, values in output.items():
        ctx.plot(title, values[-1])
