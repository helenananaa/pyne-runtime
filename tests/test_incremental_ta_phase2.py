from __future__ import annotations

import math

import pyne_runtime as pn
import pytest


def _bars(count: int = 48) -> list[dict[str, float]]:
    bars = []
    for index in range(count):
        base = 100.0 + index * 0.15 + math.sin(index / 2.5) * 3.0
        close = base + math.sin(index * 0.7)
        bars.append(
            {
                "time": (index + 1) * 60,
                "open": base - 0.4,
                "high": max(base, close) + 1.2 + (index % 3) * 0.1,
                "low": min(base, close) - 1.1 - (index % 2) * 0.2,
                "close": close,
                "volume": 100.0 + (index % 7) * 13.0,
            }
        )
    return bars


BATCH_SCRIPT = """
indicator("TA Phase 2")
source = hlc3
hma = ta.hma(close, 9)
plus_di, minus_di, adx = ta.dmi(5, 3)
sar = ta.sar(0.02, 0.02, 0.2)
mfi = ta.mfi(source, 5)
over = ta.crossover(close, hma)
under = ta.crossunder(close, hma)
either = ta.cross(close, hma)
since = ta.barssince(over)
sample = ta.valuewhen(over, close, 1)
anchor = bar_index % 12 == 0
vwap, upper, lower = ta.vwap(source, anchor, 1.5)
plot(hma, "HMA")
plot(plus_di, "Plus DI")
plot(minus_di, "Minus DI")
plot(adx, "ADX")
plot(sar, "SAR")
plot(mfi, "MFI")
plot(over, "Cross Over")
plot(under, "Cross Under")
plot(either, "Cross")
plot(since, "Bars Since")
plot(sample, "Value When")
plot(vwap, "VWAP")
plot(upper, "VWAP Upper")
plot(lower, "VWAP Lower")
"""


INCREMENTAL_SCRIPT = """
indicator("TA Phase 2", mode="incremental")

def init(ctx):
    ctx.ta.hma("hma", 9)
    ctx.ta.dmi("dmi", 5, 3)
    ctx.ta.sar("sar", 0.02, 0.02, 0.2)
    ctx.ta.mfi("mfi", 5)
    ctx.ta.crossover("over")
    ctx.ta.crossunder("under")
    ctx.ta.cross("either")
    ctx.ta.barssince("since")
    ctx.ta.valuewhen("sample", 1)
    ctx.ta.vwap("vwap")

def on_bar(ctx, bar):
    source = (bar.high + bar.low + bar.close) / 3.0
    hma = ctx.ta.hma("hma").update(bar.close)
    plus_di, minus_di, adx = ctx.ta.dmi("dmi").update(bar)
    sar = ctx.ta.sar("sar").update(bar)
    mfi = ctx.ta.mfi("mfi").update(source, bar.volume)
    over = ctx.ta.crossover("over").update(bar.close, hma)
    under = ctx.ta.crossunder("under").update(bar.close, hma)
    either = ctx.ta.cross("either").update(bar.close, hma)
    since = ctx.ta.barssince("since").update(over)
    sample = ctx.ta.valuewhen("sample").update(over, bar.close)
    vwap, upper, lower = ctx.ta.vwap("vwap").update(
        source,
        bar.volume,
        anchor=bar.bar_index % 12 == 0,
        stdev_mult=1.5,
    )
    ctx.plot("HMA", hma)
    ctx.plot("Plus DI", plus_di)
    ctx.plot("Minus DI", minus_di)
    ctx.plot("ADX", adx)
    ctx.plot("SAR", sar)
    ctx.plot("MFI", mfi)
    ctx.plot("Cross Over", over)
    ctx.plot("Cross Under", under)
    ctx.plot("Cross", either)
    ctx.plot("Bars Since", since)
    ctx.plot("Value When", sample)
    ctx.plot("VWAP", vwap)
    ctx.plot("VWAP Upper", upper)
    ctx.plot("VWAP Lower", lower)
"""


def _line_values(result: pn.PyneResult) -> dict[str, list[float | None]]:
    return {
        line["name"]: [point["value"] for point in line["data"]]
        for line in result.lines
    }


def test_incremental_ta_phase2_matches_batch_runtime() -> None:
    report = pn.run_incremental_parity(
        batch_script=BATCH_SCRIPT,
        incremental_script=INCREMENTAL_SCRIPT,
        bars=_bars(),
        settings=pn.PyneSettings(executor_mode="inline", timeframe="1"),
        normalizer=_line_values,
    )

    # Raw binary64 payloads expose different arithmetic evaluation orders.
    # This numerical control is stricter than the old eight-decimal output
    # comparison; the public parity comparator itself stays exact.
    assert report.batch_result.ok and report.incremental_result.ok
    batch = {line['name']:line['data'] for line in report.batch_result.lines}
    incremental = {line['name']:line['data'] for line in report.incremental_result.lines}
    assert batch.keys() == incremental.keys()
    for name,expected in batch.items():
        actual = incremental[name]
        assert [p['time'] for p in actual] == [p['time'] for p in expected]
        assert [p['value'] for p in actual] == pytest.approx(
            [p['value'] for p in expected],abs=1e-12,rel=0),name


def test_incremental_ta_phase2_survives_portable_restore() -> None:
    bars = _bars()
    settings = pn.PyneSettings(executor_mode="inline", timeframe="1")
    original = pn.PyneIncrementalSession(script=INCREMENTAL_SCRIPT, settings=settings)
    original.seed(bars[:31])

    restored = pn.PyneIncrementalSession.from_portable_snapshot(
        original.snapshot_portable(),
        script=INCREMENTAL_SCRIPT,
        settings=settings,
    )

    for bar in bars[31:]:
        assert restored.on_bar_closed(bar) == original.on_bar_closed(bar)
