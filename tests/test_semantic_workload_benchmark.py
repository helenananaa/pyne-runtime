"""Check benchmark evidence integrity, not machine-specific latency thresholds."""

import importlib.util
from pathlib import Path

import pytest


def load_benchmark():
    path = Path(__file__).resolve().parents[1] / "scripts" / "semantic_workload_benchmark.py"
    spec = importlib.util.spec_from_file_location("semantic_benchmark_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cycle_workload_is_active_after_first_cycle():
    module = load_benchmark()
    source = (module.ASSETS / "strategy_cycles.py").read_text(encoding="utf-8")
    settings = module.pn.PyneSettings(executor_mode="inline", timeframe="10S")
    for cycles in (1, 2, 3):
        result = module.pn.run(source, module.bars(12 * cycles), settings=settings)
        assert result.ok, result.error
        summary = result.output["strategy"]["summary"]
        # Each cycle: buy 4 at 14, sell 1 at 9, sell 3 at 15, three cash fees.
        assert summary["netprofit"] == -5 * cycles
        assert summary["commission"] == 3 * cycles
        assert summary["equity"] == 10000 - 5 * cycles


def test_benchmark_distinguishes_unavailable_replay_from_zero_cost():
    module = load_benchmark()
    report = module.measure("strategy_cycles", 32, 2, 16, 16)
    assert report["checkpoints"]["replay"]["available"] is False
    assert "history exceeded max_bars" in report["checkpoints"]["replay"]["reason"]
    assert "restore" not in report["checkpoints"]["replay"]
    assert report["preview"]["count"] == 4
    assert report["confirmed"]["count"] == 2
    assert report["checkpoints"]["local"]["bytes"] is None
    assert report["checkpoints"]["state"]["bytes"] > 0
    assert 0 < report["memory"]["retainedPythonBytes"] <= report["memory"]["peakPythonBytes"]


def test_benchmark_fails_on_incorrect_restoration(monkeypatch):
    module = load_benchmark()
    original = module.pn.PyneIncrementalSession.from_portable_snapshot

    def corrupted(*args, **kwargs):
        restored = original(*args, **kwargs)
        restored.on_bar_closed(module.bars(33)[32])
        return restored

    monkeypatch.setattr(module.pn.PyneIncrementalSession, "from_portable_snapshot", corrupted)
    with pytest.raises(AssertionError):
        module.measure("ta_chain", 32, 2, 16, 64)


def test_provider_extends_the_frozen_formula_without_future_leakage():
    module = load_benchmark()
    provider = module.Provider(20000)
    rows = provider.get_ohlcv("TEST:ASSET", "5S", 10001, 10029)
    assert [r["time"] for r in rows] == [10010, 10015, 10020, 10025]
    for row in rows:
        assert row["close"] == 20 + row["time"] // 5 % 9
    assert provider.get_ohlcv("TEST:ASSET", "30S", 20001, 20100) == []
