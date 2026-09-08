"""Current-bar diagnostics stay complete while prior-bar history is disclosed."""

import copy

import pyne_runtime as pn
import pytest


SCRIPT = '''indicator("Diagnostic retention", mode="incremental")
def on_bar(ctx, bar):
    if ctx.bar_index % 3 != 2:
        ctx.request.security("OK", "10S", "close")
        ctx.request.security("BAD", "10S", "close", ignore_invalid_symbol=True)
    ctx.plot("Close", bar.close)
'''


class Provider:
    def get_ohlcv(self, symbol, timeframe, start, end):
        if symbol == "BAD":
            raise pn.PyneInvalidSymbolError("unknown symbol")
        return []


def bar(index):
    return dict(time=index * 10, open=10, high=11, low=9, close=10, volume=1)


def settings():
    return pn.PyneSettings(executor_mode="inline", timeframe="10S", data_provider=Provider())


def new_session(source=SCRIPT):
    return pn.PyneIncrementalSession(script=source, settings=settings(), retention_bars=4)


def info(result):
    return result.meta["requestDiagnosticsInfo"]


def test_current_warnings_survive_silent_bars_and_preview_isolation():
    session = new_session()
    first = session.on_bar_closed(bar(0))
    assert [d["status"] for d in first.meta["requestDiagnostics"]] == ["ok", "ignoredInvalidSymbol"]
    assert info(first) == dict(scope="current_bar", barTime=0, retained=2, dropped=0, truncated=False)
    frozen = copy.deepcopy(first)
    for _ in range(3):
        preview = session.on_bar_updated(bar(1))
        assert info(preview)["dropped"] == 2
        assert info(preview)["retained"] == 2
        assert session.snapshot_result().meta["requestDiagnostics"] == first.meta["requestDiagnostics"]
        assert info(session.snapshot_result()) == info(first)
    second = session.on_bar_closed(bar(1))
    assert info(second)["dropped"] == 2
    assert info(second)["truncated"] is True
    silent = session.on_bar_closed(bar(2))
    assert silent.meta["requestDiagnostics"] == []
    assert info(silent) == dict(scope="current_bar", barTime=20, retained=0, dropped=4, truncated=True)
    assert first == frozen


@pytest.mark.parametrize("mode", ["local", "replay", "state"])
@pytest.mark.parametrize("cut", [2, 3])
def test_restore_preserves_dropped_counts_and_subsequent_diagnostics(mode, cut):
    session = new_session()
    session.seed([bar(i) for i in range(cut)])
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(
            session.snapshot_state(), script=SCRIPT, settings=settings())
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(
            session.snapshot_portable(mode=mode), script=SCRIPT, settings=settings())
    assert restored.snapshot_result() == session.snapshot_result()
    for i in range(cut, 12):
        assert restored.on_bar_updated(bar(i)) == session.on_bar_updated(bar(i))
        assert restored.on_bar_closed(bar(i)) == session.on_bar_closed(bar(i))


def test_diagnostic_history_is_constant_over_long_session():
    session = new_session()
    emitted = 0
    for i in range(512):
        count = 2 if i % 3 != 2 else 0
        result = session.on_bar_closed(bar(i))
        assert len(result.meta["requestDiagnostics"]) == count
        assert info(result)["dropped"] == emitted
        emitted += count
    # The retained state graph holds current diagnostics, not hidden old entries.
    snapshot = session.snapshot_state()
    assert len(snapshot.context._request_diagnostics) == 2
    assert snapshot.context._request_diagnostics_dropped == emitted - 2


def test_no_per_bar_cap_or_change_to_batch_diagnostics():
    source = '''indicator("Many calls", mode="incremental")
def on_bar(ctx, bar):
    for i in range(300):
        ctx.request.security("BAD", "10S", "close", ignore_invalid_symbol=True)
'''
    result = new_session(source).on_bar_closed(bar(0))
    assert len(result.meta["requestDiagnostics"]) == 300
    assert info(result)["dropped"] == 0
    result = pn.run('request.security("BAD", "10S", "close", ignore_invalid_symbol=True)',
                    [bar(0), bar(1)], settings=settings())
    assert result.ok, result.error
    assert len(result.meta["requestDiagnostics"]) == 1
    assert "requestDiagnosticsInfo" not in result.meta


def test_never_requested_session_has_no_diagnostic_metadata():
    result = new_session('indicator("Silent", mode="incremental")\ndef on_bar(ctx, bar):\n    pass').on_bar_closed(bar(0))
    assert "requestDiagnostics" not in result.meta
    assert "requestDiagnosticsInfo" not in result.meta
