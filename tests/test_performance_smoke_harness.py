from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_performance_smoke() -> ModuleType:
    path = ROOT / "scripts" / "performance_smoke.py"
    spec = importlib.util.spec_from_file_location("pyne_performance_smoke_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_paired_growth_check_alternates_order_and_keeps_raw_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_performance_smoke()

    def small() -> None:
        return None

    def large() -> None:
        return None

    samples: dict[Any, list[float]] = {
        small: [1.0, 1.1, 0.9],
        large: [2.0, 2.2, 1.8],
    }
    call_order: list[Any] = []

    def fake_seconds(callback: Any) -> float:
        call_order.append(callback)
        return samples[callback].pop(0)

    monkeypatch.setattr(module, "_seconds_once", fake_seconds)
    result = module._paired_growth_check(
        "paired",
        small_callback=small,
        large_callback=large,
        repeats=3,
        limit=2.1,
        unit="seconds",
    )

    assert call_order == [small, large, large, small, small, large]
    assert result["smallSamples"] == [1.0, 1.1, 0.9]
    assert result["largeSamples"] == [2.0, 2.2, 1.8]
    assert result["ratioSamples"] == [2.0, 2.0, 2.0]
    assert result["statistic"] == "median_paired_ratio"
    assert result["ratio"] == 2.0
    assert result["passed"] is True


@pytest.mark.parametrize("growth,passed", [(2.0, True), (4.0, False)])
def test_paired_growth_preserves_regression_detection_during_clock_drift(
    monkeypatch: pytest.MonkeyPatch, growth: float, passed: bool,
) -> None:
    module = _load_performance_smoke()

    def small() -> None:
        return None

    def large() -> None:
        return None

    calls = 0

    def drifting_seconds(callback: Any) -> float:
        nonlocal calls
        # Both measurements in a pair share progressively slower host service.
        scale = 1.0 + calls // 2
        calls += 1
        return scale * (growth if callback is large else 1.0)

    monkeypatch.setattr(module, "_seconds_once", drifting_seconds)
    result = module._paired_growth_check(
        "drifting_host", small_callback=small, large_callback=large,
        repeats=9, limit=3.0, unit="seconds",
    )
    assert result["passed"] is passed
    assert result["ratio"] == growth
    assert result["ratioSamples"] == [growth] * 9
    assert calls == 18
