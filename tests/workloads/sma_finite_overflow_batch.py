# ruff: noqa: F821
import numpy as np
indicator("Finite overflow SMA",mode="batch")
def inputs(i):
    large = 160000000.0 * (10. ** 300)
    return dict(positive=large, negative=-large, mixed=large if i % 2 == 0 else -large,
                recovery=large if i < 6 else float((i * 11) % 17 - 6) * .25)
rows = [inputs(i) for i in range(len(close))]
values = np.asarray([row['positive'] for row in rows],dtype=np.float64)
plot(ta.sma(values,1),'Native1 positive')
plot(ta.sma(values,2),'Native2 positive')
plot(ta.sma(values,3),'Native3 positive')
values = np.asarray([row['negative'] for row in rows],dtype=np.float64)
plot(ta.sma(values,1),'Native1 negative')
plot(ta.sma(values,2),'Native2 negative')
plot(ta.sma(values,3),'Native3 negative')
values = np.asarray([row['mixed'] for row in rows],dtype=np.float64)
plot(ta.sma(values,1),'Native1 mixed')
plot(ta.sma(values,2),'Native2 mixed')
plot(ta.sma(values,3),'Native3 mixed')
values = np.asarray([row['recovery'] for row in rows],dtype=np.float64)
plot(ta.sma(values,1),'Native1 recovery')
plot(ta.sma(values,2),'Native2 recovery')
plot(ta.sma(values,3),'Native3 recovery')
