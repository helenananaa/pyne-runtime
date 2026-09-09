"""Native Supertrend/VWMA and explicit-volume Pine formula evidence."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pyne_runtime as pn
import pytest

ROOT = Path(__file__).parent / "workloads"
CAPTURE = json.loads((ROOT / "trend_volume.tradingview.json").read_text(encoding="utf-8"))


def _script(name):
    return (ROOT / f"{name}.py").read_text(encoding="utf-8")


def _bars():
    return [dict(zip(CAPTURE["columns"][:6], row["values"][:6])) for row in CAPTURE["rows"]]


def _assert_result(result, count):
    assert result.ok, result.error
    lines = {line["name"]: line["data"] for line in result.lines}
    for col, title in enumerate(CAPTURE["columns"][6:], 6):
        if title == "VWMA formula":
            continue  # independent Pine formula corroborates native VWMA
        expected = {
            row["values"][0]: round(row["values"][col], 8)
            for row in CAPTURE["rows"][:count]
            if row["values"][col] is not None
        }
        actual = {p["time"]: p["value"] for p in lines.get(title, [])}
        assert actual.keys() == expected.keys(), title
        assert actual == pytest.approx(expected, abs=CAPTURE["tolerance"], rel=0), title


def test_native_and_formula_evidence_identity():
    for suffix, key in (("pine", "scriptSha256"), ("tradingview.txt", "logSha256")):
        content = (ROOT / f"trend_volume.{suffix}").read_text(encoding="utf-8")
        assert hashlib.sha256(content.encode()).hexdigest() == CAPTURE[key]
    raw = (ROOT / "trend_volume.tradingview.txt").read_text(encoding="utf-8")
    rows = [
        {"index": int(m[1]), "values": [None if v == "NaN" else float(v) for v in m[2].split("|")]}
        for m in re.finditer(r"PYNE_TV\|(\d+)\|([^;]+);", raw)
    ]
    assert rows == CAPTURE["rows"]
    assert [row["index"] for row in rows] == list(range(18))
    assert all(row["values"][12] == row["values"][13] for row in rows)
    assert rows[0]["values"][6:10] == [0, 1, 0, 1]


@pytest.mark.parametrize("name", ("trend_volume", "trend_volume_batch"))
@pytest.mark.parametrize("count", (1, 3, 6, 10, 18))
def test_trend_volume_external_prefix(name, count):
    _assert_result(pn.run(_script(name), _bars()[:count], executor_mode="inline"), count)


@pytest.mark.parametrize("mode", ("local", "replay", "state"))
@pytest.mark.parametrize("cut", (2, 7, 10, 13))
def test_independent_vwma_windows_restore_with_preview(mode, cut):
    source = _script("trend_volume")
    config = pn.PyneSettings(executor_mode="inline", timeframe="15")
    session = pn.PyneIncrementalSession(script=source, settings=config)
    data = _bars()
    session.seed(data[:cut])
    committed = session.snapshot_result()
    for offset in (100, 200):
        session.on_bar_updated(
            dict(
                data[cut],
                high=data[cut]["high"] + offset,
                close=data[cut]["close"] + offset,
                volume=999,
            )
        )
        assert session.snapshot_result() == committed
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(
            session.snapshot_state(), script=source, settings=config
        )
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(
            session.snapshot_portable(mode=mode), script=source, settings=config
        )
    assert restored.snapshot_result() == committed
    for bar in data[cut:]:
        restored.on_bar_closed(bar)
    _assert_result(restored.snapshot_result(), 18)
