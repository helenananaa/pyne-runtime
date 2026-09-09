# PyneSettings

`PyneSettings` controls security, execution, and resource limits.

```python
settings = pn.PyneSettings(
    security_mode="safe",
    executor_mode="process",
    timeout_seconds=5,
    max_bars=50_000,
    max_drawing_objects=500,
    max_array_size=100_000,
    max_map_size=100_000,
    max_matrix_cells=100_000,
    max_collection_depth=8,
    max_strategy_pending_operations=1_000_000,
    incremental_retention_bars=10_000,
    trace_enabled=False,
    trace_max_events=1_000,
    trace_span_events=False,
    data_provider=None,
    syminfo={"tickerid": "NASDAQ:AAPL", "mintick": 0.01},
    timeframe="1h",
    session={"ismarket": True},
)
```

Environment-backed settings:

```python
settings = pn.PyneSettings.from_env()
```

Supported security modes:

- `safe`
- `research`
- `unsafe`

Supported executor modes:

- `inline`
- `process`

Unknown `executor_mode` values are rejected at settings construction. Process
mode always uses multiprocessing `spawn` and can hard-kill the worker when
`timeout_seconds` elapses. Inline mode treats `timeout_seconds` as a best-effort
Unix-main-thread timer and does not advertise a hard kill. Set
`require_hard_timeout=True` only with `executor_mode='process'`; combining it
with `inline` raises a configuration error.

`data_provider` supplies host-backed OHLCV data for `request.security()`. The
process executor requires a pickleable provider; use `inline` for local adapters
that hold live connections or non-pickleable state.

Malformed timeframe strings such as `"1h30"` or `"15min"` are rejected. Mapping
inputs that supply both `period` and `multiplier` are rejected when those values
conflict.

Runtime metadata:

- `syminfo` supplies the Pine-like `syminfo` namespace. Supported fields include
  `ticker`, `tickerid`, `prefix`, `currency`, `basecurrency`, `mintick`,
  `pointvalue`, and `type`.
- `timeframe` supplies the Pine-like `timeframe` namespace. Common strings such
  as `"1"`, `"5"`, `"1h"`, `"1D"`, `"1W"`, and `"1M"` are parsed into
  `period`, `multiplier`, `isintraday`, `isdaily`, `isweekly`, and `ismonthly`.
  Parse, explicit multiplier, `in_seconds()`, and last-bar `time_close` share
  that one canonical duration.
- `session` supplies default host-owned session flags: `ismarket`,
  `isfirstbar`, and `islastbar`.

Batch scripts see `session.ismarket`, `session.isfirstbar`, and
`session.islastbar` as bar-level series. Hosts can provide per-bar flags in
OHLCV rows:

```python
data = [
    {
        "time": 1710000000,
        "open": 1,
        "high": 2,
        "low": 1,
        "close": 1.5,
        "volume": 100,
        "session_ismarket": True,
        "session_isfirstbar": True,
    },
    {
        "time": 1710000060,
        "open": 1.5,
        "high": 2,
        "low": 1,
        "close": 1.2,
        "volume": 120,
        "session": {"ismarket": False},
    },
]
```

When per-bar flags are omitted, `session.ismarket` uses the default setting,
`session.isfirstbar` defaults to the first loaded bar, and
`session.islastbar` defaults to the last loaded bar. Explicit per-bar false
values are preserved; the first/last fallbacks only apply when no matching
per-bar flag is supplied. Incremental scripts read the current bar's scalar
flags through `ctx.session.*`.

`syminfo.mintick` defaults to `1.0`. Strategy slippage uses it when
`strategy(..., slippage=...)` does not pass an explicit `mintick` / `min_tick`.

The same metadata can be supplied directly to `pn.run(...)`:

```python
result = pn.run(
    script,
    data,
    syminfo={"tickerid": "NASDAQ:AAPL", "mintick": 0.01},
    timeframe="1h",
    session={"ismarket": True},
)
```

Environment variables are also supported for simple host launches:

- `PYNE_TICKERID`
- `PYNE_TICKER`
- `PYNE_SYMBOL_PREFIX`
- `PYNE_CURRENCY`
- `PYNE_BASE_CURRENCY`
- `PYNE_MINTICK`
- `PYNE_POINTVALUE`
- `PYNE_SYMBOL_TYPE`
- `PYNE_TIMEFRAME`

Object limits:

- `max_drawing_objects`: maximum active `line`, `label`, `box`, and `table`
  handles in one execution.
- Environment variable: `PYNE_MAX_DRAWING_OBJECTS`.

Incremental retention:

- `incremental_retention_bars`: default rolling history retained by new
  `PyneIncrementalSession` objects. It does not cap the lifetime number of live
  confirmed events; the initial seed remains bounded by `max_bars`.
- Environment variable: `PYNE_INCREMENTAL_RETENTION_BARS`.

Collection limits:

- `max_array_size`: maximum elements in an `array.*` value created by a script.
- `max_map_size`: maximum entries in a `map.*` value created by a script.
- `max_matrix_cells`: maximum cells in a `matrix.*` value created by a script.
- `max_collection_depth`: maximum nested collection depth for values stored in
  `array.*`, `map.*`, and `matrix.*` containers.
- Environment variables: `PYNE_MAX_ARRAY_SIZE`, `PYNE_MAX_MAP_SIZE`,
  `PYNE_MAX_MATRIX_CELLS`, `PYNE_MAX_COLLECTION_DEPTH`.

Strategy work limits:

- `max_strategy_pending_operations`: maximum cumulative candidate, cancellation,
  and OCA work consumed by pending orders across all replays in one execution.
  Exceeding the budget fails closed with `PYNE_SECURITY_ERROR`.
- Environment variable: `PYNE_MAX_STRATEGY_PENDING_OPERATIONS`.

Execution trace:

- `trace_enabled`: attach a bounded structured trace under
  `result.meta["trace"]`. The default is `False`.
- `trace_max_events`: maximum retained trace events. Additional events increase
  `droppedEvents` without failing execution.
- `trace_timings_enabled`: collect monotonic hierarchical span durations. The
  default is `True` when tracing is enabled.
- `trace_span_events`: also retain `span.start` and `span.complete` in the
  bounded event list. The default is `False`; aggregate timings and slow-span
  evidence remain available without the two per-span events.
- `trace_slow_span_ms`: threshold for the bounded slow-span list.
- `trace_redacted_fields`: exact case-insensitive secret-like field-name set.
- Environment variables: `PYNE_TRACE_ENABLED`, `PYNE_TRACE_MAX_EVENTS`,
  `PYNE_TRACE_TIMINGS_ENABLED`, `PYNE_TRACE_SPAN_EVENTS`, `PYNE_TRACE_SLOW_SPAN_MS`, and
  `PYNE_TRACE_REDACTED_FIELDS`.
- See [Execution Trace](../concepts/execution_trace.md) for event and preview
  semantics.

