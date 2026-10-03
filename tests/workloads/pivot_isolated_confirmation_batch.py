# ruff: noqa: F821
import numpy as np
indicator("Isolated pivot baseline")
i = np.arange(len(close))
j = i % 8
left_high = np.array([4,np.nan,3,2,1,0,0,0])[j]
right_high = np.array([1,2,3,np.nan,4,0,0,0])[j]
ties = np.array([1,2,3,3,2,1,0,0])[j]
wave = np.array([2,1,2,3,4,3,4,5,6,3,2,1],dtype=float)[i % 12]
holes = np.where(np.isin(i,[5,17,18]),np.nan,wave)
plot(ta.pivothigh(left_high,2,2),'Pivot high left gap')
plot(ta.pivothigh(right_high,2,2),'Pivot high right gap')
plot(ta.pivotlow(-left_high,2,2),'Pivot low left gap')
plot(ta.pivotlow(-right_high,2,2),'Pivot low right gap')
plot(ta.pivothigh(ties,2,2),'Pivot high repeated')
plot(ta.pivotlow(-ties,2,2),'Pivot low repeated')
plot(ta.pivothigh(100.0-i,2,2),'Pivot high descending')
plot(ta.pivotlow(i.astype(float),2,2),'Pivot low ascending')
plot(ta.pivothigh(np.full(len(close),5.0),2,0),'Pivot high flat')
plot(ta.pivotlow(np.full(len(close),5.0),2,0),'Pivot low flat')
plot(when(ta.rising(wave,3),1.0,0.0),"Rising native")
plot(when(ta.rising(holes,3),1.0,0.0),"Rising holes")
