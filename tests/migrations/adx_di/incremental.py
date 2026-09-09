# This source code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/
# © BeikabuOyaji
#
# Namespaced Pine v5 adaptation of BeikabuOyaji ADX and DI.
# Public source: https://www.tradingview.com/script/VTPMMOrx-ADX-and-DI/
# This file remains MPL-2.0; it is not relicensed by the host package.

# ruff: noqa: F821

indicator("Pyne migration ADX DI 20260909", overlay=False, mode="incremental")

adx_len = int(params.get("len", 14))
if adx_len < 1:
    raise ValueError("len must be >= 1")
threshold = int(params.get("th", 20))


def init(ctx):
    ctx.ta.sma("adx", adx_len)


def on_bar(ctx, bar):
    prev_high = ctx.state("prev_high", 0.0)
    prev_low = ctx.state("prev_low", 0.0)
    prev_close = ctx.state("prev_close", 0.0)
    smoothed_tr = ctx.state("smoothed_tr", 0.0)
    smoothed_plus = ctx.state("smoothed_plus", 0.0)
    smoothed_minus = ctx.state("smoothed_minus", 0.0)

    prior_high = 0.0 if prev_high.value is None else float(prev_high.value)
    prior_low = 0.0 if prev_low.value is None else float(prev_low.value)
    prior_close = 0.0 if prev_close.value is None else float(prev_close.value)
    prev_tr = 0.0 if smoothed_tr.value is None else float(smoothed_tr.value)
    prev_plus = 0.0 if smoothed_plus.value is None else float(smoothed_plus.value)
    prev_minus = 0.0 if smoothed_minus.value is None else float(smoothed_minus.value)

    true_range = math.max(
        math.max(bar.high - bar.low, math.abs(bar.high - prior_close)),
        math.abs(bar.low - prior_close),
    )
    up_move = bar.high - prior_high
    down_move = prior_low - bar.low
    dm_plus = math.max(up_move, 0.0) if up_move > down_move else 0.0
    dm_minus = math.max(down_move, 0.0) if down_move > up_move else 0.0

    next_tr = prev_tr - (prev_tr / adx_len) + true_range
    next_plus = prev_plus - (prev_plus / adx_len) + dm_plus
    next_minus = prev_minus - (prev_minus / adx_len) + dm_minus
    smoothed_tr.value = next_tr
    smoothed_plus.value = next_plus
    smoothed_minus.value = next_minus

    missing = float("nan")
    if next_tr == 0:
        di_plus = None
        di_minus = None
        dx = None
    else:
        di_plus = next_plus / next_tr * 100.0
        di_minus = next_minus / next_tr * 100.0
        denom = di_plus + di_minus
        dx = missing if denom == 0 else math.abs(di_plus - di_minus) / denom * 100.0

    adx = ctx.ta.sma("adx").update(dx)
    ctx.plot("DIPlus", di_plus, title="DI+", color=color.green)
    ctx.plot("DIMinus", di_minus, title="DI-", color=color.red)
    ctx.plot("ADX", adx, title="ADX", color=color.navy)
    # Incremental has no hline API; preserve the reference as a constant plot.
    ctx.plot("Threshold", threshold, title="Threshold", color=color.black)

    prev_high.value = bar.high
    prev_low.value = bar.low
    prev_close.value = bar.close
