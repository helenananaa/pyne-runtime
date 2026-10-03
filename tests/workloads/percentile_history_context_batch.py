# ruff: noqa: F821
import numpy as np
indicator("Percentile history diagnostic")
i = np.arange(len(close))
common = np.asarray([3., np.nan, -2., 7., 1., np.nan, 5., 0.])[i%8]
sources = {"baseline": common, "ascending": np.where(i<16, i, common),
           "descending": np.where(i<16, 16-i, common),
           "leading": np.where(i<16, np.nan, common)}
for name, source in sources.items():
    for period in (2, 4, 7):
        for percentage in (0, 25, 50, 75, 100):
            plot(ta.percentile_nearest_rank(source, period, percentage),
                 "Nearest "+name+" "+str(period)+" "+str(percentage))
            plot(ta.percentile_linear_interpolation(source, period, percentage),
                 "Linear "+name+" "+str(period)+" "+str(percentage))
