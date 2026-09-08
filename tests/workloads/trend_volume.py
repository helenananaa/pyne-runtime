# ruff: noqa: F821
indicator("Trend volume boundaries", mode="incremental")


def init(ctx):
    ctx.ta.supertrend("st", factor=2.0, atr_period=3)
    ctx.ta.supertrend("st1", factor=2.0, atr_period=1)
    ctx.ta.atr("atr", 3)
    for name in (
        "VWMA close",
        "VWMA holes",
        "VWMA leading",
        "Custom price holes",
        "Custom volume holes",
        "Custom both holes",
        "Zero weight",
    ):
        ctx.ta.vwma(name, 3)


def on_bar(ctx, bar):
    i = ctx.bar_index
    src = 10.0 * (i % 4 + 1)
    holes = None if i in (1, 7, 12) else src
    leading = None if i < 3 else src
    weights = i % 3 + 1.0
    missing_weights = None if i in (2, 9) else weights
    st, direction = ctx.ta.supertrend("st").update(bar)
    st1, direction1 = ctx.ta.supertrend("st1").update(bar)
    ctx.plot("ST 3", st)
    ctx.plot("Direction 3", direction)
    ctx.plot("ST 1", st1)
    ctx.plot("Direction 1", direction1)
    ctx.plot("ATR 3", ctx.ta.atr("atr").update(bar))
    for name, value, weight in (
        ("VWMA close", bar.close, bar.volume),
        ("VWMA holes", holes, bar.volume),
        ("VWMA leading", leading, bar.volume),
        ("Custom price holes", holes, weights),
        ("Custom volume holes", src, missing_weights),
        ("Custom both holes", holes, missing_weights),
        ("Zero weight", src, 0),
    ):
        ctx.plot(name, ctx.ta.vwma(name).update(value, weight))
