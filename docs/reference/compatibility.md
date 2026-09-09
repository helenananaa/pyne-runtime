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

## Stable 0.3 Release-Line Contract

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
