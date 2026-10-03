# ruff: noqa: F821
indicator("SMA history arithmetic",mode="incremental")
def values_at(index):
    base = float((index*11)%17-6)
    power = 2.**80+base*2.**28
    holes = None if index%7 in (1,2) else base
    return dict(base=base,power=power,prefill=power if index<16 else base,
                negativePrefill=-power if index<16 else base,holes=holes,
                prefillHoles=power if index<16 else holes)

def on_bar(ctx,bar):
    values = values_at(ctx.bar_index)
    ctx.plot('Native base 1',ctx.ta.sma('Native base 1',1).update(values['base']))
    ctx.plot('Native base 2',ctx.ta.sma('Native base 2',2).update(values['base']))
    ctx.plot('Native base 3',ctx.ta.sma('Native base 3',3).update(values['base']))
    ctx.plot('Native base 7',ctx.ta.sma('Native base 7',7).update(values['base']))
    ctx.plot('Native base 11',ctx.ta.sma('Native base 11',11).update(values['base']))
    ctx.plot('Native power 1',ctx.ta.sma('Native power 1',1).update(values['power']))
    ctx.plot('Native power 2',ctx.ta.sma('Native power 2',2).update(values['power']))
    ctx.plot('Native power 3',ctx.ta.sma('Native power 3',3).update(values['power']))
    ctx.plot('Native power 7',ctx.ta.sma('Native power 7',7).update(values['power']))
    ctx.plot('Native power 11',ctx.ta.sma('Native power 11',11).update(values['power']))
    ctx.plot('Native prefill 1',ctx.ta.sma('Native prefill 1',1).update(values['prefill']))
    ctx.plot('Native prefill 2',ctx.ta.sma('Native prefill 2',2).update(values['prefill']))
    ctx.plot('Native prefill 3',ctx.ta.sma('Native prefill 3',3).update(values['prefill']))
    ctx.plot('Native prefill 7',ctx.ta.sma('Native prefill 7',7).update(values['prefill']))
    ctx.plot('Native prefill 11',ctx.ta.sma('Native prefill 11',11).update(values['prefill']))
    ctx.plot('Native negativePrefill 1',ctx.ta.sma('Native negativePrefill 1',1).update(values['negativePrefill']))
    ctx.plot('Native negativePrefill 2',ctx.ta.sma('Native negativePrefill 2',2).update(values['negativePrefill']))
    ctx.plot('Native negativePrefill 3',ctx.ta.sma('Native negativePrefill 3',3).update(values['negativePrefill']))
    ctx.plot('Native negativePrefill 7',ctx.ta.sma('Native negativePrefill 7',7).update(values['negativePrefill']))
    ctx.plot('Native negativePrefill 11',ctx.ta.sma('Native negativePrefill 11',11).update(values['negativePrefill']))
    ctx.plot('Native holes 1',ctx.ta.sma('Native holes 1',1).update(values['holes']))
    ctx.plot('Native holes 2',ctx.ta.sma('Native holes 2',2).update(values['holes']))
    ctx.plot('Native holes 3',ctx.ta.sma('Native holes 3',3).update(values['holes']))
    ctx.plot('Native holes 7',ctx.ta.sma('Native holes 7',7).update(values['holes']))
    ctx.plot('Native holes 11',ctx.ta.sma('Native holes 11',11).update(values['holes']))
    ctx.plot('Native prefillHoles 1',ctx.ta.sma('Native prefillHoles 1',1).update(values['prefillHoles']))
    ctx.plot('Native prefillHoles 2',ctx.ta.sma('Native prefillHoles 2',2).update(values['prefillHoles']))
    ctx.plot('Native prefillHoles 3',ctx.ta.sma('Native prefillHoles 3',3).update(values['prefillHoles']))
    ctx.plot('Native prefillHoles 7',ctx.ta.sma('Native prefillHoles 7',7).update(values['prefillHoles']))
    ctx.plot('Native prefillHoles 11',ctx.ta.sma('Native prefillHoles 11',11).update(values['prefillHoles']))
