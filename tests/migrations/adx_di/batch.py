# This source code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/
# © BeikabuOyaji
#
# Namespaced Pine v5 adaptation of BeikabuOyaji ADX and DI.
# Public source: https://www.tradingview.com/script/VTPMMOrx-ADX-and-DI/
# This file remains MPL-2.0; it is not relicensed by the host package.

# ruff: noqa: F821

indicator("Pyne migration ADX DI 20260909", overlay=False)

adx_len = input.int(14, "len", minval=1)
th = input.int(20, "th")

high_vals = high.values
low_vals = low.values
close_vals = close.values
bar_count = high.__len__()

di_plus_out = []
di_minus_out = []
dx_out = []

prior_high = 0.0
prior_low = 0.0
prior_close = 0.0
smoothed_tr = 0.0
smoothed_plus = 0.0
smoothed_minus = 0.0
missing = float("nan")

for index in range(bar_count):
    bar_high = float(high_vals[index])
    bar_low = float(low_vals[index])
    bar_close = float(close_vals[index])
    true_range = float(
        math.max(
            math.max(bar_high - bar_low, math.abs(bar_high - prior_close)),
            math.abs(bar_low - prior_close),
        )
    )
    up_move = bar_high - prior_high
    down_move = prior_low - bar_low
    dm_plus = float(math.max(up_move, 0.0)) if up_move > down_move else 0.0
    dm_minus = float(math.max(down_move, 0.0)) if down_move > up_move else 0.0
    smoothed_tr = smoothed_tr - (smoothed_tr / adx_len) + true_range
    smoothed_plus = smoothed_plus - (smoothed_plus / adx_len) + dm_plus
    smoothed_minus = smoothed_minus - (smoothed_minus / adx_len) + dm_minus
    if smoothed_tr == 0.0:
        di_plus = missing
        di_minus = missing
        dx = missing
    else:
        di_plus = smoothed_plus / smoothed_tr * 100.0
        di_minus = smoothed_minus / smoothed_tr * 100.0
        denom = di_plus + di_minus
        if denom == 0.0:
            dx = missing
        else:
            dx = abs(di_plus - di_minus) / denom * 100.0
    di_plus_out.append(di_plus)
    di_minus_out.append(di_minus)
    dx_out.append(dx)
    prior_high = bar_high
    prior_low = bar_low
    prior_close = bar_close

di_plus_series = close.with_values(di_plus_out)
di_minus_series = close.with_values(di_minus_out)
dx_series = close.with_values(dx_out)
adx_series = ta.sma(dx_series, adx_len)

plot(di_plus_series, "DI+", color=color.green)
plot(di_minus_series, "DI-", color=color.red)
plot(adx_series, "ADX", color=color.navy)
hline(th, color=color.black)
