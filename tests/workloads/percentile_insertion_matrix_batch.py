# ruff: noqa: F821
import numpy as np
indicator("Percentile insertion matrix diagnostic")
i = np.arange(len(close))
source = ((i * 7) % 13 - 4).astype(float)
sources = {
    "holes": np.where(np.isin(i, [7, 12, 19]), np.nan, source),
    "leading": np.where(i < 5, np.nan, source),
    "ties": np.where(np.isin(i, [6, 10, 11, 20]), np.nan, (i // 2 % 3).astype(float)),
    "alternating": np.where(np.isin(i % 5, [1, 2]), np.nan, np.where(i % 2 == 0, -5., 5.)),
    "multiple": np.where((i < 4) | np.isin(i % 6, [0, 1]), np.nan, source),
    "empty": np.full(len(close), np.nan),
}
cases = [(name, period) for name in ("holes", "ties", "alternating", "multiple")
         for period in (1, 2, 3, 4, 7)] + [("leading", 3), ("leading", 4), ("empty", 4)]
for name, period in cases:
    for pct in (0, 25, 50, 75, 100):
        plot(ta.percentile_nearest_rank(sources[name], period, pct),
             "Nearest " + name + " " + str(period) + " " + str(pct))
        plot(ta.percentile_linear_interpolation(sources[name], period, pct),
             "Linear " + name + " " + str(period) + " " + str(pct))
