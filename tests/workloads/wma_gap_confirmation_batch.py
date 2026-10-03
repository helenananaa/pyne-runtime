# ruff: noqa: F821
import numpy as np
from pyne_runtime.utils import fixnan
indicator("wma_gap_confirmation complete outputs")
index = np.arange(len(close))
source = (index * 7) % 13 - 4.0
holes = np.where(np.isin(index, [1, 7, 8, 12, 23]), np.nan, source)
filled = fixnan(holes)
w3 = ta.wma(holes, 3)
w5 = ta.wma(holes, 5)
output = {
    "WMA 3": w3,
    "Filled WMA 3": np.where(np.isnan(holes), np.nan, ta.wma(filled, 3)),
    "WMA 5": w5,
    "Filled WMA 5": np.where(np.isnan(holes), np.nan, ta.wma(filled, 5)),
    "Nested WMA": ta.wma(w3, 3),
    "Filled nested WMA": np.where(np.isnan(w3), np.nan, ta.wma(fixnan(w3), 3)),
}
for title, values in output.items():
    plot(values, title)
