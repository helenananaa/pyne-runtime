# ruff: noqa: F821
indicator("Finite overflow SMA direct",mode="incremental")
def inputs(i):
    large = 160000000.0 * (10. ** 300)
    return dict(positive=large, negative=-large, mixed=large if i % 2 == 0 else -large,
                recovery=large if i < 6 else float((i * 11) % 17 - 6) * .25)

def on_bar(ctx,bar):
    values=inputs(ctx.bar_index)
    ctx.plot('Native1 positive',ctx.ta.sma('Native1 positive',1).update(values['positive']))
    ctx.plot('Native2 positive',ctx.ta.sma('Native2 positive',2).update(values['positive']))
    ctx.plot('Native3 positive',ctx.ta.sma('Native3 positive',3).update(values['positive']))
    ctx.plot('Native1 negative',ctx.ta.sma('Native1 negative',1).update(values['negative']))
    ctx.plot('Native2 negative',ctx.ta.sma('Native2 negative',2).update(values['negative']))
    ctx.plot('Native3 negative',ctx.ta.sma('Native3 negative',3).update(values['negative']))
    ctx.plot('Native1 mixed',ctx.ta.sma('Native1 mixed',1).update(values['mixed']))
    ctx.plot('Native2 mixed',ctx.ta.sma('Native2 mixed',2).update(values['mixed']))
    ctx.plot('Native3 mixed',ctx.ta.sma('Native3 mixed',3).update(values['mixed']))
    ctx.plot('Native1 recovery',ctx.ta.sma('Native1 recovery',1).update(values['recovery']))
    ctx.plot('Native2 recovery',ctx.ta.sma('Native2 recovery',2).update(values['recovery']))
    ctx.plot('Native3 recovery',ctx.ta.sma('Native3 recovery',3).update(values['recovery']))
