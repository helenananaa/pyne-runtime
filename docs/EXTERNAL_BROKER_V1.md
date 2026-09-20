# External broker V1

`from pyne_runtime.external import run_external` exposes a host-neutral account
feedback evaluator. Pass `source`, supplied OHLCV `bars`, one authoritative
`accounts` frame per bar, and optional `params` / `settings`.

Frames contain exactly `time`, `position_size`, `position_avg_price`, `equity`,
`initial_capital`, `netprofit` and `openprofit`. `position_avg_price` may be null
when flat. Frames must match bar times. The normal batch or incremental runtime
executes the script with an intent namespace in place of the native broker.

Batch `strategy.entry_when` / `close_when`, market `entry`, full `close` and
`close_all` are supported. Incremental scripts use `ctx.strategy.configure()`
and the corresponding scalar methods. The host applies one-position entry and
reversal policy and handles actual fills; the engine emits no native account.
Order keywords and account fields outside this V1 contract raise errors. External
request data, limit/stop orders, pyramiding and native execution settings are not
supported by this contract.

Growing prefixes must include the frozen account transcript. The caller must
check that past intents remain identical before committing the new suffix. State
whose decisions change when the prefix grows is rejected by the embedding host.
Source, account frames and transcript identity form the restore contract; native
incremental checkpoints are not repurposed. Native computation semantics and
`INCREMENTAL_SEMANTICS_VERSION` are unchanged.

This module has no host application imports. Caller-selected execution settings
retain the standalone full-Python default; host security and budgets remain host
policy. This is a local candidate extension, not a published release.


## Additive order profile V2

The wire contract remains external-broker/1; optional fields extend intents without changing account frames.
Entry now accepts absolute limit and stop prices (both means stop-limit). Close accepts qty or qty_percent.
Exit accepts from_entry, absolute limit/stop and optional qty/qty_percent; both prices describe an OCO bracket, not a stop-limit order.
Cancel and cancel_all emit lifecycle intents. The host owns ID replacement, OCO cancellation, fills and quantity reduction.
No native broker is executed. Unsupported native settings and account fields still fail explicitly.
Pyne batch quantities and prices may be aligned series; incremental order values are scalars.
Historical prefix stability remains a host obligation. This is not a change to native incremental snapshot semantics.


## Optional execution passes

`run_external(..., execution_passes=groups)` accepts one nonempty group per supplied chart bar.
Each pass contains `bar` (visible OHLCV only), `account` (the authoritative external account frame),
`event_time_ms`, and `confirmed`. Times are ordered and a confirmed pass must be last in its group.
The last chart bar may have only unconfirmed passes. Order intents add `pass_index` in this profile.
The host must preserve prior pass inputs and reject rewritten prior decisions. Matching, event eligibility,
resource budgets, persistence and input acquisition remain host responsibilities.
This API emits no native fills or native account report.
Pyne requires an incremental `init/on_bar` script, `strategy.configure(calc_on_order_fills=True)`, and `on_fill(ctx, bar)`. Unconfirmed passes call on_fill; confirmed passes call on_bar. Context state is retained across callbacks; explicit indicator update calls occur exactly where the script calls them. Batch scripts are rejected for this profile. Existing incremental snapshots and semantics version are unchanged.

## Supplied request provider

run_external(..., allow_requests=True) enables the existing PyneSettings.data_provider request path for batch and incremental scripts. The default global request facade remains disabled for compatibility. The caller supplies and bounds data; this module performs no host acquisition or persistence. This adds an opt-in API and does not change committed incremental checkpoint structure.


## Additive multi-entry and pass-data profile

The result includes the declared positive integer `pyramiding`; the embedding
host decides admission limits and owns entry allocation and fills. Exit intents
now preserve positive `profit`, `loss`, `trail_price`, `trail_points`, and
`trail_offset`. A trailing exit requires exactly one activation (price or points)
and an offset. No tick conversion or matching runs in this evaluator.

Each execution pass may supply `request_data`, a list of
`{symbol, timeframe, bars}` streams. This replaces the provider for that pass and
uses a fresh request cache. The caller must freeze every prior pass's data and
provide only data permitted by its visibility policy. Empty known streams are
distinct from absent streams. Chart metadata remains separate from the provider.
Native broker entrypoints and native incremental checkpoint semantics are
unchanged: external reconstruction uses the supplied transcript, not native
broker snapshots. This is an unpublished host-neutral candidate extension.
