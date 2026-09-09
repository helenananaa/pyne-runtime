from __future__ import annotations

import json
import math
from collections import deque
from pathlib import Path

import pyne_runtime as pn
import pytest

MIGRATION_DIR = Path(__file__).resolve().parent / "migrations" / "adx_di"
BATCH_PATH = MIGRATION_DIR / "batch.py"
INCREMENTAL_PATH = MIGRATION_DIR / "incremental.py"
NAIVE_PATH = MIGRATION_DIR / "naive.py"
CAPTURE_JSON = MIGRATION_DIR / "tradingview.json"
CAPTURE_TXT = MIGRATION_DIR / "tradingview.txt"

SERIES_NAMES = ("DI+", "DI-", "ADX")


def _synthetic_bars(count: int = 40) -> list[dict[str, float]]:
    bars: list[dict[str, float]] = []
    price = 100.0
    for index in range(count):
        price += 1.25 if index % 3 else -0.75
        high = price + 1.5
        low = price - 1.25
        open_ = price - 0.25
        close = price + 0.35
        bars.append(
            {
                "time": 1_700_000_000 + index * 60,
                "open": open_,
                "high": max(high, open_, close),
                "low": min(low, open_, close),
                "close": close,
                "volume": 100.0 + index,
            }
        )
    return bars


def _capture_payload() -> dict:
    return json.loads(CAPTURE_JSON.read_text(encoding="utf-8"))


def _bars_from_capture(payload: dict) -> list[dict[str, float]]:
    bars: list[dict[str, float]] = []
    for row in payload["rows"]:
        open_, high, low, close, volume = row["ohlcv"]
        bars.append(
            {
                "time": int(row["time"]),
                "open": float(open_),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": float(volume),
            }
        )
    return bars


def _expected_from_capture(payload: dict) -> dict[int, dict[str, float | None]]:
    expected: dict[int, dict[str, float | None]] = {}
    for row in payload["rows"]:
        values = row["values"]
        expected[int(row["time"])] = {
            "DI+": values[0],
            "DI-": values[1],
            "ADX": values[2],
        }
    return expected


def _series_by_time(result: object, name: str) -> dict[int, float]:
    mapping: dict[int, float] = {}
    for line in getattr(result, "lines", None) or []:
        line_name = line.get("name") or line.get("title")
        if line_name != name:
            continue
        for point in line.get("data") or []:
            mapping[int(point["time"])] = point["value"]
    return mapping


def _adx_di_oracle(bars: list[dict[str, float]], length: int) -> dict[int, dict[str, float]]:
    prior_high = 0.0
    prior_low = 0.0
    prior_close = 0.0
    smoothed_tr = 0.0
    smoothed_plus = 0.0
    smoothed_minus = 0.0
    dx_window: deque[float] = deque()
    present = 0
    out: dict[int, dict[str, float]] = {}
    for bar in bars:
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        true_range = max(high - low, abs(high - prior_close), abs(low - prior_close))
        up_move = high - prior_high
        down_move = prior_low - low
        dm_plus = max(up_move, 0.0) if up_move > down_move else 0.0
        dm_minus = max(down_move, 0.0) if down_move > up_move else 0.0
        smoothed_tr = smoothed_tr - (smoothed_tr / length) + true_range
        smoothed_plus = smoothed_plus - (smoothed_plus / length) + dm_plus
        smoothed_minus = smoothed_minus - (smoothed_minus / length) + dm_minus
        if smoothed_tr == 0.0:
            di_plus = math.nan
            di_minus = math.nan
            dx = math.nan
        else:
            di_plus = smoothed_plus / smoothed_tr * 100.0
            di_minus = smoothed_minus / smoothed_tr * 100.0
            denom = di_plus + di_minus
            dx = math.nan if denom == 0.0 else abs(di_plus - di_minus) / denom * 100.0
        if dx == dx:
            dx_window.append(dx)
            present += 1
            if len(dx_window) > length:
                dx_window.popleft()
        adx = math.nan
        if present >= length and len(dx_window) == length:
            adx = sum(dx_window) / length
        out[int(bar["time"])] = {"DI+": di_plus, "DI-": di_minus, "ADX": adx}
        prior_high = high
        prior_low = low
        prior_close = close
    return out


def _run_batch(bars: list[dict[str, float]], params: dict | None = None):
    return pn.run(BATCH_PATH, bars, params=params, executor_mode="inline")


def _run_incremental(bars: list[dict[str, float]], params: dict | None = None):
    return pn.run(INCREMENTAL_PATH, bars, params=params, executor_mode="inline")


def _assert_close_maps(
    actual: dict[int, float],
    expected: dict[int, float | None],
    *,
    abs_tol: float,
) -> None:
    for time, expected_value in expected.items():
        if expected_value is None or (
            isinstance(expected_value, float) and math.isnan(expected_value)
        ):
            assert time not in actual
            continue
        assert time in actual
        assert actual[time] == pytest.approx(float(expected_value), abs=abs_tol, rel=0)


def test_naive_validate_records_migration_hints() -> None:
    diagnostics = pn.validate(NAIVE_PATH)
    codes = [item["code"] for item in diagnostics]
    assert "PYNE_MIGRATION_HINT" in codes
    report = pn.inspect_script(NAIVE_PATH.read_text(encoding="utf-8"))
    assert report["runtimeMode"] == "batch"
    assert report["migration"]["diagnostics"] == [
        item for item in diagnostics if item["code"] == "PYNE_MIGRATION_HINT"
    ]
    failed = pn.run(NAIVE_PATH, _synthetic_bars(), executor_mode="inline")
    assert not failed.ok
    assert failed.code == "PYNE_RUNTIME_ERROR"


@pytest.mark.parametrize("length", [14, 3])
def test_batch_incremental_agree_with_independent_formula(length: int) -> None:
    bars = _synthetic_bars()
    params = {"len": length}
    batch = _run_batch(bars, params)
    incremental = _run_incremental(bars, params)
    assert batch.ok, batch.error
    assert incremental.ok, incremental.error
    for path in (BATCH_PATH, INCREMENTAL_PATH):
        report = pn.inspect_script(path.read_text(encoding="utf-8"))
        assert report["compatibility"]["supported"] is True
        assert report["migration"]["diagnostics"] == []
    oracle = _adx_di_oracle(bars, length)
    for name in SERIES_NAMES:
        batch_map = _series_by_time(batch, name)
        inc_map = _series_by_time(incremental, name)
        assert batch_map.keys() == inc_map.keys()
        expected = {time: values[name] for time, values in oracle.items()}
        _assert_close_maps(batch_map, expected, abs_tol=1e-8)
        _assert_close_maps(inc_map, expected, abs_tol=1e-8)


def test_incremental_preview_does_not_mutate_committed_state() -> None:
    bars = _synthetic_bars(20)
    script = INCREMENTAL_PATH.read_text(encoding="utf-8")
    settings = pn.PyneSettings(executor_mode="inline")
    session = pn.PyneIncrementalSession(script=script, settings=settings, params={"len": 14})
    control = pn.PyneIncrementalSession(script=script, settings=settings, params={"len": 14})
    seeded = session.seed(bars[:-1])
    control.seed(bars[:-1])
    assert seeded.ok
    preview_bar = dict(bars[-1])
    preview_bar["high"] = preview_bar["high"] + 50.0
    preview_bar["close"] = preview_bar["close"] + 20.0
    preview = session.on_bar_updated(preview_bar)
    assert preview.ok
    committed_after_preview = session.snapshot_result()
    assert _series_by_time(committed_after_preview, "DI+") == _series_by_time(
        control.snapshot_result(), "DI+"
    )
    closed = session.on_bar_closed(bars[-1])
    control_closed = control.on_bar_closed(bars[-1])
    assert closed.ok and control_closed.ok
    for name in SERIES_NAMES:
        assert _series_by_time(closed, name) == _series_by_time(control_closed, name)


def test_incremental_snapshot_continues_with_same_formula() -> None:
    bars = _synthetic_bars(24)
    script = INCREMENTAL_PATH.read_text(encoding="utf-8")
    settings = pn.PyneSettings(executor_mode="inline")
    original = pn.PyneIncrementalSession(script=script, settings=settings, params={"len": 14})
    original.seed(bars[:12])
    restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=script)
    for bar in bars[12:]:
        assert restored.on_bar_closed(bar).ok
        assert original.on_bar_closed(bar).ok
    for name in SERIES_NAMES:
        assert _series_by_time(restored.snapshot_result(), name) == _series_by_time(
            original.snapshot_result(), name
        )
    oracle = _adx_di_oracle(bars, 14)
    _assert_close_maps(
        _series_by_time(original.snapshot_result(), "ADX"),
        {time: values["ADX"] for time, values in oracle.items()},
        abs_tol=1e-8,
    )


def test_input_guards_match_declared_scope() -> None:
    bars = _synthetic_bars(8)
    invalid_len = _run_batch(bars, {"len": 0})
    assert invalid_len.ok is False
    assert invalid_len.code == "PYNE_INVALID_PARAM"
    inverted = dict(bars[0])
    inverted["high"] = inverted["low"] - 1.0
    invalid_ohlcv = pn.run(BATCH_PATH, [inverted], executor_mode="inline")
    assert invalid_ohlcv.ok is False
    assert invalid_ohlcv.code == "PYNE_INVALID_OHLCV"


def test_adx_di_tradingview_capture_parity() -> None:
    payload = _capture_payload()
    assert CAPTURE_TXT.read_text(encoding="utf-8")
    bars = _bars_from_capture(payload)
    expected = _expected_from_capture(payload)
    assert len(bars) == 80
    batch = _run_batch(bars, {"len": 14})
    incremental = _run_incremental(bars, {"len": 14})
    assert batch.ok, batch.error
    assert incremental.ok, incremental.error
    for name in SERIES_NAMES:
        exp = {time: values[name] for time, values in expected.items()}
        _assert_close_maps(_series_by_time(batch, name), exp, abs_tol=1e-8)
        _assert_close_maps(_series_by_time(incremental, name), exp, abs_tol=1e-8)
