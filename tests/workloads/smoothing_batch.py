# ruff: noqa: F821
indicator("Smoothing composition")
holes = when((bar_index == 1) | (bar_index == 7) | (bar_index == 12), na, close)
plot(ta.ema(ta.rsi(holes, 3), 3), "Smoothed RSI")
plot(ta.tsi(holes, 2, 3), "TSI")
