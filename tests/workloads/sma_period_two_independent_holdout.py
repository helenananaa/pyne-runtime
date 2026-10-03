# ruff: noqa: F821
indicator("SMA independent holdout scalars",mode="incremental")
def inputs(i):
    base = float(i * 13 % 23 - 10) * 0.25
    power = 2.0 ** 80 + base * 2.0 ** 28
    return dict(base=base, offset=1000000000000.0 + base, power=power, prefill=power if i < 13 else base, negative=-power if i < 13 else base, mixed=power if i % 4 == 0 else -power if i % 4 == 1 else base, holes=None if i >= 13 and i % 9 in (1, 4, 5) else power if i < 13 else base, leading=None if i < 5 else 1000000000000.0 + base, empty=None, singleGap=None if i == 17 else 1000000000000.0 + base if i < 25 else base, alternate=power if i % 2 == 0 else None, regime=power if i < 24 else base if i < 48 else -power if i < 72 else base)

def on_bar(ctx,bar):
    values = inputs(ctx.bar_index)
    ctx.plot('Native2 base',ctx.ta.sma('Native2 base',2).update(values['base']))
    ctx.plot('Native3 base',ctx.ta.sma('Native3 base',3).update(values['base']))
    ctx.plot('Native2 offset',ctx.ta.sma('Native2 offset',2).update(values['offset']))
    ctx.plot('Native3 offset',ctx.ta.sma('Native3 offset',3).update(values['offset']))
    ctx.plot('Native2 power',ctx.ta.sma('Native2 power',2).update(values['power']))
    ctx.plot('Native3 power',ctx.ta.sma('Native3 power',3).update(values['power']))
    ctx.plot('Native2 prefill',ctx.ta.sma('Native2 prefill',2).update(values['prefill']))
    ctx.plot('Native3 prefill',ctx.ta.sma('Native3 prefill',3).update(values['prefill']))
    ctx.plot('Native2 negative',ctx.ta.sma('Native2 negative',2).update(values['negative']))
    ctx.plot('Native3 negative',ctx.ta.sma('Native3 negative',3).update(values['negative']))
    ctx.plot('Native2 mixed',ctx.ta.sma('Native2 mixed',2).update(values['mixed']))
    ctx.plot('Native3 mixed',ctx.ta.sma('Native3 mixed',3).update(values['mixed']))
    ctx.plot('Native2 holes',ctx.ta.sma('Native2 holes',2).update(values['holes']))
    ctx.plot('Native3 holes',ctx.ta.sma('Native3 holes',3).update(values['holes']))
    ctx.plot('Native2 leading',ctx.ta.sma('Native2 leading',2).update(values['leading']))
    ctx.plot('Native3 leading',ctx.ta.sma('Native3 leading',3).update(values['leading']))
    ctx.plot('Native2 empty',ctx.ta.sma('Native2 empty',2).update(values['empty']))
    ctx.plot('Native3 empty',ctx.ta.sma('Native3 empty',3).update(values['empty']))
    ctx.plot('Native2 singleGap',ctx.ta.sma('Native2 singleGap',2).update(values['singleGap']))
    ctx.plot('Native3 singleGap',ctx.ta.sma('Native3 singleGap',3).update(values['singleGap']))
    ctx.plot('Native2 alternate',ctx.ta.sma('Native2 alternate',2).update(values['alternate']))
    ctx.plot('Native3 alternate',ctx.ta.sma('Native3 alternate',3).update(values['alternate']))
    ctx.plot('Native2 regime',ctx.ta.sma('Native2 regime',2).update(values['regime']))
    ctx.plot('Native3 regime',ctx.ta.sma('Native3 regime',3).update(values['regime']))
