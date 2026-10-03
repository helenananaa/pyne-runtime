# ruff: noqa: F821
import numpy as np
indicator("Pivot formula control")
i = np.arange(len(close))
source = np.where(np.isin(i % 11, [1, 6]), np.nan, np.where(i % 11 >= 8, 3., (i * 7) % 13 - 4))
for side, left, right in (("high", 3, 2), ("low", 3, 2), ("high", 0, 2), ("low", 0, 2), ("high", 2, 0), ("low", 2, 0)):
    plot(getattr(ta, "pivot" + side)(source, left, right), "Pivot " + side + " " + str(left) + " " + str(right))
