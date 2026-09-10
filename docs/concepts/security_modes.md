# Execution Policies and Security Modes

## Standalone defaults

`pn.run()` and `PyneSettings()` default to full Python builtins/imports
(`security_mode="unsafe"`, the existing API name), `executor_mode="inline"`,
and `timeout_seconds=None`. This is ordinary trusted local Python execution.
There is no default quota on input bars, computation collections, plots, drawings,
or incremental state. Large workloads are subject to actual machine resources.
Importing pandas or defining a class does not require selecting another mode.

```python
import pyne_runtime as pn

result = pn.run(script, pn.from_pandas(df))
```

Input/output and computation budget fields accept `None` for unlimited. Positive
integers enable individual budgets; zero is rejected, not silently changed to one.
For compatibility, `timeout_seconds=0` also means no deadline. `PYNE_*` environment
settings are available through the normal environment-backed entry points; optional
budgets accept `none` or `unlimited` as well as positive integer strings.

Trusted batch parameters are copied with Python deepcopy, which preserves normal
Python callback identity. They do not need to be pickle-serializable in inline
execution. Incremental params/globals retain the separate isolation rules required
for preview rollback and snapshots; custom classes/closures are not portable state.

## Explicit controlled execution

The caller decides policy. A host can request restrictions without changing the
standalone defaults:

```python
settings = pn.PyneSettings(
    security_mode="safe",
    executor_mode="process",
    timeout_seconds=5,
    require_hard_timeout=True,
    max_bars=50_000,
    max_output_series=20,
    max_output_points=1_000_000,
    max_drawing_objects=500,
    max_array_size=100_000,
    max_window_size=10_000,
    max_state_keys=100,
    incremental_retention_bars=10_000,
    replay_history_bars=50_000,
)
result = pn.run(script, data, settings=settings)
```

These numbers are an example caller policy, not required runtime capacity limits.
Imports, execution strategy and individual budgets are independent choices:

- `unsafe`: full Python builtins and imports; the standalone default.
- `safe`: no imports and a restricted builtins set.
- `research`: imports from `allowed_imports`, with restricted builtins.

Research defaults include computational standard libraries (`math`, `statistics`,
`decimal`, `fractions`, `itertools`, `functools`, `collections`, `bisect`, `heapq`,
`operator`) and `numpy`, `pandas`, `scipy`, `sklearn`, `torch`. An explicit
`allowed_imports` replaces that list. Restricted modes include `iter`/`next` and
report unsupported class definitions during validation.

Safe/research are not OS or multi-tenant sandboxes. Process execution uses spawn,
requires pickle-serializable arguments/providers, and can terminate its worker
when a configured deadline expires. Those restrictions apply only when process
execution is selected. Inline deadlines are best-effort Unix-main-thread timers,
not hard interrupts on Windows or other threads. A required hard timeout needs
process execution. The full builtins mapping is copied rather than shared with
the host interpreter's builtin dictionary.

## Independent budgets

All fields below default to `None` and have uppercase `PYNE_` environment names.

| Settings | Purpose |
| --- | --- |
| `max_bars` | Admission to a batch execution or initial incremental seed |
| `max_output_series`, `max_output_points` | Output channels and data points |
| `max_drawing_objects`, `max_object_events`, `max_table_cells` | Drawing objects, event records and incremental table cells |
| `max_array_size`, `max_map_size`, `max_matrix_cells`, `max_collection_depth` | Computational collections |
| `max_window_size`, `max_total_window_items`, `max_state_keys` | Incremental windows and combined state/varip keys |
| `max_strategy_pending_operations`, `max_strategy_log_entries` | Strategy replay work and incremental log records |
| `max_state_payload_items`, `max_preview_payload_items` | Incremental stored-state and preview-global payloads |
| `incremental_retention_bars` | Retained output and state history; unlimited by default |
| `replay_history_bars` | Complete replay recording; independent of input and output history |

Drawing objects/events and strategy reports do not consume output-series slots.
Cache capacities remain bounded optimizations: `cache_max_items=32` and
`request_cache_max_bars=1_000_000`; eviction permits a later load/refetch. They do
not cap total processed bars. The optional session manager's capacity/TTL rules
apply only to users of that manager, not to directly constructed sessions.
Snapshot decoding retains separate byte, depth, node and type checks.

## Recovery and compatibility

Semantics identity 5 introduces standalone defaults, nullable budgets and
independent history recording. Rebuild older sessions from authoritative OHLCV;
never relabel older snapshots. Local snapshot schema 3 and portable replay/state
formats retain their identities; computation identity is checked separately.

Restoring requires matching script, params, language permissions, market metadata
and computation semantics. The snapshot's actual history-retention policy is
preserved. Timeout and cache settings may change. Computation budgets may change
when the copied state fits: restored collection capacities and trackers adopt the
new settings before execution continues. A smaller budget that cannot contain
existing state is rejected before replacing the live state. Replay restoration
also needs enough admission capacity for its original seed. A finite replay-record
budget cannot accept an existing longer complete recording; typed-state recovery
can be used when retaining that recording is unnecessary.

A seed rejected during input admission does not poison a healthy session. Callback
failures that may have partially changed committed state still prevent continued
execution; preview isolation and confirmed-history immutability remain intact.

## Actionable diagnostics and preflight

Capacity failures are resource/output errors, not permission requests. Direct
exceptions expose `code` and `hint`; `pn.run()` returns the corresponding
structured result. Preview/state failures have their own state-contract code.

CLI validation accepts the same import and budget options as running. Use
`pyne validate script.py --target preview` or `--target snapshot` for additional
non-executing checks. These are optional authoring aids, not a new execution gate.
See [CLI](../reference/cli.md) and [error codes](../reference/error_codes.md).
