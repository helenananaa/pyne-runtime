"""Script namespace assembly for batch Pyne runtime execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import numpy as np

from . import utils
from .cache import PyneExecutionScope
from .chart import ChartNamespace
from .collections import ArrayNamespace, MapNamespace, MatrixNamespace, order_namespace
from .color import color as color_singleton
from .context import PyneContext
from .input import InputModule
from .math_ext import PyneMath
from .pine_libraries import PineLibraryRegistry
from .plot import OutputCollector, create_plot_functions
from .request import RequestModule, barmerge
from .runtime_ext import runtime_namespace
from .security import PyneSecurityPolicy, build_builtins
from .series import switch as series_switch
from .series import when as series_when
from .series import where as series_where
from .settings import PyneSettings
from .state import PyneStateNamespace
from .strategy import StrategyModule
from .string_ext import string_namespace
from .ta import TaModule
from .ticker import TickerNamespace
from .time_ext import dayofweek_namespace, time_namespace
from .trace import PyneTraceRecorder


@dataclass
class RuntimeServices:
    """Runtime-scoped services used to build a script namespace."""

    ctx: PyneContext
    settings: PyneSettings
    params: dict[str, Any]
    policy: PyneSecurityPolicy
    execution_scope: PyneExecutionScope | None = None
    trace: PyneTraceRecorder | None = None
    ta: TaModule = field(init=False)
    input: InputModule = field(init=False)
    state: PyneStateNamespace = field(init=False)
    collector: OutputCollector = field(init=False)
    plot_functions: dict[str, Any] = field(init=False)
    request: RequestModule = field(init=False)
    strategy: StrategyModule = field(init=False)

    def __post_init__(self) -> None:
        if self.execution_scope is None:
            self.execution_scope = PyneExecutionScope.fresh(
                max_items=self.settings.cache_max_items,
            )
        from .incremental.session import _readonly_params

        self.params = _readonly_params(self.params)
        self.ta = TaModule(self.ctx)
        self.input = InputModule(params=self.params, context=self.ctx)
        self.state = PyneStateNamespace()
        self.collector = OutputCollector(
            times=self.ctx.times,
            max_drawing_objects=self.settings.max_drawing_objects,
        )
        self.plot_functions = create_plot_functions(self.collector)
        self.request = RequestModule(self.ctx, provider=self.settings.data_provider)
        self.strategy = StrategyModule(
            self.ctx,
            self.collector,
            max_pending_order_operations=self.policy.max_strategy_pending_operations,
        )
        if self.trace is None:
            self.trace = PyneTraceRecorder(
                enabled=self.settings.trace_enabled,
                max_events=self.settings.trace_max_events,
                timings_enabled=self.settings.trace_timings_enabled,
                span_events=self.settings.trace_span_events,
                slow_span_ms=self.settings.trace_slow_span_ms,
                redacted_fields=self.settings.trace_redacted_fields,
            )


def build_script_namespace(services: RuntimeServices) -> dict[str, Any]:
    """Build the global namespace injected into user scripts."""
    namespace: dict[str, Any] = {}
    for installer in (
        install_data_namespace,
        install_api_namespace,
        install_plot_namespace,
        install_utility_namespace,
        install_compat_namespace,
        install_builtins_namespace,
    ):
        _run_namespace_installer(namespace, services, installer)
    return namespace


def _run_namespace_installer(
    namespace: dict[str, Any],
    services: RuntimeServices,
    installer: Any,
) -> None:
    before = dict(namespace)
    installer(namespace, services)
    overwritten = [key for key, value in before.items() if namespace.get(key) is not value]
    if overwritten:
        names = ", ".join(sorted(overwritten))
        raise RuntimeError(f"Pyne namespace installer overwrote existing keys: {names}")


def install_data_namespace(namespace: dict[str, Any], services: RuntimeServices) -> None:
    """Install OHLCV and derived source names."""
    ctx = services.ctx
    namespace["open"] = ctx.open
    namespace["high"] = ctx.high
    namespace["low"] = ctx.low
    namespace["close"] = ctx.close
    namespace["volume"] = ctx.volume
    namespace["time"] = time_namespace(
        ctx.time,
        timeframe=ctx.timeframe,
        timezone=ctx.syminfo.timezone or "UTC",
    )
    namespace["dayofweek"] = dayofweek_namespace(ctx.time, ctx.syminfo.timezone or "UTC")
    namespace["time_close"] = ctx.time_close
    namespace["bar_index"] = ctx.bar_index
    namespace["last_bar_index"] = ctx.last_bar_index
    namespace["barstate"] = ctx.barstate
    namespace["bar_count"] = ctx.bar_count
    namespace["syminfo"] = ctx.syminfo
    namespace["timeframe"] = ctx.timeframe
    namespace["session"] = ctx.session
    namespace["hl2"] = ctx.hl2
    namespace["hlc3"] = ctx.hlc3
    namespace["ohlc4"] = ctx.ohlc4
    namespace["hlcc4"] = ctx.hlcc4


def install_api_namespace(namespace: dict[str, Any], services: RuntimeServices) -> None:
    """Install Pine-like module namespaces."""
    ctx = services.ctx
    namespace["ta"] = services.ta
    namespace["input"] = services.input
    namespace["request"] = services.request
    namespace["pine_library"] = PineLibraryRegistry(services.ctx, services.request)
    namespace["runtime"] = runtime_namespace
    namespace["barmerge"] = barmerge
    namespace["strategy"] = services.strategy
    namespace["trace"] = services.trace
    namespace["array"] = ArrayNamespace(
        max_size=services.policy.max_array_size,
        max_depth=services.policy.max_collection_depth,
    )
    namespace["map"] = MapNamespace(
        max_size=services.policy.max_map_size,
        array_max_size=services.policy.max_array_size,
        max_depth=services.policy.max_collection_depth,
    )
    namespace["matrix"] = MatrixNamespace(
        max_cells=services.policy.max_matrix_cells,
        array_max_size=services.policy.max_array_size,
        max_depth=services.policy.max_collection_depth,
    )
    namespace["order"] = order_namespace
    namespace["str"] = string_namespace
    namespace["ticker"] = TickerNamespace(ctx.syminfo)
    namespace["color"] = color_singleton
    namespace["math"] = PyneMath(mintick=getattr(ctx.syminfo, "mintick", 1.0))
    namespace["chart"] = ChartNamespace(
        current_time=ctx.time,
        current_index=ctx.bar_index,
    )
    namespace["pyne"] = _pyne_namespace(services)
    namespace["cache"] = namespace["pyne"].cache
    namespace["cache_clear"] = namespace["pyne"].cache_clear
    namespace["cache_stats"] = namespace["pyne"].cache_stats
    namespace["var"] = services.state.var
    namespace["state"] = services.state.state


def install_plot_namespace(namespace: dict[str, Any], services: RuntimeServices) -> None:
    """Install plot, drawing, and display helper functions."""
    namespace.update(services.plot_functions)


def install_utility_namespace(namespace: dict[str, Any], services: RuntimeServices) -> None:
    """Install top-level utility functions and common TA aliases."""
    ta = services.ta
    math_namespace = namespace["math"]
    chart_time = namespace["time"]
    namespace["crossover"] = utils.crossover
    namespace["cross"] = utils.cross
    namespace["crossunder"] = utils.crossunder
    namespace["when"] = series_when
    namespace["iff"] = series_when
    namespace["where"] = series_where
    namespace["switch"] = series_switch
    namespace["ref"] = utils.shift
    namespace["highest"] = utils.highest
    namespace["highestbars"] = utils.highestbars
    namespace["lowest"] = utils.lowest
    namespace["lowestbars"] = utils.lowestbars
    namespace["change"] = utils.change
    namespace["roc"] = utils.roc
    namespace["barssince"] = utils.barssince
    namespace["valuewhen"] = utils.valuewhen
    namespace["shift"] = utils.shift
    namespace["na"] = utils.na
    namespace["nz"] = utils.nz
    namespace["fixnan"] = utils.fixnan
    namespace["na_check"] = utils.na_check
    namespace["cum"] = utils.cum
    namespace["rising"] = utils.rising
    namespace["falling"] = utils.falling
    namespace["true"] = True
    namespace["false"] = False
    namespace["sma"] = ta.sma
    namespace["ema"] = ta.ema
    namespace["wma"] = ta.wma
    namespace["rma"] = ta.rma
    namespace["vwma"] = ta.vwma
    namespace["vwap"] = ta.vwap
    namespace["rsi"] = ta.rsi
    namespace["macd"] = ta.macd
    namespace["atr"] = ta.atr
    namespace["bb"] = ta.bb
    namespace["cci"] = ta.cci
    namespace["linreg"] = ta.linreg
    namespace["mfi"] = ta.mfi
    namespace["mom"] = ta.mom
    namespace["pivothigh"] = ta.pivothigh
    namespace["pivotlow"] = ta.pivotlow
    namespace["stdev"] = ta.stdev
    namespace["stoch"] = ta.stoch
    namespace["tostring"] = string_namespace.tostring
    namespace["security"] = _legacy_security(services.request)
    namespace["heikinashi"] = namespace["ticker"].heikinashi
    namespace["timestamp"] = chart_time.timestamp
    namespace["year"] = chart_time.year
    namespace["month"] = chart_time.month
    namespace["dayofmonth"] = chart_time.dayofmonth
    namespace["hour"] = chart_time.hour
    namespace["minute"] = chart_time.minute
    namespace["second"] = chart_time.second
    for name in (
        "abs",
        "avg",
        "ceil",
        "cos",
        "exp",
        "floor",
        "log",
        "log10",
        "max",
        "min",
        "pow",
        "round",
        "sign",
        "sin",
        "sqrt",
        "sum",
        "tan",
    ):
        namespace[name] = getattr(math_namespace, name)


def install_compat_namespace(namespace: dict[str, Any], services: RuntimeServices) -> None:
    """Install Python and legacy compatibility names."""
    namespace["np"] = np
    namespace["numpy"] = np
    namespace["params"] = services.params


def install_builtins_namespace(namespace: dict[str, Any], services: RuntimeServices) -> None:
    """Install policy-controlled builtins."""
    namespace["__builtins__"] = build_builtins(services.policy)


def _pyne_namespace(services: RuntimeServices) -> SimpleNamespace:
    if services.execution_scope is None:  # pragma: no cover - guarded by __post_init__
        raise RuntimeError("Runtime services have no execution scope")
    cache = services.execution_scope.cache
    return SimpleNamespace(
        cache=cache.get_or_load,
        cache_clear=cache.clear,
        cache_stats=cache.stats,
        var=services.state.var,
        state=services.state.state,
        state_snapshot=services.state.snapshot,
    )


def _legacy_security(request: RequestModule) -> Any:
    """Expose Pine v4's positional ``security`` spelling over request.security."""

    def security(
        symbol: str,
        timeframe: str,
        expression: Any,
        gaps: str = barmerge.gaps_off,
        lookahead: str = barmerge.lookahead_off,
    ) -> Any:
        return request.security(
            symbol,
            timeframe,
            expression,
            gaps=gaps,
            lookahead=lookahead,
        )

    return security
