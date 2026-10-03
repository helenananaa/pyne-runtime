# ruff: noqa: F821
import numpy as np
indicator("Keltner width matrix")
i = np.arange(len(close))
sources = {
    "close": close,
    "holes": np.where(np.isin(i, [1, 7, 8, 12, 23]), np.nan, close),
    "leading": np.where(i < 5, np.nan, close),
    "empty": np.full(len(close), np.nan),
}
cases = [("close", p, 1.5, tr) for p in (1, 3, 7) for tr in (True, False)]
cases += [("close", 3, .5, tr) for tr in (True, False)] + [("close", 3, 2.5, True)]
cases += [(name, 3, 1.5, tr) for name in ("holes", "leading", "empty") for tr in (True, False)]
for case_id, (name, period, mult, tr) in enumerate(cases):
    upper, middle, lower = ta.keltner(period, mult, source=sources[name], use_true_range=tr)
    plot(upper, "KC case" + str(case_id) + " upper")
    plot(middle, "KC case" + str(case_id) + " middle")
    plot(lower, "KC case" + str(case_id) + " lower")
