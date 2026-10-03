# ruff: noqa: F821
import numpy as np
indicator("Direction missing boundaries")
i = np.arange(len(close))
wave = np.array([2, 1, 2, 3, 4, 3, 4, 5, 6, 3, 2, 1], dtype=float)[i % 12]
sources = {
    "holes": np.where(np.isin(i, [5, 17, 18]), np.nan, wave),
    "empty": np.full(len(close), np.nan),
    "leading": np.where(i < 8, np.nan, wave),
    "alternating": np.where(i % 2 == 0, np.nan, wave),
    "flat": np.where(i % 5 == 2, np.nan, 5.),
    "descending": np.where(np.isin(i % 5, [2, 3]), np.nan, 100. - i),
}
for name, period in (("holes", 3), ("empty", 3), ("leading", 3), ("alternating", 3),
                     ("flat", 3), ("descending", 3), ("empty", 1), ("alternating", 1),
                     ("holes", 7), ("leading", 7)):
    plot(when(ta.rising(sources[name], period), 1., 0.), "Rising " + name + " " + str(period))
    plot(when(ta.falling(sources[name], period), 1., 0.), "Falling " + name + " " + str(period))
