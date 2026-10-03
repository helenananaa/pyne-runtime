# ruff: noqa: F821
indicator("Extrema tie confirmation", mode="incremental")

def init(ctx):
    ctx.ta.highest('Highest 1', 1)
    ctx.ta.lowest('Lowest 1', 1)
    ctx.ta.highestbars('Highestbars 1', 1)
    ctx.ta.lowestbars('Lowestbars 1', 1)
    ctx.ta.highest('Highest 5', 5)
    ctx.ta.lowest('Lowest 5', 5)
    ctx.ta.highestbars('Highestbars 5', 5)
    ctx.ta.lowestbars('Lowestbars 5', 5)
    ctx.ta.highestbars('Highestbars flat', 3)
    ctx.ta.lowestbars('Lowestbars flat', 3)
    ctx.ta.highest('Highest empty', 3)
    ctx.ta.lowest('Lowest empty', 3)
    ctx.ta.highestbars('Highestbars empty', 3)
    ctx.ta.lowestbars('Lowestbars empty', 3)

def on_bar(ctx, bar):
    i = ctx.bar_index
    cycle = float((i // 3) % 2)
    gap = None if i in (6, 7) or 18 <= i < 23 else cycle
    flat = 5.0
    empty = None
    ctx.plot('Highest 1', ctx.ta.highest('Highest 1').update(gap))
    ctx.plot('Lowest 1', ctx.ta.lowest('Lowest 1').update(gap))
    ctx.plot('Highestbars 1', ctx.ta.highestbars('Highestbars 1').update(gap))
    ctx.plot('Lowestbars 1', ctx.ta.lowestbars('Lowestbars 1').update(gap))
    ctx.plot('Highest 5', ctx.ta.highest('Highest 5').update(gap))
    ctx.plot('Lowest 5', ctx.ta.lowest('Lowest 5').update(gap))
    ctx.plot('Highestbars 5', ctx.ta.highestbars('Highestbars 5').update(gap))
    ctx.plot('Lowestbars 5', ctx.ta.lowestbars('Lowestbars 5').update(gap))
    ctx.plot('Highestbars flat', ctx.ta.highestbars('Highestbars flat').update(flat))
    ctx.plot('Lowestbars flat', ctx.ta.lowestbars('Lowestbars flat').update(flat))
    ctx.plot('Highest empty', ctx.ta.highest('Highest empty').update(empty))
    ctx.plot('Lowest empty', ctx.ta.lowest('Lowest empty').update(empty))
    ctx.plot('Highestbars empty', ctx.ta.highestbars('Highestbars empty').update(empty))
    ctx.plot('Lowestbars empty', ctx.ta.lowestbars('Lowestbars empty').update(empty))
