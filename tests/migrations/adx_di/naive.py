# This source code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/
# © BeikabuOyaji
#
# Namespaced Pine v5 adaptation of BeikabuOyaji ADX and DI.
# Public source: https://www.tradingview.com/script/VTPMMOrx-ADX-and-DI/
# This file remains MPL-2.0; it is not relicensed by the host package.
#
# First transliteration: Python series if/ternary, not a corrected runtime.

# ruff: noqa: F821

indicator("Pyne migration ADX DI 20260909", overlay=False)

adx_len = input.int(14, "len", minval=1)
th = input.int(20, "th")

TrueRange = math.max(
    math.max(high - low, math.abs(high - nz(close[1]))),
    math.abs(low - nz(close[1])),
)
DirectionalMovementPlus = (
    math.max(high - nz(high[1]), 0) if high - nz(high[1]) > nz(low[1]) - low else 0
)
DirectionalMovementMinus = (
    math.max(nz(low[1]) - low, 0) if nz(low[1]) - low > high - nz(high[1]) else 0
)

if bar_index == 0:
    SmoothedTrueRange = TrueRange
    SmoothedDirectionalMovementPlus = DirectionalMovementPlus
    SmoothedDirectionalMovementMinus = DirectionalMovementMinus
else:
    SmoothedTrueRange = (
        nz(SmoothedTrueRange[1])
        - (nz(SmoothedTrueRange[1]) / adx_len)
        + TrueRange
    )
    SmoothedDirectionalMovementPlus = (
        nz(SmoothedDirectionalMovementPlus[1])
        - (nz(SmoothedDirectionalMovementPlus[1]) / adx_len)
        + DirectionalMovementPlus
    )
    SmoothedDirectionalMovementMinus = (
        nz(SmoothedDirectionalMovementMinus[1])
        - (nz(SmoothedDirectionalMovementMinus[1]) / adx_len)
        + DirectionalMovementMinus
    )

DIPlus = SmoothedDirectionalMovementPlus / SmoothedTrueRange * 100
DIMinus = SmoothedDirectionalMovementMinus / SmoothedTrueRange * 100
DX = math.abs(DIPlus - DIMinus) / (DIPlus + DIMinus) * 100
ADX = ta.sma(DX, adx_len)

plot(DIPlus, color=color.green, title="DI+")
plot(DIMinus, color=color.red, title="DI-")
plot(ADX, color=color.navy, title="ADX")
hline(th, color=color.black)
