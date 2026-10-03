# ruff: noqa: F821
indicator("Oscillator boundaries")
source = (bar_index * 7) % 13 - 4.0
holes = when(
    (bar_index == 1) | (bar_index == 7) | (bar_index == 8)
    | (bar_index == 12) | (bar_index == 23), na, source,
)
flat = source * 0 + 5.0
plot(ta.cmo(holes, 3), "CMO holes")
plot(ta.cmo(flat, 3), "CMO flat")
plot(ta.cci(holes, 3), "CCI holes")
plot(ta.cci(flat, 3), "CCI flat")
plot(ta.stoch(flat, flat, flat, 3), "Stoch flat")
plot(ta.stoch(holes, holes + 1, holes - 1, 3), "Stoch holes")
plot(ta.correlation(holes, source, 3), "Correlation holes")
plot(ta.correlation(flat, source, 3), "Correlation flat")
