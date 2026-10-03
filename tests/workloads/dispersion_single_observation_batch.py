# ruff: noqa: F821
import numpy as np
indicator("Single observation dispersion")
def sources(count):
    index = np.arange(count)
    base = ((index*11)%17-6.).astype(float)
    holes = np.where(np.isin(index%7,[1,2]),np.nan,base)
    leading = np.where(index<6,np.nan,base)
    flat = np.full(count,5.)
    missing = np.full(count,np.nan)
    fractional = base/10.
    huge = 1.e12+base
    hugeHole = np.where(np.isin(index%7,[1,2]),np.nan,huge)
    return dict(base=base,holes=holes,leading=leading,flat=flat,missing=missing,
                fractional=fractional,huge=huge,hugeHole=hugeHole)
for name,value in sources(len(close)).items():
    plot(ta.stdev(value,1),"Stdev "+name)
    plot(ta.variance(value,1),"Population "+name)
    plot(ta.variance(value,1,False),"Sample "+name)
    middle,upper,lower = ta.bb(value,1,2.)
    plot(middle,"BB middle "+name)
    plot(upper,"BB upper "+name)
    plot(lower,"BB lower "+name)
