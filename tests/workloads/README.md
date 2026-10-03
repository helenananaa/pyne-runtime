# Whole-script semantic workloads

`numeric_output_precision` retains native raw logs for eight independently
generated inputs and 32 output columns with display precision two. Both execution
modes count every output at the original 1e-12 tolerance. After semantics-32
output and SMA(1) corrections, the large-offset SMA(3) column still contributes
22 batch and 24 incremental differences; these are measured arithmetic debt.
The inputs are controls, not additional output cells. Tiny and fractional raw
values, missing masks, same-version continuation, preview and retention are
checked separately. Fixed profiles do not qualify full numerical/API coverage.

These are first-party, host-neutral Pyne scripts. Run their acceptance suite from
the repository root with `python -m pytest tests/test_semantic_workloads.py -q`.
They are test assets, not additions to the packaged `examples/*.py` inventory.

| Workload | Composition | Oracle |
| --- | --- | --- |
| `ta_chain` | SMA 3/7, crossover, last-event value | TradingView Pine v6, plus batch/incremental equality |
| `requests` | HTF close, sparse LTF groups, local smoothing/spread | Batch/incremental equality, future perturbation, single-HTF confirmation assertions |
| `state_cache` | Nested cache alias, state counter, bounded rolling list, SMA | Independent sums and counters |
| `drawings` | State-held line/label handles, create/update/delete cycles | Exact event sequence, timestamps and confirmed flags |
| `strategy` | Stop cancellation, entry, partial reduction, final close, fees | Full batch strategy report equality plus position/profit/equity arithmetic |

All five run through repeated preview, local/replay/state restoration, rolling
retention, 256-bar state restoration, and failure/recovery scenarios. Tests compare
timestamped points, not just values; missing warmup points must remain missing.

`strategy_cycles.py` is a performance variant repeating the original lifecycle
every 12 bars. It keeps transactions active beyond the first nine bars, unlike
the original strategy's idle tail. Its per-cycle net profit and commission have
independent arithmetic checks; it is not an additional TradingView capture.

Run `python scripts/semantic_workload_benchmark.py --output build/semantic-performance/baseline.json`
for isolated-process timing, snapshot and Python allocation measurements of these
six workloads. The benchmark extends the synthetic request provider's time horizon;
it never fetches market data. Raw samples and source identity are retained in JSON.

## TradingView evidence

`variance_independent_holdout` (Round56) retains an official Pine logs UI CSV
download of 64 rows and independently frozen scalar inputs. Four profiles and
three periods produce 48 variance/stdev output columns; 24 native mean/meanXX
columns are diagnostic controls only. All 256 input cells are reconstructed
from Pine and both recipes. The 3,072 canonical cells enter each runtime mode,
including readiness and every numeric discrepancy. Sample stdev explicitly uses
sqrt(sample variance); the public stdev API has no bias parameter. Native formula
matches and diagnostic controls do not add parity cells or establish private
implementation. `variance_native_diagnostic.py` verifies the download, identities
and inputs; altered or rehashed evidence fails closed. This evidence does not
qualify the rejected public-SMA variance candidate or complete API coverage.

`recursive_composition_ohlcv_holdout` and `recursive_composition_weekly_holdout`
(Round55) record the initial 64 monthly and weekly BINANCE:BTCUSDT bars with six
source/control columns and 13 native TR/ATR/DMI outputs. Native output fields
never supply runtime inputs. DMI lengths 3/7 and ADX smoothing 3/7 run
unconditionally from native bar zero; tolerance stays 1e-8. The weekly design
and candidate kernel were frozen before weekly observation. Correct strict-TR
seeding matches all columns in both modes; public ATR retains its origin fallback.
Genuine installed rc31 /36 snapshots are retained, rejected before constructing
semantics-37 sessions, and new-version preview/state/replay checks cross readiness.
These complete OHLCV captures do not qualify fabricated gaps or the full API.

`legacy_dmi_wrapper_discriminator` separately evaluates old fallback and strict
custom formulas on source OHLCV from three imported fixtures. All 115 imported
DI points reproduce exactly with the old formula; 111 differ from strict values.
Raw discrepancies remain counted, with exact per-point native witnesses. This
diagnostic is not a direct native built-in capture, does not prove historical
origin, and contributes no additional runtime parity cells. It remains listed
among unmeasured native diagnostics; the exporter now uses the strict formula.

`recursive_state_holdout` (Round54) supplies three independent source profiles
from seed 2026100354: leading gaps, flat sign runs with missing blocks, and
ordinary 1e4/small/-1e4 regime changes. All unconditional EMA/RMA/RSI calls at
periods 1/2/3/7/11 are recorded for 64 bars. The 192 input cells are controls;
all 45 numerical output columns (2,880 cells) enter both batch and direct scalar
callback comparison at the unchanged 1e-8 tolerance. Runtime rc29 emitted stale
RMA values at 154 missing positions per mode. Semantics 36 preserves the state
and emits missing at those positions; all 45 columns then match. The same
expanded corpus has 308 repairs and no introductions, while all previous 184
mode results remain unchanged. Preview and local/state/replay continuation
tests traverse seed readiness and gaps; genuine installed rc29 /34 fixtures
are rejected before constructing a new-version session. No captured expected
outputs are supplied as runtime inputs. ATR and DMI retain their old composition
policy; intermediate rc30 /35 snapshots are also rejected using genuine fixtures.
The controlled composition check does not qualify native DMI missing behavior.
This bounded holdout does not establish
all recursive-TA parameter or workload behavior.

`sma_near_edge_isolated_case0` through `case3` (Round53) independently repeat
Round52's four supplied profiles in four separate Pine scripts. Each script
has exactly one unconditional SMA and one SUM call. The diagnostic
`scripts/sma_near_edge_isolation_diagnostic.py` verifies the candidate-only RNG
inputs, executed formulas, source/log hashes, raw JSON identity, periods and
independent missing flags. All 256 numerical outputs and 256 flags reproduce
the combined-script capture exactly at zero tolerance. Both uniform guard
counterexamples therefore survive this isolation. It does not qualify universal
context invariance or a replacement accumulator. The four recaptures are
diagnostic-only, remain in `unmeasuredNativeWorkloads`, and add no runtime
agreement cells or recipes. All previous 184 mode reports are unchanged.

`dispersion_single_observation.pine` was run in native TradingView through Chrome
on 2026-10-02. Eight input profiles cover ordinary/fractional values, periodic
holes, leading/all missing values, a flat source and 1e12 offsets. All 48 output
columns over 32 rows are measured in batch and callback execution: 3,072 numeric
cells, zero differences at unchanged 1e-8 absolute tolerance. Sample variance at
period 1 remains missing; population variance/stdev are exactly zero once ready,
and all BB bounds coincide with the latest present observation. Full log blocks,
executed-editor copy, screenshot and restoration proof are retained in round39.

The seven partially mapped callback recipes now expose all 33 remaining output
columns. The added 1,138 cells include 968 active agreements and 170 both missing,
with zero differences. Each recipe preserves its existing direct helper calls;
new Donchian composites use direct full-window highest/lowest readiness. Other
new outputs use public Python batch execution and retain full OHLCV in state.
Preview, local/replay/state continuation and explicit retention are tested.
These callbacks do not expand the 39 direct incremental TA APIs or qualify bounded
streaming cost. All 77 registered recipes /154 modes now map every captured
output; full API/parameter coverage and small-difference acceptance remain unproved.

`weighted_boundaries.pine` and `wma_gap_confirmation.pine` were run through
Chrome in TradingView Pine v6 on 2026-09-30. Their `.tradingview.txt` and JSON
files retain 32 rows each, raw native outputs, source/log hashes and provenance.
The second probe compares native WMA with unconditional `fixnan`/WMA formulas
to distinguish real-observation warmup from carrying input through later gaps.
`test_weighted_boundaries_external.py` covers both execution modes, prefixes,
preview isolation and local/replay/state restore. These captures do not change
the existing 58 capture-family totals. See
[acceptance](../../docs/development/weighted_boundaries_acceptance_zh.md).

`ta_chain.pine` was entered into a new Pine indicator using Chrome on 2026-09-07.
The source consumes a synthetic sequence indexed by `bar_index`, not chart prices.
`ta_chain.tradingview.txt` contains the 40 observed Pine Logs rows, including
warmup `NaN` and the first crossover. `ta_chain.tradingview.json` records provenance,
LF-normalized SHA-256 digests, column meanings, the index/time mapping and parsed
values. Tests verify both digests, raw-log/JSON consistency, row completeness,
input identity, timestamps and values for both execution modes.

Pine logged ten decimal places. Pyne plot transport serializes eight decimals;
comparison rounds the captured values to eight decimals before applying the
1e-9 absolute tolerance. Raw evidence is retained unchanged. This evidence is
separate from the pre-existing 58 request/strategy/TA capture cases, and is tested
by pytest, not included in their generated capture-family totals.

To recapture, run the checked-in Pine source in a fresh personal indicator,
select its Pine Logs stream, and collect indices 0 through 39. Preserve the raw
rows and update provenance/digests together. Do not derive external expected
values from Pyne output. Re-run this suite and the full package gate.

## Limits

This is an initial representative suite, not certification of arbitrary Pine
source or all indicators. It does not resolve the separate EMA/RSI/Supertrend/
VWMA and OCA questions in the historical bug audit. No market data service or
renderer is embedded; the provider is an immutable test double.

Replay v1 stores closed bars without their preceding preview visits. Its
`barstate.isnew` can differ from the original live session. The five replay
workloads deliberately do not branch on intrabar history; comparisons omit only
that metadata field. State-v2 has a separate event-sensitive test. Use state-v2
or local snapshots for committed state that depends on intrabar visitation.
Active preview state is excluded from all checkpoint formats.

## EMA / RSI boundary slice

Run `python -m pytest tests/test_ta_external_boundaries.py -q` for the second slice.
`ema_rsi.py` and its batch companion cover EMA initialization with leading/internal
missing values, MACD, flat/rising/falling RSI and RSI gaps. `smoothing.py` covers
RSI-to-EMA composition; its batch companion additionally covers TSI. Incremental
TSI is not added. Each corresponding `.pine`, `.tradingview.txt` and
`.tradingview.json` set preserves independent Pine v6 evidence, digests and parsed
values. Both captures have 18 complete synthetic bars. The raw outputs are never
regenerated from Pyne. The suite checks 27 cases including prefix independence,
preview isolation and local/replay/state restore during initialization and gaps.

The first suite's limitations above describe that earlier slice. EMA/MACD and RSI
questions are now addressed by this second slice; Supertrend, VWMA and OCA remain
separate work. Rebuild old EMA/RSI sessions from OHLCV after updating their semantics.

## Trend / volume / OCA slice

Run `python -m pytest tests/test_trend_volume_external.py tests/test_oca_external_timing.py -q`.
The third slice has 36 cases. `trend_volume.py` and its batch companion consume
the 18 OHLCV rows recorded alongside native Pine Supertrend/VWMA output. Explicit
custom-volume cases use independently captured Pine SMA ratios. Native Supertrend
starts at zero, so its behavior is retained; VWMA now has two independent windows
of non-missing products and weights.

`oca_timing.pine` submits 20 orders covering same-tick markets, pending siblings
before/after markets, a non-OCA reachable control, a marketable stop, and pending
cancel/reduce positive controls. The JSON command inventory is checked against
the Pine source and used to generate equivalent public-API Pyne scripts. Tests
compare settled quantities and lifecycle outcomes, not exact intrabar fill prices.
The first four chart rows are linked to the trend/volume capture; the chosen stop
prices cannot trigger on the submission bar but are crossed on the next bar.

All `.pine`, `.tradingview.txt` and `.tradingview.json` evidence remains checked in
with digests. Old Supertrend/VWMA/OCA questions are resolved for these exact cases;
there is no general claim covering every OCA order family or all Pine semantics.

## Rolling statistics slice

Run `python -m pytest tests/test_rolling_statistics_external.py -q` for 30 cases.
`rolling_statistics.py` and its batch companion cover SMA, biased/unbiased
variance, standard deviation, BB, leading/interior/all-missing inputs and period 1.
The `.pine`, `.tradingview.txt` and `.tradingview.json` files preserve all 18 native
capture rows. Fourteen output columns are parity-tested; `High Stdev` and
`High Variance` are explicitly reference-only. Native Pine reports cancellation
artifacts for those 1e9-offset inputs, while Pyne retains stable centered results.
No raw external value is rewritten or hidden by a widened tolerance.

Independent centered arithmetic checks the two reference-only columns. Additional
streams cover 9,000 updates at offsets 0/1e9/1e12 and periods 3/63, and the public
SMA ratios are tested against the preceding VWMA capture in both modes. Local,
replay and typed-state recovery preserve the new rolling observation states.
Rebuild affected old sessions when adopting this change.

## Oscillator boundaries

Run `python -m pytest tests/test_oscillator_boundaries_external.py -q` for 52 cases.
Four 32-row native captures cover CMO branch/sum behavior and Stochastic missing
inputs, zero ranges, and transitions; the Stochastic transition probe is repeated
in Pine v5 and v6. Raw captures, digests and parsed values remain independent.
CMO stays batch-only. Stochastic's first two dataset-origin bars remain an
explicit available-history startup difference, and correlation missing/flat
columns remain reference-only stable-Pearson differences. See
[acceptance and limits](../../docs/development/oscillator_boundaries_acceptance_zh.md).

## Extrema boundaries

Run `python -m pytest tests/test_extrema_boundaries_external.py -q` for 86 cases.
Two independent 32-row Pine v6 captures cover gap resets, earliest ties and
missing bars-back offsets, including period 1/5, flat and all-missing inputs.
A 24-row percentile control confirms normal-input nearest-rank/Hazen formulas;
missing percentile columns remain reference-only complete-window differences.
Extrema comparison starts after the initial lookback span, with Pyne's startup
differences explicitly tested. Both modes, preview isolation, local/replay/state
continuation and independent window arithmetic are covered. See
[acceptance and upgrade](../../docs/development/extrema_boundaries_acceptance_zh.md).

## Continuing official-alignment assessment

`conditions_pivot` (48 rows) and `pivot_isolated_confirmation` (32 rows) preserve
new Chrome/Pine Logs evidence of unresolved pivot tie/gap/startup and rising-gap
differences. Their batch scripts reproduce the inputs; they are diagnostic
comparisons. At initial capture their incremental mappings were unmeasured;
the subsequent correction and qualification are recorded below.
The independent strict/record rising formulas are controls, not Pyne output columns.
`pivot_formula_confirmation` adds 32 rows and six independent native/formula pairs.
All three pivot recipes now have batch/incremental mappings; pivot ties, gap stops
and complete-span warmup are corrected in semantics 8. The rising missing-input
columns remain unresolved and separately measured. Run
`python -m pytest tests/test_pivot_boundaries_external.py -q` for 112 native,
prefix, preview and recovery checks.

Run `python scripts/official_alignment_report.py --output .tmp/official-alignment.json`
for all registered columns, including startup and former reference-only values.
`--require-small-difference` currently fails because whole-scope acceptance is
unproved. See [baseline and remaining scope](../../docs/development/official_alignment_goal_zh.md).

## Direction conditions

`direction_missing` and `direction_transition_confirmation` each preserve 32 rows
of native rising/falling for six missing-input streams and periods 1/3/7. The first
keeps a rejected neutral-missing formula; the second uses a scoped queue of valid
adjacent comparisons and agrees with all 640 native control cells. These control
columns are disclosed separately from the runtime outputs.

The batch mappings now agree on all native direction columns. No scalar helper is
added to the incremental TA namespace. Ordinary Python callbacks can call the
public functions, so computation identity is 9 and real semantics-8 snapshots are
rejected. `tests/test_direction_boundaries_external.py` has 36 checks for native
prefixes, an independent randomized stream, preview isolation and all recovery
modes for a Python callback. Existing gaps in other domains remain in the Goal.

## Foundation and context

`foundation`, `cross_confirmation` and `context_foundation` add 96 native rows.
The first covers changes/momentum/ROC/cum/nz/shift and crossing gaps/equalities;
the second contains six independent cross/crossover/crossunder formula pairs
(576 native/formula comparisons). The third preserves actual dataset-origin
OHLCV, ADX, TR, OBV, volume SMA, anchored VWAP and Donchian/Keltner controls.

Cumulative sums and OBV now emit no value on missing current observations while
retaining their accumulator. Cross helpers retain the last jointly valid pair;
cross requires strict sign reversal, whereas directional crossing permits the
previous pair to be equal. Semantics 10 rejects real old semantics-9 artifacts.

ATR-width Keltner differs from native EMA-width KC, and Donchian startup differs
from a native dataset-origin window. Those columns remain in the full diagnostic
report; the focused suite explicitly qualifies its narrower comparison scope.
Run `python -m pytest tests/test_foundation_boundaries_external.py -q` for 82
prefix, independent-formula, preview and recovery checks. All 55 batch methods
now appear in capture recipes; that is not whole-scope acceptance.
## Percentile missing-order diagnostics (2026-09-30)

`percentile_missing_sort` and `percentile_insertion_matrix` retain 64 new native
rows. The latter measures 23 source/period combinations and five percentages;
its independent rolling-insertion formula is **rejected** by 188 of 3,680 native
linear-percentile cells. Formula columns are counterexample evidence, not Pyne
parity outputs. The diagnostic batch scripts map every native percentile output,
including missing-input failures, and `percentile_confirmation_batch.py` maps
the earlier 24-row probe. No scalar helper or computation semantics changed.

The same parameters reproduce across the three captures. Native `array.sort`
puts missing items last while native TA missing ranks need not do so. Neither
array sorting nor the rejected insertion formula is a valid general replacement
for the observed TA missing-input rule. Full finite windows are qualified only
within the captured combinations; missing windows remain explicitly unqualified.

## Keltner widths (2026-10-01)

`keltner_width_matrix` retains 32 native rows with fifteen source/period/multiplier
and range-mode cases. Its 1,440 native channel cells agree with independent EMA
formulas. Batch and ordinary Python replay map all 45 native output columns;
entirely missing columns stay in the diagnostic denominator. The two separate
`keltner_invalid_*.tradingview-error.json` records retain native rejection of zero
and negative multipliers. Default width now uses EMA of true range; explicit
`width_smoothing="atr"` retains the prior formula and its foundation controls.
Run `python -m pytest tests/test_keltner_boundaries_external.py -q` for 47 prefix,
preview, snapshot continuation and input-validation checks. No scalar incremental
TA helper is declared by this generic Python callback fixture.

## Percentile earlier-history control (2026-10-01)

`percentile_history_context` records 64 native rows and 120 output columns.
Four earlier histories become identical from index 16. At the same index and
parameters, 16 of 1,340 identical-complete-window groups have different native
outputs, proving a dependency outside the current window. This refutes a purely
stateless missing-sort rule without identifying the internal update algorithm.
Every native output is retained in diagnostics. Run
`python -m pytest tests/test_percentile_history_external.py -q` for raw identity,
controlled-history witnesses, finite-window controls and full measured coverage.

## Frozen-model percentile holdout (2026-10-01)

`percentile_state_holdout` preserves 96 native rows, five input columns and 168
output columns (16,128 cells). It tests periods 5/9/17 and percentages
0/12.5/33/50/67/87.5/100 across periodic gaps, ties, leading and consecutive gaps,
and entirely missing input. The order rule was frozen against four earlier
captures before this independent probe was collected. Its original source and
freeze metadata are retained in `tests/golden/percentile_state_model`; source
identity is checked against the native record. No holdout values select the rule.

All five percentile captures now match the corrected runtime (32,640 cells).
`test_percentile_boundaries_external.py` checks every output, input immutability,
prefix boundaries, the frozen model and generic Python callback preview/restore
continuation. The callback discloses all 168 titles, so a runtime that emits only
missing values is still included in diagnostics. This correction changes
computation semantics to 12; older diagnostic paragraphs describe preceding rounds.

## Strategy live-slot admission (2026-10-01)

`strategy_pyramiding_0/1/2/3` capture 32 native rows each, covering same-direction
caps, reversal, `strategy.order` bypass, full closure and partial closure of
repeated-ID lots. `strategy_pyramiding_orders_confirmation` independently tests
order-created lots consuming entry capacity and freeing capacity after closure.
Together they retain 3,040 native output cells; all 20/15 columns map to batch
and ordinary Python callbacks, including per-ID signed holdings. Actual captured
OHLCV supplies execution prices; no host service is required.

The old rc7 wheel has 245 differences across both modes. The correction uses
current open-lot count for entry admission and recalculates remaining weighted
average after batch closure. Internal golden profit expectations are corrected
from their existing lot quantities/prices, without modifying native evidence.
Run `python -m pytest tests/test_strategy_pyramiding_external.py -q` for raw
identity, complete mapping, prefix, preview/restore and independent ledger checks.
Computation semantics is 13; real rc7 semantics-12 snapshots are retained and rejected.

## OCA complete output timeline (2026-10-01 audit)

The existing `oca_timing` native capture now has standalone batch and callback
recipes mapping all 22 output columns across four rows. Actual captured `bars`
supply OHLCV and must have timestamps matching the raw logs. Count and quantity
comparison is exact; the old native metadata and hashes remain unchanged.

The callback matches all 88 cells and is checked at every prefix and after preview
and local/replay/state restore. The semantics-13 batch had ten differences at row
1: it displayed position 14 and open trade count 11 instead of native 30/19 until
row 2. Earlier settled-holdings checks did not measure this discrepancy.
Semantics 14 processes carried pending fills before recording calculation state
and submitting current-bar close-fill commands. Both modes now match all 88
cells, including the trigger row. Prefix controls also check that current close
or cancel commands cannot hide carried fills from the visible calculation state.
No exact intrabar fill-price qualification is added.

The batch recipe combines public scalar IDs with public size histories because
this particular capture only appends long lots, with no closes or slot reordering.
This mapping does not claim general historical string-ID series support.

## Previously omitted native captures and public sum (2026-10-01)

`wma_gap_confirmation`, `oscillator_formula` and `stoch_transitions_v5` now map
every output in batch and callback reports: 6/12/6 columns, 32 rows each, totaling
768 native cells or 1,536 mode comparisons. The v5 and v6 Stochastic probes use
the same controlled inputs; they provide version confirmation rather than
independent coverage of additional parameter combinations.

The formula probe directly measures `math.sum` alongside TA calls. The previous
runtime omitted results on gaps in the down-momentum sum, causing 52 differences
across the sum and CMO formula in the two modes. Computation semantics 15 sums
the last requested number of non-missing observations, carrying results across
gaps with the existing robust linear kernel. All captured sum/formula cells now
match. Available-history extrema and Stochastic startup still contribute 34
additional differences; they are retained in the report.

The callback for formula/WMA probes uses ordinary Python prefix computation;
it does not declare new scalar incremental APIs. The batch formula uses the
script-facing `math.sum` namespace. Native qualification is length 3 on this
capture; other lengths and missing patterns have independent Python arithmetic
tests, not new official evidence. No saved raw logs or official JSON values changed.
An empty unmeasured-capture list means all saved captures are registered, not
that the full supported surface has been independently qualified.

### Pending-entry pyramiding: native gaps measured, not fixed

Six `strategy_pending_pyramiding_*` captures contain 32 native COINBASE:BTCUSD
daily bars, six OHLCV input columns and nine complete output columns. Both
Python execution recipes expose all state and per-ID quantities. The probes
only append long lots, so batch scalar IDs identify stable slots without exits.
Pine source and raw log hashes are verified before measurement.

At semantics 15, stop/limit/stop-limit and staggered stop probes disagree with
native price-order admission or fill timing. Native holdings are A=1, B=2,
C=3 even with pyramiding=1. Existing-full and market-order controls match.
The six captures contribute 1,040 differences across 3,434 active cells in
the two modes; 22 both-missing cells are separate. Keep these gaps visible in
the report until a verified correction replaces this baseline. Evidence tests
validate raw provenance and complete measurement, not blanket runtime parity.

Semantics 16 registers three additional mixed/favorable stop captures. Eight of
the nine pending-entry cases now match every state/holding cell in batch and
callback modes, including prefixes, isolated previews and restored continuation.
The remaining stop-limit case contributes 31 average-price differences per mode:
activation before its limit phase remains unqualified. The nine-case family has
5,184 cells, 5,146 active and 38 both missing, with 62 differences. Risk-lock
scaffolds explicitly use pyramiding=2 where their purpose requires admitting the
seed and a pending entry. Existing official capture payloads remain unchanged.

Eight additional `strategy_pending_pyramiding_stop_limit_*` captures qualify
native observations of activation, delayed limits, never-activated controls,
gap activation and price paths before/after activation in both directions.
At semantics 16 these newly measured cases have 1,162 differences across 4,498
active cells; 110 both-missing cells are separate. The evidence tests validate
official timelines and complete measurement, and deliberately do not assert
runtime parity. Activation state and post-activation price paths remain to fix.

Semantics 17 replaces the semantics-16 stop-limit baseline with persistent
activation followed by limit matching on the remaining inferred price path.
All 17 pending-entry cases match every native state/holding column in both
modes, with no unmapped outputs. Eight stop-limit cases also verify 160 prefix
combinations and 24 local/replay/state continuation combinations with isolated
previews. Equal-distance extreme ordering remains a deterministic Pyne choice,
not qualified by these native probes. The complete 50-workload assessment still
contains 307 differences across 54,370 active cells; this selected measurement
does not establish full declared-scope compatibility. Native evidence and recipe
hashes are identical to the retained semantics-16 comparison.

Three additional semantics-17 pending lifecycle captures cover same-ID amendment
after activation, cancel then resubmit, and repeated identical submission. Native
amendment resets the stop condition; identical submissions yield one lot. Pyne
currently retains old same-ID pending entries, producing 322 new differences in
both modes, while explicit cancel/resubmit matches. Full assessment now measures
629 / 55,998 active cells across 56 workloads; the earlier 50-workload result is
historical. Evidence tests validate provenance and complete measurement without
claiming amendment parity. Runtime correction remains pending.

Semantics 18 supersedes an admitted same-ID pending price entry, restarting
activation and preserving the old submission as canceled in the ledger. All 20
pending-entry native captures now align in both modes. New lifecycle verification
includes 48 prefixes and 27 isolated-preview/snapshot continuations. Current
56-workload totals are 307 differences / 55,952 active cells, with 26,126
both-missing cells separate. Market/mixed-ID/direction/OCA amendment qualification
is outstanding; no full declared-scope acceptance is claimed.

Four further semantics-18 captures expose market/price same-ID replacement timing
and repeated `order` submissions. A pyramiding=2 control isolates same-calculation
replacement from the pyramiding=1 zero-fill result, reproduced in a second native
run. These probes contribute 818 additional differences. Current totals are
1,125 / 58,228 active cells across 64 workloads, with 26,154 both-missing cells.
A separate native direction-change error (RE10028 on bar 2) is hash-verified from
Pine, visible DOM and accessibility snapshot; both Pyne modes currently succeed.
`nativeRuntimeErrorChecks` records this gap outside numeric-cell denominators.
Error presence does not establish cause or atomicity. No post-error rows are
synthesized, and the semantic implementation remains at the preceding baseline.

The cancel-before-direction-change native control succeeds with one short A lot,
size -2 and price 398 from row 6. Both modes match all nine state/holding columns.
This control distinguishes forbidden same-ID direction mutation from an allowed
cancel/new submission. Current totals are 1,125 / 58,792 active cells across 66
workloads, with 26,166 both-missing cells. The lower rate comes solely from added
matching control cells; the two native error-presence gaps remain uncorrected.
Future rejection must preserve submission ledger/sequence, pending activation,
derived reports and resource accounting when a caller catches the error.

Semantics 19 implements pending-entry direction rejection before incremental
submission mutation and via isolated batch replay before commit. Both native
error witnesses now reject with the expected diagnostic marker. Eight caught
error/preview/restore checks preserve old ledger, sequence, activation, results
and resource accounting; cancel/new continuation matches native full columns.
All numeric workload results remain unchanged (1,125 / 58,792 active cells).
The market/order amendment gaps remain open; error parity is separate from
numeric differences and full declared-scope qualification.

Semantics 20 replaces same-kind same-ID pending price orders and restarts
activation. Moving an existing order out of an OCA cancel group withdraws the
old group. Five native order probes (repeat/update/reassign/same-group/new-ID)
match complete state/holding columns in both modes, including 90 prefixes and
45 preview/snapshot continuations. Old/new official and recipe hashes are equal.
The 74-workload matrix falls from 1,517 / 61,042 to 987 / 60,990 active cells;
26,272 both-missing cells remain separate. Reduce-group, mixed-ID, direction and
market amendment qualification remains incomplete; no full-scope acceptance.

Four full native market-update and stop-limit-to-market controls (pyramiding
1/2) retain only the last A market order, quantity 2, average 370. Native first
bar state after commands is flat. The separate after-command diagnostic exposes
16 state gaps across four witnesses, without inflating matrix denominators.
Semantics 21 orders replay by submission time, not prior derived fill time.
Inactive cancel calls cannot change full results or ledger. The fix removes an
accidental match and exposes 92 additional cells: 1,665 / 63,286 active cells
across 82 workloads; 26,280 both-missing cells remain separate. Market execution
phase gaps and full-scope qualification remain open.

Semantics 22 honors callback process_orders_on_close and stages market entry
commands until end of calculation, preserving after-command visible state.
Same-ID amendments replace pending commands; other market entries reserve
pyramiding slots. Market-to-price admission uses the old market reservation and
cancels it even if pyramiding rejects the price replacement. Repeated native
pyramiding 1/2 controls match all 32 prior rows and add no denominator cells.
Seven amendment cases pass 84 prefixes and 105 preview/restore continuations.
The corpus contains 66 recipes and 132 modes: 126 measured, 6 unmapped, and
9 measured modes partially mapped. Historical "82 workloads" wording was a
counting error, not an API coverage denominator. On identical oracle/recipe
hashes, differences fall from 1,665 / 63,286 to
307 / 63,208; 78 false nonempty cells become both missing (26,358 total).
Four after-command witnesses now have zero gaps. Default-mode callbacks and
market order/close/exit/reversal/risk combinations still need qualification.

The assessor now observes successful callback plot calls, including dynamic
all-missing outputs that retain no curve. Static plot mentions are not execution
evidence. Scoped observation leaves results unchanged and restores the plot
method on exceptions. Four existing columns (18 rows each) add 72 both-missing
cells, with zero additional active cells. The corpus still has 66 recipes/132
modes, 126 measured/6 unmapped; partially mapped modes fall from 9 to 7.
Counts are 89,638 total/26,430 both missing/63,208 active/307 differences.
Remaining unmapped recipes and outputs disclose static batch dependency leads
against declared direct incremental TA methods; this is not API qualification.
Runtime rc17, semantics 22, oracle/recipe hashes and old measured cells remain
unchanged. Source and installed-wheel observation assessments agree.

The array_missing_sort native workload contains eight fixed numeric array cases,
two cycles /16 rows /35 columns. Case and original-input columns are controls;
29 output columns per mode add 928 cells. Ascending missing values sort last,
descending first; descending indices reverse ascending, including ties.
The identical oracle/recipe baseline has 384 array gaps; semantics 23 removes
all of them. Existing non-array assessments are unchanged. Totals are 90,566
cells /63,872 active /26,694 both missing /307 differences (0.481%).
67 recipes /134 modes: 128 measured, 6 unmapped, 7 measured modes partial.
Repeated cycles do not count as 16 distinct cases. Numeric array controls do
not establish string collation, full collection API or parameter qualification.

The matrix_missing_reshape native probe has eight fixed numeric 2x2 cases in
two cycles /16 rows /62 columns. Ten original-input controls are excluded;
52 outputs per mode add 1,664 cells. Pyne add/sub map to Pine two-operand
sum/diff. Aggregate sum and the reshape return value are Python extensions.
Native missing arithmetic, reshape mutation/aliases, transpose and scalar
copy witnesses remove 420 gaps; prior non-matrix assessments remain identical.
Totals: 92,230 cells /65,176 active /27,054 both missing /307 differences
(0.471%); 68 recipes /136 modes, 130 measured /6 unmapped /7 partial.
Repeated cycles are eight distinct cases. Broader matrix shapes, types, empty
dimensions, object references and full collection APIs remain unqualified.

The array_slice_reference native probe has 16 valid fixed scalar mutation cases
in two cycles /32 rows /31 columns. Only Case is a control; 30 output columns
per mode add 1,920 cells. Logs are assembled from beginning/end visible DOM
states with duplicate log entries removed. Connected parent/nested windows,
copy detachment, structural edits, sorting and parent truncation/regrowth remove
348 differences on identical final oracle/recipe hashes. Formatting changes
preserve AST; the genuine old wheel recheck preserves original baseline columns.
Totals: 94,150 cells /66,332 active /27,818 both missing /307 differences (0.463%).
69 recipes /138 modes: 132 measured /6 unmapped /7 partial. Repeated cycles are
16 distinct cases. Bounds, reference types, maps and full collection APIs remain
unqualified; runtime budget/restore controls do not enlarge the native denominator.

The map_scalar_mutation native probe has 16 fixed int-key /float or missing-value
cases in two cycles /32 rows /40 columns. Only Case is a control. Insertion order,
overwrite/remove/reinsert, missing keys, detached scalar copies/extractions,
put_all overlap/self merge and clearing add 2,496 comparison cells: 1,524 active
agreements /972 both missing. Old and new source/installed reports are identical.
The existing 307 differences remain; 0.452% over 67,856 active cells reflects
expanded coverage, not a numeric repair. 70 recipes /140 modes: 134 measured,
6 unmapped /7 partial. Atomic merge rejection tests cover independent runtime
contracts and do not count as native evidence. Other keys, reference types,
native errors and full APIs/parameters remain unqualified.

The array_search_fill_join probe retains 32 rows /28 numeric columns and four
exact-text columns. Sixteen float profiles, eight string profiles and two Boolean
construction profiles repeat; only Case is a numeric control. It adds 1,728
numeric and 256 separate text cells across both modes. Missing search and Boolean
defaults remove 112 numeric gaps; default separators, missing conversion and
numeric text remove 132 exact-string gaps. Old/new source/installed reports use
identical oracle and recipe hashes. Sixteen numeric transport gaps remain at
indexes13/29 in First /Filled first /Filled0 /Parent0: official0.123456789 vs
Pyne0.12345679, retained in the strict1e-10 assessment. Existing307 unchanged;
current323 /69,372 active cells (0.466%) /29,002 both missing /98,374 numeric cells.
71 recipes /142 modes:136 measured /6 unmapped /7 partial. Exact text is0 /256,
never added to numeric denominators. Broader types, ranges, formats and propagation
through other collection types remain unqualified.


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

The `matrix_rectangular_products` probe retains 24 native rows /37 columns, with
only Case as a control. Twelve profiles include six finite shapes and six
missing/zero operand arrangements. Product and reverse transpose product cells,
input detachment after result writes, and copied/aliased reshape values add
1,728 numeric cells /1,052 active /676 both missing, with zero differences.
Totals are 323 /71,788 active (0.450%), 101,510 numeric cells /29,722 both missing;
74 recipes /148 modes, 142 measured /6 unmapped /7 partial. Lower rate reflects
expanded samples; all prior differences are retained. Three separately hashed
native dimension-error witnesses live in `tests/golden/matrix_dimension_rejections`;
their six execution-mode comparisons do not enter numeric denominators. Native
post-error atomicity and complete matrix/API/parameter coverage remain unproved.

The six direction/percentile probes formerly missing callback recipes now have
complete generic Python callbacks using `TaModule` and retained history. The
recipes declare `generic_python_full_history_recompute`; the report records this
route and static leads without granting a direct incremental API or bounded-cost
qualification. All registered modes are measured: 74 recipes /148 modes, zero
absent /seven partial. Added 17,792 cells comprise 11,725 active agreements and
6,067 both missing. Totals are 323 /83,513 active (0.387%), 119,302 numeric cells
/35,789 both missing. Existing differences remain unchanged; default budgets stay
unlimited. Callback prefix, preview, state/history, local/replay/state restoration
and explicit display/replay retention tests are independent runtime controls.
The same native scripts/logs are reused and verified; no new capture is claimed.

The correlation correction adds `correlation_missing_diagnostic` (ten fixed
profiles) and a fresh Chrome `correlation_window_holdout` (32 profiles). Each has
32 rows, independently derived Python inputs, batch and generic full-history
callback recipes, hash-verified Pine source and visible native logs. Input and
plain-formula controls are excluded from numeric output denominators; all native
correlation columns remain measured at absolute tolerance 1e-8. The diagnostic
has zero differences across 640 cells; the holdout retains 342 differences
across 2,048 cells, including ten modest shifted roundoff gaps and large-offset
native arithmetic discrepancies. No output column is dropped to claim parity.
The two correlation outputs in `oscillator_flat` also have callback mappings;
the two CMO outputs remain unmapped. Coverage is now 76 recipes /152 measured
modes /zero absent /seven partial /33 unmeasured output columns. Prefix, preview,
retention and genuine semantics-29 rejection controls are separate runtime
evidence; the fixed profiles do not qualify general numerical behavior or
bounded streaming cost. Goal stays active.
# Window readiness holdout (2026-10-02)

`window_readiness_holdout` retains a fresh TradingView Pine v6 source and raw
Pine Logs collected through the authenticated Codex in-app browser. It evaluates
highest/lowest, their offsets and Stoch unconditionally from dataset bar zero,
over lengths 1/2/3/5/11 and base/ties, holes, leading-missing, flat and all-missing
profiles. All 125 outputs and 64 timestamps are compared in both modes, including
initial missing masks: 16,000 cells at absolute tolerance 1e-8. Input columns are
independently generated and excluded from numeric output agreement. This finite
holdout does not establish full-scope compatibility or resolve imported sparse
records whose original history is unavailable.

# Correlation arithmetic diagnosis (2026-10-02)

`correlation_arithmetic_decomposition` retains 64 rows and 206 columns from
TradingView's native Pine v6 runtime in the authenticated in-app browser.
Only eight Native correlation columns have batch/callback Pyne recipes; six
inputs and 192 formula/moment controls are excluded from numeric agreement.
Python inputs are independently generated without reading expected results.
The callback explicitly recomputes full retained history; it does not grant a
direct incremental correlation API or a bounded streaming-cost claim.
The 1,024 paired cells retain 634 disagreements at the original absolute 1e-8
tolerance. All previous native workload results are unchanged.

`correlation_reduction_order` retains 64 rows /57 columns of native primitive
products, SMA and independent Pine newest/oldest/Kahan/Neumaier/paired folds.
It is a native-to-native diagnostic with no Pyne recipe and remains visible in
`unmeasuredNativeWorkloads`. Its formula matches do not count as Pyne agreement.
`scripts/correlation_arithmetic_diagnostic.py` verifies raw logs/source hashes,
reproduces guarded-formula agreement across 512 native correlation results and
preserves rejected formulas and period-3/7 reduction counterexamples. Primitive
products and operand recomposition agree exactly in binary64; this does not
establish the native rolling-reduction implementation. Kernel and semantics
remain unchanged. Finite formula explanations do not establish whole-scope
compatibility, and the Goal remains active.

`sma_history_arithmetic` retains 96 rows /48 columns from the authenticated
in-app browser: six independently generated inputs, 30 native SMA outputs
(periods 1/2/3/7/11), and twelve independent Pine accumulation controls. Only
the 30 SMA outputs enter batch/direct-incremental comparison. The callback uses
the declared `ctx.ta.sma(...).update(...)` interface. Large prefixes, opposite
signs and gaps expose persistent native rounding residues after the prefixes
leave the window. Period two also retains a residue when the tail has gaps.
Every disagreement stays in the unchanged absolute 1e-8 comparison.

Semantics 34 fixes two separate runtime invariants: per-output batch fallback
cannot inspect future values, and incremental means preserve exact finite sums
independently of centered variance. Independent exact-arithmetic, prefix,
preview, retention and restore controls do not count as native agreement.
The expanded matrix keeps 3,239 differences /109,378 active cells (151,096 total;
41,718 both missing). Against the actual rc28 wheel, 152 locations are repaired,
114 introduced, and 3,125 retained. Previously registered native difference
locations are unchanged. Genuine rc28 states and the failed first rc29 Windows
timezone installation remain retained; neither finite controls nor corrected
package dependencies qualify complete native compatibility.

`legacy_masked_history_context` and its independent Pine v5 repeat retain
40 rows /52 columns each: 30 supplied input controls, 16 native extrema/Stoch
outputs and six original exporter WPR-helper controls. Inputs reproduce five
preserved legacy windows from dataset origin and after 16 missing source bars.
The 2,560 paired native cells align; generic callback replay does not qualify
bounded direct incremental APIs. Helper controls remain excluded from native
built-in fidelity.

`scripts/legacy_capture_context_diagnostic.py` verifies source/log identities,
1,200 input cells per Pine version, unchanged original fixtures and all 32 exact
startup witnesses. The original five fixture files are retained under
`tests/golden/legacy_capture_context_baseline`. Context annotations disclose
those exact original values and Pyne missing outputs; raw imported counts remain
33/1,353. Missing prices are not fabricated, and original export provenance is
not upgraded to complete. Both helper-origin zero differences and the separate
Pivot discrepancy stay visible. Runtime and computation identity remain unchanged.

`sma_period_two_independent_holdout` promotes the separate Round44 native
arithmetic holdout into canonical runtime comparison. Its original 96 rows,
72 columns, Pine source and raw logs are retained unchanged: twelve supplied
inputs, 24 native SMA(2/3) outputs and 36 Pine candidate/pair controls. All 48
input/formula controls stay outside output agreement. Independently generated
Python inputs match all 1,152 native input cells; recipes never read native
expected values or formula controls. The callback uses direct
`ctx.ta.sma(...).update(...)` helpers. All native masks and timestamps enter the
original absolute 1e-8 comparison, including all-missing plots observed at
execution. Batch retains 994 differences and direct incremental retains 966.

The expanded corpus measures 84 recipes /168 modes, 158,264 total cells,
115,230 active and 43,034 both missing. Differences are 5,199 (4.512% of active
cells). All original 166 complete mode reports are unchanged: the additional
1,960 differences expose previously unmeasured arithmetic gaps, not a kernel
change. Neither candidate/formula matches nor native-to-native identities
increase runtime agreement.

`scripts/sma_arithmetic_diagnostic.py` reproduces all 3,456 separately executed
Pine candidate/pair control cells exactly. A compensated remove-before-add
model matches 768 older period-two cells but fails 458 independent period-two
and 489 period-three cells; direct pair mean fails 438. Forty native mean/sum
pairs agree exactly across 2,560 cells. The latter identity narrows further
investigation to sum arithmetic; it does not establish the implementation.
The diagnostic rejects corrupted source/log/row evidence or Python/Pine
candidate disagreement. Runtime semantics stay 34 and the Goal remains active.

`sma_history_sources` is a new native-to-native diagnostic collected through the
authenticated in-app browser: 40 rows /48 columns over power, prefill, missing-tail
and regime profiles repeated from the independent holdout. Current input, two
Pine history indices and two independent array entries match 800 independently
generated cells exactly. Calendar-pair arithmetic matches 320 cells; repeated
native SMA matches 320 earlier captured outputs, native sum/mean matches 320
cells, and dyadic input scaling matches 160. These fixed identities constrain
arithmetic investigation without proving a rolling accumulator or injecting any
native result into runtime computation. The public SMA diagnostic verifies them
and rejects independently rehashed input/history tampering. This capture has no
Pyne recipe and stays visible in `unmeasuredNativeWorkloads`; its matches add no
runtime agreement or statistical independence. Runtime counts remain those of
Round45, with 5,199 differences /115,230 active cells. Goal remains active.

`sma_finite_overflow` retains 24 rows /32 columns from the authenticated in-app
browser. Four independently generated finite binary64 profiles cover positive,
negative, alternating signs and a six-large-value prefix followed by small
fractional values. All 12 native SMA(1/2/3) outputs enter batch and direct helper
comparison; four input, eight native sum and eight independently scaled-mean
control columns stay excluded. Each mode has 288 cells and 135 missing
differences at unchanged absolute tolerance 1e-8. The expanded corpus measures
85 recipes /170 modes, 158,840 total cells /115,782 active /43,058 both missing
and 5,469 differences (4.724%). Every original 168 complete mode report remains
unchanged. These extreme samples do not establish ordinary-price impact or
general overflow recovery.

`sma_overflow_state_guard` separately repeats the same input formulas and native
calls over 24 rows /64 columns. Native `na()`, nonzero halving invariance and
sign flags verify that missing texts represent native missing states in the
observed profiles. The public `scripts/sma_overflow_diagnostic.py` verifies all
192 input cells, 1,440 state cells and 192 Python/Pine scaled-mean controls.
Mathematically finite means do not replace official expected missing values:
135 full windows remain native missing, including 33 fully small tail windows.
Consistently rehashed mask/input/native/helper tampering is rejected. Guard
controls remain diagnostic-only, visible as unmeasured and excluded from runtime
agreement. A 24-row persistence witness does not qualify a permanent poison rule.

Assessment schema 2 preserves any Pyne nonfinite outputs as explicit
`nonfiniteNumber` objects, separately from native missing `null`; exported JSON
contains no nonstandard `Infinity` or `NaN` constants. Counts and old mode results
are unchanged. The report format change does not alter package/snapshot/wire or
computation semantics, which remains 34. Goal stays active.

`sma_overflow_update_order` retains 32 rows /42 columns from an authenticated
in-app-browser execution. Six independently supplied profiles cover half-sized
extreme finite values, mirrored rotating signs, small-value recovery, and a
missing interval before recovery. All 12 native SMA and 12 `math.sum` outputs
enter both modes at the original absolute tolerance 1e-8; 18 input/na controls
are excluded. Callback SMA uses direct helpers, while sums recompute independent
Python history with `utils.sum_`. Its explicit execution-route declaration
does not qualify a bounded direct incremental sum API. Each mode retains
654 missing differences /768 total cells /732 active /36 both missing.

`sma_overflow_order_guard` independently repeats the native calls and records
48 state columns over 32 rows. The public `scripts/sma_update_order_diagnostic.py`
verifies 192 independently generated input cells and 1,536 separate state cells,
including the `na()` masks behind sum log texts. Four independently initialized
arithmetic witnesses reject simple add-before-remove, but do not qualify a
remove-before-add replacement. The native SMA/sum bridge now has 62 missing-mask
counterexamples /384 paired cells; the old 2,560 selected finite-data matches
remain valid within their recorded scope. Neither bridge nor candidate matches
increase runtime agreement. Thirty-two rows and 86 fully small recovery windows
still missing do not qualify permanent poisoning or general recovery behavior.
The guard remains explicitly unmeasured in the canonical report.

The expanded corpus is 86 recipes /172 modes, 160,376 total cells /117,246 active
/43,130 both missing and 6,777 differences (5.780%). Runtime and computation
semantics remain rc29 /34. Overall official alignment is unproved; Goal stays active.

`sum_constant_isolated`, `sum_series_isolated` and `sum_branch_isolated` each
retain 32 rows /six columns from a separate single-SMA/single-SUM execution.
All 96 supplied numeric inputs and 288 native state controls verify independently.
The constant expression gives 31 missing SUM outputs after readiness, while
the arithmetic and branch series expressions give 31 finite sums with identical
logged input values. All two native outputs per script enter both modes; four
input/state controls are excluded. Constant-expression differences remain counted
(31 per mode); the two series captures have zero differences within their fixed
scope. This is a source-expression boundary, not evidence to emulate Pine's
compiler inside the standalone Python package. Const/series labels follow
[official type rules](https://www.tradingview.com/pine-script-docs/language/type-system/);
the internal compiler mechanism behind the observed output difference is unproved.

`sma_long_overflow_recovery_extended` retains 86 selected observations /ten
columns. Every native SMA(2/3) and SUM(2/3) call executes on every minute-chart
bar. The coverage log records confirmed index 26,793 and all 86 selected points.
Selections include 4,096, 5,000, 8,192, 10,000, 16,384 and 25,000 boundaries;
the last sampled index is 25,001. Four native outputs are missing at every
sample, with directly logged `na()` flags. Batch supplies all 25,002 independent
formula inputs and selects the 86 outputs; callback independently recomputes
the entire supplied prefix at each selection. Its generic Python execution route
does not qualify a bounded direct incremental API. Each mode retains 338 missing
differences /344 total cells /338 active /six both missing.

The public `scripts/sma_sum_source_context_diagnostic.py` verifies expression
context, input identities, states, sample-index mapping, the unobserved input
formula and execution coverage. It also discloses standalone direct SMA helper
gaps at 85 and 84 sampled points, without adding duplicate runtime agreement.
Consistently rehashed input, state, sample selection, coverage and input-formula
tampering is rejected. Only 344 native long-history output cells are logged;
neither every intervening output nor permanent poisoning is established.

The expanded corpus measures 90 recipes /180 modes, 161,448 cells /118,294 active
/43,154 both missing and 7,515 differences (6.353%). All original 172 mode reports
are unchanged. Input context checks and native-to-native comparisons add no
runtime agreement. Runtime and semantics stay rc29 /34; Goal remains active.


`sma_overflow_mask_holdout` (Round50) preserves the executed Pine source, raw
visible Pine Logs and hash-verified 32-row JSON for nine finite/gapped profiles.
All 288 source inputs are independently generated. Its 72 outputs are `na()`
flags (2,304 cells), **not numeric output values**; no Pyne recipe is registered
and it remains visible in `unmeasuredNativeWorkloads`. The diagnostic
`scripts/sma_overflow_mask_diagnostic.py` reports six input-only candidate masks,
explicit-series source context, native SMA/SUM mask counterexamples and the
separate Kahan numerical holdout. Candidate nonfinite-to-missing mapping is an
explicit hypothesis; actual Pyne infinity is never relabeled as missing.
Mask agreement adds no cells to runtime numeric agreement or overall acceptance.


`sma_overflow_discriminator` (Round51) executes the candidate-only selection
seed 2026100351, trial 2, with 32 independently supplied finite inputs. Native
SMA7 and SUM7 yield 64 numerical cells; 64 same-capture `na()` flags corroborate
their states. At index 16, both native results are finite while sticky oldest-first
window recomputation predicts missing. The falsification does not qualify another
kernel. Both native columns enter both modes; the three input/state columns are
excluded. Callback SUM recomputes full supplied history. The diagnostic script
`scripts/sma_overflow_discriminator_diagnostic.py` adds no extra parity cells.
The matrix is now 91 recipes /182 modes and 7,575 /118,398 active differences
(6.398%); previous 180 mode reports remain unchanged. Overall Goal stays active.


`sma_near_edge_discriminator` (Round52) executes four independent ULP-boundary
inputs at periods 7/7/3/3, preselected with seed 2026100352, trials 9/24/68/444.
The executed Pine source, visible logs and 32×20 JSON preserve 128 independently
reconstructed inputs, 256 native numerical outputs and 256 `na()` flags. Eight
numerical columns enter each execution mode; twelve input/state columns do not.
The diagnostic `scripts/sma_near_edge_diagnostic.py` falsifies uniform remove/add
and Kahan overflow guards in both directions. Its controls do not add parity
cells, and selecting a rule by period after observation does not qualify it.
Canonical totals are 92 recipes /184 modes, 162,088 cells /118,846 active,
43,242 both missing and 7,858 differences (6.612%). New coverage adds 283 gaps;
all original 182 mode reports remain unchanged. Callback SUM recomputes full
supplied history. No core arithmetic, wheel or semantics change is qualified.

`variance_source_operations` (Round57) retains an actual official UI-downloaded
64-row, 84-column CSV, executed Pine source and raw logs. All 256 source inputs
are independently reconstructed and equal the previously frozen variance
holdout. Native multiplication, power, sum/period and square-mean identities
are exact for these profiles; 3,072 previous native outputs recapture exactly
and 2,048 new cells only discriminate source operations. This workload has no
runtime recipe, is diagnostic-only and remains in `unmeasuredNativeWorkloads`.
`scripts/variance_source_operations_diagnostic.py` pins both source and CSV
identity, validates the full monthly selection and retains all counterexamples
for eight normalization orders. Native sums enter only those diagnostics,
never runtime input. The best order still has 38 /1,536 differences. No added
parity cells or universal source-context/private-implementation claim follows.

`sum_history_prefix_holdout` (Round58) independently freezes three different
prefixes followed by the same 30-value tail before official observation. The
complete 32×15 UI download preserves 96 inputs and 384 native SUM/SMA outputs,
with periods 2/3 and explicit missing gaps. All 228 equal-current-window paired
cells have different native outputs. This diagnoses retained state and does not
provide a runtime recipe or additional parity cells. The verified diagnostic
`scripts/sum_history_prefix_diagnostic.py` defines six binary64 addition trees
explicitly rather than relying on version-dependent Python `sum()`. A Kahan
remove-before-add hypothesis matches this selected holdout but still has 146
exact square-sum counterexamples in the previous capture. No production
replacement or universal source-context invariance is qualified.
