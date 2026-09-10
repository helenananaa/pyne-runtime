# Schema Migrations

Pyne exposes host-facing contracts through `pn.schema()`. Each schema section
owns an independent `schemaVersion` so hosts can branch on the specific contract
they consume.

Current schema versions:

- `input`: `PYNE_INPUT_SCHEMA_VERSION`
- `output`: `PYNE_OUTPUT_SCHEMA_VERSION`
- `params`: `PYNE_PARAM_SCHEMA_VERSION`
- `requestProvider`: `PYNE_REQUEST_PROVIDER_SCHEMA_VERSION`
- `strategyReport`: `PYNE_STRATEGY_REPORT_SCHEMA_VERSION`
- `runtimeCapabilities`: `PYNE_RUNTIME_CAPABILITIES_SCHEMA_VERSION`
- execution trace: `PYNE_TRACE_SCHEMA_VERSION`
- process-local incremental snapshot: `PYNE_INCREMENTAL_SNAPSHOT_VERSION`
- portable incremental snapshot: `PYNE_INCREMENTAL_PORTABLE_SNAPSHOT_VERSION`
- portable typed-state snapshot: `PYNE_INCREMENTAL_PORTABLE_STATE_SNAPSHOT_VERSION`
- script inspection: `PYNE_SCRIPT_INSPECTION_SCHEMA_VERSION`
- directory inspection: `PYNE_SCRIPT_DIRECTORY_INSPECTION_SCHEMA_VERSION`

## Incremental Snapshot Schemas

### Computation semantics identity

The computation identity is `INCREMENTAL_SEMANTICS_VERSION`, currently **5**.
Portable payloads carry `semanticsVersion`; local snapshots carry
`semantics_version`. This identity is independent of the package and snapshot
wire-format versions. Missing or mismatched identities are rejected with
`PYNE_SNAPSHOT_SEMANTICS_MISMATCH`, even if other snapshot fields match.

Version 5 makes computation quotas nullable, changes standalone execution defaults,
separates retained history from replay recording and validates restore budgets
against stored state rather than requiring all settings to be identical. Rebuild
version-4 and older sessions from authoritative OHLCV.

Version 4 separates resource budgets from import permissions and records all
new budgets in local and portable snapshot settings. Rebuild version-3 and older
sessions from authoritative host OHLCV; never relabel old payloads.

Version 3 replaces the weighted-seed BLAS reduction with a NumPy reduction.
The mathematical formula is unchanged, but accumulation order can change
unrounded values used by request expressions and script state. The identity
therefore advances conservatively. Rebuild version-2 and older sessions from
authoritative host OHLCV; never relabel old payloads. See
[Session Recovery](../tutorials/session_recovery.md) for the intrabar-history limit.
Same-version continuation, script/settings checks and wire-format validation
still apply; matching this number alone is not sufficient to restore a snapshot.

Process-local incremental snapshots are currently version 3, adding the settings
contract used to preserve and validate execution budgets. They are opaque
Python runtime objects and are valid only for matching script, settings,
parameters, retention policy, and runtime semantics.

Portable replay snapshots use format
`PYNE_INCREMENTAL_PORTABLE_SNAPSHOT_FORMAT` and schema version 1. Their
canonical JSON envelope includes a checksum and is decoded with byte, depth,
and node limits. Restore replays the bounded committed bar history.

Portable typed-state snapshots use
`PYNE_INCREMENTAL_PORTABLE_STATE_SNAPSHOT_FORMAT` and schema version 2. They
omit replay history and encode a bounded object graph from an exact runtime type
allowlist. Payloads cannot select import paths or arbitrary user classes.
Providers are deliberately not embedded in either format and must be supplied
again for provider-backed scripts. The restore entry point detects the exact
format identifier; older or unknown versions fail closed rather than being
guessed or migrated implicitly.

Typed-state v2 restore validates exact node fields, duplicate decoded mapping
keys, set/hashability constraints, ndarray shape and element budgets, and
method/dunder shadowing before reconstruction. Graph nodes retain their source
objects during encoding so temporary object-id reuse cannot create accidental
aliases. These checks are fail-closed compatibility rules, not best-effort
repairs of malformed payloads.

Script inspection schema version 2 adds provider/output requirements, migration
readiness, and signature-aware resource hints. Directory inspection schema
version 1 wraps per-script v2 manifests with deterministic paths and summary
counts; hosts should branch on both independent versions.

## Runtime Capability And Trace Schemas

`pn.schema()["runtimeCapabilities"]` is an additive top-level schema-bundle
section. It has an independent version and declares batch/incremental support,
pinned library modes, trace availability, and security/language boundaries.
Hosts should branch on its `schemaVersion` rather than infer support from a
package version or namespace name.

An enabled execution trace appears under `result.meta["trace"]` and has an
independent `schemaVersion`. Trace metadata is additive: hosts that do not use
diagnostic traces can ignore the field. Consumers must allow bounded event
lists and inspect `droppedEvents` before treating the trace as complete.
Trace schema version 2 adds hierarchical timing spans, aggregate/slow-span
summaries, and field-redaction metadata. Duration values are nondeterministic
diagnostics and should not be used as replay equality keys.
Per-span event records are disabled by default to bound hot-path overhead;
`trace_span_events` opts into them. Decoders restoring older state treat the
missing setting as `False`.

## Output Schema

`pn.schema()["output"]["migration"]` is the machine-readable migration policy
for host renderers.

Version 1 remains supported for legacy hosts. It defines:

- top-level result metadata and error fields;
- structured renderer collections under `result.output`;
- drawing object snapshots under `output["objects"]`;
- incremental drawing object events under `output["object_events"]`;
- strategy reports under `output["strategy"]`, with details in
  `pn.schema()["strategyReport"]`.

There are no breaking changes recorded inside output schema version 1.

Version 2 is current. It adds `output.candles`, `objects.linefills`,
`objects.polylines`, and `objects.tables[*].merges`. Hosts that validate exact
collection names must branch on `schemaVersion`; the v1 fallback is valid only
for scripts whose output stays within the v1 surface.

Compatibility notes:

- `result.lines` remains a backward-compatible flat plot view.
- `output["labels"]` is a legacy simple text label collection.
- Hosts should prefer `output["objects"]["labels"]` for Pine-like drawing
  labels.

## Request Provider Schema

`pn.schema()["requestProvider"]["migration"]` is the machine-readable migration
policy for host-backed `request.*` integrations.

Version 10 is the current request provider schema. Error categories no longer
publish `messageContains`; consumers must branch on
`RequestProviderErrorCategory`, `PyneRequestError.category`, or serialized
`errorDetail.requestProviderCategory`. Provider adapters may use the exported
typed provider exceptions, and the package includes a reusable conformance kit.

Version 9 changed provider `start` / `end` coordinates to describe the bounded
warmup-expanded fetch window and the last
chart bar's close boundary, rather than the raw first/last chart opening-time
range. A non-empty result with too few actual pre-chart bars can trigger a
four-times wider lookback, capped at six widenings. A valid empty result stops
the sequence immediately. This is bounded best effort and does not guarantee
unlimited requested history. The
`get_ohlcv(symbol, timeframe, start, end)` signature remains inclusive and
unchanged. Version 10 preserves version 9 range behavior, version 8
`request.security_lower_tf()` invalid-timeframe discovery metadata, version 7
`supportedApis`, version 6 `errorDetail.requestProviderRequest` for failed
request calls, version 5 `meta.requestDiagnostics` entries, and version 4
structured `errorCategories` for host-facing request diagnostics.

Compatibility notes:

- Hosts that only read `errors` can continue doing so.
- Hosts can read `supportedApis` to decide which request APIs to expose in UI,
  editor help, and provider capability checks.
- Hosts that display request integration failures should prefer
  `errorCategories`, which records stable error codes, typed classifications,
  whether `get_ohlcv` is called, and `ignore_invalid_symbol` behavior.
- Runtime request failures include the matching category as
  `errorDetail.requestProviderCategory`.
- Runtime request failures include failed `api/symbol/timeframe/start/end`
  coordinates as `errorDetail.requestProviderRequest`.
- Successful request calls append one entry to `meta.requestDiagnostics`; cache
  reuse is indicated by `cacheHit`.
- Diagnostic `start` / `end` values match the expanded coordinates passed to
  the final `get_ohlcv(...)` attempt after adaptive widening, so hosts upgrading
  from version 8 must not assume they equal either the first and last chart
  opening timestamps or the initially calculated warmup range.
- A provider error during adaptive widening records the final attempted range
  in `errorDetail.requestProviderRequest`.
- Adaptive results are cached by their final range. When the widening budget is
  exhausted, the same or a smaller warmup requirement reuses that result; only
  a larger requirement resumes widening.
- Valid empty provider results are successful requested contexts: they report
  `status="ok"`, `bars=0`, and can be reused from the request cache.
- `invalidSymbol` remains the only provider-side error class that can be
  intentionally converted into empty request output by `ignore_invalid_symbol`.
  Those ignored invalid-symbol results report `status="ignoredInvalidSymbol"`
  and are not cached.
- `request.security_lower_tf(..., ignore_invalid_timeframe=True)` can convert a
  recognized invalid non-lower requested timeframe into empty lower-timeframe
  groups before `get_ohlcv()` is called. Those results report
  `status="ignoredInvalidTimeframe"` and are not cached.

## Breaking Change Checklist

Any breaking change to a host-facing schema must include all of these in the
same change set:

- bump the affected `schemaVersion`;
- add a migration note to the affected schema's migration policy;
- update the reference documentation;
- update or add a contract test;
- update the host consumption fixture when renderer output changes.

For output schema changes, the packaged
`examples/host_output_contract.py` fixture should continue to represent the
renderer collections and drawing object groups hosts are expected to consume.
