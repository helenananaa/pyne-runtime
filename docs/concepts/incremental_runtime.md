# Incremental Runtime

Batch scripts are the default. For a single script shared by historical data and
realtime sessions, define `on_bar(ctx, bar)`: `pn.run()` evaluates it over supplied
history and `PyneIncrementalSession` continues the same logic on live bars.
See [CSV to realtime](../tutorials/csv_to_realtime.md) for the complete workflow.

```python
indicator("Incremental MA", mode="incremental", overlay=True)

def on_bar(ctx, bar):
    value = ctx.ta.sma("ma", period=20).update(bar.close)
    ctx.plot("MA", value, color=color.orange)
```

Incremental mode is useful for realtime hosts because updates can avoid recomputing the full history.

Named helpers initialize on first use; `init()` remains optional for explicit
registration. Keep names and parameters stable and update each helper once per
bar, even when its result is used conditionally. This does not automatically
translate vectorized batch scripts or extend the incremental capability surface.

Callback context exposes Pine-like scalar clock values for the current event:

- `ctx.bar_index` and `bar.bar_index`
- `ctx.last_bar_index` and `bar.last_bar_index`
- `ctx.barstate.isrealtime`
- `ctx.barstate.isnew`
- `ctx.barstate.isconfirmed`
- `ctx.barstate.ishistory`

`on_bar_updated()` runs as an unconfirmed realtime preview on a cloned context,
so preview state does not mutate the persistent session. `on_bar_closed()`
confirms the realtime bar and advances persistent state.

## Host Integration Flow

A realtime host usually keeps one `PyneIncrementalSession` per chart/script
instance:

```python
import pyne_runtime as pn

session = pn.PyneIncrementalSession(
    script=script,
    params=params,
    settings=pn.PyneSettings(executor_mode="inline"),
    retention_bars=10_000,
)
```

Seed historical bars once before streaming live events:

```python
seeded = session.seed(history_bars)
render_snapshot(seeded)
```

Each bar dict should include `time`, `open`, `high`, `low`, `close`, and
`volume`. Optional fields such as `time_close` and session flags are preserved
when present. The seed result is committed history: its plotted lines, markers,
drawing object snapshot, object events, and strategy report can be rendered as
the durable chart state.

Committed incremental output follows Render IR v2 for `ctx.plot()`,
`ctx.plotcandle()`, markers, line/label/box/table objects, line fills,
polylines, and merged table cells. Line color, width, style,
histogram/columns output, marker shape/location/size, and default pane
assignment match the covered batch surface. Explicit `pane=` values still
override the indicator default.

Send unconfirmed realtime ticks or partial OHLCV updates through
`on_bar_updated()`:

```python
preview = session.on_bar_updated(live_bar)
render_preview(preview)
```

The preview result is temporary. It may include preview-only plot points,
object snapshots, `output["object_events"]`, or strategy orders/fills, but it
does not mutate the persistent session. Repeated previews for the same bar time
reuse `ctx.varip()` cells, while `ctx.state()` changes remain isolated inside
the cloned preview context.

Preview isolation also covers script module globals, mutable function defaults,
and mutable attributes added to built-in script namespaces such as `math`.
Functions that capture closure cells and scripts that define classes are
rejected before a preview callback runs because those states cannot be isolated
safely in-process. Imported modules remain usable for ordinary read/compute
operations, while module attribute writes and known stateful APIs are rejected
instead of being allowed to leak state outside the preview.

Incremental `params` are read-only. Nested JSON-style mappings and collections
are frozen, and a supported custom mutable object is copied each time it is
read, so changing the returned object cannot mutate either the session's
canonical parameters or the caller's original object. Values with uncopyable
or shared mutable class-level state are rejected with `PyneSecurityError`.

Treat preview drawing objects and strategy output as an overlay. A preview may
create an object or submit a strategy order, including a pending stop/limit
order, but those preview-only objects, lifecycle entries, orders, fills, and
trade-ledger changes are not visible from `snapshot_result()` and are not
carried into the later `on_bar_closed()` result.

When the realtime bar is final, submit the final OHLCV through
`on_bar_closed()`:

```python
committed = session.on_bar_closed(final_bar)
merge_committed_result(committed)
```

This callback advances persistent state, TA helpers, drawing objects, and the
strategy ledger. If a preview for the same `time` was already seen,
`ctx.barstate.isnew` is false during the confirmed callback; if the host sends
only a closed bar, it is true.

The currently promoted incremental TA helpers are `adx`, `alma`, `atr`,
`barssince`, `bb`, `boll`, `cci`, `change`, `cross`, `crossover`,
`crossunder`, `cum`, `dev`, `dmi`, `ema`, `highest`, `highestbars`, `hma`,
`lowest`, `lowestbars`, `macd`, `mfi`, `pivot_point_levels`, `pivothigh`,
`pivotlow`, `rma`, `rsi`, `sar`, `sma`, `stdev`, `stoch`, `supertrend`,
`swma`, `tr`, `valuewhen`, `variance`, `vwap`, `vwma`, and `wma`. Query
`pn.runtime_capabilities()["modes"]["incremental"]` instead of assuming every
batch `ta.*` helper has a scalar incremental implementation. `pn.validate()`
and session preparation report statically visible unsupported `ctx.ta.*` calls
before bar processing.

Event times must remain monotonic. Once a host has submitted a preview for a
later bar, it must not submit a closed event for an earlier bar; close the
current preview bar before advancing to the next preview time.

`ctx.state()` cells keep committed history snapshots. Use `cell[1]` to read the
previous confirmed bar's value. If the cell stores an `array`, `map`, or
`matrix`, the historical value is a collection snapshot, so mutating the
current collection does not alter previous-bar state. Nested arrays, maps, and
matrices are snapshotted recursively, so mutating an inner collection on the
current bar does not change the previous bar's nested collection view.

`snapshot_result()` returns the current committed session without replaying the
script:

```python
current = session.snapshot_result()
```

Use it when a UI reconnects, when a viewport range changes, or after a host
needs to discard a preview overlay and redraw the last committed state.

Committed history is unlimited by default. `retention_bars` defaults to
`PyneSettings.incremental_retention_bars` (`None`). An explicit positive value
retains a rolling window of plot points, markers, object events, strategy logs
and state history. `meta.totalCommittedBars` remains an absolute lifetime counter, while
`meta.retainedBars` and `meta.retentionBars` disclose the current window. The
initial seed has an optional, independent `max_bars` admission budget. TA windows, open trades, pending
orders, and live drawing objects remain as active state even when old report
history is trimmed.

For process-local recovery, capture committed state separately from the render
snapshot:

```python
checkpoint = session.snapshot_state()
restored = pn.PyneIncrementalSession.from_snapshot(
    checkpoint,
    script=script,
    settings=settings,
)
```

`snapshot_state()` includes committed context, TA/state/strategy/drawing state,
module globals, the session-scoped cache, counters, and retention position. It
excludes temporary preview state. The snapshot is an opaque in-process Python
object, not a JSON or distributed persistence format. Script hash, params,
security mode, snapshot version, and retention policy must match at restore.
Closures and script-defined classes fail closed because they cannot be safely
rebound to a fresh execution namespace.

For a bounded checkpoint that can cross process boundaries, the default
portable format remains replay v1:

```python
payload = session.snapshot_portable()

restored = pn.PyneIncrementalSession.from_portable_snapshot(
    payload,
    script=script,
    settings=settings,
)
```

The portable payload is canonical JSON with a format identifier, version, and
SHA-256 checksum. Decode and restore enforce byte, nesting-depth, and node-count
limits before replaying the retained committed bars. The data provider is never
serialized; a provider-backed session must receive matching settings or an
explicit provider during restore. Replay export fails closed if the session has
committed more bars than its explicitly configured `replay_history_bars` recording bound, because a partial history
could restore different state.

Replay v1 does not record preview visits. Replayed closed bars therefore have
`barstate.isnew=True`, even if the original live close followed a preview and
had `isnew=False`. Use local or typed-state snapshots when committed calculations
depend on intrabar visitation; replay equivalence applies to scripts whose
committed state is determined by the recorded closed bars. No checkpoint format
preserves the active, uncommitted preview overlay.

For restart latency independent of replay length, opt into typed-state v2:

```python
payload = session.snapshot_portable(mode="state")
# Equivalent convenience spelling:
payload = session.snapshot_portable_state()

restored = pn.PyneIncrementalSession.from_portable_snapshot(
    payload,
    script=script,
    settings=settings,
)
```

Typed-state v2 omits committed replay bars and restores the runtime-managed
state graph directly. It accepts JSON-like containers, bounded numeric/string
arrays, and an exact allowlist of Pyne runtime types; it never imports a class
named by the payload. Unknown user classes, closures, functions, unsupported
array dtypes, invalid references, and limit violations fail closed. It is not a
general Python serializer. The script hash, parameters, security and retention
contracts still have to match, and providers must still be supplied by the
host. `from_portable_snapshot()` detects replay v1 and typed-state v2 from the
format identifier.

Use `run_incremental_parity()` when one feature must produce equivalent batch
and incremental host output:

```python
report = pn.run_incremental_parity(
    batch_script=batch_script,
    incremental_script=incremental_script,
    data=data,
)
report.assert_ok()
```

The runner normalizes transport-only identifiers before comparing output and
returns structured differences. Projects can supply a custom semantic-view
function when only a documented subset should be equivalent.

Incremental callbacks also expose `ctx.request.security()` and
`ctx.request.security_lower_tf()`. The first returns the requested value aligned
to the current chart bar; the second returns a `PyneArray` containing the current
bar's lower-timeframe group. Provider diagnostics are published under
`result.meta["requestDiagnostics"]`, and authoritative provider ranges are
cached across callbacks within the `request_cache_max_bars` / `cache_max_items` limits. Preview
diagnostics stay temporary, while fetched provider evidence may warm that
bounded cache for the matching confirmed callback.

For multi-chart services, `PyneIncrementalSessionManager` provides a small
in-process shared-session cache:

```python
manager = pn.PyneIncrementalSessionManager(
    max_sessions=64,
    idle_ttl_seconds=300,
)
shared = manager.acquire(chart_key, lambda: pn.PyneIncrementalSession(script=script))

try:
    seeded_or_snapshot = manager.seed_or_snapshot(shared, history_bars)
    update = manager.process_bar(shared, live_bar, preview=True)
    committed = manager.process_bar(shared, final_bar, preview=False)
finally:
    manager.release(chart_key)
```

`seed_or_snapshot()` seeds once and returns snapshots afterward. `process_bar()`
deduplicates identical repeated bar events, which helps UI transports that can
retry the same message. Released sessions with a positive TTL remain idle for
quick reconnects. `collect_expired()` removes expired idle sessions. When the
capacity is full, the least-recently-used idle session is evicted; if every slot
is active, acquisition fails with `PyneIncrementalSessionCapacityError`.
`close(key)` explicitly removes an idle session, while an active session
requires the deliberate `force=True` override.

## Consuming Object Events

Incremental drawing output has two layers:

- `output["objects"]`: the current object snapshot for the returned result.
- `output["object_events"]`: create/update/delete events scoped to the returned
  seed, preview, or committed bar range.

Preview object events have `confirmed: false` and should be rendered as a
temporary overlay. Confirmed events have `confirmed: true` and can be merged
into the durable UI object store. When a preview is replaced by a new preview
for the same bar, redraw from the latest preview result. When a bar closes,
discard preview-only UI state and merge the `on_bar_closed()` result.

The same overlay rule applies to strategy output returned by a preview. Hosts
can display preview orders, fills, lifecycle rows, and position changes as
temporary state, but should merge only the strategy report returned by
`on_bar_closed()` into the durable ledger.

## Internal Responsibilities

Incremental runtime code is split by lifecycle role:

- `incremental.bar` defines `IncrementalBar` and scalar barstate wiring.
- `incremental.result` defines `IncrementalPyneResult`.
- `incremental.limits` tracks drawing, state, and resource limits.
- `incremental.ta` owns step-by-step technical-analysis helpers.
- `incremental.drawing` owns line, label, box, and table mutation helpers.
- `incremental.request` adapts the typed batch request provider contract to
  current-bar scalar and lower-timeframe array results.
- `incremental.checkpoint` owns the bounded replay-v1 and typed-state-v2
  portable snapshot envelopes; `incremental.state_codec` owns the fixed typed
  object-graph allowlist.
- `incremental.parity` compares normalized batch and incremental semantics.
- `capabilities` publishes the mode-aware supported surface and early
  diagnostics.
- `incremental.strategy` owns scalar current-bar strategy state and callback
    reporting, while reusing shared batch strategy constants and pure helpers.
- `incremental.context` exposes the callback-facing `ctx` object.
- `incremental.session` owns script compilation, preview cloning, and confirmed
    bar commits.
- `incremental.manager` provides reusable shared-session orchestration.
- `incremental.detection` decides whether a script should use incremental mode.

Public imports remain stable through `pyne_runtime.incremental` and the package
top level. These imports continue to work:

```python
from pyne_runtime.incremental import PyneIncrementalSession
from pyne_runtime import PyneIncrementalSession
```

## Snapshot semantic compatibility

Snapshots now carry a computation semantics identity independently of package
and wire-format versions: `semantics_version` in local state and
`payload.semanticsVersion` in portable replay-v1 and typed-state-v2 envelopes.
The current identity is integer `5`. Identity 5 makes standalone execution
unrestricted by default, separates history policies and allows resource-policy
changes on restore when existing state fits. Identity 4 separates configurable resource
budgets from import permissions and persists them in checkpoint settings. Identity 1 covered corrected TA observation
windows, smoothing, OCA timing and single-bar request confirmation behavior.
Identity 2 also scopes incremental request diagnostics to the current bar.
Identity 3 changes weighted-seed accumulation order to avoid BLAS dispatch
overhead. Semantics-4 and older snapshots must be rebuilt; see
[schema migrations](../reference/schema_migrations.md).

Unmarked legacy snapshots and mismatched identities raise
`PynePortableSnapshotError` with `code == "PYNE_SNAPSHOT_SEMANTICS_MISMATCH"`.
Restore checks this before replacing live state; portable restore checks the
envelope before decoding the graph or constructing/executing a session. The
typed-state root must also carry a matching identity. Existing format names
remain unchanged; older consumers that require exact payload fields reject new
snapshots rather than ignoring the identity.

Rebuild from authoritative OHLCV in a fresh session after an incompatible upgrade.
Do not edit the identity to force restoration. Replay under new semantics can
produce different results and is a rebuild, not equivalent restoration. Intrabar
history and external provider data remain host responsibilities. Since legacy
snapshots have no reliable semantic identity, rejection applies to all unmarked
snapshots, including scripts that might happen to be unaffected.

Contributors must bump `INCREMENTAL_SEMANTICS_VERSION` when a change makes stored
state or replay behavior incompatible. Documentation-only and compatible changes
do not require a bump. This identity is a compatibility contract, not an automatic
code fingerprint or an authentication mechanism.

### Incremental request diagnostic retention

`meta.requestDiagnostics` contains all diagnostics generated in the current bar,
including successful calls and ignored-invalid-symbol/timeframe diagnostics.
Starting the next bar discards earlier entries. Batch diagnostics are unchanged.
There is no new per-bar entry cap: this bounds lifetime history growth, not the
number or size of requests a script can execute in one callback.

When diagnostics exist or have been discarded, `meta.requestDiagnosticsInfo`
contains `scope="current_bar"`, `barTime`, `retained` (current entry count),
`dropped` (cumulative prior-bar entry count) and `truncated` (`dropped > 0`).
Discarded entries include successful calls; this is not a count of missed errors.
A bar without requests returns an empty diagnostic list and the accumulated
discard count. A session that never requested data has neither metadata field.
`snapshot_result()` reports diagnostics for the latest bar, even when a different
output time range is selected; `barTime` identifies that scope explicitly.

Preview starts from committed counts and reports its own current-bar diagnostics;
repeated previews never advance committed counts. Local and typed-state snapshots
retain the count, while replay reconstructs it. All three restore modes reject
semantics-1 snapshots; rebuild from authoritative OHLCV after upgrading.
Unhandled request/provider exceptions keep their existing failure behavior.
Hosts needing complete diagnostic history must collect each confirmed result;
bounded opt-in trace remains a separate diagnostic channel.
