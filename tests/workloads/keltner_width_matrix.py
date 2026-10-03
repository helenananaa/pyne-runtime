# ruff: noqa: F821
import numpy as np
import pyne_runtime.ta as batch_ta

indicator("Keltner generic Python replay", mode="incremental")

def init(ctx):
    ctx.state("ohlc", [])
    # Literal titles disclose completely missing outputs to static diagnostics.
    ctx.plot("KC case13 upper", None)
    ctx.plot("KC case13 middle", None)
    ctx.plot("KC case13 lower", None)
    ctx.plot("KC case14 upper", None)
    ctx.plot("KC case14 middle", None)
    ctx.plot("KC case14 lower", None)

def on_bar(ctx, bar):
    history = ctx.state("ohlc").value
    history.append((bar.high, bar.low, bar.close))
    values = np.asarray(history, dtype=float)
    close = values[:, 2]
    i = np.arange(len(close))
    sources = {
        "close": close,
        "holes": np.where(np.isin(i, [1, 7, 8, 12, 23]), np.nan, close),
        "leading": np.where(i < 5, np.nan, close),
        "empty": np.full(len(close), np.nan),
    }
    cases = [("close", p, 1.5, tr) for p in (1, 3, 7) for tr in (True, False)]
    cases += [("close", 3, .5, tr) for tr in (True, False)] + [("close", 3, 2.5, True)]
    cases += [(name, 3, 1.5, tr) for name in ("holes", "leading", "empty") for tr in (True, False)]
    module = batch_ta.TaModule()
    for case_id, (name, period, mult, tr) in enumerate(cases):
        output = module.keltner(period, mult, values[:, 0], values[:, 1], close,
                                source=sources[name], use_true_range=tr)
        for side, result in zip(("upper", "middle", "lower"), output):
            ctx.plot("KC case" + str(case_id) + " " + side, result[-1])
