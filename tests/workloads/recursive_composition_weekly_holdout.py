# ruff: noqa: F821
indicator("Native initial OHLCV compositions", mode="incremental")


def on_bar(ctx, bar):
    ctx.plot("TR", ctx.ta.tr("TR").update(bar))
    for period in (1, 3, 7):
        title = f"ATR{period}"
        ctx.plot(title, ctx.ta.atr(title, period).update(bar))
    for title, period, adx_period in (("3", 3, 3), ("7", 7, 7), ("3x", 3, 7)):
        plus, minus, adx = ctx.ta.dmi("DMI" + title, period, adx_period).update(bar)
        ctx.plot("plus" + title, plus)
        ctx.plot("minus" + title, minus)
        ctx.plot("ADX" + title, adx)
