# ruff: noqa: F821
import numpy as np
indicator("Overflow update order", mode="batch")
def inputs(i):
    large = 160000000.0 * (10. ** 300)
    half = 80000000.0 * (10. ** 300)
    return dict(half=half, negativeHalf=-half,
                rotation=-large if i % 3 == 1 else large,
                negativeRotation=large if i % 3 == 1 else -large,
                recovery=large if i < 6 else float((i * 11) % 17 - 6) * .25,
                gapRecovery=large if i < 6 else None if i < 12 else float((i * 11) % 17 - 6) * .25)

rows = [inputs(i) for i in range(len(close))]
values = np.asarray([row['half'] for row in rows], dtype=np.float64)
plot(ta.sma(values, 2), 'Native2 half')
plot(math.sum(values, 2), 'Sum2 half')
plot(ta.sma(values, 3), 'Native3 half')
plot(math.sum(values, 3), 'Sum3 half')
values = np.asarray([row['negativeHalf'] for row in rows], dtype=np.float64)
plot(ta.sma(values, 2), 'Native2 negativeHalf')
plot(math.sum(values, 2), 'Sum2 negativeHalf')
plot(ta.sma(values, 3), 'Native3 negativeHalf')
plot(math.sum(values, 3), 'Sum3 negativeHalf')
values = np.asarray([row['rotation'] for row in rows], dtype=np.float64)
plot(ta.sma(values, 2), 'Native2 rotation')
plot(math.sum(values, 2), 'Sum2 rotation')
plot(ta.sma(values, 3), 'Native3 rotation')
plot(math.sum(values, 3), 'Sum3 rotation')
values = np.asarray([row['negativeRotation'] for row in rows], dtype=np.float64)
plot(ta.sma(values, 2), 'Native2 negativeRotation')
plot(math.sum(values, 2), 'Sum2 negativeRotation')
plot(ta.sma(values, 3), 'Native3 negativeRotation')
plot(math.sum(values, 3), 'Sum3 negativeRotation')
values = np.asarray([row['recovery'] for row in rows], dtype=np.float64)
plot(ta.sma(values, 2), 'Native2 recovery')
plot(math.sum(values, 2), 'Sum2 recovery')
plot(ta.sma(values, 3), 'Native3 recovery')
plot(math.sum(values, 3), 'Sum3 recovery')
values = np.asarray([row['gapRecovery'] for row in rows], dtype=np.float64)
plot(ta.sma(values, 2), 'Native2 gapRecovery')
plot(math.sum(values, 2), 'Sum2 gapRecovery')
plot(ta.sma(values, 3), 'Native3 gapRecovery')
plot(math.sum(values, 3), 'Sum3 gapRecovery')
