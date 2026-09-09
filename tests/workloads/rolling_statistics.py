# ruff: noqa: F821
indicator("Rolling statistics", mode="incremental")


def init(ctx):
    for name in ("SMA base", "SMA holes", "SMA leading", "High SMA", "Empty SMA"):
        ctx.ta.sma(name, 3)
    ctx.ta.sma("SMA 1", 1)
    for name in ("Stdev", "High Stdev", "Empty Stdev"):
        ctx.ta.stdev(name, 3)
    for name in ("Variance", "High Variance"):
        ctx.ta.variance(name, 3)
    ctx.ta.variance("Sample variance", 3, biased=False)
    ctx.ta.variance("Sample variance 1", 1, biased=False)
    ctx.ta.bb("bb", 3, mult=2)


def on_bar(ctx, bar):
    i = ctx.bar_index
    holes = None if i in (1, 7, 12) else bar.close
    leading = None if i < 3 else bar.close
    high_source = None if holes is None else 1000000000.0 + holes
    for name, value in (
        ("SMA base", bar.close),
        ("SMA holes", holes),
        ("SMA leading", leading),
        ("High SMA", high_source),
        ("SMA 1", holes),
        ("Empty SMA", None),
    ):
        ctx.plot(name, ctx.ta.sma(name).update(value))
    for name, value in (("Stdev", holes), ("High Stdev", high_source), ("Empty Stdev", None)):
        ctx.plot(name, ctx.ta.stdev(name).update(value))
    for name, value in (
        ("Variance", holes),
        ("High Variance", high_source),
        ("Sample variance", holes),
        ("Sample variance 1", holes),
    ):
        ctx.plot(name, ctx.ta.variance(name, biased=not name.startswith("Sample")).update(value))
    mid, upper, lower = ctx.ta.bb("bb").update(holes)
    ctx.plot("Middle", mid)
    ctx.plot("Upper", upper)
    ctx.plot("Lower", lower)
