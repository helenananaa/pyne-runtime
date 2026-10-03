# ruff: noqa: F821
import numpy as np
indicator("Percentile confirmation diagnostic")
i = np.arange(len(close))
source = ((i * 7) % 13 - 4).astype(float)
holes = np.where(np.isin(i, [7, 12, 19]), np.nan, source)
for pct in (0, 25, 50, 75, 100):
    plot(ta.percentile_nearest_rank(source, 4, pct), "Nearest " + str(pct))
    plot(ta.percentile_linear_interpolation(source, 4, pct), "Linear " + str(pct))
for pct in (25, 50, 75):
    plot(ta.percentile_nearest_rank(holes, 4, pct), "Nearest holes " + str(pct))
    plot(ta.percentile_linear_interpolation(holes, 4, pct), "Linear holes " + str(pct))
