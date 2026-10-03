# ruff: noqa: F821
import numpy as np
indicator("oscillator_formula complete outputs")
index = np.arange(len(close))
source = (index * 7) % 13 - 4.0
holes = np.where(np.isin(index, [1, 7, 8, 12, 23]), np.nan, source)
hh = ta.highest(holes + 1, 3)
ll = ta.lowest(holes - 1, 3)
momentum = ta.change(holes)
up = np.where(momentum >= 0, momentum, 0.0)
down = np.where(momentum >= 0, 0.0, -momentum)
us = math.sum(up, 3)
ds = math.sum(down, 3)
with np.errstate(divide="ignore", invalid="ignore"):
    stoch_formula = 100 * (holes - ll) / (hh - ll)
    cmo_formula = 100 * (us - ds) / (us + ds)
output = {
    "Highest": hh, "Lowest": ll, "Stoch formula": stoch_formula,
    "Stoch native": ta.stoch(holes, holes + 1, holes - 1, 3),
    "Stoch source only": ta.stoch(holes, source + 1, source - 1, 3),
    "Momentum": momentum, "Up": up, "Down": down,
    "Up sum": us, "Down sum": ds, "CMO formula": cmo_formula,
    "CMO native": ta.cmo(holes, 3),
}
for title, values in output.items():
    plot(values, title)
