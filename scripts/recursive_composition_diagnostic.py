"""Verify initial native chart inputs independently of indicator outputs."""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = (("recursive_composition_ohlcv_holdout", "1M"), ("recursive_composition_weekly_holdout", "1W"))
INPUTS = ("time", "open", "high", "low", "close", "volume")
OUTPUTS = ("TR", "ATR1", "ATR3", "ATR7", "plus3", "minus3", "ADX3",
           "plus7", "minus7", "ADX7", "plus3x", "minus3x", "ADX3x")
SOURCE_SHA = "737d07c8a1d610cd15dcb437063f4a22fb28ef56da73f8a3f57e5fbab83a42c7"


def build_diagnostic(root=ROOT):
    spec = importlib.util.spec_from_file_location("composition_reporter", root / "scripts/official_alignment_report.py")
    reporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reporter)
    folder = root / "tests/workloads"
    supplied = []
    cases = []
    for name, timeframe in CASES:
        capture = json.loads((folder / (name + ".tradingview.json")).read_text(encoding="utf-8"))
        reporter.verify_evidence(folder, name, capture)
        selection = dict(firstNativeBarIndex=0, rows=64, atrPeriods=[1, 3, 7],
                         dmiPeriods=[[3, 3], [7, 7], [3, 7]], nativeIndicatorOutputsSuppliedAsInputs=False)
        if (capture["columns"] != list(INPUTS + OUTPUTS) or len(capture["rows"]) != 64
                or capture.get("scriptSha256") != SOURCE_SHA or capture.get("missingValueToken") != "NA"
                or capture.get("tolerance") != 1e-8 or capture.get("diagnosticOnly") is not False
                or capture.get("symbol") != "BINANCE:BTCUSDT" or capture.get("timeframe") != timeframe
                or capture.get("sourceExpressionClass") != "native_initial_ohlcv_compositions"
                or capture.get("selection") != selection):
            raise ValueError("Incomplete or incorrectly qualified native composition evidence")
        bars = reporter._bars(name, capture)
        native_inputs = [row["values"][:6] for row in capture["rows"]]
        if [list(bar.values()) for bar in bars] != native_inputs:
            raise ValueError("Supplied OHLCV differs from native source columns")
        times = [bar["time"] for bar in bars]
        if any(a >= b for a, b in zip(times, times[1:])):
            raise ValueError("Native source timestamps are not strictly increasing")
        dates = [datetime.fromtimestamp(value, timezone.utc) for value in times]
        if any(date.hour or date.minute or date.second for date in dates):
            raise ValueError("Native chart bar time is not UTC midnight")
        if timeframe == "1W" and any(b - a != 604800 for a, b in zip(times, times[1:])):
            raise ValueError("Native weekly input spacing differs")
        if timeframe == "1M" and (any(date.day != 1 for date in dates) or any(
                (b.year * 12 + b.month) - (a.year * 12 + a.month) != 1 for a, b in zip(dates, dates[1:]))):
            raise ValueError("Native monthly input spacing differs")
        for bar in bars:
            if (not all(math.isfinite(v) for v in bar.values()) or bar["volume"] < 0
                    or not bar["low"] <= min(bar["open"], bar["close"]) <= max(bar["open"], bar["close"]) <= bar["high"]):
                raise ValueError("Invalid native source OHLCV")
        supplied.append(native_inputs)
        cases.append(dict(name=name, timeframe=timeframe, rows=64, inputCellsVerified=384,
                          nativeOutputCells=832, datasetStartsAtNativeBarIndex=0))
    if supplied[0] == supplied[1]:
        raise ValueError("Independent chart datasets unexpectedly duplicate source inputs")
    return dict(schema="pyne.native-recursive-composition-input-diagnostic/1", cases=cases,
        inputCellsVerified=768, nativeNumericOutputCells=1664, nativeOutputColumnsPerCase=13,
        countedAsAdditionalRuntimeAgreement=False, acceptanceProved=False,
        qualification="Actual initial chart OHLCV is verified as source input, with indicator outputs excluded. All 13 outputs per case enter canonical comparisons. Monthly and independently selected weekly datasets do not qualify fabricated gaps, every instrument, or complete API behavior.")
