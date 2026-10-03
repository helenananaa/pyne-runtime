# ruff: noqa: F821
import numpy as np
indicator("Cross confirmation")
i = np.arange(len(close))
source = ((i * 7) % 13 - 4).astype(float)
holes = np.where(np.isin(i, [1, 7, 8, 12, 23]), np.nan, source)
leading = np.where(i < 4, np.nan, source)
empty = np.full(len(close), np.nan)
other = ((i * 3) % 7 - 2).astype(float)
other_holes = np.where(np.isin(i, [2, 7, 13, 23]), np.nan, other)
zeros = np.where(i % 5 == 0, 0., source)
for case, (a, b) in enumerate(((holes, other_holes), (leading, other), (source, other), (holes, 0.), (empty, other), (zeros, 1.))):
    plot(when(ta.cross(a, b), 1., 0.), "Cross case " + str(case))
    plot(when(ta.crossover(a, b), 1., 0.), "Crossover case " + str(case))
    plot(when(ta.crossunder(a, b), 1., 0.), "Crossunder case " + str(case))
