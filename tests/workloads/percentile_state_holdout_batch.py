# ruff: noqa: F821
import numpy as np

indicator("Percentile state independent holdout")
i = np.arange(len(close))
base = ((i*i*17+i*31+7)%23-11).astype(float)*.25
sources = {
    "holes": np.where(np.isin(i%11, (2, 3, 4)), np.nan, base),
    "ties": np.where(np.isin(i%17, (7, 8)), np.nan, (i//3)%5-2).astype(float),
    "leading": np.where((i<13)|((i>=45)&(i<58)), np.nan, base),
    "empty": np.full(len(close), np.nan),
}
for name, source in sources.items():
    for period in (5, 9, 17):
        for percentage in (0, 12.5, 33, 50, 67, 87.5, 100):
            suffix = f"{name} {period} {percentage:g}"
            plot(ta.percentile_nearest_rank(source, period, percentage), "Nearest "+suffix)
            plot(ta.percentile_linear_interpolation(source, period, percentage), "Linear "+suffix)
