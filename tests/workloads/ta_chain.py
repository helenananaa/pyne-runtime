# ruff: noqa: F821
"""First-party workload: smoothing, crossover and last-event state."""

indicator("TA chain", mode="incremental")


def init(ctx):
    ctx.ta.sma("fast", 3)
    ctx.ta.sma("slow", 7)
    ctx.ta.crossover("cross")
    ctx.ta.valuewhen("last", 0)


def on_bar(ctx, bar):
    fast = ctx.ta.sma("fast").update(bar.close)
    slow = ctx.ta.sma("slow").update(bar.close)
    crossed = ctx.ta.crossover("cross").update(fast, slow)
    last = ctx.ta.valuewhen("last").update(crossed, bar.close)
    ctx.plot("Fast", fast)
    ctx.plot("Slow", slow)
    ctx.plot("Cross", int(crossed))
    ctx.plot("Last cross", last)
