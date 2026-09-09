"""Real source migration against independently captured TradingView market bars."""

import copy
import hashlib
import json
from pathlib import Path

import pyne_runtime as pn
import pytest


ROOT = Path(__file__).parent / "migrations" / "adx_di"
CAPTURE = json.loads((ROOT / "tradingview.json").read_text(encoding="utf-8"))


def bars():
    return [dict(time=row["time"], **dict(zip(CAPTURE["ohlcvColumns"], row["ohlcv"])))
            for row in CAPTURE["rows"]]


def expected(end=80, start=0):
    return {
        name: [{"time": row["time"], "value": round(row["values"][index], 8)}
               for row in CAPTURE["rows"][start:end] if row["values"][index] is not None]
        for index, name in enumerate(CAPTURE["columns"])
    }


def assert_external(result, end=80, start=0):
    assert result.ok, result.error
    actual = {line["name"]: line["data"] for line in result.lines}
    for name, points in expected(end, start).items():
        observed = actual.get(name, [])
        assert [point["time"] for point in observed] == [point["time"] for point in points]
        assert [point["value"] for point in observed] == pytest.approx(
            [point["value"] for point in points], abs=1e-9, rel=0
        )


def test_market_capture_identity_and_raw_rows():
    for name, digest in CAPTURE["sha256"].items():
        assert hashlib.sha256((ROOT / name).read_text(encoding="utf-8").encode()).hexdigest() == digest
    raw = (ROOT / "tradingview.txt").read_text(encoding="utf-8").splitlines()
    assert len(raw) == len(CAPTURE["rows"]) == 80
    for index, (line, parsed) in enumerate(zip(raw, CAPTURE["rows"])):
        fields = line.split("PYNE_ADX|")[1].split("|")
        assert parsed["index"] == int(fields[0]) == index
        assert parsed["time"] * 1000 == int(fields[1])
        numeric = [None if value == "NaN" else float(value) for value in fields[2:]]
        assert parsed["ohlcv"] + parsed["values"] == numeric
        assert parsed["time"] == CAPTURE["rows"][0]["time"] + 900 * index
    assert CAPTURE["parameters"] == {"length": 14, "threshold": 20}
    assert CAPTURE["rows"][0]["values"] == [100., 0., None]
    assert all(row["values"][2] is None for row in CAPTURE["rows"][:13])
    assert CAPTURE["rows"][13]["values"][2] is not None


@pytest.mark.parametrize("mode", ["batch", "incremental"])
@pytest.mark.parametrize("end", [1, 14, 40, 80])
def test_migrated_source_matches_market_capture_prefix(mode, end):
    source = (ROOT / f"{mode}.py").read_text(encoding="utf-8")
    result = pn.run(source, bars()[:end], executor_mode="inline", timeframe="15")
    assert_external(result, end)


def test_market_migration_preview_retention_and_restart():
    source = (ROOT / "incremental.py").read_text(encoding="utf-8")
    settings = pn.PyneSettings(executor_mode="inline", timeframe="15")
    session = pn.PyneIncrementalSession(script=source, settings=settings, retention_bars=24)
    data = bars()
    for index, bar in enumerate(data):
        if index:
            committed = copy.deepcopy(session.snapshot_result())
            for offset in (-10., 10.):
                preview = dict(bar, close=bar["close"] + offset,
                               high=max(bar["high"], bar["close"] + 10.),
                               low=min(bar["low"], bar["close"] - 10.))
                assert session.on_bar_updated(preview).ok
                assert session.snapshot_result() == committed
        session.on_bar_closed(bar)
        assert_external(session.snapshot_result(), index + 1, max(0, index + 1 - 24))
        if index in (4, 12, 13, 39, 63):
            before = session.snapshot_result()
            session = pn.PyneIncrementalSession.from_portable_snapshot(
                session.snapshot_portable_state(), script=source, settings=settings
            )
            assert session.snapshot_result() == before


def test_incremental_preserves_threshold_reference_parameter():
    source = (ROOT / "incremental.py").read_text(encoding="utf-8")
    result = pn.run(source, bars()[:3], params={"th": 27}, executor_mode="inline")
    assert result.ok, result.error
    points = next(line["data"] for line in result.lines if line["name"] == "Threshold")
    assert [point["time"] for point in points] == [row["time"] for row in bars()[:3]]
    assert [point["value"] for point in points] == [27.] * 3
