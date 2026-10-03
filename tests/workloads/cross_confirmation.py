# ruff: noqa: F821
indicator("Cross confirmation", mode="incremental")


def init(ctx):
    for case in range(6):
        ctx.ta.cross("Cross case " + str(case))
        ctx.ta.crossover("Crossover case " + str(case))
        ctx.ta.crossunder("Crossunder case " + str(case))


def on_bar(ctx, bar):
    i = ctx.bar_index
    source = float((i * 7) % 13 - 4)
    holes = None if i in (1, 7, 8, 12, 23) else source
    leading = None if i < 4 else source
    other = float((i * 3) % 7 - 2)
    other_holes = None if i in (2, 7, 13, 23) else other
    zeros = 0. if i % 5 == 0 else source
    for case, (a, b) in enumerate(((holes, other_holes), (leading, other), (source, other), (holes, 0.), (None, other), (zeros, 1.))):
        for method, title in (("cross", "Cross"), ("crossover", "Crossover"), ("crossunder", "Crossunder")):
            name = title + " case " + str(case)
            ctx.plot(name, float(getattr(ctx.ta, method)(name).update(a, b)))
