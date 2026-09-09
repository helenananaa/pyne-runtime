"""Independent TradingView evidence for EMA/MACD/RSI missing-value semantics."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pyne_runtime as pn
import pytest


ROOT = Path(__file__).parent / "workloads"
CAPTURE = json.loads((ROOT / "ema_rsi.tradingview.json").read_text(encoding="utf-8"))


def _source(name):
    return (ROOT / f"{name}.py").read_text(encoding="utf-8")


def _bars(count=18):
    sequence = (1, 4, 2, 5, 3, 6, 2, 4)
    return [
        {
            "time": i * 60,
            "open": sequence[i % 8],
            "high": sequence[i % 8] + 1,
            "low": sequence[i % 8] - 1,
            "close": sequence[i % 8],
            "volume": 10,
        }
        for i in range(count)
    ]


def _assert_capture(result, *, end=18, start=0):
    assert result.ok, result.error
    lines = {line["name"]: line["data"] for line in result.lines}
    for column, title in enumerate(CAPTURE["columns"][3:], 3):
        expected = {
            row["index"] * 60: round(row["values"][column], 8)
            for row in CAPTURE["rows"]
            if start <= row["index"] < end and row["values"][column] is not None
        }
        actual = {p["time"]: p["value"] for p in lines.get(title, [])}
        assert actual.keys() == expected.keys(), title
        assert actual == pytest.approx(expected, abs=CAPTURE["tolerance"], rel=0), title


def test_external_boundary_evidence_identity():
    for suffix, key in (("pine", "scriptSha256"), ("tradingview.txt", "logSha256")):
        content = (ROOT / f"ema_rsi.{suffix}").read_text(encoding="utf-8")
        assert hashlib.sha256(content.encode()).hexdigest() == CAPTURE[key]
    raw = (ROOT / "ema_rsi.tradingview.txt").read_text(encoding="utf-8")
    rows = [
        {"index": int(m[1]), "values": [None if v == "NaN" else float(v) for v in m[2].split("|")]}
        for m in re.finditer(r"PYNE_EDGE\|(\d+)\|([^;]+);", raw)
    ]
    assert rows == CAPTURE["rows"]
    assert [r["index"] for r in rows] == list(range(18))
    for row, bar in zip(rows, _bars()):
        i = row["index"]
        assert row["values"][:3] == [
            bar["close"],
            None if i < 3 else bar["close"],
            None if i in (1, 7, 12) else bar["close"],
        ]


@pytest.mark.parametrize("name", ("ema_rsi", "ema_rsi_batch"))
@pytest.mark.parametrize("end", (1, 3, 6, 8, 13, 18))
def test_ema_macd_rsi_match_external_prefixes(name, end):
    _assert_capture(pn.run(_source(name), _bars(end), executor_mode="inline"), end=end)


@pytest.mark.parametrize("mode", ("local", "replay", "state"))
@pytest.mark.parametrize("cut", (2, 5, 8, 13))
def test_boundary_states_restore_during_seed_and_after_missing_values(mode, cut):
    source = _source("ema_rsi")
    settings = pn.PyneSettings(executor_mode="inline", timeframe="1")
    session = pn.PyneIncrementalSession(script=source, settings=settings)
    session.seed(_bars()[:cut])
    before = session.snapshot_result()
    for offset in (30, 50):
        bar = _bars()[cut]
        session.on_bar_updated(dict(bar, close=bar["close"] + offset, high=bar["high"] + 50))
        assert session.snapshot_result() == before
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(
            session.snapshot_state(), script=source, settings=settings
        )
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(
            session.snapshot_portable(mode=mode), script=source, settings=settings
        )
    assert restored.snapshot_result() == before
    for bar in _bars()[cut:]:
        restored.on_bar_closed(bar)
    _assert_capture(restored.snapshot_result())


@pytest.mark.parametrize("name", ("smoothing", "smoothing_batch"))
def test_nested_smoothing_matches_external_capture(name):
    capture = json.loads((ROOT / "smoothing.tradingview.json").read_text(encoding="utf-8"))
    for suffix, key in (("pine", "scriptSha256"), ("tradingview.txt", "logSha256")):
        content = (ROOT / f"smoothing.{suffix}").read_text(encoding="utf-8")
        assert hashlib.sha256(content.encode()).hexdigest() == capture[key]
    raw = (ROOT / "smoothing.tradingview.txt").read_text(encoding="utf-8")
    parsed = [
        {"index": int(m[1]), "values": [None if v == "NaN" else float(v) for v in m[2].split("|")]}
        for m in re.finditer(r"PYNE_SMOOTH\|(\d+)\|([^;]+);", raw)
    ]
    assert parsed == capture["rows"]
    assert [r["index"] for r in parsed] == list(range(18))
    result = pn.run(_source(name), _bars(), executor_mode="inline")
    assert result.ok, result.error
    titles = capture["columns"] if name.endswith("batch") else capture["columns"][:1]
    for column, title in enumerate(titles):
        actual = {p["time"]: p["value"] for p in result.get_series(title)}
        expected = {
            row["index"] * 60: round(row["values"][column], 8)
            for row in parsed
            if row["values"][column] is not None
        }
        assert actual.keys() == expected.keys(), title
        assert actual == pytest.approx(expected, abs=capture["tolerance"], rel=0), title
