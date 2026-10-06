"""Independent admission and strategy configuration lifecycle regressions."""
from __future__ import annotations

import copy
import json
import math

import pyne_runtime as pn
import pytest

from pyne_runtime.context import PyneContext
from pyne_runtime.plot import OutputCollector
from pyne_runtime.security import PyneResourceLimitError
from pyne_runtime.strategy import StrategyModule


BARS = [
    {"time": index, "open": 10, "high": 12, "low": 8, "close": 10, "volume": 1}
    for index in (1, 2, 3)
]


def _strategy(mode):
    if mode == "batch":
        context = PyneContext.from_ohlcv(BARS)
        collector = OutputCollector(context.times)
        strategy = StrategyModule(context, collector)
        strategy.configure(initial_capital=1000)
        strategy.entry("good", qty=2, when=[True, False, False])
        return strategy, collector, None
    session = pn.PyneIncrementalSession(script='def on_bar(ctx, bar): pass')
    session.seed(BARS[:1])
    strategy = session._ctx.strategy
    strategy.configure(initial_capital=1000)
    strategy.entry("good", qty=2)
    return strategy, None, session


def _receipt(strategy, collector):
    report = collector.to_dict() if collector is not None else copy.deepcopy(strategy.to_report())
    settings = {
        name: value for name, value in vars(strategy).items()
        if isinstance(value, (int, float, str, bool)) or value is None
    }
    return report, settings


@pytest.mark.parametrize("capital", [0, 1000, 250000])
def test_equity_without_any_order_starts_at_configured_capital(capital):
    result = pn.run(f'strategy("Idle", initial_capital={capital})\nplot(strategy.equity,"E")', BARS)
    assert result.ok
    assert result.values("E") == [capital] * 3
    no_op = pn.run(
        f'strategy("Idle", initial_capital={capital})\nstrategy.entry("unused", when=False)'
        '\nplot(strategy.equity,"E")', BARS,
    )
    assert no_op.ok
    assert no_op.values("E") == result.values("E")


def test_equity_uses_default_capital_before_declaration():
    result = pn.run('plot(strategy.equity,"E")', BARS)
    assert result.ok
    assert result.values("E") == [100000] * 3


def test_late_batch_configuration_updates_arrays_position_and_report_together():
    result = pn.run('''
strategy("Late", initial_capital=1000)
strategy.entry("good", qty=2, when=bar_index == 0)
plot(strategy.equity, "Before")
strategy.configure(initial_capital=2000, commission_type=strategy.commission.cash_per_order,
                   commission_value=3, slippage=2, mintick=0.1)
plot(strategy.equity, "After")
plot(strategy.position_avg_price, "Price")
''', BARS)
    assert result.ok
    assert result.values("Before") == [1000] * 3
    assert result.values("After") == pytest.approx([1996.6] * 3)
    assert result.values("Price") == pytest.approx([10.2] * 3)
    report = result.output["strategy"]
    assert report["summary"]["initial_capital"] == 2000
    assert report["summary"]["commission"] == 3
    assert report["summary"]["equity"] == 1996.6
    assert report["position"] == {"size": 2.0, "side": "long", "avg_price": 10.2}
    assert report["orders"][0]["commission"] == 3


@pytest.mark.parametrize("mode", ["batch", "incremental"])
@pytest.mark.parametrize("option", [
    "initial_capital", "commission_value", "margin_long", "margin_short", "mintick",
    "min_tick", "pyramiding", "slippage", "backtest_fill_limits_assumption",
])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "nan"])
def test_invalid_configuration_rejects_every_field_before_any_mutation(mode, option, value):
    strategy, collector, session = _strategy(mode)
    before = _receipt(strategy, collector)
    options = {"initial_capital": 2000, "currency": "USD", option: value}
    with pytest.raises(ValueError, match="finite"):
        strategy.configure(**options)
    assert _receipt(strategy, collector) == before
    if session is not None:
        assert session.on_bar_closed(BARS[1]).ok
        assert strategy.equity == 1000


@pytest.mark.parametrize("mode", ["batch", "incremental"])
@pytest.mark.parametrize("option", ["commission_type", "same_bar_fill_priority", "intrabar_path"])
def test_invalid_enum_does_not_commit_preceding_numeric_configuration(mode, option):
    strategy, collector, _ = _strategy(mode)
    before = _receipt(strategy, collector)
    with pytest.raises(ValueError):
        strategy.configure(initial_capital=2000, slippage=3, **{option: "invalid"})
    assert _receipt(strategy, collector) == before


@pytest.mark.parametrize("mode", ["batch", "incremental"])
@pytest.mark.parametrize("method", ["max_drawdown", "max_intraday_loss", "max_position_size",
                                   "max_intraday_filled_orders"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_invalid_risk_number_preserves_strategy_and_report(mode, method, value):
    strategy, collector, _ = _strategy(mode)
    before = _receipt(strategy, collector)
    with pytest.raises(ValueError, match="finite"):
        getattr(strategy.risk, method)(value)
    assert _receipt(strategy, collector) == before


@pytest.mark.parametrize("mode", ["batch", "incremental"])
@pytest.mark.parametrize("method", ["max_drawdown", "max_intraday_loss"])
def test_invalid_risk_mode_does_not_change_the_existing_threshold(mode, method):
    strategy, collector, _ = _strategy(mode)
    getattr(strategy.risk, method)(50)
    before = _receipt(strategy, collector)
    with pytest.raises(ValueError, match="risk mode"):
        getattr(strategy.risk, method)(5, "invalid")
    assert _receipt(strategy, collector) == before


@pytest.mark.parametrize("mode", ["batch", "incremental"])
@pytest.mark.parametrize("method", ["entry", "order", "close", "close_all", "exit"])
def test_invalid_order_numbers_leave_position_logs_sequence_and_risk_unchanged(mode, method):
    strategy, collector, _ = _strategy(mode)
    before = _receipt(strategy, collector)
    options = {"qty": float("inf")} if method != "close_all" else {"price": float("inf")}
    if method == "exit":
        options["limit"] = 11
    with pytest.raises(ValueError, match="finite"):
        if method == "close_all":
            strategy.close_all(**options)
        else:
            getattr(strategy, method)("bad", **options)
    assert _receipt(strategy, collector) == before
    strategy.close("good", qty=1, when=[False, False, True] if mode == "batch" else True)
    size = strategy.position_size
    if mode == "batch":
        size = size.values[-1]
    assert size == 1


@pytest.mark.parametrize("mode", ["batch", "incremental"])
@pytest.mark.parametrize("method", ["entry", "order"])
def test_nan_required_quantity_cannot_create_a_flat_nan_position(mode, method):
    strategy, collector, _ = _strategy(mode)
    before = _receipt(strategy, collector)
    with pytest.raises(ValueError, match="finite"):
        getattr(strategy, method)("bad", qty=float("nan"))
    assert _receipt(strategy, collector) == before


@pytest.mark.parametrize("mode", ["batch", "incremental"])
@pytest.mark.parametrize("field", ["price", "limit", "stop"])
def test_infinite_prices_are_validated_before_order_sequence_or_risk_reads(mode, field):
    strategy, collector, _ = _strategy(mode)
    before = _receipt(strategy, collector)
    with pytest.raises(ValueError, match="finite"):
        strategy.entry("bad", **{field: float("inf")})
    assert _receipt(strategy, collector) == before


def test_batch_vector_admission_does_not_publish_valid_prefix_of_invalid_command():
    strategy, collector, _ = _strategy("batch")
    before = _receipt(strategy, collector)
    with pytest.raises(ValueError, match="finite"):
        strategy.order("bad", price=[10, 10, float("inf")])
    assert _receipt(strategy, collector) == before
    with pytest.raises(ValueError, match="finite"):
        strategy.close("good", qty=[None, None, float("inf")])
    assert _receipt(strategy, collector) == before


@pytest.mark.parametrize("mode", ["batch", "incremental"])
@pytest.mark.parametrize("missing", [None, pn.na, float("nan")])
def test_optional_close_quantity_preserves_missing_argument_meaning(mode, missing):
    strategy, collector, _ = _strategy(mode)
    strategy.close("good", qty=missing, qty_percent=missing)
    size = strategy.position_size
    if mode == "batch":
        size = size.values[-1]
    assert size == 0
    report = collector.to_dict() if collector is not None else strategy.to_report()
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("mode", ["batch", "incremental"])
def test_missing_explicit_price_omits_order_and_none_uses_current_price(mode):
    strategy, collector, _ = _strategy(mode)
    before = _receipt(strategy, collector)
    strategy.order("missing", price=float("nan"))
    assert _receipt(strategy, collector) == before
    strategy.order("normal", price=None, limit=pn.na, stop=float("nan"))
    size = strategy.position_size
    if mode == "batch":
        size = size.values[-1]
        assert size == 5  # Batch order applies once per bar.
    else:
        assert size == 3


def test_failed_configuration_replay_preserves_previous_calculation_and_budget():
    context = PyneContext.from_ohlcv(BARS)
    collector = OutputCollector(context.times)
    strategy = StrategyModule(context, collector)
    strategy.configure(initial_capital=1000, margin_long=100)
    strategy.entry("pending", qty=2000, limit=200, when=[True, False, False])
    assert strategy._pending_order_operations > 0
    strategy._max_pending_order_operations = strategy._pending_order_operations
    before = _receipt(strategy, collector)
    strategy.configure(initial_capital=1000)
    assert _receipt(strategy, collector) == before
    with pytest.raises(PyneResourceLimitError):
        strategy.configure(initial_capital=2000)
    assert _receipt(strategy, collector) == before
    assert strategy.equity.values.tolist() == [1000] * 3


def test_finite_admission_and_missing_optionals_keep_batch_incremental_parity():
    report = pn.run_incremental_parity(
        batch_script='''
strategy("Finite", initial_capital=1000, slippage=2, mintick=0.1,
         commission_type=strategy.commission.cash_per_order, commission_value=2)
strategy.entry("good", qty=2, price=None, limit=na, stop=na, when=bar_index == 0)
strategy.close("good", qty=1, price=None, when=bar_index == 2)
plot(strategy.position_size,"P")
plot(strategy.equity,"E")
''',
        incremental_script='''
def init(ctx):
    ctx.strategy.configure(initial_capital=1000, slippage=2, mintick=0.1,
        commission_type=ctx.strategy.commission.cash_per_order, commission_value=2)
def on_bar(ctx,bar):
    ctx.strategy.entry("good", qty=2, price=None, limit=float("nan"), stop=float("nan"),
                       when=bar.bar_index == 0)
    ctx.strategy.close("good", qty=1, price=None, when=bar.bar_index == 2)
    ctx.plot("P",ctx.strategy.position_size)
    ctx.plot("E",ctx.strategy.equity)
''', bars=BARS,
    )
    report.assert_ok()
    assert report.batch_result.output["strategy"]["summary"]["equity"] == 995.4


@pytest.mark.parametrize("snapshot_kind", ["local", "state", "replay"])
def test_caught_invalid_commands_keep_preview_restore_and_continuation_healthy(snapshot_kind):
    script = '''
def init(ctx):
    ctx.strategy.configure(initial_capital=1000)
def on_bar(ctx,bar):
    for command in (lambda: ctx.strategy.configure(initial_capital=2000, commission_value=float("nan")),
                    lambda: ctx.strategy.entry("bad", qty=float("inf")),
                    lambda: ctx.strategy.exit("bad_exit", limit=float("inf")),
                    lambda: ctx.strategy.risk.max_drawdown(float("nan"))):
        try:
            command()
        except ValueError:
            pass
    ctx.strategy.entry("good",qty=2,when=bar.bar_index == 0)
    ctx.strategy.close("good",qty=1,when=bar.bar_index == 2)
    ctx.plot("E",ctx.strategy.equity)
    ctx.plot("P",ctx.strategy.position_size)
'''
    session = pn.PyneIncrementalSession(script=script)
    session.seed(BARS[:1])
    snapshot = session.snapshot_state()
    before = session.snapshot_result()
    portable = (session.snapshot_portable_state() if snapshot_kind == "state"
                else session.snapshot_portable()) if snapshot_kind != "local" else None
    assert session.on_bar_updated(BARS[1]).ok
    assert session.snapshot_result() == before
    restored = (pn.PyneIncrementalSession.from_snapshot(script=script, snapshot=snapshot)
                if snapshot_kind == "local" else
                pn.PyneIncrementalSession.from_portable_snapshot(portable, script=script))
    for bar in BARS[1:]:
        actual = session.on_bar_closed(bar)
        expected = restored.on_bar_closed(bar)
        assert actual.ok and expected.ok
        assert actual.lines == expected.lines
        assert actual.output == expected.output
    assert actual.output["strategy"]["position"]["size"] == 1
    assert actual.output["strategy"]["summary"]["initial_capital"] == 1000
    assert math.isfinite(actual.output["strategy"]["summary"]["equity"])
    json.dumps(actual.output, allow_nan=False)
