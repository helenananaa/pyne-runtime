"""Long-lived incremental execution session."""

from __future__ import annotations

import builtins as python_builtins
import copy
import hashlib
import inspect
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from types import (
    BuiltinFunctionType,
    BuiltinMethodType,
    FunctionType,
    GetSetDescriptorType,
    MemberDescriptorType,
    MethodType,
    ModuleType,
    SimpleNamespace,
)
from typing import Any, Callable

from ..barstate import PyneIncrementalBarState
from ..capabilities import capability_diagnostics
from ..cache import PyneCache, PyneCacheNamespace, PyneCacheSnapshot, PyneExecutionScope
from ..chart import ChartNamespace
from ..collections import ArrayNamespace, MapNamespace, MatrixNamespace, order_namespace
from ..color import color as color_singleton
from ..data import PyneData
from ..math_ext import PyneMath
from ..plot.objects import _DrawingNamespace
from ..request import DataProvider, barmerge
from ..security import (
    PyneSecurityError,
    PyneSecurityPolicy,
    build_builtins,
    execution_timeout,
    validate_script_security,
)
from ..settings import PyneSettings
from ..trace import PyneTraceRecorder, bounded_trace_value
from .bar import IncrementalBar
from .checkpoint import (
    DEFAULT_PORTABLE_SNAPSHOT_MAX_BYTES,
    INCREMENTAL_SEMANTICS_VERSION,
    PortableCheckpoint,
    PortableStateCheckpoint,
    PynePortableSnapshotError,
    decode_portable_checkpoint,
    decode_portable_state_checkpoint,
    encode_portable_checkpoint,
    encode_portable_state_checkpoint,
    portable_snapshot_format,
    portable_settings_contract,
    settings_from_portable_contract,
    validate_snapshot_semantics,
)
from .context import IncrementalContext
from .limits import (
    IncrementalLimits,
    IncrementalResourceLimitError,
    _state_payload_items,
)
from .result import IncrementalPyneResult
from .request import IncrementalRequestModule


PYNE_INCREMENTAL_SNAPSHOT_VERSION = 2


@dataclass(frozen=True)
class _FunctionStateSnapshot:
    defaults: Any
    kwdefaults: Any
    attributes: dict[str, Any]


@dataclass(frozen=True)
class PyneIncrementalSessionSnapshot:
    """Opaque process-local snapshot of committed incremental state."""

    schema_version: int
    script_sha256: str
    params: dict[str, Any]
    security_mode: str
    retention_bars: int
    context: IncrementalContext | None
    meta: dict[str, Any]
    global_values: dict[str, Any]
    function_states: dict[str, _FunctionStateSnapshot]
    cache: PyneCacheSnapshot
    last_closed_time: int | None
    closed_count: int
    retained_closed_times: tuple[int, ...]
    portable_bars: tuple[dict[str, Any], ...]
    portable_seed_count: int
    portable_complete: bool
    namespace_names: tuple[str, ...] = ()
    trace: PyneTraceRecorder | None = None
    semantics_version: int | None = None


class PyneIncrementalSession:
    """Long-lived incremental Pyne execution session."""

    def __init__(
        self,
        *,
        script: str,
        params: dict[str, Any] | None = None,
        security_mode: str | None = None,
        policy: PyneSecurityPolicy | None = None,
        settings: PyneSettings | None = None,
        execution_scope: PyneExecutionScope | None = None,
        retention_bars: int | None = None,
        trace: PyneTraceRecorder | None = None,
    ) -> None:
        self.script = script
        self.params = _readonly_params(params or {})
        self.settings = settings or PyneSettings.from_env()
        self.policy = policy or PyneSecurityPolicy.from_settings(self.settings, security_mode)
        self.retention_bars = min(
            self.policy.max_bars,
            max(int(retention_bars or self.settings.incremental_retention_bars), 1),
        )
        self.execution_scope = execution_scope or PyneExecutionScope.fresh(
            max_items=self.settings.cache_max_items,
        )
        self.security_mode = self.policy.mode
        self.trace = trace or PyneTraceRecorder(
            enabled=self.settings.trace_enabled,
            max_events=self.settings.trace_max_events,
            timings_enabled=self.settings.trace_timings_enabled,
            span_events=self.settings.trace_span_events,
            slow_span_ms=self.settings.trace_slow_span_ms,
            redacted_fields=self.settings.trace_redacted_fields,
        )
        self._limits = IncrementalLimits.for_policy(
            self.policy,
            retention_bars=self.retention_bars,
        )
        self._globals: dict[str, Any] = {}
        self._meta: dict[str, Any] = {}
        self._init_func: Callable[..., Any] | None = None
        self._on_bar: Callable[..., Any] | None = None
        self._on_preview: Callable[..., Any] | None = None
        self._ctx: IncrementalContext | None = None
        self._active_ctx: IncrementalContext | None = None
        self._prepared = False
        self.last_closed_time: int | None = None
        self._closed_count = 0
        self._active_preview_time: int | None = None
        self._preview_varip_states: dict[str, Any] = {}
        self._base_namespace_names: set[str] = set()
        self._base_namespace_values: dict[str, Any] = {}
        self._prepared_namespace_names: set[str] = set()
        self._prepared_namespace_values: dict[str, Any] = {}
        self._cache_namespace: PyneCacheNamespace | None = None
        self._poisoned_reason: str | None = None
        self._retained_closed_times: list[int] = []
        self._portable_bars: list[dict[str, Any]] = []
        self._portable_seed_count = 0
        self._portable_complete = True

    def prepare(self) -> None:
        self._ensure_healthy()
        if self._prepared:
            return
        validate_script_security(self.script, self.policy)
        unsupported = capability_diagnostics(self.script, runtime_mode="incremental")
        if unsupported:
            raise PyneSecurityError(str(unsupported[0]["message"]))
        self._globals = self._build_namespace()
        self._base_namespace_names = set(self._globals)
        self._base_namespace_values = dict(self._globals)
        with execution_timeout(self.policy.timeout_seconds):
            exec(self.script, self._globals)  # noqa: S102
        self._init_func = self._globals.get("init") if callable(self._globals.get("init")) else None
        self._on_bar = (
            self._globals.get("on_bar") if callable(self._globals.get("on_bar")) else None
        )
        self._on_preview = (
            self._globals.get("on_preview") if callable(self._globals.get("on_preview")) else None
        )
        if self._on_bar is None:
            raise PyneSecurityError("Incremental Pyne scripts must define on_bar(ctx, bar)")
        self._prepared_namespace_names = set(self._globals)
        self._prepared_namespace_values = dict(self._globals)
        self._prepared = True

    def seed(
        self,
        ohlcv: list[dict[str, Any]],
        *,
        start_s: int | None = None,
        end_s: int | None = None,
    ) -> IncrementalPyneResult:
        self._ensure_healthy()
        if len(ohlcv) > self.policy.max_bars:
            error = PyneSecurityError(f"Too many data points (max {self.policy.max_bars})")
            self._poison(error)
            raise error
        PyneData.from_ohlcv(ohlcv, allow_empty=True)
        self.prepare()
        self._ctx = IncrementalContext(
            params=self.params,
            meta=self._meta,
            limits=self._limits,
            syminfo=self.settings.syminfo,
            timeframe=self.settings.timeframe,
            session=self.settings.session,
            max_drawing_objects=self.settings.max_drawing_objects,
            trace=self.trace,
        )
        self._call_optional(self._init_func, self._ctx)
        self._closed_count = 0
        self.last_closed_time = None
        self._active_preview_time = None
        self._preview_varip_states = {}
        self._retained_closed_times = []
        portable_bars: list[dict[str, Any]] = []
        last_bar_index = len(ohlcv) - 1
        for index, item in enumerate(ohlcv):
            bar = IncrementalBar.from_dict(item, is_confirmed=True)
            self._run_bar(
                self._ctx,
                bar,
                preview=False,
                bar_index=index,
                last_bar_index=last_bar_index,
                barstate=PyneIncrementalBarState(
                    isfirst=index == 0,
                    islast=index == last_bar_index,
                    ishistory=True,
                    isrealtime=False,
                    isnew=True,
                    isconfirmed=True,
                    islastconfirmedhistory=index == last_bar_index,
                ),
            )
            self.last_closed_time = bar.time
            self._closed_count = index + 1
            self._commit_retention(bar.time)
            portable_bars.append(copy.deepcopy(bar.raw))
        self._portable_bars = portable_bars
        self._portable_seed_count = len(portable_bars)
        self._portable_complete = True
        return self._to_result(self._ctx, start_s=start_s, end_s=end_s)

    def on_bar_closed(self, item: dict[str, Any]) -> IncrementalPyneResult:
        self._ensure_healthy()
        bar = IncrementalBar.from_dict(item, is_confirmed=True)
        self._validate_event_time(bar, preview=False)
        self.prepare()
        if self._ctx is None:
            self._ctx = IncrementalContext(
                params=self.params,
                meta=self._meta,
                limits=self._limits,
                syminfo=self.settings.syminfo,
                timeframe=self.settings.timeframe,
                session=self.settings.session,
                max_drawing_objects=self.settings.max_drawing_objects,
                trace=self.trace,
            )
            self._call_optional(self._init_func, self._ctx)
        bar_index = self._closed_count
        had_preview = self._active_preview_time == bar.time
        self._run_bar(
            self._ctx,
            bar,
            preview=False,
            bar_index=bar_index,
            last_bar_index=bar_index,
            barstate=PyneIncrementalBarState(
                isfirst=bar_index == 0,
                islast=True,
                ishistory=False,
                isrealtime=True,
                isnew=not had_preview,
                isconfirmed=True,
                islastconfirmedhistory=False,
            ),
        )
        self.last_closed_time = bar.time
        self._closed_count = bar_index + 1
        self._commit_retention(bar.time)
        self._record_portable_bar(bar)
        if self._active_preview_time is not None and bar.time >= self._active_preview_time:
            self._active_preview_time = None
            self._preview_varip_states = {}
        return self._to_result(self._ctx, start_s=bar.time, end_s=bar.time)

    def on_bar_updated(self, item: dict[str, Any]) -> IncrementalPyneResult:
        self._ensure_healthy()
        bar = IncrementalBar.from_dict(item, is_confirmed=False)
        self._validate_event_time(bar, preview=True)
        self.prepare()
        if self._ctx is None:
            self._ctx = IncrementalContext(
                params=self.params,
                meta=self._meta,
                limits=self._limits,
                syminfo=self.settings.syminfo,
                timeframe=self.settings.timeframe,
                session=self.settings.session,
                max_drawing_objects=self.settings.max_drawing_objects,
                trace=self.trace,
            )
            self._call_optional(self._init_func, self._ctx)
        preview_ctx = self._ctx.clone_for_preview()
        bar_index = self._closed_count
        is_new = self._active_preview_time != bar.time
        if is_new:
            self._preview_varip_states = {}
        try:
            preview_ctx.adopt_varip_states(self._preview_varip_states)
        except (PyneSecurityError, IncrementalResourceLimitError) as exc:
            self._poison(exc)
            raise
        self._run_bar(
            preview_ctx,
            bar,
            preview=True,
            bar_index=bar_index,
            last_bar_index=bar_index,
            barstate=PyneIncrementalBarState(
                isfirst=bar_index == 0,
                islast=True,
                ishistory=False,
                isrealtime=True,
                isnew=is_new,
                isconfirmed=False,
                islastconfirmedhistory=False,
            ),
        )
        self._active_preview_time = bar.time
        return self._to_result(preview_ctx, start_s=bar.time, end_s=bar.time)

    def _run_bar(
        self,
        ctx: IncrementalContext,
        bar: IncrementalBar,
        *,
        preview: bool,
        bar_index: int,
        last_bar_index: int,
        barstate: PyneIncrementalBarState,
    ) -> None:
        try:
            before_state = (
                {
                    key: bounded_trace_value(
                        cell.value,
                        redacted_fields=ctx.trace.redacted_fields,
                    )
                    for key, cell in {**ctx._states, **ctx._varip_states}.items()
                }
                if ctx.trace.enabled
                else {}
            )
            ctx.begin_bar(
                bar,
                bar_index=bar_index,
                last_bar_index=last_bar_index,
                barstate=barstate,
            )
            func = self._on_preview if preview and self._on_preview is not None else self._on_bar
            previous_ctx = self._active_ctx
            previous_request_namespace = ctx._request_namespace
            self._active_ctx = ctx
            ctx._request_namespace = self._globals["request"]
            try:
                callback_name = "on_preview" if preview and self._on_preview is not None else "on_bar"
                with ctx.trace.span(
                    f"callback.{callback_name}",
                    category="callback",
                    time=bar.time,
                    preview=preview,
                ):
                    with self._preview_global_scope(enabled=preview, func=func) as active_func:
                        with execution_timeout(self.policy.timeout_seconds):
                            self._call_required(active_func, ctx, bar)
            finally:
                ctx._request_namespace = previous_request_namespace
                self._active_ctx = previous_ctx
            ctx.sync_varip_payload()
            ctx.strategy.end_bar()
            if ctx.trace.enabled:
                after_cells = {**ctx._states, **ctx._varip_states}
                for key, cell in after_cells.items():
                    previous = before_state.get(key)
                    current = bounded_trace_value(
                        cell.value,
                        redacted_fields=ctx.trace.redacted_fields,
                    )
                    if previous != current:
                        ctx.trace._emit_runtime(
                            "state.change",
                            time=bar.time,
                            name=key,
                            previous=previous,
                            current=current,
                            preview=preview,
                        )
                if ctx.strategy.touched:
                    ctx.trace._emit_runtime(
                        "strategy.bar",
                        time=bar.time,
                        position=ctx.strategy.position_size,
                        orders=len(ctx.strategy._orders),
                        closedTrades=len(ctx.strategy._closed_trades),
                        preview=preview,
                    )
            if barstate.isconfirmed and not preview:
                ctx.commit_request_bar()
                ctx.commit_state_history()
        except Exception as exc:
            self._poison(exc)
            raise

    def _commit_retention(self, bar_time: int) -> None:
        self._retained_closed_times.append(int(bar_time))
        if len(self._retained_closed_times) <= self.retention_bars:
            return
        del self._retained_closed_times[: -self.retention_bars]
        if self._ctx is not None:
            self._ctx.prune_before_time(self._retained_closed_times[0])

    def _record_portable_bar(self, bar: IncrementalBar) -> None:
        if not self._portable_complete:
            return
        if len(self._portable_bars) >= self.policy.max_bars:
            self._portable_bars = []
            self._portable_seed_count = 0
            self._portable_complete = False
            return
        self._portable_bars.append(copy.deepcopy(bar.raw))

    def _ensure_healthy(self) -> None:
        if self._poisoned_reason is not None:
            raise PyneSecurityError(
                "Incremental session is poisoned after a callback failure: "
                f"{self._poisoned_reason}"
            )

    def _poison(self, error: BaseException) -> None:
        if self._poisoned_reason is None:
            self._poisoned_reason = str(error)
        self._ctx = None
        self._active_ctx = None
        self._active_preview_time = None
        self._preview_varip_states = {}

    def _validate_event_time(self, bar: IncrementalBar, *, preview: bool) -> None:
        if self.last_closed_time is not None and bar.time <= self.last_closed_time:
            raise ValueError("OHLCV time values must be strictly increasing")
        if self._active_preview_time is not None and bar.time < self._active_preview_time:
            event = "preview" if preview else "closed"
            raise ValueError(f"Incremental {event} bar time cannot move backwards")

    @contextmanager
    def _preview_global_scope(
        self,
        *,
        enabled: bool,
        func: Callable[..., Any] | None,
    ) -> Iterator[Callable[..., Any] | None]:
        if not enabled:
            yield func
            return

        original_globals = dict(self._globals)
        user_globals = {
            key: value
            for key, value in original_globals.items()
            if key not in self._base_namespace_names
            or value is not self._base_namespace_values[key]
        }
        if self._ctx is not None:
            self._ctx._limit_tracker.validate_preview_payload(
                _preview_payload_items(user_globals.values())
            )
        try:
            preview_globals, memo = _clone_preview_globals(
                original_globals,
                script_globals=self._globals,
                base_values=self._base_namespace_values,
            )
        except PyneSecurityError:
            raise
        except Exception as exc:
            failed_names = _unisolatable_preview_globals(user_globals)
            names = ", ".join(failed_names) if failed_names else "unknown"
            raise PyneSecurityError(
                f"Incremental preview cannot isolate module globals: {names}. "
                "Use deepcopy-compatible values or keep intrabar state in ctx.varip()."
            ) from exc

        preview_func = memo.get(id(func), func) if func is not None else None
        if self._cache_namespace is None:
            raise PyneSecurityError("Incremental preview cache namespace is unavailable")
        preview_cache = _clone_preview_cache(self.execution_scope.cache)
        self._globals.clear()
        self._globals.update(preview_globals)
        try:
            with self._cache_namespace._using_cache(preview_cache):
                yield preview_func
        finally:
            self._globals.clear()
            self._globals.update(original_globals)

    def _build_namespace(self) -> dict[str, Any]:
        def indicator(title: str = "", overlay: bool = True, **kwargs: Any) -> None:
            self._meta = {"title": title, "overlay": overlay, **kwargs}

        def active_ctx(feature: str) -> IncrementalContext:
            if self._active_ctx is None:
                raise PyneSecurityError(f"{feature} can only be used inside incremental callbacks")
            return self._active_ctx

        def state(name: str, default: Any = None):
            return active_ctx("state()").state(name, default)

        def varip(name: str, default: Any = None):
            return active_ctx("varip()").varip(name, default)

        drawing_namespaces = self._drawing_namespaces()
        request_namespace = IncrementalRequestModule(
            lambda: active_ctx("request.*"),
            settings=self.settings,
            provider=self.settings.data_provider,
        )
        cache_namespace = PyneCacheNamespace(self.execution_scope.cache)
        self._cache_namespace = cache_namespace
        trace_namespace = SimpleNamespace(
            emit=lambda event, **details: active_ctx("trace.emit()").trace.emit(
                event,
                **details,
            )
        )
        pyne_namespace = SimpleNamespace(
            cache=cache_namespace.cache,
            cache_clear=cache_namespace.cache_clear,
            cache_stats=cache_namespace.cache_stats,
            state=state,
            var=state,
            varip=varip,
        )
        return {
            "indicator": indicator,
            "params": self.params,
            "syminfo": self.settings.syminfo,
            "timeframe": self.settings.timeframe,
            "session": self.settings.session,
            "true": True,
            "false": False,
            "color": color_singleton,
            "math": PyneMath(mintick=getattr(self.settings.syminfo, "mintick", 0.01)),
            "array": ArrayNamespace(
                max_size=self.policy.max_array_size,
                max_depth=self.policy.max_collection_depth,
            ),
            "map": MapNamespace(
                max_size=self.policy.max_map_size,
                array_max_size=self.policy.max_array_size,
                max_depth=self.policy.max_collection_depth,
            ),
            "matrix": MatrixNamespace(
                max_cells=self.policy.max_matrix_cells,
                array_max_size=self.policy.max_array_size,
                max_depth=self.policy.max_collection_depth,
            ),
            "order": order_namespace,
            "pyne": pyne_namespace,
            "cache": cache_namespace.cache,
            "cache_clear": cache_namespace.cache_clear,
            "cache_stats": cache_namespace.cache_stats,
            "state": state,
            "var": state,
            "varip": varip,
            "request": request_namespace,
            "trace": trace_namespace,
            "barmerge": barmerge,
            "security": request_namespace.security,
            **drawing_namespaces,
            "__builtins__": build_builtins(self.policy),
        }

    def _drawing_namespaces(self) -> dict[str, Any]:
        def ctx() -> IncrementalContext:
            if self._active_ctx is None:
                raise PyneSecurityError(
                    "Drawing objects can only be mutated inside incremental callbacks"
                )
            return self._active_ctx

        def current_time() -> int | None:
            active = ctx()
            return None if active.current_bar is None else active.current_bar.time

        line_namespace = _DrawingNamespace(
            all_getter=lambda: ctx().line_all(),
            new=lambda *args, **kwargs: ctx().line_new(*args, **kwargs),
            set_xy1=lambda *args, **kwargs: ctx().line_set_xy1(*args, **kwargs),
            set_xy2=lambda *args, **kwargs: ctx().line_set_xy2(*args, **kwargs),
            set_first_point=lambda *args, **kwargs: ctx().line_set_first_point(
                *args,
                **kwargs,
            ),
            set_second_point=lambda *args, **kwargs: ctx().line_set_second_point(
                *args,
                **kwargs,
            ),
            set_x1=lambda *args, **kwargs: ctx().line_set_x1(*args, **kwargs),
            set_y1=lambda *args, **kwargs: ctx().line_set_y1(*args, **kwargs),
            set_x2=lambda *args, **kwargs: ctx().line_set_x2(*args, **kwargs),
            set_y2=lambda *args, **kwargs: ctx().line_set_y2(*args, **kwargs),
            set_color=lambda *args, **kwargs: ctx().line_set_color(*args, **kwargs),
            set_width=lambda *args, **kwargs: ctx().line_set_width(*args, **kwargs),
            set_style=lambda *args, **kwargs: ctx().line_set_style(*args, **kwargs),
            set_extend=lambda *args, **kwargs: ctx().line_set_extend(*args, **kwargs),
            delete=lambda *args, **kwargs: ctx().line_delete(*args, **kwargs),
            style_solid="solid",
            style_dashed="dashed",
            style_dotted="dotted",
            extend_none="none",
            extend_left="left",
            extend_right="right",
            extend_both="both",
        )
        label_namespace = _DrawingNamespace(
            all_getter=lambda: ctx().label_all(),
            new=lambda *args, **kwargs: ctx().label_new(*args, **kwargs),
            set_xy=lambda *args, **kwargs: ctx().label_set_xy(*args, **kwargs),
            set_point=lambda *args, **kwargs: ctx().label_set_point(*args, **kwargs),
            set_x=lambda *args, **kwargs: ctx().label_set_x(*args, **kwargs),
            set_y=lambda *args, **kwargs: ctx().label_set_y(*args, **kwargs),
            set_text=lambda *args, **kwargs: ctx().label_set_text(*args, **kwargs),
            set_color=lambda *args, **kwargs: ctx().label_set_color(*args, **kwargs),
            set_textcolor=lambda *args, **kwargs: ctx().label_set_textcolor(*args, **kwargs),
            set_style=lambda *args, **kwargs: ctx().label_set_style(*args, **kwargs),
            set_size=lambda *args, **kwargs: ctx().label_set_size(*args, **kwargs),
            set_xloc=lambda *args, **kwargs: ctx().label_set_xloc(*args, **kwargs),
            set_yloc=lambda *args, **kwargs: ctx().label_set_yloc(*args, **kwargs),
            delete=lambda *args, **kwargs: ctx().label_delete(*args, **kwargs),
            style_label_up="label_up",
            style_label_down="label_down",
            style_label_left="label_left",
            style_label_right="label_right",
            style_label_center="label_center",
        )
        box_namespace = _DrawingNamespace(
            all_getter=lambda: ctx().box_all(),
            new=lambda *args, **kwargs: ctx().box_new(*args, **kwargs),
            set_left=lambda *args, **kwargs: ctx().box_set_left(*args, **kwargs),
            set_top=lambda *args, **kwargs: ctx().box_set_top(*args, **kwargs),
            set_right=lambda *args, **kwargs: ctx().box_set_right(*args, **kwargs),
            set_bottom=lambda *args, **kwargs: ctx().box_set_bottom(*args, **kwargs),
            set_lefttop=lambda *args, **kwargs: ctx().box_set_lefttop(*args, **kwargs),
            set_rightbottom=lambda *args, **kwargs: ctx().box_set_rightbottom(*args, **kwargs),
            set_top_left_point=lambda *args, **kwargs: ctx().box_set_top_left_point(
                *args,
                **kwargs,
            ),
            set_bottom_right_point=lambda *args, **kwargs: ctx().box_set_bottom_right_point(
                *args,
                **kwargs,
            ),
            set_bgcolor=lambda *args, **kwargs: ctx().box_set_bgcolor(*args, **kwargs),
            set_border_color=lambda *args, **kwargs: ctx().box_set_border_color(*args, **kwargs),
            set_border_width=lambda *args, **kwargs: ctx().box_set_border_width(*args, **kwargs),
            delete=lambda *args, **kwargs: ctx().box_delete(*args, **kwargs),
            border_style_solid="solid",
            border_style_dashed="dashed",
            border_style_dotted="dotted",
        )
        table_namespace = SimpleNamespace(
            new=lambda *args, **kwargs: ctx().table_new(*args, **kwargs),
            cell=lambda *args, **kwargs: ctx().table_cell(*args, **kwargs),
            clear=lambda *args, **kwargs: ctx().table_clear(*args, **kwargs),
            merge_cells=lambda *args, **kwargs: ctx().table_merge_cells(*args, **kwargs),
            set_position=lambda *args, **kwargs: ctx().table_set_position(*args, **kwargs),
            set_bgcolor=lambda *args, **kwargs: ctx().table_set_bgcolor(*args, **kwargs),
            set_frame_color=lambda *args, **kwargs: ctx().table_set_frame_color(*args, **kwargs),
            set_border_color=lambda *args, **kwargs: ctx().table_set_border_color(*args, **kwargs),
            delete=lambda *args, **kwargs: ctx().table_delete(*args, **kwargs),
        )
        linefill_namespace = SimpleNamespace(
            new=lambda *args, **kwargs: ctx().linefill_new(*args, **kwargs),
            set_color=lambda *args, **kwargs: ctx().linefill_set_color(*args, **kwargs),
            delete=lambda *args, **kwargs: ctx().linefill_delete(*args, **kwargs),
        )
        polyline_namespace = SimpleNamespace(
            new=lambda *args, **kwargs: ctx().polyline_new(*args, **kwargs),
            delete=lambda *args, **kwargs: ctx().polyline_delete(*args, **kwargs),
        )
        return {
            "chart": ChartNamespace(
                current_time=current_time,
                current_index=lambda: ctx().bar_index,
            ),
            "line": line_namespace,
            "label": label_namespace,
            "box": box_namespace,
            "table": table_namespace,
            "linefill": linefill_namespace,
            "polyline": polyline_namespace,
            "plot": SimpleNamespace(
                style_line="line",
                style_histogram="histogram",
                style_columns="histogram",
            ),
            "position": SimpleNamespace(
                top_left="top_left",
                top_center="top_center",
                top_right="top_right",
                middle_left="middle_left",
                middle_center="middle_center",
                middle_right="middle_right",
                bottom_left="bottom_left",
                bottom_center="bottom_center",
                bottom_right="bottom_right",
            ),
            "shape": SimpleNamespace(
                circle="circle",
                cross="cross",
                triangleup="triangle_up",
                triangledown="triangle_down",
                flag="flag",
                arrowup="arrow_up",
                arrowdown="arrow_down",
                labelup="label_up",
                labeldown="label_down",
                square="square",
                diamond="diamond",
            ),
            "location": SimpleNamespace(
                abovebar="above",
                belowbar="below",
                top="above",
                bottom="below",
                absolute="absolute",
            ),
            "xloc": SimpleNamespace(bar_index="bar_index", bar_time="bar_time"),
            "yloc": SimpleNamespace(price="price", abovebar="abovebar", belowbar="belowbar"),
            "text": SimpleNamespace(
                align_left="left",
                align_center="center",
                align_right="right",
                align_top="top",
                align_middle="middle",
                align_bottom="bottom",
            ),
            "size": SimpleNamespace(
                tiny="tiny",
                small="small",
                normal="normal",
                large="large",
                huge="huge",
            ),
        }

    def _call_optional(self, func: Callable[..., Any] | None, ctx: IncrementalContext) -> None:
        if func is None:
            return
        try:
            with execution_timeout(self.policy.timeout_seconds):
                self._call_by_arity(func, ctx)
        except Exception as exc:
            self._poison(exc)
            raise

    def _call_required(
        self,
        func: Callable[..., Any] | None,
        ctx: IncrementalContext,
        bar: IncrementalBar,
    ) -> None:
        if func is None:
            raise PyneSecurityError("Incremental Pyne scripts must define on_bar(ctx, bar)")
        self._call_by_arity(func, ctx, bar)

    def _call_by_arity(
        self,
        func: Callable[..., Any],
        ctx: IncrementalContext,
        bar: IncrementalBar | None = None,
    ) -> None:
        signature = inspect.signature(func)
        params = list(signature.parameters.values())
        has_varargs = any(item.kind == inspect.Parameter.VAR_POSITIONAL for item in params)
        if bar is None:
            if len(params) == 0 and not has_varargs:
                func()
            else:
                func(ctx)
            return
        if has_varargs or len(params) >= 2:
            func(ctx, bar)
        elif len(params) == 1:
            func(bar)
        else:
            func()

    def snapshot_result(
        self,
        *,
        start_s: int | None = None,
        end_s: int | None = None,
    ) -> IncrementalPyneResult:
        self._ensure_healthy()
        self.prepare()
        if self._ctx is None:
            self._ctx = IncrementalContext(
                params=self.params,
                meta=self._meta,
                limits=self._limits,
                syminfo=self.settings.syminfo,
                timeframe=self.settings.timeframe,
                session=self.settings.session,
                max_drawing_objects=self.settings.max_drawing_objects,
            )
            self._call_optional(self._init_func, self._ctx)
        return self._to_result(self._ctx, start_s=start_s, end_s=end_s)

    def _to_result(
        self,
        ctx: IncrementalContext,
        *,
        start_s: int | None = None,
        end_s: int | None = None,
    ) -> IncrementalPyneResult:
        result = ctx.to_result(start_s=start_s, end_s=end_s)
        result.meta = {
            **result.meta,
            "retentionBars": self.retention_bars,
            "retainedBars": len(self._retained_closed_times),
            "totalCommittedBars": self._closed_count,
            "snapshotVersion": PYNE_INCREMENTAL_SNAPSHOT_VERSION,
        }
        return result

    def snapshot_state(self) -> PyneIncrementalSessionSnapshot:
        """Capture committed process-local state for restart in this process.

        The snapshot deliberately excludes active preview state. Scripts with
        closures or script-defined classes fail closed because their object
        graphs cannot be safely rebound to a fresh execution namespace.
        """

        self._ensure_healthy()
        self.prepare()
        memo: dict[int, Any] = {}
        global_values, function_states = self._snapshot_user_globals(memo)
        return PyneIncrementalSessionSnapshot(
            schema_version=PYNE_INCREMENTAL_SNAPSHOT_VERSION,
            semantics_version=INCREMENTAL_SEMANTICS_VERSION,
            script_sha256=_script_sha256(self.script),
            params=copy.deepcopy(dict(self.params.items()), memo),
            security_mode=self.security_mode,
            retention_bars=self.retention_bars,
            context=copy.deepcopy(self._ctx, memo),
            meta=copy.deepcopy(self._meta, memo),
            global_values=global_values,
            function_states=function_states,
            cache=self.execution_scope.cache.snapshot_state(memo=memo),
            last_closed_time=self.last_closed_time,
            closed_count=self._closed_count,
            retained_closed_times=tuple(self._retained_closed_times),
            portable_bars=tuple(copy.deepcopy(self._portable_bars, memo)),
            portable_seed_count=self._portable_seed_count,
            portable_complete=self._portable_complete,
            namespace_names=tuple(self._globals),
            trace=copy.deepcopy(self.trace, memo),
        )

    def snapshot_portable(
        self,
        *,
        max_bytes: int = DEFAULT_PORTABLE_SNAPSHOT_MAX_BYTES,
        mode: str = "replay",
    ) -> bytes:
        """Return a deterministic cross-process replay or typed-state checkpoint.

        ``mode="replay"`` preserves the version-1 event checkpoint. ``mode="state"``
        emits the version-2 native typed-state format without replay history.
        Both formats exclude active preview state and Provider internals.
        """
        self._ensure_healthy()
        self.prepare()
        normalized_mode = str(mode).strip().lower()
        if normalized_mode not in {"replay", "state"}:
            raise ValueError("portable snapshot mode must be 'replay' or 'state'")
        if normalized_mode == "state":
            snapshot = replace(
                self.snapshot_state(),
                portable_bars=(),
                portable_seed_count=0,
                portable_complete=False,
            )
            return encode_portable_state_checkpoint(
                PortableStateCheckpoint(
                    script_sha256=_script_sha256(self.script),
                    settings=portable_settings_contract(self.settings),
                    provider_required=self.settings.data_provider is not None,
                    snapshot=snapshot,
                ),
                max_bytes=max_bytes,
            )
        if not self._portable_complete:
            raise PynePortableSnapshotError(
                "Portable snapshot history exceeded max_bars; use the process-local snapshot "
                "or start a new portable checkpoint boundary"
            )
        provider_required = self.settings.data_provider is not None
        return encode_portable_checkpoint(
            PortableCheckpoint(
                script_sha256=_script_sha256(self.script),
                params=copy.deepcopy(dict(self.params.items())),
                settings=portable_settings_contract(self.settings),
                retention_bars=self.retention_bars,
                bars=tuple(copy.deepcopy(self._portable_bars)),
                seed_count=self._portable_seed_count,
                provider_required=provider_required,
            ),
            max_bytes=max_bytes,
        )

    def snapshot_portable_state(
        self,
        *,
        max_bytes: int = DEFAULT_PORTABLE_SNAPSHOT_MAX_BYTES,
    ) -> bytes:
        """Return the version-2 allowlisted typed-state checkpoint."""
        return self.snapshot_portable(max_bytes=max_bytes, mode="state")

    def restore_state(self, snapshot: PyneIncrementalSessionSnapshot) -> None:
        """Replace this session's committed state from a matching snapshot."""

        self._ensure_healthy()
        if not isinstance(snapshot, PyneIncrementalSessionSnapshot):
            raise TypeError("snapshot must be a PyneIncrementalSessionSnapshot")
        validate_snapshot_semantics(getattr(snapshot, "semantics_version", None))
        if snapshot.schema_version != PYNE_INCREMENTAL_SNAPSHOT_VERSION:
            raise ValueError(f"Unsupported incremental snapshot version {snapshot.schema_version}")
        if snapshot.script_sha256 != _script_sha256(self.script):
            raise ValueError("Incremental snapshot script does not match this session")
        if snapshot.security_mode != self.security_mode:
            raise ValueError("Incremental snapshot security mode does not match this session")
        if snapshot.retention_bars != self.retention_bars:
            raise ValueError("Incremental snapshot retention policy does not match this session")
        if dict(self.params.items()) != snapshot.params:
            raise ValueError("Incremental snapshot params do not match this session")

        self.prepare()
        memo: dict[int, Any] = {}
        new_ctx = copy.deepcopy(snapshot.context, memo)
        snapshot_trace = getattr(snapshot, "trace", None)
        new_trace = (
            copy.deepcopy(snapshot_trace, memo)
            if snapshot_trace is not None
            else new_ctx.trace
            if new_ctx is not None
            else self.trace
        )
        new_meta = copy.deepcopy(snapshot.meta, memo)
        new_global_values = {
            name: copy.deepcopy(value, memo)
            for name, value in snapshot.global_values.items()
        }
        prepared_functions: dict[
            str,
            tuple[FunctionType, Any, Any, dict[str, Any]],
        ] = {}
        for name, state in snapshot.function_states.items():
            function = self._prepared_namespace_values.get(name, self._globals.get(name))
            if not isinstance(function, FunctionType):
                raise ValueError(f"Incremental snapshot function is missing: {name}")
            prepared_functions[name] = (
                function,
                copy.deepcopy(state.defaults, memo),
                copy.deepcopy(state.kwdefaults, memo),
                copy.deepcopy(state.attributes, memo),
            )
        new_portable_bars = list(copy.deepcopy(snapshot.portable_bars, memo))
        incoming_cache = PyneCache(max_items=max(int(snapshot.cache.max_items), 1))
        incoming_cache.restore_state(snapshot.cache, memo=memo)
        restored_names = set(new_global_values) | set(prepared_functions)
        stored_namespace_names = tuple(getattr(snapshot, "namespace_names", ()))
        namespace_names = (
            set(stored_namespace_names)
            if stored_namespace_names
            else set(self._base_namespace_names) | restored_names
        )
        if not all(isinstance(name, str) for name in namespace_names):
            raise ValueError("Incremental snapshot namespace names must be strings")
        replacement_globals: dict[str, Any] = {}
        for name in namespace_names:
            if name in new_global_values:
                replacement_globals[name] = new_global_values[name]
                continue
            if name in prepared_functions:
                replacement_globals[name] = prepared_functions[name][0]
                continue
            if name in self._prepared_namespace_values:
                replacement_globals[name] = self._prepared_namespace_values[name]
                continue
            if name in self._base_namespace_values:
                replacement_globals[name] = self._base_namespace_values[name]
                continue
            current = self._globals.get(name)
            if isinstance(current, ModuleType):
                replacement_globals[name] = current
                continue
            raise ValueError(f"Incremental snapshot global is missing: {name}")

        self._ctx = new_ctx
        self.trace = new_trace
        self._meta = new_meta
        self._globals.clear()
        self._globals.update(replacement_globals)
        for name, (function, defaults, kwdefaults, attributes) in prepared_functions.items():
            function.__defaults__ = defaults
            function.__kwdefaults__ = kwdefaults
            function.__dict__.clear()
            function.__dict__.update(attributes)
        self.execution_scope.cache.adopt_state(incoming_cache)
        self._init_func = self._callback("init")
        self._on_bar = self._callback("on_bar")
        self._on_preview = self._callback("on_preview")
        self.last_closed_time = snapshot.last_closed_time
        self._closed_count = snapshot.closed_count
        self._retained_closed_times = list(snapshot.retained_closed_times)
        self._portable_bars = new_portable_bars
        self._portable_seed_count = snapshot.portable_seed_count
        self._portable_complete = snapshot.portable_complete
        self._active_ctx = None
        self._active_preview_time = None
        self._preview_varip_states = {}

    @classmethod
    def from_snapshot(
        cls,
        snapshot: PyneIncrementalSessionSnapshot,
        *,
        script: str,
        settings: PyneSettings | None = None,
        execution_scope: PyneExecutionScope | None = None,
    ) -> "PyneIncrementalSession":
        """Create a fresh session and restore a matching process-local snapshot."""
        validate_snapshot_semantics(getattr(snapshot, "semantics_version", None))

        session = cls(
            script=script,
            params=copy.deepcopy(snapshot.params),
            security_mode=snapshot.security_mode,
            settings=settings,
            execution_scope=execution_scope,
            retention_bars=snapshot.retention_bars,
        )
        session.restore_state(snapshot)
        return session

    @classmethod
    def from_portable_snapshot(
        cls,
        payload: bytes | bytearray | memoryview | str,
        *,
        script: str,
        settings: PyneSettings | None = None,
        data_provider: DataProvider | None = None,
        execution_scope: PyneExecutionScope | None = None,
        max_bytes: int = DEFAULT_PORTABLE_SNAPSHOT_MAX_BYTES,
    ) -> "PyneIncrementalSession":
        """Restore either a replay-v1 or typed-state-v2 portable checkpoint."""
        format_name = portable_snapshot_format(payload, max_bytes=max_bytes)
        if format_name == "pyne.incremental-state/2":
            state_checkpoint = decode_portable_state_checkpoint(payload, max_bytes=max_bytes)
            if state_checkpoint.script_sha256 != _script_sha256(script):
                raise PynePortableSnapshotError(
                    "Portable incremental snapshot script does not match this session"
                )
            resolved_settings = _portable_restore_settings(
                state_checkpoint.settings,
                provider_required=state_checkpoint.provider_required,
                settings=settings,
                data_provider=data_provider,
            )
            snapshot = state_checkpoint.snapshot
            if not isinstance(snapshot, PyneIncrementalSessionSnapshot):
                raise PynePortableSnapshotError(
                    "Portable typed state root is not an incremental session snapshot"
                )
            validate_snapshot_semantics(getattr(snapshot, "semantics_version", None))
            restored = cls(
                script=script,
                params=copy.deepcopy(snapshot.params),
                security_mode=resolved_settings.security_mode,
                settings=resolved_settings,
                execution_scope=execution_scope,
                retention_bars=snapshot.retention_bars,
            )
            restored.restore_state(snapshot)
            return restored
        checkpoint = decode_portable_checkpoint(payload, max_bytes=max_bytes)
        if checkpoint.script_sha256 != _script_sha256(script):
            raise PynePortableSnapshotError(
                "Portable incremental snapshot script does not match this session"
            )
        resolved_settings = _portable_restore_settings(
            checkpoint.settings,
            provider_required=checkpoint.provider_required,
            settings=settings,
            data_provider=data_provider,
        )
        restored = cls(
            script=script,
            params=copy.deepcopy(checkpoint.params),
            security_mode=resolved_settings.security_mode,
            settings=resolved_settings,
            execution_scope=execution_scope,
            retention_bars=checkpoint.retention_bars,
        )
        bars = [copy.deepcopy(item) for item in checkpoint.bars]
        if checkpoint.seed_count:
            restored.seed(bars[: checkpoint.seed_count])
        else:
            restored.prepare()
        for item in bars[checkpoint.seed_count :]:
            restored.on_bar_closed(item)
        if restored._closed_count != len(bars):
            raise PynePortableSnapshotError(
                "Portable incremental snapshot replay did not restore the expected bar count"
            )
        return restored

    def _snapshot_user_globals(
        self,
        memo: dict[int, Any],
    ) -> tuple[dict[str, Any], dict[str, _FunctionStateSnapshot]]:
        values: dict[str, Any] = {}
        functions: dict[str, _FunctionStateSnapshot] = {}
        for name, value in self._globals.items():
            if name in self._base_namespace_names and value is self._base_namespace_values[name]:
                continue
            if (
                name in self._prepared_namespace_values
                and value is self._prepared_namespace_values[name]
                and (
                    _is_deeply_immutable(value)
                    or isinstance(
                        value,
                        (BuiltinFunctionType, BuiltinMethodType, MethodType, ModuleType),
                    )
                )
            ):
                continue
            if isinstance(value, FunctionType):
                if value.__closure__:
                    raise PyneSecurityError(
                        f"Incremental snapshot cannot safely restore closure: {name}"
                    )
                functions[name] = _FunctionStateSnapshot(
                    defaults=copy.deepcopy(value.__defaults__, memo),
                    kwdefaults=copy.deepcopy(value.__kwdefaults__, memo),
                    attributes=copy.deepcopy(value.__dict__, memo),
                )
                continue
            if isinstance(value, type):
                raise PyneSecurityError(
                    f"Incremental snapshot cannot safely restore script class: {name}"
                )
            if isinstance(value, ModuleType):
                continue
            values[name] = copy.deepcopy(value, memo)
        return values, functions

    def _restore_function_states(
        self,
        states: dict[str, _FunctionStateSnapshot],
        memo: dict[int, Any],
    ) -> None:
        for name, state in states.items():
            function = self._globals.get(name)
            if not isinstance(function, FunctionType):
                raise ValueError(f"Incremental snapshot function is missing: {name}")
            function.__defaults__ = copy.deepcopy(state.defaults, memo)
            function.__kwdefaults__ = copy.deepcopy(state.kwdefaults, memo)
            function.__dict__.clear()
            function.__dict__.update(copy.deepcopy(state.attributes, memo))

    def _callback(self, name: str) -> Callable[..., Any] | None:
        value = self._globals.get(name)
        return value if callable(value) else None


def _script_sha256(script: str) -> str:
    return hashlib.sha256(script.encode("utf-8")).hexdigest()


def _portable_restore_settings(
    contract: Mapping[str, Any],
    *,
    provider_required: bool,
    settings: PyneSettings | None,
    data_provider: DataProvider | None,
) -> PyneSettings:
    if settings is None:
        resolved = settings_from_portable_contract(contract)
        if data_provider is not None:
            resolved = replace(resolved, data_provider=data_provider)
        elif provider_required:
            raise PynePortableSnapshotError(
                "Portable snapshot restore requires matching settings or a data_provider"
            )
        return resolved
    resolved = replace(settings, data_provider=data_provider) if data_provider is not None else settings
    if portable_settings_contract(resolved) != contract:
        raise PynePortableSnapshotError(
            "Portable incremental snapshot settings do not match this session"
        )
    if provider_required and resolved.data_provider is None:
        raise PynePortableSnapshotError("Portable snapshot restore requires a data_provider")
    return resolved


class _ReadOnlyMapping(Mapping[Any, Any]):
    __slots__ = ("__values",)

    def __init__(self, values: Mapping[Any, Any]) -> None:
        object.__setattr__(self, "_ReadOnlyMapping__values", dict(values))

    def __getattribute__(self, name: str) -> Any:
        if name in {"_values", "__values", "_ReadOnlyMapping__values", "__dict__"}:
            raise AttributeError("incremental params storage is private")
        return object.__getattribute__(self, name)

    def __getitem__(self, key: Any) -> Any:
        values = object.__getattribute__(self, "_ReadOnlyMapping__values")
        return _param_value_for_read(values[key])

    def __iter__(self) -> Iterator[Any]:
        values = object.__getattribute__(self, "_ReadOnlyMapping__values")
        return iter(values)

    def __len__(self) -> int:
        values = object.__getattribute__(self, "_ReadOnlyMapping__values")
        return len(values)

    def __deepcopy__(self, memo: dict[int, Any]) -> "_ReadOnlyMapping":
        return self

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mapping):
            return False
        return dict(self.items()) == dict(other.items())

    def __repr__(self) -> str:
        values = object.__getattribute__(self, "_ReadOnlyMapping__values")
        return repr(values)


def _readonly_params(params: Mapping[Any, Any]) -> _ReadOnlyMapping:
    return _ReadOnlyMapping({key: _freeze_param_value(value) for key, value in params.items()})


def _freeze_param_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _readonly_params(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_param_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_param_value(item) for item in value)
    if _is_deeply_immutable(value):
        return value
    _validate_param_class_state(value)
    return _isolated_param_copy(value, label="caller params")


def _param_value_for_read(value: Any) -> Any:
    if isinstance(value, _ReadOnlyMapping) or _is_deeply_immutable(value):
        return value
    if isinstance(value, tuple):
        return tuple(_param_value_for_read(item) for item in value)
    if isinstance(value, frozenset):
        return frozenset(_param_value_for_read(item) for item in value)
    return _isolated_param_copy(value, label="incremental params")


def _isolated_param_copy(value: Any, *, label: str) -> Any:
    try:
        cloned = copy.deepcopy(value)
    except Exception as exc:
        raise PyneSecurityError(
            f"{label} contains a value that cannot be copied safely: {type(value).__qualname__}"
        ) from exc
    shared = _mutable_object_ids(value) & _mutable_object_ids(cloned)
    if shared:
        raise PyneSecurityError(
            f"{label} contains shared mutable state that cannot be exposed safely: "
            f"{type(value).__qualname__}"
        )
    return cloned


def _validate_param_class_state(value: Any) -> None:
    cls = type(value)
    if cls.__module__ == "builtins":
        return
    for name, item in vars(cls).items():
        if name.startswith("__"):
            continue
        if isinstance(
            item,
            (
                FunctionType,
                BuiltinFunctionType,
                staticmethod,
                classmethod,
                property,
                MemberDescriptorType,
                GetSetDescriptorType,
            ),
        ):
            continue
        if not _is_deeply_immutable(item):
            raise PyneSecurityError(
                "caller params contains mutable class-level state that cannot be "
                f"exposed safely: {cls.__qualname__}.{name}"
            )


def _mutable_object_ids(value: Any) -> set[int]:
    mutable: set[int] = set()
    seen: set[int] = set()
    pending = [value]
    while pending:
        current = pending.pop()
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        if isinstance(current, _ReadOnlyMapping) or _is_deeply_immutable(current):
            continue
        if isinstance(
            current,
            (
                FunctionType,
                BuiltinFunctionType,
                BuiltinMethodType,
                MethodType,
                ModuleType,
                type,
            ),
        ):
            mutable.add(identity)
            continue
        if isinstance(current, tuple | frozenset):
            pending.extend(current)
            continue
        mutable.add(identity)
        if isinstance(current, Mapping):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, (list, set)):
            pending.extend(current)
        elif hasattr(current, "__dict__"):
            pending.extend(vars(current).values())
    return mutable


def _is_deeply_immutable(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float, complex, str, bytes, range)):
        return True
    if isinstance(value, tuple | frozenset):
        return all(_is_deeply_immutable(item) for item in value)
    return False


def _clone_preview_cache(source_cache: PyneCache) -> PyneCache:
    """Clone committed cache state for one isolated preview callback."""
    cloned = PyneCache(max_items=max(int(source_cache.stats()["maxItems"]), 1))
    cloned.restore_state(source_cache.snapshot_state())
    return cloned


def _clone_preview_globals(
    values: Mapping[str, Any],
    *,
    script_globals: dict[str, Any],
    base_values: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[int, Any]]:
    class_names = _script_class_names(values, script_globals=script_globals)
    if class_names:
        names = ", ".join(class_names)
        raise PyneSecurityError(
            f"Incremental preview cannot safely isolate script classes: {names}. "
            "Keep preview state in module values or ctx.varip()."
        )

    script_functions = _collect_functions(values, script_globals=script_globals)
    closure_names = sorted({func.__qualname__ for func in script_functions if func.__closure__})
    if closure_names:
        names = ", ".join(closure_names)
        raise PyneSecurityError(
            f"Incremental preview cannot safely isolate function closures: {names}. "
            "Keep preview state in module values or ctx.varip()."
        )

    base_functions = _collect_functions(base_values, script_globals=None)
    cloned_functions = script_functions | base_functions
    memo = _preview_copy_memo(values)
    clones: list[tuple[FunctionType, FunctionType]] = []
    for original in cloned_functions:
        function_globals = (
            script_globals if original.__globals__ is script_globals else original.__globals__
        )
        cloned = FunctionType(
            original.__code__,
            function_globals,
            name=original.__name__,
            argdefs=None,
            closure=original.__closure__,
        )
        memo[id(original)] = cloned
        clones.append((original, cloned))

    preview_globals = copy.deepcopy(dict(values), memo)
    for original, cloned in clones:
        try:
            cloned.__defaults__ = copy.deepcopy(original.__defaults__, memo)
            cloned.__kwdefaults__ = copy.deepcopy(original.__kwdefaults__, memo)
            cloned.__annotations__ = copy.deepcopy(original.__annotations__, memo)
            cloned.__dict__.update(copy.deepcopy(original.__dict__, memo))
        except Exception as exc:
            raise PyneSecurityError(
                "Incremental preview cannot isolate mutable function state: "
                f"{original.__qualname__}. Keep state in module values or ctx.varip()."
            ) from exc
        cloned.__doc__ = original.__doc__
        cloned.__module__ = original.__module__
        cloned.__qualname__ = original.__qualname__
    return preview_globals, memo


def _preview_payload_items(values: Any) -> int:
    """Estimate deepcopy work before allocating a preview-global clone."""
    total = 0
    for value in values:
        if _is_deeply_immutable(value):
            continue
        total += _state_payload_items(value)
        if isinstance(value, FunctionType):
            total += _state_payload_items(value.__defaults__)
            total += _state_payload_items(value.__kwdefaults__)
            total += _state_payload_items(value.__dict__)
        elif hasattr(value, "__dict__"):
            total += _state_payload_items(vars(value))
    return total


def _preview_copy_memo(value: Any) -> dict[int, Any]:
    memo: dict[int, Any] = {}
    module_proxies: dict[int, _PreviewModuleProxy] = {}
    seen: set[int] = set()
    pending = [value]
    while pending:
        current = pending.pop()
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        if isinstance(current, ModuleType):
            proxy = module_proxies.setdefault(identity, _PreviewModuleProxy(current))
            memo[identity] = proxy
        elif isinstance(
            current,
            (BuiltinFunctionType, BuiltinMethodType, FunctionType, MethodType, type),
        ):
            memo[identity] = current
        elif isinstance(current, Mapping):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, (list, tuple, set, frozenset)):
            pending.extend(current)
        elif hasattr(current, "__dict__"):
            pending.extend(vars(current).values())
    return memo


def _collect_functions(
    value: Any,
    *,
    script_globals: dict[str, Any] | None,
) -> set[FunctionType]:
    functions: set[FunctionType] = set()
    seen: set[int] = set()
    pending = [value]
    while pending:
        current = pending.pop()
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        if isinstance(current, FunctionType):
            if script_globals is None or current.__globals__ is script_globals:
                functions.add(current)
                pending.extend(current.__defaults__ or ())
                pending.extend((current.__kwdefaults__ or {}).values())
                pending.extend(current.__dict__.values())
            continue
        if isinstance(current, (ModuleType, type, BuiltinFunctionType, BuiltinMethodType)):
            continue
        if isinstance(current, Mapping):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, (list, tuple, set, frozenset)):
            pending.extend(current)
        elif isinstance(current, SimpleNamespace):
            pending.extend(vars(current).values())
    return functions


def _script_class_names(
    value: Any,
    *,
    script_globals: dict[str, Any],
) -> list[str]:
    names: set[str] = set()
    seen: set[int] = set()
    pending = [value]
    while pending:
        current = pending.pop()
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        candidate = current if isinstance(current, type) else type(current)
        is_unregistered_builtin_class = (
            isinstance(current, type)
            and candidate.__module__ == "builtins"
            and getattr(python_builtins, candidate.__name__, None) is not candidate
        )
        if is_unregistered_builtin_class or _is_script_class(
            candidate,
            script_globals=script_globals,
        ):
            names.add(candidate.__qualname__)
            continue
        if isinstance(current, FunctionType):
            pending.extend(current.__defaults__ or ())
            pending.extend((current.__kwdefaults__ or {}).values())
            pending.extend(current.__dict__.values())
        elif isinstance(current, Mapping):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, (list, tuple, set, frozenset)):
            pending.extend(current)
    return sorted(names)


def _is_script_class(cls: type[Any], *, script_globals: dict[str, Any]) -> bool:
    for item in vars(cls).values():
        functions: tuple[Any, ...]
        if isinstance(item, (staticmethod, classmethod)):
            functions = (item.__func__,)
        elif isinstance(item, property):
            functions = (item.fget, item.fset, item.fdel)
        else:
            functions = (item,)
        if any(
            isinstance(func, FunctionType) and func.__globals__ is script_globals
            for func in functions
        ):
            return True
    return False


_RISKY_MODULE_CALLS = {
    "clear",
    "disable",
    "enable",
    "reset",
    "seed",
    "set_state",
    "setbufsize",
    "seterr",
    "seterrcall",
    "set_numeric_ops",
    "set_printoptions",
    "set_string_function",
}


class _PreviewModuleProxy:
    __slots__ = ("_cache", "_module")

    def __init__(self, module: ModuleType) -> None:
        object.__setattr__(self, "_module", module)
        object.__setattr__(self, "_cache", {})

    def __getattribute__(self, name: str) -> Any:
        if name in {"_module", "_cache", "__dict__"}:
            raise PyneSecurityError(
                "Incremental preview cannot expose mutable external module state"
            )
        if name in {"__class__", "__repr__", "__getattr__", "__setattr__", "__delattr__"}:
            return object.__getattribute__(self, name)
        return object.__getattribute__(self, name)

    def __getattr__(self, name: str) -> Any:
        module = object.__getattribute__(self, "_module")
        cache = object.__getattribute__(self, "_cache")
        if name in cache:
            return cache[name]
        value = getattr(module, name)
        if isinstance(value, ModuleType):
            cloned: Any = _PreviewModuleProxy(value)
        elif callable(value):
            if name.lower() in _RISKY_MODULE_CALLS:
                raise PyneSecurityError(
                    "Incremental preview cannot call stateful external module API: "
                    f"{module.__name__}.{name}"
                )
            cloned = value
        elif _is_deeply_immutable(value):
            cloned = value
        else:
            try:
                cloned = copy.deepcopy(value, _preview_copy_memo(value))
            except Exception as exc:
                raise PyneSecurityError(
                    "Incremental preview cannot isolate external module attribute: "
                    f"{module.__name__}.{name}"
                ) from exc
        cache[name] = cloned
        return cloned

    def __setattr__(self, name: str, value: Any) -> None:
        module = object.__getattribute__(self, "_module")
        raise PyneSecurityError(
            f"Incremental preview cannot mutate external module state: {module.__name__}.{name}"
        )

    def __delattr__(self, name: str) -> None:
        self.__setattr__(name, None)

    def __repr__(self) -> str:
        module = object.__getattribute__(self, "_module")
        return f"<preview module proxy {module.__name__}>"


def _unisolatable_preview_globals(values: Mapping[str, Any]) -> list[str]:
    failed: list[str] = []
    for name, value in values.items():
        try:
            copy.deepcopy(value, _preview_copy_memo(value))
        except Exception:
            failed.append(name)
    return failed
