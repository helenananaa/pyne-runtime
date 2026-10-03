# ruff: noqa: F821
import numpy as np
import pyne_runtime.ta as batch_ta
indicator("Correlation arithmetic decomposition",mode="incremental")
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
NATIVE_RECIPE_EXECUTION_ROUTE = "generic_python_full_history_recompute"

def on_bar(ctx,bar):
    history = ctx.state("history",[]).value
    history.append(bar.close)
    values = sources(len(history))
    module = batch_ta.TaModule()
    for title,(a,b,p) in zip(COLUMNS,CASES,strict=True):
        ctx.plot(title,float(module.correlation(values[a],values[b],p)[-1]))
