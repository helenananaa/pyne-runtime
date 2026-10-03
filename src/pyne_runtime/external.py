"""Host-neutral external-broker/1: account frames in, market order intents out.

The host owns all matching/accounting. This evaluator never runs a native broker.
Batch and incremental scripts retain their normal language/data calculation paths.
"""
from __future__ import annotations

import math
import numpy as np

from .runtime import PyneRuntime
from .series import PyneSeries
from .incremental import PyneIncrementalSession, is_incremental_pyne_script
from .settings import PyneSettings

ACCOUNT_FIELDS = ("position_size", "position_avg_price", "equity", "initial_capital", "netprofit", "openprofit")


def unsupported(message):
    raise ValueError("PYNE_EXTERNAL_UNSUPPORTED: " + message)


class _NoRequests:
    def __getattr__(self, name):
        unsupported("external V1 does not accept request data")


class _PassRequests:
    """Stable facade for aliases; a fresh request cache for each scheduled pass."""
    def __init__(self):
        self.delegate = None

    def __getattr__(self, name):
        if self.delegate is None:
            unsupported("pass request data is only available during callbacks")
        return getattr(self.delegate, name)


class _PassProvider:
    def __init__(self, streams):
        from .data import PyneData
        if not isinstance(streams, list):
            unsupported("request_data must be a stream list")
        self.streams = {}
        for stream in streams:
            if (not isinstance(stream, dict) or set(stream) != {"symbol", "timeframe", "bars"}
                    or not isinstance(stream["symbol"], str) or not stream["symbol"].strip()
                    or not isinstance(stream["timeframe"], str)):
                unsupported("invalid requested stream")
            key = (stream["symbol"], stream["timeframe"])
            if key in self.streams:
                unsupported("duplicate requested stream")
            if stream["bars"]:
                PyneData.from_ohlcv(stream["bars"])
            self.streams[key] = stream["bars"]

    def get_ohlcv(self, symbol, timeframe, start, end):
        if (symbol, timeframe) not in self.streams:
            unsupported("missing requested stream " + symbol + "@" + timeframe)
        return [dict(bar) for bar in self.streams[symbol, timeframe] if start <= bar["time"] <= end]


class _IntentStrategy:
    long = "long"
    short = "short"
    touched = False

    def __init__(self, frames, collector=None, ctx=None, fill_passes=False):
        self.frames, self.collector, self.ctx = frames, collector, ctx
        self.intents = []
        self.declared = False
        self.pyramiding = 1
        self.fill_passes = fill_passes
        self.active_pass = None
        self.active_account = None

    def __getattr__(self, name):
        if name not in ACCOUNT_FIELDS:
            unsupported("account field or order API " + name)
        if self.ctx is not None:
            value = (self.active_account or self.frames[max(0, self.ctx.bar_index)])[name]
            return float("nan") if value is None else value
        return PyneSeries(np.asarray([float("nan") if frame[name] is None else frame[name] for frame in self.frames]))

    def __call__(self, title="", overlay=True, **settings):
        self.configure(**settings)
        if self.collector is not None:
            self.collector.set_indicator_meta(title=title, overlay=overlay)

    def configure(self, **settings):
        if (set(settings) - {"initial_capital", "pyramiding", "calc_on_order_fills"}
                or type(settings.get("pyramiding", 1)) is not int
                or settings.get("pyramiding", 1) < 1
                or settings.get("calc_on_order_fills", False) is not self.fill_passes):
            unsupported("host settings require positive pyramiding and explicit fill callback opt-in")
        if self.declared and self.pyramiding != settings.get("pyramiding", 1):
            unsupported("pyramiding must be fixed for an external run")
        self.pyramiding = settings.get("pyramiding", 1)
        self.declared = True

    def begin_bar(self):
        pass

    def end_bar(self):
        pass

    def prune_history(self, cutoff):
        pass

    def _emit(self, action, id, direction=None, qty=None, when=True, **fields):
        if not self.declared:
            unsupported("strategy declaration or configure is required")
        if action not in {"close_all", "cancel_all"} and (not isinstance(id, str) or not id):
            unsupported("nonempty string id is required")
        if direction is not None and direction not in {"long", "short"}:
            unsupported("invalid direction")
        if qty is not None and "qty_percent" in fields:
            unsupported("choose qty or qty_percent")
        if self.ctx is not None:
            indices = [self.ctx.bar_index] if bool(when) else []
        else:
            flags = np.asarray(when)
            if flags.ndim == 0:
                flags = np.full(len(self.frames), bool(flags))
            if flags.shape != (len(self.frames),) or flags.dtype.kind != "b":
                unsupported("condition must be a boolean series")
            indices = np.flatnonzero(flags)
        for index in indices:
            def number(value, name):
                values = np.asarray(value)
                if values.ndim == 0:
                    selected = float(values)
                elif self.ctx is None and values.shape == (len(self.frames),):
                    selected = float(values[index])
                else:
                    unsupported("order field must be scalar or a matching series")
                if not math.isfinite(selected) or selected <= 0 or (name == "qty_percent" and selected > 100):
                    unsupported("invalid price or quantity")
                return selected
            extra = {} if self.active_pass is None else {"pass_index": self.active_pass}
            for name, value in fields.items():
                if name == "from_entry":
                    if not isinstance(value, str):
                        unsupported("from_entry must be a string")
                    extra[name] = value
                else:
                    extra[name] = number(value, name)
            self.intents.append({"bar_index": int(index), "action": action, "id": id, "direction": direction,
                                 "qty": None if qty is None else number(qty, "qty"), **extra})

    def entry(self, id, direction="long", *, qty=1, when=True, **kwargs):
        if set(kwargs) - {"limit", "stop"}:
            unsupported("unsupported entry argument")
        self._emit("entry", id, direction, qty, when, **kwargs)

    def entry_when(self, condition, id, direction="long", *, qty=1, **kwargs):
        self.entry(id, direction, qty=qty, when=condition, **kwargs)

    def close(self, id, *, when=True, **kwargs):
        if set(kwargs) - {"qty", "qty_percent"}:
            unsupported("unsupported close argument")
        self._emit("close", id, when=when, **kwargs)

    def close_when(self, condition, id, **kwargs):
        self.close(id, when=condition, **kwargs)

    def close_all(self, *, when=True, **kwargs):
        if kwargs:
            unsupported("V1 accepts full market close only")
        self._emit("close_all", "", when=when)

    def exit(self, id, from_entry="", *, when=True, **kwargs):
        if set(kwargs) - {"qty", "qty_percent", "limit", "stop", "profit", "loss", "trail_price", "trail_points", "trail_offset"}:
            unsupported("unsupported exit argument")
        activation = {"trail_price", "trail_points"} & set(kwargs)
        if bool(activation) != ("trail_offset" in kwargs) or len(activation) > 1:
            unsupported("trailing exit requires one activation and trail_offset")
        if not ({"limit", "stop", "profit", "loss", "trail_offset"} & set(kwargs)):
            unsupported("exit requires a price, distance or trailing bracket")
        self._emit("exit", id, when=when, from_entry=from_entry, **kwargs)

    def exit_when(self, condition, id, from_entry="", **kwargs):
        self.exit(id, from_entry, when=condition, **kwargs)

    def cancel(self, id, *, when=True):
        self._emit("cancel", id, when=when)

    def cancel_all(self, *, when=True):
        self._emit("cancel_all", "", when=when)


def run_external(source, bars, accounts, *, params=None, settings=None, execution_passes=None, allow_requests=False):
    """Evaluate a historical prefix using exactly one host account frame per bar.

    Callers must persist earlier frames and verify prefix-stable intent history.
    Returned output contains graphics but no native trades, balance or fills.
    """
    if len(accounts) != len(bars) or not bars:
        unsupported("account feedback count differs from bars")
    feedback = list(zip(bars, accounts, strict=True))
    if execution_passes is not None:
        if not is_incremental_pyne_script(source) or len(execution_passes) != len(bars):
            unsupported("fill feedback requires an incremental script and matching pass groups")
        for bar, group in zip(bars, execution_passes, strict=True):
            if not group:
                unsupported("invalid pass count")
            previous = None
            for event in group:
                if ((set(event) - {"request_data"}) != {"bar", "account", "event_time_ms", "confirmed"}
                        or type(event["confirmed"]) is not bool or type(event["event_time_ms"]) is not int
                        or event["bar"]["time"] != bar["time"] or event["event_time_ms"] < bar["time"]*1000
                        or (previous and (previous["confirmed"] or previous["event_time_ms"] > event["event_time_ms"]))):
                    unsupported("invalid execution pass")
                from .data import PyneData
                PyneData.from_ohlcv([event["bar"]])
                feedback.append((event["bar"], event["account"]))
                if "request_data" in event:
                    _PassProvider(event["request_data"])
                previous = event
    for bar, frame in feedback:
        if set(frame) != {"time", *ACCOUNT_FIELDS} or frame["time"] != bar["time"]:
            unsupported("invalid account fields or time")
        for name in ACCOUNT_FIELDS:
            if frame[name] is None and name == "position_avg_price" and frame["position_size"] == 0:
                continue
            if not isinstance(frame[name], (int, float)) or isinstance(frame[name], bool) or not math.isfinite(frame[name]):
                unsupported("nonfinite account feedback")
    settings = settings or PyneSettings()
    if is_incremental_pyne_script(source):
        class ExternalSession(PyneIncrementalSession):
            observer = None
            def _call_optional(self, func, ctx):
                if self.observer is None:
                    self.observer = _IntentStrategy(accounts, ctx=ctx, fill_passes=execution_passes is not None)
                    ctx.strategy = self.observer
                    if not allow_requests:
                        self._globals["request"] = _NoRequests()
                    elif execution_passes is not None:
                        self.pass_requests = _PassRequests()
                        self._globals["request"] = self.pass_requests
                return super()._call_optional(func, ctx)
            def _run_bar(self, ctx, bar, **kwargs):
                if execution_passes is None:
                    return super()._run_bar(ctx, bar, **kwargs)
                from .incremental.bar import IncrementalBar
                from .barstate import PyneIncrementalBarState
                on_fill = self._globals.get("on_fill")
                if not callable(on_fill):
                    unsupported("fill feedback requires on_fill(ctx, bar)")
                normal = self._on_bar
                try:
                    group = execution_passes[kwargs["bar_index"]]
                    for index, event in enumerate(group):
                        if allow_requests:
                            from .incremental.request import IncrementalRequestModule
                            provider = (_PassProvider(event["request_data"]) if "request_data" in event
                                        else self.settings.data_provider)
                            self.pass_requests.delegate = IncrementalRequestModule(
                                lambda: ctx, settings=self.settings, provider=provider)
                        self.observer.active_pass = index
                        self.observer.active_account = event["account"]
                        self._on_bar = normal if event["confirmed"] else on_fill
                        state = PyneIncrementalBarState(isfirst=kwargs["bar_index"] == 0,
                            islast=kwargs["bar_index"] == kwargs["last_bar_index"], ishistory=True,
                            isrealtime=False, isnew=index == 0, isconfirmed=event["confirmed"],
                            islastconfirmedhistory=event["confirmed"] and kwargs["bar_index"] == kwargs["last_bar_index"])
                        super()._run_bar(ctx, IncrementalBar.from_dict(event["bar"], is_confirmed=event["confirmed"]),
                            **{**kwargs, "barstate": state})
                finally:
                    self._on_bar = normal
        session = ExternalSession(script=source, params=params or {}, settings=settings)
        result = session.seed(bars)
        strategy = session.observer
    else:
        class ExternalBatch(PyneRuntime):
            observer = None
            def _build_namespace(self, services):
                namespace = super()._build_namespace(services)
                self.observer = _IntentStrategy(accounts, collector=services.collector)
                namespace["strategy"] = self.observer
                if not allow_requests:
                    namespace["request"] = _NoRequests()
                return namespace
        runtime = ExternalBatch(settings=settings)
        result = runtime.execute(source, bars, params or {})
        strategy = runtime.observer
    if not result.ok:
        unsupported(str(result.error))
    if strategy is None or not strategy.declared:
        unsupported("strategy declaration is required")
    if result.output.get("strategy"):
        unsupported("native account output is forbidden")
    return {"protocol": "external-broker/1", "pyramiding": strategy.pyramiding, "intents": sorted(strategy.intents, key=lambda intent: intent["bar_index"]),
            "output": result.output, "graphics": result.lines}
