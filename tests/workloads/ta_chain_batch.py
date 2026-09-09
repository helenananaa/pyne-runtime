# ruff: noqa: F821
indicator("TA chain")
fast = ta.sma(close, 3)
slow = ta.sma(close, 7)
crossed = ta.crossover(fast, slow)
plot(fast, "Fast")
plot(slow, "Slow")
plot(crossed, "Cross")
plot(ta.valuewhen(crossed, close, 0), "Last cross")
