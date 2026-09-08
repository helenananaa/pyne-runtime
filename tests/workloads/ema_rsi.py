# ruff: noqa: F821
indicator("EMA RSI boundaries", mode="incremental")


def init(ctx):
    for name in ("EMA", "EMA leading", "EMA holes"):
        ctx.ta.ema(name, 3)
    ctx.ta.macd("macd", fast=2, slow=4, signal=3)
    for name in ("RSI flat", "RSI rising", "RSI falling", "RSI holes", "RSI leading", "RSI base"):
        ctx.ta.rsi(name, 3)


def on_bar(ctx, bar):
    i = ctx.bar_index
    leading = None if i < 3 else bar.close
    holes = None if i in (1, 7, 12) else bar.close
    for name, source in (("EMA", bar.close), ("EMA leading", leading), ("EMA holes", holes)):
        ctx.plot(name, ctx.ta.ema(name).update(source))
    macd, signal, histogram = ctx.ta.macd("macd").update(holes)
    ctx.plot("MACD", macd)
    ctx.plot("Signal", signal)
    ctx.plot("Histogram", histogram)
    for name, source in (
        ("RSI flat", 10),
        ("RSI rising", i + 1),
        ("RSI falling", 100 - i),
        ("RSI holes", holes),
        ("RSI leading", leading),
        ("RSI base", bar.close),
    ):
        ctx.plot(name, ctx.ta.rsi(name).update(source))
