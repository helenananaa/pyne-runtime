# ruff: noqa: F821
indicator("Numeric output precision",mode="incremental",precision=2)
def values_at(index):
    value=float((index*11)%17-6)
    tiny=value/1.e11
    fractional=0.1234567891234567+value/1.e4
    gap=index%7 in (1,2)
    return dict(tiny=tiny,fractional=fractional,negative=-fractional,
        holes=None if gap else tiny,leading=None if index<6 else tiny,
        flat=0.000000000001234567891234567,missing=None,
        large=100000.12345678912+value/10.)
NAMES=['tiny','fractional','negative','holes','leading','flat','missing','large']
def init(ctx):
    for name in NAMES:
        ctx.ta.sma("SMA1 "+name,1)
        ctx.ta.sma("SMA3 "+name,3)
        ctx.ta.bb("BB "+name,1,mult=2.)
def on_bar(ctx,bar):
    for name,value in values_at(ctx.bar_index).items():
        ctx.plot("Raw "+name,value)
        ctx.plot("SMA1 "+name,ctx.ta.sma("SMA1 "+name).update(value))
        ctx.plot("SMA3 "+name,ctx.ta.sma("SMA3 "+name).update(value))
        middle,_,_=ctx.ta.bb("BB "+name).update(value)
        ctx.plot("BB middle "+name,middle)
