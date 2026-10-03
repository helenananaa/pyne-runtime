# ruff: noqa: F821
import numpy as np
from pyne_runtime.utils import sum_
indicator("Overflow update order callback", mode="incremental")
# SMA uses direct helpers; math.sum uses a full-history Python recomputation.
NATIVE_RECIPE_EXECUTION_ROUTE = "generic_python_full_history_recompute"
def inputs(i):
    large = 160000000.0 * (10. ** 300)
    half = 80000000.0 * (10. ** 300)
    return dict(half=half, negativeHalf=-half,
                rotation=-large if i % 3 == 1 else large,
                negativeRotation=large if i % 3 == 1 else -large,
                recovery=large if i < 6 else float((i * 11) % 17 - 6) * .25,
                gapRecovery=large if i < 6 else None if i < 12 else float((i * 11) % 17 - 6) * .25)

def on_bar(ctx, bar):
    values = inputs(ctx.bar_index)
    rows = [inputs(i) for i in range(ctx.bar_index + 1)]
    history = np.asarray([row['half'] for row in rows], dtype=np.float64)
    ctx.plot('Native2 half', ctx.ta.sma('Native2 half', 2).update(values['half']))
    ctx.plot('Sum2 half', sum_(history, 2)[-1])
    ctx.plot('Native3 half', ctx.ta.sma('Native3 half', 3).update(values['half']))
    ctx.plot('Sum3 half', sum_(history, 3)[-1])
    history = np.asarray([row['negativeHalf'] for row in rows], dtype=np.float64)
    ctx.plot('Native2 negativeHalf', ctx.ta.sma('Native2 negativeHalf', 2).update(values['negativeHalf']))
    ctx.plot('Sum2 negativeHalf', sum_(history, 2)[-1])
    ctx.plot('Native3 negativeHalf', ctx.ta.sma('Native3 negativeHalf', 3).update(values['negativeHalf']))
    ctx.plot('Sum3 negativeHalf', sum_(history, 3)[-1])
    history = np.asarray([row['rotation'] for row in rows], dtype=np.float64)
    ctx.plot('Native2 rotation', ctx.ta.sma('Native2 rotation', 2).update(values['rotation']))
    ctx.plot('Sum2 rotation', sum_(history, 2)[-1])
    ctx.plot('Native3 rotation', ctx.ta.sma('Native3 rotation', 3).update(values['rotation']))
    ctx.plot('Sum3 rotation', sum_(history, 3)[-1])
    history = np.asarray([row['negativeRotation'] for row in rows], dtype=np.float64)
    ctx.plot('Native2 negativeRotation', ctx.ta.sma('Native2 negativeRotation', 2).update(values['negativeRotation']))
    ctx.plot('Sum2 negativeRotation', sum_(history, 2)[-1])
    ctx.plot('Native3 negativeRotation', ctx.ta.sma('Native3 negativeRotation', 3).update(values['negativeRotation']))
    ctx.plot('Sum3 negativeRotation', sum_(history, 3)[-1])
    history = np.asarray([row['recovery'] for row in rows], dtype=np.float64)
    ctx.plot('Native2 recovery', ctx.ta.sma('Native2 recovery', 2).update(values['recovery']))
    ctx.plot('Sum2 recovery', sum_(history, 2)[-1])
    ctx.plot('Native3 recovery', ctx.ta.sma('Native3 recovery', 3).update(values['recovery']))
    ctx.plot('Sum3 recovery', sum_(history, 3)[-1])
    history = np.asarray([row['gapRecovery'] for row in rows], dtype=np.float64)
    ctx.plot('Native2 gapRecovery', ctx.ta.sma('Native2 gapRecovery', 2).update(values['gapRecovery']))
    ctx.plot('Sum2 gapRecovery', sum_(history, 2)[-1])
    ctx.plot('Native3 gapRecovery', ctx.ta.sma('Native3 gapRecovery', 3).update(values['gapRecovery']))
    ctx.plot('Sum3 gapRecovery', sum_(history, 3)[-1])
