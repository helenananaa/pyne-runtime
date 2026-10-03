# ruff: noqa: F821
import numpy as np
indicator("Recursive state holdout batch")

def inputs(i):
    codes = (-27, 31, -24, 26, 15, -8, -31, 2, 14, 18, -31, -35, -12, -23, 1, -33, 4, 5, 34, -24, -37, 25, -12, 8, 24, 0, 37, -12, -4, -20, -40, -11, 39, 24, 5, 27, -31, 1, 2, 5, -9, 34, -13, -11, 6, -4, 8, -13, -28, -35, -34, -33, -11, -20, 25, -34, -30, 14, 10, -37, 22, 5, 40, -31)
    base = float(codes[i % 64]) * .25
    return dict(leading=None if i < 5 or i % 13 in (8, 9) else base,
        flat_runs=None if 6 <= i % 17 <= 9 else 0. if i < 12 else 3. if i % 12 < 6 else -3.,
        regime=None if i % 19 in (3, 4) else 10000. + base if i < 16 else base if i < 48 else -10000. + base)

for profile in ("leading", "flat_runs", "regime"):
    values = np.asarray([inputs(i)[profile] for i in range(len(close))], dtype=np.float64)
    for method in ("ema", "rma", "rsi"):
        for period in (1, 2, 3, 7, 11):
            plot(getattr(ta, method)(values, period), f"{method.upper()}{period} {profile}")
