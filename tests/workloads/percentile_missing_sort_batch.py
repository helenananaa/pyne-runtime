# ruff: noqa: F821
import numpy as np
indicator("Percentile missing sort diagnostic")
i = np.arange(len(close))
source = ((i * 7) % 13 - 4).astype(float)
sources = {
    "holes": np.where(np.isin(i, [7, 12, 19]), np.nan, source),
    "leading": np.where(i < 5, np.nan, source),
    "empty": np.full(len(close), np.nan),
}
cases = [(name, 4) for name in sources] + [("holes", 1), ("holes", 2)]
for name, period in cases:
    percentages = (0, 25, 50, 75, 100) if period == 4 else (50,)
    for pct in percentages:
        plot(ta.percentile_nearest_rank(sources[name], period, pct),
             "Nearest " + name + " " + str(period) + " " + str(pct))
        plot(ta.percentile_linear_interpolation(sources[name], period, pct),
             "Linear " + name + " " + str(period) + " " + str(pct))
