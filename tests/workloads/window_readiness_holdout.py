# ruff: noqa: F821
indicator("Window readiness holdout", mode="incremental")
def sources(i):
    base = float(((i // 3) * 7) % 13 - 4)
    return dict(base=base, holes=None if i == 1 or 6 <= i <= 9 or 23 <= i <= 30 else base,
                leading=None if i < 8 else base, flat=5., missing=None)

def on_bar(ctx, bar):
    values = sources(ctx.bar_index)
    v = values['base']
    ctx.plot('highest base 1', ctx.ta.highest('highest base 1', 1).update(v))
    v = values['base']
    ctx.plot('lowest base 1', ctx.ta.lowest('lowest base 1', 1).update(v))
    v = values['base']
    ctx.plot('highestbars base 1', ctx.ta.highestbars('highestbars base 1', 1).update(v))
    v = values['base']
    ctx.plot('lowestbars base 1', ctx.ta.lowestbars('lowestbars base 1', 1).update(v))
    v = values['base']
    ctx.plot('stoch base 1', ctx.ta.stoch('stoch base 1', 1).update(v, None if v is None else v + 1, None if v is None else v - 1))
    v = values['base']
    ctx.plot('highest base 2', ctx.ta.highest('highest base 2', 2).update(v))
    v = values['base']
    ctx.plot('lowest base 2', ctx.ta.lowest('lowest base 2', 2).update(v))
    v = values['base']
    ctx.plot('highestbars base 2', ctx.ta.highestbars('highestbars base 2', 2).update(v))
    v = values['base']
    ctx.plot('lowestbars base 2', ctx.ta.lowestbars('lowestbars base 2', 2).update(v))
    v = values['base']
    ctx.plot('stoch base 2', ctx.ta.stoch('stoch base 2', 2).update(v, None if v is None else v + 1, None if v is None else v - 1))
    v = values['base']
    ctx.plot('highest base 3', ctx.ta.highest('highest base 3', 3).update(v))
    v = values['base']
    ctx.plot('lowest base 3', ctx.ta.lowest('lowest base 3', 3).update(v))
    v = values['base']
    ctx.plot('highestbars base 3', ctx.ta.highestbars('highestbars base 3', 3).update(v))
    v = values['base']
    ctx.plot('lowestbars base 3', ctx.ta.lowestbars('lowestbars base 3', 3).update(v))
    v = values['base']
    ctx.plot('stoch base 3', ctx.ta.stoch('stoch base 3', 3).update(v, None if v is None else v + 1, None if v is None else v - 1))
    v = values['base']
    ctx.plot('highest base 5', ctx.ta.highest('highest base 5', 5).update(v))
    v = values['base']
    ctx.plot('lowest base 5', ctx.ta.lowest('lowest base 5', 5).update(v))
    v = values['base']
    ctx.plot('highestbars base 5', ctx.ta.highestbars('highestbars base 5', 5).update(v))
    v = values['base']
    ctx.plot('lowestbars base 5', ctx.ta.lowestbars('lowestbars base 5', 5).update(v))
    v = values['base']
    ctx.plot('stoch base 5', ctx.ta.stoch('stoch base 5', 5).update(v, None if v is None else v + 1, None if v is None else v - 1))
    v = values['base']
    ctx.plot('highest base 11', ctx.ta.highest('highest base 11', 11).update(v))
    v = values['base']
    ctx.plot('lowest base 11', ctx.ta.lowest('lowest base 11', 11).update(v))
    v = values['base']
    ctx.plot('highestbars base 11', ctx.ta.highestbars('highestbars base 11', 11).update(v))
    v = values['base']
    ctx.plot('lowestbars base 11', ctx.ta.lowestbars('lowestbars base 11', 11).update(v))
    v = values['base']
    ctx.plot('stoch base 11', ctx.ta.stoch('stoch base 11', 11).update(v, None if v is None else v + 1, None if v is None else v - 1))
    v = values['holes']
    ctx.plot('highest holes 1', ctx.ta.highest('highest holes 1', 1).update(v))
    v = values['holes']
    ctx.plot('lowest holes 1', ctx.ta.lowest('lowest holes 1', 1).update(v))
    v = values['holes']
    ctx.plot('highestbars holes 1', ctx.ta.highestbars('highestbars holes 1', 1).update(v))
    v = values['holes']
    ctx.plot('lowestbars holes 1', ctx.ta.lowestbars('lowestbars holes 1', 1).update(v))
    v = values['holes']
    ctx.plot('stoch holes 1', ctx.ta.stoch('stoch holes 1', 1).update(v, None if v is None else v + 1, None if v is None else v - 1))
    v = values['holes']
    ctx.plot('highest holes 2', ctx.ta.highest('highest holes 2', 2).update(v))
    v = values['holes']
    ctx.plot('lowest holes 2', ctx.ta.lowest('lowest holes 2', 2).update(v))
    v = values['holes']
    ctx.plot('highestbars holes 2', ctx.ta.highestbars('highestbars holes 2', 2).update(v))
    v = values['holes']
    ctx.plot('lowestbars holes 2', ctx.ta.lowestbars('lowestbars holes 2', 2).update(v))
    v = values['holes']
    ctx.plot('stoch holes 2', ctx.ta.stoch('stoch holes 2', 2).update(v, None if v is None else v + 1, None if v is None else v - 1))
    v = values['holes']
    ctx.plot('highest holes 3', ctx.ta.highest('highest holes 3', 3).update(v))
    v = values['holes']
    ctx.plot('lowest holes 3', ctx.ta.lowest('lowest holes 3', 3).update(v))
    v = values['holes']
    ctx.plot('highestbars holes 3', ctx.ta.highestbars('highestbars holes 3', 3).update(v))
    v = values['holes']
    ctx.plot('lowestbars holes 3', ctx.ta.lowestbars('lowestbars holes 3', 3).update(v))
    v = values['holes']
    ctx.plot('stoch holes 3', ctx.ta.stoch('stoch holes 3', 3).update(v, None if v is None else v + 1, None if v is None else v - 1))
    v = values['holes']
    ctx.plot('highest holes 5', ctx.ta.highest('highest holes 5', 5).update(v))
    v = values['holes']
    ctx.plot('lowest holes 5', ctx.ta.lowest('lowest holes 5', 5).update(v))
    v = values['holes']
    ctx.plot('highestbars holes 5', ctx.ta.highestbars('highestbars holes 5', 5).update(v))
    v = values['holes']
    ctx.plot('lowestbars holes 5', ctx.ta.lowestbars('lowestbars holes 5', 5).update(v))
    v = values['holes']
    ctx.plot('stoch holes 5', ctx.ta.stoch('stoch holes 5', 5).update(v, None if v is None else v + 1, None if v is None else v - 1))
    v = values['holes']
    ctx.plot('highest holes 11', ctx.ta.highest('highest holes 11', 11).update(v))
    v = values['holes']
    ctx.plot('lowest holes 11', ctx.ta.lowest('lowest holes 11', 11).update(v))
    v = values['holes']
    ctx.plot('highestbars holes 11', ctx.ta.highestbars('highestbars holes 11', 11).update(v))
    v = values['holes']
    ctx.plot('lowestbars holes 11', ctx.ta.lowestbars('lowestbars holes 11', 11).update(v))
    v = values['holes']
    ctx.plot('stoch holes 11', ctx.ta.stoch('stoch holes 11', 11).update(v, None if v is None else v + 1, None if v is None else v - 1))
    v = values['leading']
    ctx.plot('highest leading 1', ctx.ta.highest('highest leading 1', 1).update(v))
    v = values['leading']
    ctx.plot('lowest leading 1', ctx.ta.lowest('lowest leading 1', 1).update(v))
    v = values['leading']
    ctx.plot('highestbars leading 1', ctx.ta.highestbars('highestbars leading 1', 1).update(v))
    v = values['leading']
    ctx.plot('lowestbars leading 1', ctx.ta.lowestbars('lowestbars leading 1', 1).update(v))
    v = values['leading']
    ctx.plot('stoch leading 1', ctx.ta.stoch('stoch leading 1', 1).update(v, None if v is None else v + 1, None if v is None else v - 1))
    v = values['leading']
    ctx.plot('highest leading 2', ctx.ta.highest('highest leading 2', 2).update(v))
    v = values['leading']
    ctx.plot('lowest leading 2', ctx.ta.lowest('lowest leading 2', 2).update(v))
    v = values['leading']
    ctx.plot('highestbars leading 2', ctx.ta.highestbars('highestbars leading 2', 2).update(v))
    v = values['leading']
    ctx.plot('lowestbars leading 2', ctx.ta.lowestbars('lowestbars leading 2', 2).update(v))
    v = values['leading']
    ctx.plot('stoch leading 2', ctx.ta.stoch('stoch leading 2', 2).update(v, None if v is None else v + 1, None if v is None else v - 1))
    v = values['leading']
    ctx.plot('highest leading 3', ctx.ta.highest('highest leading 3', 3).update(v))
    v = values['leading']
    ctx.plot('lowest leading 3', ctx.ta.lowest('lowest leading 3', 3).update(v))
    v = values['leading']
    ctx.plot('highestbars leading 3', ctx.ta.highestbars('highestbars leading 3', 3).update(v))
    v = values['leading']
    ctx.plot('lowestbars leading 3', ctx.ta.lowestbars('lowestbars leading 3', 3).update(v))
    v = values['leading']
    ctx.plot('stoch leading 3', ctx.ta.stoch('stoch leading 3', 3).update(v, None if v is None else v + 1, None if v is None else v - 1))
    v = values['leading']
    ctx.plot('highest leading 5', ctx.ta.highest('highest leading 5', 5).update(v))
    v = values['leading']
    ctx.plot('lowest leading 5', ctx.ta.lowest('lowest leading 5', 5).update(v))
    v = values['leading']
    ctx.plot('highestbars leading 5', ctx.ta.highestbars('highestbars leading 5', 5).update(v))
    v = values['leading']
    ctx.plot('lowestbars leading 5', ctx.ta.lowestbars('lowestbars leading 5', 5).update(v))
    v = values['leading']
    ctx.plot('stoch leading 5', ctx.ta.stoch('stoch leading 5', 5).update(v, None if v is None else v + 1, None if v is None else v - 1))
    v = values['leading']
    ctx.plot('highest leading 11', ctx.ta.highest('highest leading 11', 11).update(v))
    v = values['leading']
    ctx.plot('lowest leading 11', ctx.ta.lowest('lowest leading 11', 11).update(v))
    v = values['leading']
    ctx.plot('highestbars leading 11', ctx.ta.highestbars('highestbars leading 11', 11).update(v))
    v = values['leading']
    ctx.plot('lowestbars leading 11', ctx.ta.lowestbars('lowestbars leading 11', 11).update(v))
    v = values['leading']
    ctx.plot('stoch leading 11', ctx.ta.stoch('stoch leading 11', 11).update(v, None if v is None else v + 1, None if v is None else v - 1))
    v = values['flat']
    ctx.plot('highest flat 1', ctx.ta.highest('highest flat 1', 1).update(v))
    v = values['flat']
    ctx.plot('lowest flat 1', ctx.ta.lowest('lowest flat 1', 1).update(v))
    v = values['flat']
    ctx.plot('highestbars flat 1', ctx.ta.highestbars('highestbars flat 1', 1).update(v))
    v = values['flat']
    ctx.plot('lowestbars flat 1', ctx.ta.lowestbars('lowestbars flat 1', 1).update(v))
    v = values['flat']
    ctx.plot('stoch flat 1', ctx.ta.stoch('stoch flat 1', 1).update(v, v, v))
    v = values['flat']
    ctx.plot('highest flat 2', ctx.ta.highest('highest flat 2', 2).update(v))
    v = values['flat']
    ctx.plot('lowest flat 2', ctx.ta.lowest('lowest flat 2', 2).update(v))
    v = values['flat']
    ctx.plot('highestbars flat 2', ctx.ta.highestbars('highestbars flat 2', 2).update(v))
    v = values['flat']
    ctx.plot('lowestbars flat 2', ctx.ta.lowestbars('lowestbars flat 2', 2).update(v))
    v = values['flat']
    ctx.plot('stoch flat 2', ctx.ta.stoch('stoch flat 2', 2).update(v, v, v))
    v = values['flat']
    ctx.plot('highest flat 3', ctx.ta.highest('highest flat 3', 3).update(v))
    v = values['flat']
    ctx.plot('lowest flat 3', ctx.ta.lowest('lowest flat 3', 3).update(v))
    v = values['flat']
    ctx.plot('highestbars flat 3', ctx.ta.highestbars('highestbars flat 3', 3).update(v))
    v = values['flat']
    ctx.plot('lowestbars flat 3', ctx.ta.lowestbars('lowestbars flat 3', 3).update(v))
    v = values['flat']
    ctx.plot('stoch flat 3', ctx.ta.stoch('stoch flat 3', 3).update(v, v, v))
    v = values['flat']
    ctx.plot('highest flat 5', ctx.ta.highest('highest flat 5', 5).update(v))
    v = values['flat']
    ctx.plot('lowest flat 5', ctx.ta.lowest('lowest flat 5', 5).update(v))
    v = values['flat']
    ctx.plot('highestbars flat 5', ctx.ta.highestbars('highestbars flat 5', 5).update(v))
    v = values['flat']
    ctx.plot('lowestbars flat 5', ctx.ta.lowestbars('lowestbars flat 5', 5).update(v))
    v = values['flat']
    ctx.plot('stoch flat 5', ctx.ta.stoch('stoch flat 5', 5).update(v, v, v))
    v = values['flat']
    ctx.plot('highest flat 11', ctx.ta.highest('highest flat 11', 11).update(v))
    v = values['flat']
    ctx.plot('lowest flat 11', ctx.ta.lowest('lowest flat 11', 11).update(v))
    v = values['flat']
    ctx.plot('highestbars flat 11', ctx.ta.highestbars('highestbars flat 11', 11).update(v))
    v = values['flat']
    ctx.plot('lowestbars flat 11', ctx.ta.lowestbars('lowestbars flat 11', 11).update(v))
    v = values['flat']
    ctx.plot('stoch flat 11', ctx.ta.stoch('stoch flat 11', 11).update(v, v, v))
    v = values['missing']
    ctx.plot('highest missing 1', ctx.ta.highest('highest missing 1', 1).update(v))
    v = values['missing']
    ctx.plot('lowest missing 1', ctx.ta.lowest('lowest missing 1', 1).update(v))
    v = values['missing']
    ctx.plot('highestbars missing 1', ctx.ta.highestbars('highestbars missing 1', 1).update(v))
    v = values['missing']
    ctx.plot('lowestbars missing 1', ctx.ta.lowestbars('lowestbars missing 1', 1).update(v))
    v = values['missing']
    ctx.plot('stoch missing 1', ctx.ta.stoch('stoch missing 1', 1).update(v, None if v is None else v + 1, None if v is None else v - 1))
    v = values['missing']
    ctx.plot('highest missing 2', ctx.ta.highest('highest missing 2', 2).update(v))
    v = values['missing']
    ctx.plot('lowest missing 2', ctx.ta.lowest('lowest missing 2', 2).update(v))
    v = values['missing']
    ctx.plot('highestbars missing 2', ctx.ta.highestbars('highestbars missing 2', 2).update(v))
    v = values['missing']
    ctx.plot('lowestbars missing 2', ctx.ta.lowestbars('lowestbars missing 2', 2).update(v))
    v = values['missing']
    ctx.plot('stoch missing 2', ctx.ta.stoch('stoch missing 2', 2).update(v, None if v is None else v + 1, None if v is None else v - 1))
    v = values['missing']
    ctx.plot('highest missing 3', ctx.ta.highest('highest missing 3', 3).update(v))
    v = values['missing']
    ctx.plot('lowest missing 3', ctx.ta.lowest('lowest missing 3', 3).update(v))
    v = values['missing']
    ctx.plot('highestbars missing 3', ctx.ta.highestbars('highestbars missing 3', 3).update(v))
    v = values['missing']
    ctx.plot('lowestbars missing 3', ctx.ta.lowestbars('lowestbars missing 3', 3).update(v))
    v = values['missing']
    ctx.plot('stoch missing 3', ctx.ta.stoch('stoch missing 3', 3).update(v, None if v is None else v + 1, None if v is None else v - 1))
    v = values['missing']
    ctx.plot('highest missing 5', ctx.ta.highest('highest missing 5', 5).update(v))
    v = values['missing']
    ctx.plot('lowest missing 5', ctx.ta.lowest('lowest missing 5', 5).update(v))
    v = values['missing']
    ctx.plot('highestbars missing 5', ctx.ta.highestbars('highestbars missing 5', 5).update(v))
    v = values['missing']
    ctx.plot('lowestbars missing 5', ctx.ta.lowestbars('lowestbars missing 5', 5).update(v))
    v = values['missing']
    ctx.plot('stoch missing 5', ctx.ta.stoch('stoch missing 5', 5).update(v, None if v is None else v + 1, None if v is None else v - 1))
    v = values['missing']
    ctx.plot('highest missing 11', ctx.ta.highest('highest missing 11', 11).update(v))
    v = values['missing']
    ctx.plot('lowest missing 11', ctx.ta.lowest('lowest missing 11', 11).update(v))
    v = values['missing']
    ctx.plot('highestbars missing 11', ctx.ta.highestbars('highestbars missing 11', 11).update(v))
    v = values['missing']
    ctx.plot('lowestbars missing 11', ctx.ta.lowestbars('lowestbars missing 11', 11).update(v))
    v = values['missing']
    ctx.plot('stoch missing 11', ctx.ta.stoch('stoch missing 11', 11).update(v, None if v is None else v + 1, None if v is None else v - 1))
