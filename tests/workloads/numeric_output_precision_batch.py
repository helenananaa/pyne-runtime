# ruff: noqa: F821
import numpy as np
indicator("Numeric output precision",precision=2)
def sources(count):
    index=np.arange(count)
    value=((index*11)%17-6.).astype(float)
    tiny=value/1.e11
    fractional=0.1234567891234567+value/1.e4
    gap=np.isin(index%7,[1,2])
    return dict(tiny=tiny,fractional=fractional,negative=-fractional,
        holes=np.where(gap,np.nan,tiny),leading=np.where(index<6,np.nan,tiny),
        flat=np.full(count,0.000000000001234567891234567),missing=np.full(count,np.nan),
        large=100000.12345678912+value/10.)
for name,value in sources(len(close)).items():
    plot(value,"Raw "+name,precision=0)
    plot(ta.sma(value,1),"SMA1 "+name)
    plot(ta.sma(value,3),"SMA3 "+name)
    middle,_,_=ta.bb(value,1,2.)
    plot(middle,"BB middle "+name)
