# Compatibility

Pyne Runtime is currently pre-1.0.

Compatibility goals:

- Patch versions should not break public root imports.
- Minor versions may add new public APIs.
- Breaking changes should be documented in `CHANGELOG.md`.
- `pn.__version__` follows the installed package version.

Stable root imports are documented in [Public API](../api/public_api.md).
The detailed Pine-like feature matrix lives in
[Pine-Like API Matrix](pine_like_api_matrix.md).

## 0.4 Release-Line Contract

Version 0.4 changes the standalone defaults to full Python in the caller process,
with no default deadline or computation quotas. Hosts upgrading from 0.3 must
explicitly select their import policy, process isolation, and resource budgets;
see [execution policies](../concepts/security_modes.md).

- Within 0.4.x, patch releases preserve documented package-root imports, call
  signatures, and existing CLI commands. Numeric fixes may require recalculation
  and must be identified in the changelog.
- The 0.4.1 computation semantics is 42; published 0.4.0 uses 5. This identity
  is separate from package and wire-format versions. WMA gaps (including
  HMA/composed WMA), CMO boundaries and Stochastic cached/extrema state change
  calculation results; extrema gap resets and earliest-tie offsets add a second
  correction. Pivot tie/gap/startup rules add a further correction.
  Rising/falling valid-comparison windows also affect generic Python callbacks.
  Cumulative/OBV missing output and cross pair-state/tie rules add another correction.
  Default Keltner EMA range widths affect batch results and generic Python replay;
  select `width_smoothing="atr"` explicitly for the preceding ATR-width formula.
  Missing-percentile order updates change results after differing earlier histories.
  Strategy entry admission uses live trade slots; partial lot closure updates
  weighted average and frees capacity. Carried pending fills precede close-fill
  batch calculation state and current-bar commands. Committed state with an
  incompatible computation identity must be rebuilt.
  Public positive-length `math.sum` also uses non-missing observation windows
  rather than rejecting a bar window containing gaps.
  Older incompatible snapshots are rejected; rebuild from authoritative OHLCV.
  Version 42 also repairs causal weighted windows, incremental cancellation,
  mutable parameter isolation and configured strategy equity; see
  [0.4.1 upgrade guidance](../development/release_0.4.1_zh.md).
- Resource policy is independent of computation identity. Compatible state may
  restore under a new budget when it fits; restored objects adopt that budget.
- Source and installed-wheel qualification, supported platforms, and workload
  evidence for each release are recorded in [current status](current_status.md).
  The declared API matrix remains the compatibility boundary.

## Historical 0.3 Release-Line Contract

These are the promotion requirements for the first stable 0.3 release line,
not a claim that the current candidate has completed release qualification.
The [delivery ledger](../development/stable_delivery_zh.md) tracks that decision.

- Supported execution is trusted Python scripts over host-supplied OHLCV using
  the documented public API and each mode's declared capabilities. Python
  3.11/3.12/3.13 on Windows, Linux and macOS require source and installed-wheel
  evidence for the selected release commit. Other versions or platforms are
  unqualified even if package installation accepts them.
- Within 0.3.x, patch releases preserve documented package-root imports, call
  signatures and existing CLI commands. Removing or changing those contracts
  requires a later release line, migration documentation and focused checks.
- Host-facing schema versions are independent. Additive fields may appear;
  consumers should tolerate unknown optional fields. Incompatible field meanings
  require the relevant schema version and migration instructions, not only a
  package version change.
- Numeric correctness fixes may change outputs in a patch release. Release notes
  must identify the affected algorithms and required recalculation. Incompatible
  committed-state or replay semantics must advance the computation-semantics
  identity and reject incompatible snapshots. There is no promise of bitwise
  output identity across a documented semantic correction.
- The supported recovery path is compatible state restore or reconstruction from
  authoritative input. OHLCV alone cannot reconstruct past preview visitation;
  see [Session Recovery](../tutorials/session_recovery.md). Providers, persistence
  and distributed coordination remain host-owned.
- Compatibility claims are limited to the declared feature matrix and identified
  acceptance cases. Inspectors expose requirements and advisory hints; they do
  not certify arbitrary Python execution. Bar-based strategy replay, untrusted
  code isolation and renderer integration retain the boundaries in
  [Current Project Status](current_status.md).
- Capacity reports identify workloads, source identities, settings and measured
  hosts. They support the measured operating range, not a universal latency SLA
  or a concurrency limit for arbitrary scripts and providers.

The output schema has its own version: `PYNE_OUTPUT_SCHEMA_VERSION`.
Script parameter schemas have their own version:
`PYNE_PARAM_SCHEMA_VERSION`.
The host request-provider contract has its own version:
`PYNE_REQUEST_PROVIDER_SCHEMA_VERSION`.
Schema migration policy and breaking-change requirements are documented in
[Schema Migrations](schema_migrations.md).
Release versioning and release-candidate checks are documented in
[Release Process](release_process.md).

## Pine-Like Surface

The 2026-09-07 source candidate corrects EMA/MACD missing-value seeding/output and
RSI missing/flat behavior against new Pine v6 evidence. Scripts that relied on
early EMA seeds, carried gap values, or flat RSI=0 will produce different output.
Rebuild affected sessions from OHLCV when adopting this change; reusing snapshots
computed under the old semantics is not a supported migration. This does not
change API names or output schema versions. Details are in the
[TA boundary acceptance report](../development/ta_boundary_acceptance_zh.md).

The follow-on slice corrects VWMA's independent non-missing observation windows
and incremental market `strategy.order` OCA effects. Rebuild affected VWMA/OCA
sessions from original OHLCV when adopting the candidate; old computed snapshots
are not a supported semantic migration. Supertrend's first zero is retained
because a native Pine capture confirms it. See
[trend/volume/OCA acceptance](../development/trend_volume_oca_acceptance_zh.md).

The rolling-statistics slice aligns SMA/stdev/variance/BB missing-value windows
and the public SMA-ratio composition behind VWMA. Rebuild affected old sessions
from OHLCV. Stable centered dispersion is retained as a deliberate numeric
difference from two high-offset native Pine capture columns; their raw values
are preserved as reference evidence, not counted as zero-diff parity. Details:
[rolling statistics acceptance](../development/rolling_statistics_acceptance_zh.md).

Supported:

- `close[1]` and other non-negative bars-back history references.
- `na`, `nz()`, `when()`, and `switch()` helpers for Python-friendly series logic.
- `bar_index`, `last_bar_index`, and `barstate.*` in batch execution.
- `var()` / `pyne.var()` state cells.
- `line` and `label` drawing object handles.
- `box` and `table` drawing object handles.
- `request.security()` for host-backed OHLCV field requests and callable expression thunks.
- `request.security_lower_tf()` for host-backed lower-timeframe grouping.
- `strategy.entry_when()` and `strategy.close_when()` event output.
- `strategy.exit()` stop/limit event output.

Known differences:

- Pyne scripts are Python, not TradingView Pine source code.
- Python `if` cannot branch directly on a series; use `when()` or `switch()`.
- `request.security()` cannot capture already evaluated Python expressions such
  as `ta.ema(close, 20)`; use `lambda ctx: ctx.ta.ema(ctx.close, 20)`.
- Higher-timeframe `request.security()` confirmation alignment is covered by a
  TradingView-backed HTF capture parity fixture.
- `request.security_lower_tf()` returns grouped Python/Pyne objects rather than
  Pine native arrays. Higher-timeframe gaps/lookahead alignment and
  lower-timeframe grouping behavior are covered by golden-style fixtures in
  `tests/golden/`.
- Request provider diagnostics distinguish legal empty provider results from
  ignored invalid symbols: legal `[]` results are successful cached contexts,
  while `PyneInvalidSymbolError` converted by `ignore_invalid_symbol=True`
  returns empty output without populating the provider cache.
- Strategy support emits deterministic events and a lightweight position
  timeline; it is not a full broker simulator and does not model a complete
  intrabar path or broker liquidation.


The `collection_string_extraction` native scalar probe adds eight fixed matrix/map
string profiles and two Boolean matrix constructors. Semantics 28 retains string
conversion intent through extraction and committed/restored collection state;
Boolean matrices default to false. Its 224 exact text cells remain separate from
numeric cells and earlier join text. Broader collection types, shape/bounds,
reference-valued extraction, and initially-all-missing generic map intent remain
unqualified; Python extensions do not imply Pine typing equivalence. Genuine
semantics-27 checkpoints require rebuilding from authoritative supplied OHLCV.


The `matrix_empty_shapes` native probe qualifies eight fixed empty shape and
reshape profiles, scalar arithmetic and degenerate products. Computation
semantics 29 retains matrix width when no rows exist, including committed
history and restore. Genuine semantics-28 snapshots must be rebuilt from supplied
OHLCV. Eight fixed profiles and 1,152 numeric cells do not establish full matrix
shape/type/parameter coverage; the cumulative alignment goal remains active.

The rectangular-matrix evidence expansion keeps computation semantics 29 and
runtime implementation unchanged. It adds twelve fixed float profiles and three
native dimension-error witnesses. Repeated finite samples, reverse transpose
products and zero/missing products do not establish general types, conditioning,
dimensions or rejection boundaries. Native error-presence and Python after-error
state tests are separate qualifications; the alignment Goal remains active.

Computation semantics 30 changes correlation to independent present-observation
windows for x, y and x*y. Ready zero numerator and denominator return zero;
nonzero numerator with zero denominator remains missing. Period-one variance
is exactly zero, and missing-window results are not clipped to [-1, 1]. Coherent
finite windows retain stable centered Pearson arithmetic. Genuine installed
rc24 /semantics-29 ordinary and correlation checkpoints are retained and rejected
before construction; rebuild from authoritative supplied OHLCV. Moderate shifted
roundoff and large-offset native disagreements remain counted at the original
strict tolerance. These fixed profiles do not qualify general numerical behavior.

Computation semantics 31 additionally makes ready finite period-one population
variance/stdev exactly zero and the incremental mean exactly the latest present
observation. Single-observation BB bounds therefore coincide. Sample variance
remains missing and missing-observation readiness/carrying is preserved. Genuine
installed rc25 /semantics-30 ordinary and affected dispersion state/replay
checkpoints are retained under `tests/golden/` and rejected before construction.
Rebuild from authoritative supplied OHLCV; changing old envelope labels is not a
migration. Same-version local/replay/state continuation and preview isolation
remain tested. Fixed native profiles do not qualify Python infinity behavior.

Computation semantics 32 preserves raw binary64 output values independently of
display precision and makes batch SMA(1) exactly the latest present observation.
Incremental strategy calculation properties preserve their arithmetic before
scripts and risk checks consume them. Existing ledger/report formatting remains
separate; arbitrary financial precision is not qualified. Actual installed rc26
/semantics-31 ordinary and affected output snapshots are retained and rejected
before construction. Rebuild from authoritative supplied OHLCV; never relabel
old envelopes. Portable wire formats remain unchanged. Same-version local,
replay and state continuation, retention and preview isolation remain tested.

Computation semantics 33 unifies the initial dataset-origin lookback for batch
extrema, their bars-back offsets and Stoch. All modes wait the first `length`
bars; missing input resets candidate windows without restarting that initial
clock. Donchian and WPR inherit batch extrema readiness. Stoch retains its later
missing/flat holding behavior. Genuine rc27 /semantics-32 ordinary and affected
snapshots are rejected before construction. Rebuild from authoritative supplied
OHLCV; do not relabel checkpoints. A fresh independently generated native
holdout qualifies five fixed lengths and five input profiles. Thirty-two sparse
imported startup conflicts lack sufficient original-history provenance and
remain unexpected differences; full candidate qualification has not passed.
