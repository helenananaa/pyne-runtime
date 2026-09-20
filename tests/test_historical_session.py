import copy
import pytest
from pyne_runtime.historical import HistoricalSession
from pyne_runtime.incremental import PyneIncrementalSession

SOURCE = """def init(ctx):
    ctx.strategy.configure(initial_capital=10000)
def on_bar(ctx, bar):
    if ctx.bar_index == 0:
        ctx.strategy.entry("L", ctx.strategy.long, qty=1)
    if ctx.bar_index == 4:
        ctx.strategy.close("L")
"""
BARS = [dict(time=i*60, open=10+i, high=11+i, low=9+i, close=10+i, volume=100) for i in range(6)]


def test_history_snapshot_and_batch_parity():
    history = HistoricalSession(SOURCE, BARS)
    history.advance(2)
    snapshot = history.snapshot()
    final = history.advance(6)
    history.restore(snapshot)
    assert history.cursor == 2
    assert history.advance(6).output == final.output == PyneIncrementalSession(script=SOURCE).seed(BARS).output
    assert len(history.equity) == 6


def test_snapshot_validation_and_horizon_isolation():
    history = HistoricalSession(SOURCE, BARS)
    history.advance(2)
    snapshot = history.snapshot()
    bad = copy.copy(snapshot)
    bad["cursor"] = 3
    with pytest.raises(ValueError, match="cursor mismatch"):
        history.restore(bad)
    assert history.cursor == 2
    snapshot["horizon"][0]["close"] = 100
    with pytest.raises(ValueError, match="horizon mismatch"):
        history.restore(snapshot)
    assert history.advance(6).output == PyneIncrementalSession(script=SOURCE).seed(BARS).output


def test_reject_invalid_history_before_execution():
    with pytest.raises(ValueError):
        HistoricalSession(SOURCE, BARS + [BARS[0]])
    with pytest.raises(ValueError, match="init/on_bar"):
        HistoricalSession('strategy("batch")', BARS)
