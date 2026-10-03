# ruff: noqa: F821
import numpy as np
import pyne_runtime.ta as batch_ta
indicator("Correlation observations",mode='incremental')
CASES = [['source', 'source', 1], ['source', 'source', 2], ['source', 'source', 3], ['source', 'source', 5], ['holes', 'source', 3], ['holes', 'holes', 3], ['holes', 'other', 3], ['leading', 'source', 3], ['flat', 'source', 3], ['source', 'holes', 3]]
COLUMNS = ['Native source source 1', 'Native source source 2', 'Native source source 3', 'Native source source 5', 'Native holes source 3', 'Native holes holes 3', 'Native holes other 3', 'Native leading source 3', 'Native flat source 3', 'Native source holes 3']
def sources(count):
    index = np.arange(count)
    source = ((index*7)%13-4.).astype(float)
    holes = np.where(np.isin(index,[1,7,8,12,23]),np.nan,source)
    other = np.where(np.isin(index,[2,7,11,12,17]),np.nan,source)
    leading = np.where(index<5,np.nan,source)
    flat = np.full(count,5.)
    return {'flat':flat,'holes':holes,'leading':leading,'other':other,'source':source}
NATIVE_RECIPE_EXECUTION_ROUTE = "generic_python_full_history_recompute"

def on_bar(ctx,bar):
    history = ctx.state("history",[]).value
    history.append(bar.close)
    values = sources(len(history))
    module = batch_ta.TaModule()
    for title,(a,b,p) in zip(COLUMNS,CASES,strict=True):
        ctx.plot(title,float(module.correlation(values[a],values[b],p)[-1]))
