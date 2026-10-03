"""Native Pine weighted-window evidence, including missing samples and composition."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pyne_runtime as pn
import pytest

ROOT = Path(__file__).parent / "workloads"
CAPTURE = json.loads((ROOT / "weighted_boundaries.tradingview.json").read_text(encoding="utf-8"))


def _script(name):
    return (ROOT / f"{name}.py").read_text(encoding="utf-8")


def _bars(count=32):
    return [dict(time=i * 60, open=1, high=2, low=0, close=1, volume=10) for i in range(count)]


def _assert_result(result, count):
    assert result.ok, result.error
    lines = {line["name"]: {p["time"]: p["value"] for p in line["data"]} for line in result.lines}
    for col, title in enumerate(CAPTURE["columns"][3:], 3):
        expected = {
            row["index"] * 60: row["values"][col]
            for row in CAPTURE["rows"][:count]
            if row["values"][col] is not None
        }
        actual = lines.get(title, {})
        assert actual.keys() == expected.keys(), title
        assert actual == pytest.approx(expected, abs=CAPTURE["tolerance"], rel=0), title


@pytest.mark.parametrize("name, marker", (
    ("weighted_boundaries", "PYNE_WEIGHTED"),
    ("wma_gap_confirmation", "PYNE_WMA_CONFIRM"),
))
def test_official_weighted_capture_identity(name, marker):
    capture = json.loads((ROOT / f"{name}.tradingview.json").read_text(encoding="utf-8"))
    for suffix, key in (("pine", "scriptSha256"), ("tradingview.txt", "logSha256")):
        raw = (ROOT / f"{name}.{suffix}").read_text(encoding="utf-8")
        assert hashlib.sha256(raw.encode()).hexdigest() == capture[key]
    raw = (ROOT / f"{name}.tradingview.txt").read_text(encoding="utf-8")
    rows = [
        {"index": int(m[1]), "values": [None if v == "NaN" else float(v) for v in m[2].split("|")]}
        for m in re.finditer(marker + r"\|(\d+)\|([^;]+);", raw)
    ]
    assert rows == capture["rows"]
    assert [row["index"] for row in rows] == list(range(32))
    assert all(len(row["values"]) == len(capture["columns"]) for row in rows)


def test_second_native_capture_disambiguates_warmup_and_gap_weights():
    from pyne_runtime.ta import TaModule

    capture = json.loads((ROOT / "wma_gap_confirmation.tradingview.json").read_text(encoding="utf-8"))
    rows = np.asarray([row["values"] for row in capture["rows"]], dtype=float)
    module = TaModule()
    wma = module.wma(rows[:, 0], 3)
    for actual, col in ((wma, 2), (module.wma(rows[:, 0], 5), 4), (module.wma(wma, 3), 6)):
        np.testing.assert_allclose(actual, rows[:, col], rtol=0, atol=1e-8, equal_nan=True)
    # Carrying values explains weights after warmup, but must not make native
    # WMA ready before it has received period real observations.
    assert np.isnan(rows[2, 2]) and rows[2, 3] == -3.5
    assert np.isnan(rows[4, 4]) and rows[4, 5] == -1
    np.testing.assert_allclose(rows[5:, 2], rows[5:, 3], rtol=0, atol=0, equal_nan=True)
    np.testing.assert_allclose(rows[5:, 4], rows[5:, 5], rtol=0, atol=0, equal_nan=True)
    np.testing.assert_allclose(rows[:, 6], rows[:, 7], rtol=0, atol=0, equal_nan=True)


@pytest.mark.parametrize("name", ("weighted_boundaries", "weighted_boundaries_batch"))
@pytest.mark.parametrize("count", (1, 3, 4, 6, 9, 11, 14, 25, 32))
def test_official_weighted_prefix(name, count):
    _assert_result(pn.run(_script(name), _bars(count), executor_mode="inline"), count)


@pytest.mark.parametrize("mode", ("local", "replay", "state"))
@pytest.mark.parametrize("cut", (3, 8, 9, 13, 24))
def test_weighted_preview_and_restore(mode, cut):
    script = _script("weighted_boundaries")
    settings = pn.PyneSettings(executor_mode="inline")
    session = pn.PyneIncrementalSession(script=script, settings=settings)
    data = _bars()
    session.seed(data[:cut])
    committed = session.snapshot_result()
    _assert_result(committed, cut)
    for offset in (10, 20):
        session.on_bar_updated(dict(data[cut], high=30 + offset, close=10 + offset))
        assert session.snapshot_result() == committed
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(
            session.snapshot_state(), script=script, settings=settings,
        )
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(
            session.snapshot_portable(mode=mode), script=script, settings=settings,
        )
    assert restored.snapshot_result() == committed
    for bar in data[cut:]:
        restored.on_bar_closed(bar)
    _assert_result(restored.snapshot_result(), len(data))


@pytest.mark.parametrize("period", (1, 2, 3, 5, 17))
def test_wma_matches_independent_gap_window(period):
    from pyne_runtime.incremental.ta import _StepWMA
    from pyne_runtime.ta import TaModule

    source = [None if i % 7 in (1, 2) or i > 45 else float((i * 11) % 19 - 8) for i in range(50)]
    expected = []
    window = []
    observations = 0
    previous = None
    for value in source:
        if value is not None:
            observations += 1
            previous = value
        window.append(previous)
        window = window[-period:]
        expected.append(
            sum(weight * sample for weight, sample in enumerate(window, 1))
            / (period * (period + 1) / 2)
            if value is not None and observations >= period else np.nan
        )
    actual = TaModule().wma(np.asarray(source, dtype=float), period)
    np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-12, equal_nan=True)
    step = _StepWMA(period)
    incremental = [step.update(value) for value in source]
    np.testing.assert_allclose(np.asarray(incremental, dtype=float), expected, rtol=0, atol=1e-12)
