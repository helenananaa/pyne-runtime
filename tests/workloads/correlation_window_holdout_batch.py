# ruff: noqa: F821
import numpy as np
indicator("Correlation observations",mode='batch')
CASES = [['base', 'base', 1], ['base', 'base', 2], ['base', 'base', 3], ['base', 'base', 7], ['holes', 'base', 1], ['holes', 'base', 2], ['holes', 'base', 3], ['holes', 'base', 7], ['holes', 'other', 1], ['holes', 'other', 2], ['holes', 'other', 3], ['holes', 'other', 7], ['holes', 'shifted', 1], ['holes', 'shifted', 2], ['holes', 'shifted', 3], ['holes', 'shifted', 7], ['leading', 'base', 1], ['leading', 'base', 2], ['leading', 'base', 3], ['leading', 'base', 7], ['flat', 'base', 1], ['flat', 'base', 2], ['flat', 'base', 3], ['flat', 'base', 7], ['hugeA', 'hugeB', 1], ['hugeA', 'hugeB', 2], ['hugeA', 'hugeB', 3], ['hugeA', 'hugeB', 7], ['hugeHole', 'hugeB', 1], ['hugeHole', 'hugeB', 2], ['hugeHole', 'hugeB', 3], ['hugeHole', 'hugeB', 7]]
COLUMNS = ['Native base base 1', 'Native base base 2', 'Native base base 3', 'Native base base 7', 'Native holes base 1', 'Native holes base 2', 'Native holes base 3', 'Native holes base 7', 'Native holes other 1', 'Native holes other 2', 'Native holes other 3', 'Native holes other 7', 'Native holes shifted 1', 'Native holes shifted 2', 'Native holes shifted 3', 'Native holes shifted 7', 'Native leading base 1', 'Native leading base 2', 'Native leading base 3', 'Native leading base 7', 'Native flat base 1', 'Native flat base 2', 'Native flat base 3', 'Native flat base 7', 'Native hugeA hugeB 1', 'Native hugeA hugeB 2', 'Native hugeA hugeB 3', 'Native hugeA hugeB 7', 'Native hugeHole hugeB 1', 'Native hugeHole hugeB 2', 'Native hugeHole hugeB 3', 'Native hugeHole hugeB 7']
def sources(count):
    index = np.arange(count)
    base = ((index*11)%17-6.).astype(float)
    holes = np.where(np.isin(index%7,[1,2]),np.nan,base)
    other = np.where(index%5==3,np.nan,-3*base+5)
    shifted = np.where(index%5==3,np.nan,1000+base*.25)
    leading = np.where(index<6,np.nan,base)
    flat = np.full(count,5.)
    hugeA = 1.e12+base
    hugeB = -7.e11+base*2
    hugeHole = np.where(np.isin(index%7,[1,2]),np.nan,hugeA)
    return {'base':base,'flat':flat,'holes':holes,'hugeA':hugeA,'hugeB':hugeB,'hugeHole':hugeHole,'leading':leading,'other':other,'shifted':shifted}
values = sources(len(close))
for title,(a,b,p) in zip(COLUMNS,CASES,strict=True):
    plot(ta.correlation(values[a],values[b],p),title)
