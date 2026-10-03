# ruff: noqa: F821
indicator("Pivot formula control", mode="incremental")


def init(ctx):
    for side, left, right in (("high", 3, 2), ("low", 3, 2), ("high", 0, 2), ("low", 0, 2), ("high", 2, 0), ("low", 2, 0)):
        title = "Pivot " + side + " " + str(left) + " " + str(right)
        getattr(ctx.ta, "pivot" + side)(title, left, right)


def on_bar(ctx, bar):
    i = ctx.bar_index
    value = None if i % 11 in (1, 6) else 3. if i % 11 >= 8 else float((i * 7) % 13 - 4)
    for side, left, right in (("high", 3, 2), ("low", 3, 2), ("high", 0, 2), ("low", 0, 2), ("high", 2, 0), ("low", 2, 0)):
        title = "Pivot " + side + " " + str(left) + " " + str(right)
        ctx.plot(title, getattr(ctx.ta, "pivot" + side)(title).update(value))
