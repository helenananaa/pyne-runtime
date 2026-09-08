# ruff: noqa: F821
indicator("Smoothing composition", mode="incremental")


def init(ctx):
    ctx.ta.rsi("rsi", 3)
    ctx.ta.ema("ema", 3)


def on_bar(ctx, bar):
    holes = None if ctx.bar_index in (1, 7, 12) else bar.close
    rsi = ctx.ta.rsi("rsi").update(holes)
    ctx.plot("Smoothed RSI", ctx.ta.ema("ema").update(rsi))
