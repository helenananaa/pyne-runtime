# ruff: noqa: F821
indicator("Single observation dispersion",mode="incremental")
def values_at(index):
    base = float((index*11)%17-6)
    huge = 1.e12+base
    gap = index%7 in (1,2)
    return dict(base=base,holes=None if gap else base,leading=None if index<6 else base,
                flat=5.,missing=None,fractional=base/10.,huge=huge,hugeHole=None if gap else huge)
NAMES = ['base', 'holes', 'leading', 'flat', 'missing', 'fractional', 'huge', 'hugeHole']
def init(ctx):
    for name in NAMES:
        ctx.ta.stdev("Stdev "+name,1)
        ctx.ta.variance("Population "+name,1)
        ctx.ta.variance("Sample "+name,1,biased=False)
        ctx.ta.bb("BB "+name,1,mult=2.)

def on_bar(ctx,bar):
    for name,value in values_at(ctx.bar_index).items():
        ctx.plot("Stdev "+name,ctx.ta.stdev("Stdev "+name).update(value))
        ctx.plot("Population "+name,ctx.ta.variance("Population "+name).update(value))
        ctx.plot("Sample "+name,ctx.ta.variance("Sample "+name,biased=False).update(value))
        middle,upper,lower = ctx.ta.bb("BB "+name).update(value)
        ctx.plot("BB middle "+name,middle)
        ctx.plot("BB upper "+name,upper)
        ctx.plot("BB lower "+name,lower)
