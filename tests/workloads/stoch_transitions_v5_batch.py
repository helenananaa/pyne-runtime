# ruff: noqa: F821
indicator("Stochastic transitions")
source = (bar_index * 7) % 13 - 4.0
holes = when(
    (bar_index == 1) | (bar_index == 7) | (bar_index == 8)
    | (bar_index == 12) | (bar_index == 23), na, source,
)
high_hole = when((bar_index == 7) | (bar_index == 8), na, source + 1)
low_hole = when(bar_index == 12, na, source - 1)
tail = when(bar_index >= 16, 5.0, source)
tail_high = when(bar_index >= 16, 5.0, source + 1)
tail_low = when(bar_index >= 16, 5.0, source - 1)
leading = when(bar_index < 8, 5.0, source)
leading_high = when(bar_index < 8, 5.0, source + 1)
leading_low = when(bar_index < 8, 5.0, source - 1)
plot(ta.stoch(source, source + 1, source - 1, 3), "Stoch base")
plot(ta.stoch(holes, source + 1, source - 1, 3), "Stoch source only")
plot(ta.stoch(source, high_hole, source - 1, 3), "Stoch high only")
plot(ta.stoch(source, source + 1, low_hole, 3), "Stoch low only")
plot(ta.stoch(tail, tail_high, tail_low, 3), "Stoch flat tail")
plot(ta.stoch(leading, leading_high, leading_low, 3), "Stoch flat leading")
