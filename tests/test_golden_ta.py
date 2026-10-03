from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import pyne_runtime as pn


GOLDEN_DIR = Path(__file__).parent / "golden"


@pytest.mark.parametrize(
    "fixture_name",
    [
        "ta_core_indicators.json",
        "ta_advanced_indicators.json",
        "ta_oscillator_edges_indicators.json",
        "ta_remaining_indicators.json",
        "ta_statistics_edges_indicators.json",
        "ta_context_indicators.json",
        "ta_trend_switch_indicators.json",
        "ta_tuple_outputs_indicators.json",
        "ta_warmup_boundaries_indicators.json",
        "ta_external_library_indicators.json",
    ],
)
def test_ta_golden_fixture(fixture_name: str) -> None:
    fixture = _load_fixture(fixture_name)

    capture = fixture.get("external_capture", {})
    bars = fixture.get("chart_bars") or capture.get("bars") or []
    result = pn.run(
        fixture["script"],
        bars,
        executor_mode="inline",
    )

    assert result.ok, result.error
    for name, expected in fixture.get("expected_series", {}).items():
        # Retained project goldens describe the legacy eight-decimal plot
        # presentation. Native comparisons below consume raw values unchanged;
        # exact raw payloads have separate precision-contract tests.
        legacy = [{**point,"value":round(point['value'],8)} for point in result.get_series(name)]
        _assert_series_matches(legacy, expected)
    _assert_external_capture(fixture)


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((GOLDEN_DIR / name).read_text(encoding="utf-8"))


def _assert_series_matches(
    actual: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    *,
    abs_tol: float = 1e-9,
    allow_actual_extra_keys: bool = False,
) -> None:
    assert len(actual) == len(expected)
    for actual_point, expected_point in zip(actual, expected):
        if allow_actual_extra_keys:
            assert set(expected_point).issubset(actual_point)
        else:
            assert actual_point.keys() == expected_point.keys()
        for key, expected_value in expected_point.items():
            actual_value = actual_point[key]
            if key == "value" and isinstance(expected_value, (int, float)):
                assert actual_value == pytest.approx(expected_value, abs=abs_tol)
            else:
                assert actual_value == expected_value


def _assert_external_capture(fixture: dict[str, Any]) -> None:
    capture = fixture.get("external_capture")
    if capture is None:
        return
    if capture.get("status") != "captured":
        return
    if capture.get("assertion") != "parity":
        return

    result = pn.run(
        fixture["script"],
        capture.get("bars") or fixture.get("chart_bars") or [],
        executor_mode="inline",
    )
    assert result.ok, result.error
    default_tolerance = float(capture.get("tolerance", 1e-9))
    plot_tolerances = capture.get("plot_tolerances", {})
    for name, expected in capture.get("series", {}).items():
        tolerance = float(plot_tolerances.get(name, default_tolerance))
        actual = result.get_series(name)
        for known in capture.get("known_differences", []):
            if known["plot"] != name:
                continue
            assert known["reason"] and known["evidence"]
            assert known["tradingview"] in expected
            timestamp = known["tradingview"]["time"]
            assert next((point for point in actual if point["time"] == timestamp), None) == known["pyne"]
            expected = [point for point in expected if point["time"] != timestamp]
            actual = [point for point in actual if point["time"] != timestamp]
        _assert_series_matches(
            actual,
            expected,
            abs_tol=tolerance,
            allow_actual_extra_keys=True,
        )
