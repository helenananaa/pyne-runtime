# ruff: noqa: F821
indicator("Weighted boundaries")
source = (bar_index * 7) % 13 - 4.0
holes = when(
    (bar_index == 1) | (bar_index == 7) | (bar_index == 8)
    | (bar_index == 12) | (bar_index == 23), na, source,
)
leading = when(bar_index < 4, na, source)
wma = ta.wma(holes, 3)
plot(wma, "WMA holes")
plot(ta.wma(holes, 1), "WMA 1")
plot(ta.wma(leading, 3), "WMA leading")
plot(ta.hma(source, 5), "HMA 5")
plot(ta.hma(source, 7), "HMA 7")
plot(ta.hma(source, 9), "HMA 9")
plot(ta.hma(holes, 7), "HMA holes")
plot(ta.swma(holes), "SWMA")
plot(ta.alma(holes, 3, 0.85, 6), "ALMA")
plot(ta.dev(holes, 3), "DEV")
plot(ta.wma(wma, 3), "Nested WMA")
plot(ta.wma(holes * na, 3), "Empty WMA")
