# ruff: noqa: F821
import numpy as np
indicator("Correlation arithmetic decomposition",mode="batch")
CASES = [['base', 'base', 3], ['holes', 'shifted', 3], ['hugeA', 'hugeB', 2], ['hugeA', 'hugeB', 3], ['hugeA', 'hugeB', 7], ['hugeHole', 'hugeB', 3], ['hugeHole', 'hugeB', 7], ['hugeA', 'hugeA', 3]]
COLUMNS = ['Native base base 3', 'Native holes shifted 3', 'Native hugeA hugeB 2', 'Native hugeA hugeB 3', 'Native hugeA hugeB 7', 'Native hugeHole hugeB 3', 'Native hugeHole hugeB 7', 'Native hugeA hugeA 3']
def sources(count):
    index = np.arange(count)
    base = ((index*11)%17-6.).astype(float)
    holes = np.where(np.isin(index%7,[1,2]),np.nan,base)
    shifted = np.where(index%5==3,np.nan,1000+base*.25)
    hugeA = 1.e12+base
    hugeB = -7.e11+base*2
    hugeHole = np.where(np.isin(index%7,[1,2]),np.nan,hugeA)
    return dict(base=base,holes=holes,shifted=shifted,hugeA=hugeA,hugeB=hugeB,hugeHole=hugeHole)
values = sources(len(close))
for title,(a,b,p) in zip(COLUMNS,CASES,strict=True):
    plot(ta.correlation(values[a],values[b],p),title)
