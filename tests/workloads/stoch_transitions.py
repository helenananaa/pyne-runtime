# ruff: noqa: F821
indicator("Stochastic transitions", mode="incremental")


def init(ctx):
    for name in (
        "Stoch base", "Stoch source only", "Stoch high only",
        "Stoch low only", "Stoch flat tail", "Stoch flat leading",
    ):
        ctx.ta.stoch(name, 3)


def on_bar(ctx, bar):
    i = ctx.bar_index
    source = float((i * 7) % 13 - 4)
    holes = None if i in (1, 7, 8, 12, 23) else source
    tail = 5.0 if i >= 16 else source
    lead = 5.0 if i < 8 else source
    for name, price, high, low in (
        ("Stoch base", source, source + 1, source - 1),
        ("Stoch source only", holes, source + 1, source - 1),
        ("Stoch high only", source, None if i in (7, 8) else source + 1, source - 1),
        ("Stoch low only", source, source + 1, None if i == 12 else source - 1),
        ("Stoch flat tail", tail, 5.0 if i >= 16 else source + 1, 5.0 if i >= 16 else source - 1),
        ("Stoch flat leading", lead, 5.0 if i < 8 else source + 1, 5.0 if i < 8 else source - 1),
    ):
        ctx.plot(name, ctx.ta.stoch(name).update(price, high, low))
