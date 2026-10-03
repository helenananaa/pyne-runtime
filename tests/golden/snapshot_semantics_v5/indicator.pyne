# ruff: noqa: F821
indicator("Weighted boundaries", mode="incremental")


def init(ctx):
    for name, period in (
        ("WMA holes", 3), ("WMA 1", 1), ("WMA leading", 3),
        ("Nested WMA", 3), ("Empty WMA", 3),
    ):
        ctx.ta.wma(name, period)
    for name, period in (("HMA 5", 5), ("HMA 7", 7), ("HMA 9", 9), ("HMA holes", 7)):
        ctx.ta.hma(name, period)
    ctx.ta.swma("SWMA")
    ctx.ta.alma("ALMA", 3, 0.85, 6)
    ctx.ta.dev("DEV", 3)


def on_bar(ctx, bar):
    i = ctx.bar_index
    source = float((i * 7) % 13 - 4)
    holes = None if i in (1, 7, 8, 12, 23) else source
    leading = None if i < 4 else source
    wma = ctx.ta.wma("WMA holes").update(holes)
    ctx.plot("WMA holes", wma)
    ctx.plot("WMA 1", ctx.ta.wma("WMA 1").update(holes))
    ctx.plot("WMA leading", ctx.ta.wma("WMA leading").update(leading))
    for name in ("HMA 5", "HMA 7", "HMA 9"):
        ctx.plot(name, ctx.ta.hma(name).update(source))
    ctx.plot("HMA holes", ctx.ta.hma("HMA holes").update(holes))
    ctx.plot("SWMA", ctx.ta.swma("SWMA").update(holes))
    ctx.plot("ALMA", ctx.ta.alma("ALMA").update(holes))
    ctx.plot("DEV", ctx.ta.dev("DEV").update(holes))
    ctx.plot("Nested WMA", ctx.ta.wma("Nested WMA").update(wma))
    ctx.plot("Empty WMA", ctx.ta.wma("Empty WMA").update(None))
