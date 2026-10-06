# Current Project Status

This document is the current source of truth for Pyne Runtime's implemented
capabilities and product boundaries. Roadmaps describe future intent; this page
describes what the repository can support and substantiate now.

**Pyne Runtime 0.4.0 is published and its public assets are verified.**
Tag `v0.4.0` points to `b1f55c8817a05509ca8a06ea8fbc809f86239fda`.
The release is neither a draft nor a prerelease.

Version 0.4.0 defaults to full Python in the caller process with no imposed
execution deadline or computation quotas. Hosts select restricted imports,
process isolation, and resource budgets explicitly. It includes installed
script templates, CSV column/time-unit mapping and selected-series export,
a shared historical/realtime callback workflow, and actionable validation and
execution diagnostics. Computation semantics is **5**; incompatible older
snapshots require rebuilding from authoritative OHLCV.

The 0.4.0 release Windows gate passed 1,236 tests, performance/stability checks,
58 capture fixtures with zero differences, distribution checks, and installed
wheel acceptance with nine workflows and 55,075 comparison points. PR and main CI each passed all 19 checks; the release workflow passed all
11 jobs, including nine installed-wheel combinations. Public wheel and source
archive hashes match SHA256SUMS. Details are tracked in the
[0.4.0 release record](../development/release_0.4.0_zh.md).

Pyne is a standalone Pine-inspired Python runtime with host-neutral extension
contracts. Its supported surface is bounded by the documented API matrix;
market data, chart rendering, and operational isolation belong to the caller.

### Unreleased development changes

The current milestone is **0.4.1 release closeout / computation semantics 42**.
Functionality is frozen at the qualified rc38 implementation; only release
metadata, migration guidance and delivery evidence change during closeout.
See the [current release milestone](../development/release_0.4.1_zh.md) for
acceptance and stopping conditions. Historical plans do not extend its scope.

The current continuation candidate is **rc38 / computation semantics 42**.
Historical strategy replay now has explicit scheduling, fill, risk, state and
output phases. Its coordinator is 33 lines; scheduling, fills and risk work
through explicit bindings instead of the strategy owner's private fields.
Exact ALMA convolution uses narrow exponent
bands when their combined guarded width and per-pair work estimate is smaller than one dense product,
retaining one final rounding and causal prefixes. Authentic rc37 /42 state and
replay artifacts continue without relabeling. The
[replay and ALMA repair record](../development/replay_alma_repair_zh.md) tracks
this continuation's performance and qualification receipts under
`.tmp/audit-replay-alma-20261004/`; previous counts below belong to rc37.

The rc38 candidate passes **5,475 distinct tests**, including **108 additions**
over rc37, in three disjoint 1,825-test shards with unchanged source hashes.
Its independently installed wheel passes **538 checks**; all 105 package Python
files match the qualified source byte for byte. Nine offline workflows and
55,075 comparison points, 14 performance checks at nine repeats, and stability
with 16 sessions of 256 bars pass. Independent review matches 346 strategy
records and 64 bidirectional state/replay restore-preview-continuation checks
against rc37. Extreme 40k-bar ALMA convolution-core samples improve 9.54–23.37 times, while their
worker peak working set increases about 10–12 MiB; ordinary samples remain
near baseline. This is local Windows candidate qualification; it does not
establish general TradingView compatibility or live-trading qualification.
The rc38 qualification receipts predate local delivery; Git history records
subsequent commits. This candidate has not been pushed or published.

The preceding weighted/state audit repair candidate is **rc37 / computation semantics 42**.
It makes WMA, linreg and ALMA causal under appended future inputs, removes
incremental WMA/VWMA cancellation drift, isolates mutable scalar subclass
parameters, and restores supported custom parameter graphs without invoking
user equality. Empty-result queries retain the selected tracing context.
Configured no-trade strategy equity reflects the initial capital; strategy
numeric admission and configuration updates are validated before mutation.
Input floats require finite values. Local POSIX deadlines survive caught caller
alarm exceptions. Unlimited varip creation and linefill dependency deletion
avoid quadratic full-state scans, while missing percentile inputs affect only
their actual suffix. Plot line operations and shared strategy configuration
contracts have focused modules; the strategy replay function still carries
structural debt. Genuine rc36 /41 state and replay artifacts are retained in
`tests/golden/audit_semantics_v41`; rebuild incompatible state from supplied OHLCV.
The [weighted and state repair record](../development/weighted_state_audit_repair_zh.md)
records validation and the cost of exact ALMA for extreme dynamic ranges.

The rc37 candidate passes **5,367 distinct tests**, including **401 new
regressions**, in three disjoint 1,789-test shards. Source hashes remain unchanged
throughout the complete run. Its independently installed wheel passes 407 checks
(the 401 additions plus six existing timeout checks), nine standalone workflows
and 55,075 comparison points. All 99 package Python files match the qualified
source byte for byte. Fourteen performance checks at nine repeats, stability,
capture checks, real POSIX alarm composition, build and distribution validation
pass. The same frozen rc36 baseline and current native matrix retain identical
difference records; this does not establish general TradingView compatibility.
Receipts are under `.tmp/audit-fix-20261004/`. This is local Windows candidate
qualification, with the timer helper additionally checked under WSL; rc37 had
not been committed, pushed or published at qualification time.

The preceding remaining-issue repair candidate is **rc36 / computation semantics 41**.
It preserves shared/deep collection graphs in snapshots, checks real owned
resources and historical time axes before restore, isolates incoming bar graphs
and replay inputs, rejects recursive same-key session creation, and avoids
quadratic bulk cache eviction. Request arrays use explicit collection budgets,
deferred expressions preserve floating-error policy and custom metadata callbacks,
and process execution reports transport errors and closes its resources. Nested
local POSIX deadlines retain the caller's alarm and elapsed remaining budget.
Real rc35 /40 checkpoints are retained in `tests/golden/audit_semantics_v40`.
The [remaining issue repair record](../development/remaining_audit_repair_zh.md)
tracks this candidate and its independent qualification; previous counts below
belong to their stated candidates.

The rc36 candidate covers **4,966 distinct tests**, including **191 new regressions**.
Its initial disjoint run passed 4,965; one prior copy-failure fixture supplied a
malformed equity entry, now rejected by earlier shape admission. The corrected
fixture uses a valid real-number entry with an explicitly failing copy. All 131
related tests pass on rerun, with no runtime source changes or test warnings.
The independently installed wheel passes the 191 new regressions, the 131 related
checks (overlapping coverage counted separately), and nine standalone workflows
with 55,075 comparison points. All 93 package Python files match the qualified
source byte for byte. Performance, stability, capture parity, build and distribution
checks pass. The original failure log and current coverage accounting are retained
under `.tmp/audit-remaining-20261004/`. This records local qualification of the
preceding candidate; the rc37 qualification above uses rc36's clean commit as its
baseline.

The preceding structural repair candidate is **rc35 / computation semantics 40**.
It addresses requested-row loss and invalid cache admission, malformed local
restore atomicity, repeated initialization, stale session releases, late input
and matrix budgets, shared collection graph traversal, and incremental request
and Pivot costs. Actual rc34 /39 state and replay fixtures are retained under
`tests/golden/audit_semantics_v39`; incompatible sessions require rebuilding from
authoritative supplied OHLCV. Current validation is recorded separately under
`.tmp/audit-structural-repair-20261004/`.
See the [structural repair record](../development/structural_audit_repair_zh.md)
for triggers, work-count comparisons and remaining execution boundaries.

The preceding rc35 candidate covers **4,775 distinct tests**, including 186 new
regressions. Its full initial run passed 4,774; one obsolete assertion expected
resource admission on a second `seed`. That test now checks first-seed rejection,
unchanged typed state and successful subsequent initialization. All 76 related
tests pass on rerun, with no runtime source changes and no duplicate coverage
counts. There are no test warnings. The independent installed wheel passes the
186 new regressions and nine standalone workflows with 55,075 comparison points;
all 88 package Python files match the qualified source byte for byte. Performance,
stability, capture parity, build and distribution checks also pass. This is local
candidate qualification; rc35 has not been published.

The preceding audit candidate was **rc34 / computation semantics 39**. Rolling
variance, stdev and correlation preserve previously computed prefixes when
future data is appended; batch and incremental MFI agree on missing-volume
windows. Live request ranges are refreshed where bars may still arrive.
Confirmed output points are detached from caller-visible results, and preview
and local recovery rebind context-held script functions to the isolated graph.
Explicit budgets also apply to batch table cells, array construction, fixed
historical input and seed replay recording. Failed historical restores remain
atomic; nonfinite process grace values are rejected. Preview and retention
history work and batch table updates avoid the audited full-history scans.
Standard deviation and Bollinger dispersion now remain representable when
binary64 variance itself underflows or overflows. Ordinary finite variance
behavior is retained. Providers can opt into the generic
[history finality contract](../api/request_history_finality.md) to certify
complete, immutable sparse history; unpromised or revoked history still refreshes.
Object-graph isolation and rolling-moment kernels are separated from session
and public TA orchestration, preserving import and typed snapshot identities.
The standalone unlimited defaults and host ownership boundary remain unchanged.
Real rc32 /37 and rc33 /38 state and replay checkpoints are retained under
`tests/golden/audit_semantics_v37` and `tests/golden/audit_semantics_v38`
and must be rejected before construction;
rebuild from authoritative caller-supplied OHLCV. The native-alignment rounds
below are historical evidence for their stated candidates; their difference
counts do not qualify the audit repair candidate.

The prior frozen rc33 source passed **4,505 tests** in three exhaustive,
nonoverlapping groups (1,475 /1,705 /1,325). One architecture warning retains
the large `incremental/session.py` and `ta.py` modules as technical debt.
Compileall, Ruff, project status, diff checks, performance growth, incremental
stability, distribution checks and independent installed-wheel acceptance pass;
the installation checks cover nine workflows and 55,075 comparison points.
Selected Strategy and Request capture checks have zero differences. The TA
capture check retains 144 disclosed differences and zero unexpected differences.
Receipts are under `.tmp/audit-repair-20261003/`. These are the previous
candidate's checks; rc34 validation receipts are retained separately
under `.tmp/audit-continuation-20261004/`.

The preceding rc34 validation covers **4,589 distinct tests** across three
nonoverlapping groups (1,503 /1,733 /1,353). The initial run passed 4,587 with
two documentation registration failures; both missing entries were corrected
and all 12 documentation/index/status checks passed afterward. There are no
architecture warnings: session orchestration is 1,466 lines and public TA
orchestration 1,401, with their independent helpers below the existing review
threshold. The new wheel is also independently installed outside the checkout;
all 84 newly added regressions pass there against identical packaged source.
Compileall, Ruff, project status, diff checks, performance growth, incremental
stability, build, Twine and independent offline installation acceptance all pass.
The installation workflows cover nine cases and 55,075 comparison points.
Selected Strategy and Request capture checks retain zero differences; selected
TA checks retain 144 disclosed differences and zero unexpected differences.

The independent rc33/rc34 numeric comparison covers **8,136 output cells** in
15 fixed profiles (population batch/scalar and sample scalar dispersion),
including minimum subnormals, near-zero variance division, maximum finite
inputs, missing observations and changing scales. Of 4,325 changed outputs,
all improve exact-window Fraction/Decimal reference error; 1,695 regain a lost
nonzero result and 2,037 regain a representable finite result. All batch
prefixes are preserved. Unchanged ordinary centered-moment roundoff remains;
the largest observed relative error is about 7.97e-12. This fixed check does
not establish correctly rounded ordinary statistics or native equivalence.
The paired receipt is `paired-numeric-qualification.json` in the current
rc34 validation directory.

In the controlled sparse-provider check, 500 successive callbacks return
125,252 rows without finality and 1,499 with it; every callback matches the
independent authoritative slice. The largest fetch span after warmup shrinks
from 30,000 to 180 seconds. Fetch count remains 500 because mutable tails
refresh. This measures provider retrieval work, not the full request evaluator's
scalability; `request-finality-controlled.json` retains both the 256- and
500-callback comparisons.

The frozen 3,072-cell variance diagnostic now has **1,945 native differences**
in each execution mode. Paired against the actual rc32 wheel, batch changes from
1,797 differences (212 introduced, 64 removed, 1,733 retained); incremental
changes from 1,946 (8 introduced, 9 removed, 1,937 retained). Every introduced
difference improves the independent exact-window mathematical error, and the
new batch output preserves every prefix. Only 62 batch introductions directly
witness the old future dependency; the other 150 reflect recovery from numerical
cancellation. The batch native difference count increases by 148, so this repair
is not a claim of improved overall native compatibility. Original captures,
tolerances and missing-value assertions remain unchanged. The complete paired
cell receipt is `.tmp/audit-repair-20261003/variance-native-qualification.json`.

For the supplied no-request preview benchmark with 50,000 committed bars,
Python temporary allocation peak decreases from 17.86 MiB to 0.106 MiB.
This measures allocation during the preview, not total retained session memory.

Live request caching retains completed positive rows; caching absent coordinates
also requires an explicit finality promise. Without one, unobserved coordinates
refresh in one coalesced fetch per query and the span can still approach the full
retained history. With one, successful reads certify only their safely ended
intersection with the declared watermark; mutable tails and uncertified ranges
refresh. Invalid, regressed or withdrawn promises discard the affected context's
cache and fall back to conservative retrieval. Cache budgets remain separate
from computation admission. This repair does not establish correctly rounded
ordinary statistics across all inputs or close the separately documented
native-alignment gaps.

Round59 evaluates general compensated-state replacements across all **192
existing modes**, without modifying production code. An SMA/SUM candidate
removes **3,042 differences but introduces 350**, retaining 8,909 differences.
Adding raw-moment variance/stdev removes **6,071 but introduces 384**, retaining
5,914. Actual source and independently installed wheel experiments agree.
All repaired, introduced and retained counterexamples remain in separate
candidate receipts; lower total differences do not qualify a replacement.
Seven quotient-rounding and 56 compensation-transition hypotheses also retain
counterexamples. No native indicator output supplies candidate input.
Fresh canonical source/wheel reports remain identical to Round58: **11,601
/131,586 active differences (8.816%), 96 recipes /192 modes**. The rc32 /37
runtime tree is unchanged. This round reruns 25 documentation tests and the
evidence checks; Round58's 159 targeted tests and Round55's 4,381 full tests are
prior unchanged-runtime receipts, not newly rerun gates. Strict reports exit 1.
The receipt is `.tmp/tv-alignment-round59-20261003/compensated-candidate-qualification.json`.
**Overall acceptance remains unproved; Goal stays active.**

Round58 independently executes positive/zero/negative history prefixes followed
by the same supplied tail. All **96 inputs and 384 diagnostic outputs** are
retained in a complete 32-row official UI download. The native results differ
at **228 /228 equal-current-window paired cells**: for example SUM2 over
`[1, 2]` is 2 after a large prefix and 3 after a zero prefix. Selected native
outputs therefore cannot be reconstructed from the current window alone.
Remove-before-add Kahan state matches all 384 new diagnostic cells, yet keeps
**146 /768** exact counterexamples in the preceding square-sum capture; six
explicit addition trees also fail. These candidates add no runtime agreement.
Explicit folds avoid treating Python's compensated `sum()` as naive addition.
All **192 previous mode objects**, the **11,601 /131,586 (8.816%)** active-cell
differences and rc32 /37 core remain unchanged. Twelve retained diagnostic
workloads are unmeasured. Source and the existing independent wheel each pass
**159 targeted tests**, plus 25 documentation tests; strict reports exit 1.
The receipt is `.tmp/tv-alignment-round58-20261003/sum-prefix-qualification.json`.
**Overall acceptance remains unproved; Goal stays active.**

Round57 adds a separate official source-operation diagnostic over the same
frozen variance inputs. Its complete 64-row UI download verifies **256 input
cells, 3,072 exact native recapture cells and 2,048 new diagnostic cells**.
Multiplication, power, square mean and sum/period agree exactly in the selected
profiles. None adds runtime parity. All 4,608 supplied-input raw-moment models
retain counterexamples (best 205 /1,536); eight formulas using the native sum
as a diagnostic still retain at least 38 /1,536 differences. No replacement
accumulator or private implementation is qualified. All previous **192 mode
objects and 11,601 /131,586 active differences (8.816%)** remain unchanged;
11 retained diagnostic workloads are explicitly unmeasured. Source and the
existing standalone rc32 /37 wheel each pass **148 targeted tests**, with
25 documentation tests. Strict reports exit 1. Core and semantics are unchanged;
Round55 remains the prior 4,381-test full gate. The receipt is
`.tmp/tv-alignment-round57-20261003/variance-source-qualification.json`.
**Overall acceptance remains unproved; Goal stays active.**

Round56 adds an independently frozen scalar variance/stdev holdout: the official
Pine logs UI download retains **256 source inputs, 3,072 canonical outputs and
1,536 diagnostic cells**. Batch and callback comparisons disclose **1,797 and
1,946 numeric differences** with no missing-position differences. The expanded
matrix is **96 recipes /192 complete modes; 177,320 cells /131,586 active /
45,734 both missing; 11,601 differences (8.816%)**. The increase reflects newly
measured inputs; all previous 190 mode objects and the rc32 /37 runtime tree
remain unchanged. A candidate using public SMA helpers introduces 66 batch and
2 callback differences and remains unqualified. Sample stdev is explicitly a
sqrt(sample variance) recipe; the public stdev API has no bias parameter.
Source and the existing independently installed wheel each pass **135 targeted
tests**. Round55's 4,381-test full gate remains the prior runtime receipt;
this evidence-only round does not rerun the full suite. Strict reports still
exit 1. The receipt is
`.tmp/tv-alignment-round56-20261003/variance-holdout-qualification.json`.
**Overall acceptance remains unproved; Goal stays active.**

Round55 corrects DMI's initial true-range denominator while preserving public
TR and ATR initialization. A preselected 64-bar monthly capture identifies the
problem; a weekly capture independently verifies the frozen candidate. All
**768 source input cells and 1,664 native output cells** are retained, including
readiness. Each dataset's 13 output columns match in batch and direct scalar
execution at the unchanged 1e-8 tolerance. The same expanded corpus removes
**1,144 differences** without introducing canonical differences. Previous
186 modes keep all difference counts; two ADX numeric-error summaries change
within tolerance and the other 184 mode objects remain identical.

The matrix measures **95 recipes /190 complete modes; 171,176 cells /126,018
active /45,158 both missing; 7,858 differences (6.236%)**. Imported sparse TA
references separately retain **144 /1,353 raw differences**: 33 previous
differences and 111 DMI custom-formula differences. An independent native
evaluation exactly reproduces all 115 imported DI values with the old wrapper;
the strict wrapper differs at those 111 positions and matches the runtime.
This does not prove historical capture provenance or add runtime parity cells.
The prepared exporter now uses strict DMI true range and discloses helper
substitution. Original imported values and tolerances remain intact.

The development candidate is **rc32 / computation semantics 37**. Genuine
installed rc31 /36 generic and affected-DMI snapshots are retained for upgrade
rejection. Final complete regression passed **4,381 tests**; source and the
independently installed wheel each passed **518 targeted tests**. The 25
documentation checks, ruff, distribution validation and dependency checks pass.
Source and wheel reports differ only in distribution location metadata; both
strict acceptance commands exit 1. The final receipt is
`.tmp/tv-alignment-round55-20261003/dmi-origin-qualification.json`.
Ten native diagnostics remain unmeasured. **Overall acceptance is unproved;
Goal stays active.**

Round54 independently executes 64 bars of EMA, RMA and RSI over three supplied
profiles and five periods. The input seed was frozen before native observation;
all **192 input cells and 2,880 native outputs** are retained. The native RMA
emits missing output on a missing input while retaining its accumulator. Both
previous runtime modes emitted stale values at 154 positions each. The narrow
correction removes **308 differences**, with **zero newly introduced gaps** in
the same expanded corpus; all prior 184 mode reports are unchanged.

The matrix measures **93 recipes /186 complete modes; 167,848 cells /122,934
active /44,914 both missing; 7,858 differences (6.392%)**. The new 45 native
columns have zero differences in both modes at the unchanged 1e-8 tolerance.
These selected ordinary-scale cases do not qualify complete API behavior.
The development candidate is **rc31 / computation semantics 36**. Genuine
installed rc29 /semantics34 and intermediate rc30 /semantics35 state and replay
artifacts are retained; restore
rejects them before constructing a session. New-version previews and local,
portable-state and replay continuation are checked through the captured gaps.
ATR and DMI retain their original composition behavior; these controlled
compatibility checks do not establish native parity for those missing cases.
Final regression passes **4,315 tests**, and source plus independently installed
rc31 each pass **439 targeted tests**. Documentation checks pass 25 tests; wheel
and sdist validation and dependency checks pass. Both strict acceptance commands
return 1. The qualification receipt is
`.tmp/tv-alignment-round54-20261003/recursive-state-qualification.json`. **Overall acceptance is unproved;
Goal stays active.**

Round53 repeats the four near-edge profiles in four separately executed native
scripts, each containing one SMA and one SUM call. All **128 independently
supplied inputs, 256 numerical recaptures and 256 state flags** reproduce the
combined-script capture exactly at zero tolerance. The two uniform overflow
guards remain falsified after this call-site isolation. This rules out a need
for combined calls for these four witnesses; it does not establish universal
source-context invariance or a replacement arithmetic algorithm.

The assessment exposes `nativeNearEdgeCallIsolation`. Four diagnostic-only
recaptures remain visible among **nine unmeasured native workloads** and add no
runtime parity cells. All previous **184 mode reports** and totals remain
unchanged: **7,858 /118,846 active differences (6.612%)**. Runtime rc29,
computation semantics 34 and the previously installed wheel remain unchanged.
Source and independently installed targeted tests pass **290 tests each**;
documentation checks pass 25 tests. Full regression remains the historical
Round44 receipt. **Overall acceptance is unproved; Goal stays active.**

Round52 executes four ULP-boundary profiles selected before native observation
(seed 2026100352; trials 9/24/68/444; periods 7/7/3/3). Independent reconstruction
verifies **128 input cells, 256 native numerical outputs and 256 same-capture
state flags**. Both ordinary remove/add and Kahan guards have native counterexamples
in both directions. At two witnesses the native sum is the largest finite
binary64 value; a candidate incorrectly predicts missing. At two others native
results are missing while a candidate predicts finite. Neither uniform guard nor
an after-the-fact period-specific rule is qualified as a kernel replacement.

All eight native columns enter both modes. The matrix measures **92 recipes
/184 complete modes; 162,088 cells /118,846 active /43,242 both missing; 7,858
differences (6.612%)**. New coverage adds 203 numerical and 80 missing differences;
all previous 182 mode reports are unchanged. Callback SUM still recomputes supplied
history. Runtime, rc29 wheel and computation semantics 34 remain unchanged.
Source and the actual installed wheel each pass **277 targeted tests**;
documentation checks pass 25 tests. Strict reports agree apart from distribution
metadata/import location, and both acceptance commands return 1. A further
retrospective search rejects all 240 separate add/remove compensation variants
over 82 retained profiles /5,920 cells; its best model still has 2,148 gaps,
including one missing-state error. This candidate denominator adds no parity
coverage and does not qualify an arithmetic or state-only replacement.
**Overall acceptance is unproved; Goal stays active.**

Round51 executes a candidate-only, preselected 32-input numerical discriminator
(seed 2026100351, trial 2). At index 16, native SMA7 and SUM7 are finite;
oldest-first window recomputation overflows in an intermediate addition and its
sticky variant incorrectly predicts missing. The 64 native numerical outputs
and 64 same-capture state flags reject that replacement hypothesis; selected
mask fits still do not qualify another arithmetic kernel or permanent poisoning.

Both native numerical columns enter both modes. The matrix now measures **91
recipes /182 complete modes; 161,576 cells /118,398 active /43,178 both missing;
7,575 differences (6.398% of active cells)**. The 60 additional missing gaps are
new coverage; all previous 180 complete mode reports remain unchanged. Callback
SMA uses a direct helper, while SUM recomputes the supplied prefix and does not
qualify bounded streaming. Runtime, rc29 wheel and semantics 34 remain unchanged.
Source and the actual installed wheel each pass **260 targeted tests plus one
independent seed/trial reconstruction test**; documentation checks pass 25 tests.
Both strict acceptance commands return 1, and both reports agree except for
distribution metadata/import location. Full regression remains historical Round44.
**Overall acceptance is unproved; Goal stays active.**

Round50 retains a new 32-row, nine-profile native state holdout: **288 independent
input cells and 2,304 `na()` flags**, with no native numeric output cells. Six
independently initialized state models disagree in 31, 153, 519, 31, 561 and 31
cells respectively (remove/add, add/remove, recomputed window, sticky recomputed
window, exact window sum and Kahan remove/add). Three models fit the bar-dependent
profiles but fail the 31-cell static-expression SUM witness. An explicit `series`
declaration does not establish equivalent source context. A separate existing
numerical holdout rejects Kahan in **947 /2,304 cells** even though it fits the
new bar-dependent masks. This corrects the qualification boundary: missing-state
agreement alone cannot qualify arithmetic values or a replacement kernel.

The report exposes these masks separately and lists the capture among five
unmeasured native diagnostics. Numeric totals below remain unchanged, and no
runtime, wheel or computation-semantics change is justified by this probe.
Source and actual installed wheel each pass **245 targeted tests**; documentation
checks pass 25 tests. The source/installed reports agree apart from distribution
version and import location; all 180 previous mode reports are unchanged.
**Overall acceptance is unproved; Goal stays active.**

Round49 isolates one native SMA and one native SUM call in three separate
32-row scripts. All 96 logged inputs match independently supplied Python values,
and 288 same-capture state flags agree. A constant expression keeps SUM missing;
arithmetic and branch expressions involving `bar_index` give 31 finite SUM
outputs with the same logged numeric inputs. The source-expression effect is
observed; its hidden compiler mechanism is unproved. Pine qualifier labels follow
the [official type rules](https://www.tradingview.com/pine-script-docs/language/type-system/).
Python array arithmetic does not adopt a guessed Pine compiler rule, and all
constant-expression gaps remain in the raw assessment counts.

A separate minute-chart probe executes through confirmed index 26,793 and logs
**86 selected observations through index 25,001**. All four native SMA/SUM
outputs remain missing at those samples after the large prefix has left the
windows. Python independently supplies all 25,002 intervening observations;
this is **344 sampled native output cells**, not a contiguous 25,002-row oracle.
The canonical callback recomputes the full supplied prefix; bounded streaming
cost and permanent poisoning remain unproved.

The report now exposes native source-expression context and sampled-history
boundaries separately from output agreement. The corpus measures **90 recipes
/180 modes; 161,448 cells /118,294 active /43,154 both missing; 7,515 differences
(6.353% of active cells)**. All original 172 complete mode reports are unchanged;
the additional 738 missing differences come from new coverage. Source and actual
installed reports agree except for distribution version/import location; both
targeted suites pass **233 tests**. Runtime, rc29 wheel and semantics 34 remain
unchanged. Full regression remains the historical Round44 result below.
**Overall acceptance is unproved; Goal stays active.**

Round48 retains two authenticated 32-row native overflow-order captures.
Independent formulas verify 192 input cells; separate `na()`, halving and sign
guards verify 1,536 state cells. Four finite-output witnesses reject a simple
add-before-remove accumulator, without reconstructing compensated native state.
The earlier selected-data `SMA = math.sum / length` identity has **62 missing-mask
counterexamples** at extreme finite magnitudes. Both APIs must remain independently
measured; the selected-data bridge is not a universal implementation rule.

All 12 native SMA and 12 native sum outputs enter both modes, adding 1,308
missing differences. Callback SMA uses direct helpers; callback sums recompute
supplied Python history and do not qualify a bounded incremental sum API.
The corpus now measures **86 recipes /172 modes; 160,376 cells /117,246 active
/43,130 both missing; 6,777 differences (5.780% of active cells)**.
Every original 170 complete mode report remains unchanged. Source and actual
installed reports agree except for distribution metadata and import location;
both targeted suites pass **261 tests**, and documentation checks pass 25.
Full regression remains the historical Round44 receipt below, not a new full run.
Runtime, rc29 wheel and computation semantics 34 are unchanged. Thirty-two
observed rows do not establish general overflow recovery. A 14,400-variant
compensation search also fails its 5,184-cell holdout. **Goal stays active**.

Round47 adds an authenticated 24-row native SMA finite-overflow probe and a
separate 24-row state-guard probe. All 192 supplied input cells are independently
verified as finite. Native `na()`, halving and sign checks verify 1,440 state
cells; 135 mathematically finite window means are native missing outputs,
including 33 wholly small-value recovery windows. The 192 scaled-mean control
cells are references, not native agreement. All 12 original native SMA outputs
enter batch and direct incremental comparison, adding 270 missing differences.
The current corpus measures **85 recipes /170 modes; 158,840 cells /115,782
active /43,058 both missing; 5,469 differences (4.724% of active cells)**.
All original 168 complete mode reports and imported TA diagnostics are unchanged.

The extreme outputs also exposed an assessment export defect: raw `Infinity`
produced nonstandard JSON. Assessment schema **2** now encodes nonfinite numbers
explicitly as `{"nonfiniteNumber": "positiveInfinity"}` (or `negativeInfinity`
or `NaN`), preserving their distinction from missing `null` and every difference
count. Strict JSON export rejects accidental nonstandard constants. This is a
diagnostic-format correction; runtime, installed rc29 wheel, computation
semantics 34 and snapshots are unchanged. Both targeted suites pass **182 tests**.
The initial 180-test receipts and failed strict-JSON export validation remain
retained. Full regression remains the Round44 result below.

A 9,216-variant compensation-operation search retains 1,200 exact fits on 768
older cells, but every survivor fails the broader 5,184-cell corpus. Native
overflow persistence is established only for the 24 observed rows; no guessed
permanent-missing rule or compensated-sum replacement is applied. Native
accumulation and recovery semantics remain open; **Goal stays active**.

Round46 retains a new authenticated in-app-browser SMA source-history probe:
40 rows /48 columns over four repeated input profiles. Observable Pine history
indices and independent arrays match 800 independently generated input/history
cells exactly. Direct pair arithmetic matches 320 cells; 320 native SMA outputs
reproduce the earlier holdout. Native sum/mean and dyadic scaling identities also
match 320 and 160 cells. These checks constrain the source of arithmetic residues
without establishing the rolling accumulator. They remain diagnostic-only and
explicitly unmeasured in the canonical report, alongside `correlation_reduction_order`.
Runtime counts and all original 168 mode reports remain unchanged from Round45
below; source and actual installed targeted suites each pass **165 tests**.
The browser was restored, with the original script and ChartArt strategy retained.
Native sum reconstruction and whole-scope acceptance remain open; **Goal is active**.

Round45 adds independent batch and direct-incremental Python recipes for the
retained 96-row SMA holdout. All 24 native outputs enter comparison; 48 input
and formula controls stay excluded. The current corpus measures **84 recipes
/168 modes; 158,264 cells /115,230 active /43,034 both missing; 5,199 differences
(4.512% of active cells)**. The additional 1,960 numerical differences come
entirely from newly measured outputs, rather than a runtime change. All original
166 complete mode reports are unchanged; source and actual installed rc29 reports
agree except for distribution metadata and import location. Both targeted suites
pass **161 tests**; full regression remains the previous Round44 result below.
The unchanged wheel and runtime retain computation semantics 34.

The public SMA arithmetic diagnostic independently verifies 1,152 supplied input
cells and 3,456 Python/Pine formula-control cells. The older Kahan model's 768
exact cells do not qualify its independent 458 period-two and 489 period-three
counterexamples. Forty native SMA/sum pairs agree exactly over 2,560 cells:
`SMA = math.sum / length`. This constrains further reconstruction but provides
no Pyne agreement or general arithmetic proof. Rolling-sum models remain
falsified; **whole-scope acceptance is unproved and Goal remains active**.

Round44 preserves the original five legacy TA fixtures and verifies their 32
startup conflicts with independent Pine **v5 and v6** masked-history probes.
The old exporter supplies missing sources before an interior chart window,
whereas local replay starts a new dataset. Every conflict reproduces after a
16-bar missing-source prefix: 22 native extrema/Stoch witnesses and ten exporter
WPR-helper witnesses. Exact context annotations retain **33/1,353 raw imported
differences**, now all disclosed; no input, expected output or tolerance changes.
The WPR helper's zero-before-readiness output is explicitly excluded from native
built-in WPR evidence. Original CSV provenance remains incomplete.

Each probe independently measures 16 native outputs over 40 rows in batch and
generic callback replay: **2,560 added cells /1,720 active /840 both missing**,
with zero differences. That round's denominator was **83 recipes /166 modes;
153,656 cells /111,098 active /42,558 both missing; 3,239 differences (2.915%)**.
The original 81-recipe difference count stays 3,239; this rate change is coverage
expansion, not a numerical repair. Runtime source identity, candidate rc29 and
computation semantics 34 remain unchanged. Source and independent installed
specialist checks each pass 136 tests; full source regression passes **4,121 tests**
(one existing architecture warning). The old six failed checks remain in Round43's immutable
receipt. **Whole-scope acceptance is unproved and Goal remains active.**

During that regression, a Kahan remove-before-add hypothesis matched nine older
period-two SMA profiles but failed an independent 96-row /12-input native
holdout at **458/1,152** candidate cells. The candidate was not applied to the
runtime; the holdout entered the canonical matrix in Round45. This retained counterexample makes a simple rolling-sum
replacement unjustified. Native arithmetic reconstruction continues.

Candidate **rc29 /computation semantics 34** makes batch rolling-sum fallback
admission depend only on available history for each output. A future small value
or overflow can no longer rewrite prior batch SMA values. Incremental finite
means retain an exact raw sum separately from centered variance, preserving small
tails after a large level shift and finite means when a raw sum overflows.
Genuine installed rc28 /semantics-33 ordinary and affected snapshots are retained
for rejection before construction; rebuild from authoritative supplied OHLCV.
No package wire format or host policy changes are introduced.

Round43 retains a 96-row, 30-output native SMA history probe, with six independently
generated inputs and twelve separate native accumulation controls. All **81
registered recipes /162 modes** are measured. On identical **151,096 numeric cells
/109,378 active /41,718 both missing**, old rc28 has **3,277 differences** and the
corrected source and independently installed wheel have **3,239 (2.961% of active
cells)**. The paired audit records **152 repaired, 114 introduced and 3,125 retained**
locations, a net reduction of 38. Official period-3/7/11 large-prefix residues persist
after the large values leave the window; a prefill followed by gaps also keeps
a period-two native residue. Every native disagreement remains counted at 1e-8.
The rate does not qualify practical impact, complete API coverage or a release.
The first fresh wheel installation exposed 25 request/timezone differences across
1,753 imported points because Windows lacked an IANA timezone database. The
generic `tzdata` dependency is now declared. A second fresh environment, with
system timezone data disabled, passes 152 timezone/request/report/package checks
and nine standalone workflows /55,075 points; its assessment equals the source
assessment except for distribution version and import location. The original
failure and both wheel hashes remain retained. The initial specialist installation
passed 851 checks and failed only that timezone-dependent report assertion.
History controls pass 63 checks, the initial kernel suite passes 306, and performance
and stability checks pass. The full source suite ends at **4,102 passed /6 failed**:
five legacy TA golden cases and the strict documentation qualification check
(32 unexpected imported conflicts). The final documentation subset ends at
19 passed /1 failed at that same strict check. These failures remain visible;
overall candidate qualification is false. **Goal remains active.**

Round42 retains two fresh 64-row native arithmetic probes from the authenticated
in-app browser. The correlation probe compares eight independently executed
Pyne outputs; its six inputs and 192 native operator/moment controls stay outside
runtime agreement. The second probe compares native SMA with independent Pine
reduction hypotheses and is explicitly listed as an **unmeasured native workload**,
with no Pyne agreement claim. The guarded raw-moment formula explains all 512
native correlation results, but native period-3/7 SMA still has counterexamples
for newest/oldest/Kahan/Neumaier/paired folds. Binary64 products and logged
operand recomposition agree exactly; rolling reduction remains unreconstructed.
The runtime stays **rc28 /semantics33**, with no kernel or snapshot changes.

All preceding 79 registered recipes and their 448 differences remain identical.
The eight new outputs add **1,024 paired cells /960 active /64 both missing /
634 differences** (270 value and 364 missing). Expanded totals are **80 registered
recipes /160 measured modes**, **145,336 cells /103,870 active /41,466 both missing /
1,082 differences (1.042%)**. The increased rate comes from adding stress witnesses,
not regressions or repairs. Native-to-native formula agreement never enters this
denominator. The rate does not bound practical impact or qualify complete API /
parameter coverage. Imported sparse TA conflicts and overall candidate qualification
remain unresolved; **Goal stays active**. See the Round42 arithmetic diagnostic and
qualification receipts; Round41 totals below describe its preceding corpus.

Candidate **rc28 /computation semantics 33** aligns batch extrema, extrema
offsets and Stoch with the initial dataset-origin lookback span. Missing input
clears extrema candidates without restarting that initial clock; later Stoch
missing/flat holding is preserved. Genuine installed rc27 /semantics-32 ordinary
and affected snapshots are retained and rejected before construction. Rebuild
from authoritative supplied OHLCV; portable wire formats remain unchanged.

The in-app browser now provides authenticated native TradingView evidence.
A fresh 64-row holdout evaluates 125 outputs across lengths 1/2/3/5/11 and
five synthetic input profiles, producing **16,000 paired numeric cells with
zero differences** at the original 1e-8 tolerance. Raw native logs, executed
source, hashes and capture context are retained. The expanded **79 recipes
/158 modes** map every output. Identical 144,312 numeric cells produce
**912 old rc27 differences versus 448 current differences**. Active cells change
from 103,374 to 102,910 because 464 false premature outputs become both missing;
both-missing cells change from 40,938 to 41,402. Current differences comprise
238 value and 210 missing differences, **0.435% of active cells**. The unchanged
preceding corpus accounts for 114 repairs and the fresh holdout for 350.

The imported sparse TA diagnostic remains separate: **33 differences, including
32 unexpected startup conflicts**, in 1,353 imported points. Native source/log
and prior-history provenance are absent for these imports; their conflicts are
unresolved, not masked, retoleranced or relabeled as expected. Five external
capture golden checks consequently fail. Candidate qualification and full-scope
acceptance remain **not passed /not proved**. The Goal remains active. Round41
validation receipts are recorded separately; the previous Round40 pass below
does not qualify this candidate. Correlation and numerical-precision debt remain.

Round41's 230 window checks and three added input/full-history controls pass.
The first full source run recorded **3,974 passed /24 failed**; 16 failures came
from uninstalled Anaconda child imports, two from stale local sum expectations,
and six from imported native parity. After correcting the environment and those
local assertions, the targeted run records **398 passed /1 failed**, retaining
the strict documentation parity failure. Five unchanged external-capture golden
failures remain. These assembled receipts do not constitute a green full run.
The actual fresh installed rc28 wheel initially records **2,925 passed /7 failed**;
two stale sum assertions and four new checks were separately verified, while the
strict documentation parity check still fails. Its nine independent workflows
pass **55,075 points**; build/Twine, performance/stability, strategy/request
capture checks pass, and TA capture parity fails with the same 32 conflicts.
Source and installed reports agree apart from import/distribution metadata.
The actual runtime tree is
`44fb16dc0da59190d1f175b4d0db5586b40d2936f29ae18c845882b9d4be1b19`;
the wheel SHA256 is
`325c85a5ca8ddc28c458b40bc73a5a4e755ecca36c6f31794d2c07357b65e6ed`.
The terminal qualification receipt
`.tmp/tv-alignment-round41-20261002/paired-window-qualification.json`
explicitly records `overallPassed=false` and `goalStatus=active`.

Candidate **rc27 /computation semantics 32** preserves raw binary64 plot,
candle, drawing and signal values independently of display precision, fixes
batch SMA(1) to return the latest present observation exactly, and preserves
incremental strategy calculation properties before scripts/risk consume them.
Existing strategy ledger/report formatting remains a separate precision limit.
Actual installed rc26 /semantics-31 ordinary and affected snapshots are retained
and rejected before construction; rebuild from authoritative supplied OHLCV.

The expanded **78 recipes /156 modes** map every native output. On the same
128,312 numeric cells /90,682 active cells /37,630 both missing, retained rc26
has 2,300 differences and corrected source has **562 (0.620%)**, consisting of
238 numeric and 324 missing differences. The 1,738 repaired locations comprise
108 previous output-truncation gaps and 1,630 gaps in the new precision probe;
there are zero new difference locations. All original per-probe tolerances stay
unchanged. The new 32-output probe still counts 46 large-offset SMA(3) gaps.
Remaining native correlation discrepancies can exceed 2e11 in absolute error;
the corpus rate does not establish small practical impact or full declared-scope
alignment. The Goal remains active. Round40 paired qualification records source,
actual installed-wheel identity and terminal validation separately.

Round40 validation passed **3,762 source tests /2,600 independent installed
tests**, performance/stability and capture checks, build/Twine, and nine installed
workflows /55,075 comparison points in each installation path. Source and actual
site-packages official reports are identical except for import path. The runtime
tree is `6e95e8e397257da99e995f9d7eca684b333e467ff3db36042943bbad38c949b9`;
the independently tested wheel SHA256 is
`3d579b29604dab8930f9767a1081f70bccffcb3bd824a8dbd31d7c48590b4455`.
Initial test failures and PowerShell build-stderr interruption receipts remain
retained. Completed suites were preserved; remaining build/install components
were completed with real process exit codes after the expectation-helper repair,
with runtime identity rechecked. The paired receipt is
`.tmp/tv-alignment-round40-20261002/paired-precision-acceptance.json`.

Candidate **rc26 /computation semantics 31** fixes finite single-observation
population variance/stdev and incremental mean. Eight freshly captured native
profiles measure all 48 dispersion/BB outputs over 32 rows in both modes:
**3,072 cells with zero differences** at unchanged absolute tolerance 1e-8.
The same expanded recipes have 690 differences in the retained installed rc25
runtime and **624 /88,990 active cells (0.701%)** in corrected source, with
126,264 numeric cells /37,274 both missing. The 66 removed gaps affect batch
stdev and period-one BB bounds. Every previous column and separate witness is
exactly unchanged. Python extreme-exponent/infinity controls remain separate
from native evidence. Genuine semantics-30 ordinary and affected checkpoints
are retained and rejected before construction; rebuild from authoritative OHLCV.

All **77 recipes /154 modes** now map every native output, with zero absent or
partially mapped modes. Completing 33 output columns adds 1,138 cells /968 active
agreements /170 both missing. Existing direct helper calls are preserved;
Donchian composites use existing full-window highest/lowest helpers. Other new
outputs use public Python batch execution with retained full OHLCV. The direct
incremental TA API stays at 39 methods. Default computation budgets stay `None`;
display/replay retention does not bound callback computation history or cost.
The 330 dispersion/snapshot specialist checks and 466 callback-related checks
pass. The full Windows gate passes **3,724 tests**, performance/stability,
all capture gates, build/Twine and nine installed workflows /55,075 points.
Independent installed checks pass **2,562 tests** and the same nine
workflows. Actual site-packages rc26 /semantics 31 has the identical runtime tree;
source and installed native reports agree except for the import path. The first
gate retains three failed historical mapping assertions /3,721 passing tests.
Complete-corpus assertions and an independently omitted-output fixture replace
those stale assumptions; 101 report checks and the full retry pass. Failures and
explicit terminal codes remain recorded. Forty-two Python-only cost observations
at 16/32/64 bars confirm full computation history and matching retained results.
At 64 bars, retaining display/replay 3 still serializes 45,302–62,462 bytes;
default history serializes 292,075–407,171 bytes. Every recipe's state grows from
16 to 64 bars under both policies. These byte counts are not peak RAM or bounded
performance qualification. Paired receipt:
`.tmp/tv-alignment-round39-20261002/paired-dispersion-acceptance.json`.
Full API/parameter/numerical coverage and practical impact remain unproved;
**Goal remains active**.

Results below are historical.

The rc25 /semantics-30 correlation correction uses independently advancing
present-observation windows for x, y and x*y. Ready zero numerator/denominator
return zero; nonzero numerator with zero denominator remains missing. Exact
period-one variance avoids history-dependent floating residues. Missing-window
results can exceed one; coherent finite windows retain stable centered Pearson
arithmetic. The retained installed rc24 /semantics-29 runtime has 1,744
differences on the same expanded corpus; the corrected source has **624
/85,842 active cells (0.727%)**, 122,054 numeric cells /36,212 both missing.
All unaffected previous workload columns and separate witnesses remain unchanged.
The existing batch oscillator correlation removes 41 old differences; the
added callback mapping removes the same 41 on identical expanded recipes.

The original ten-profile native diagnostic is now formally registered and
matches all 640 batch/callback cells. A fresh Chrome native 32-profile /32-row
holdout retains 342 differences across 2,048 output cells: ten modest shifted
roundoff gaps plus large-offset native arithmetic differences. Strict absolute
tolerance stays 1e-8; every native output column remains counted. Nine independently
generated inputs and plain moment formulas are separate controls. The visible
editor source was copied and verified; the temporary probe was removed and the
original draft restored. Complete log blocks and screenshots are retained.

All 76 recipes /152 modes are measured, with zero absent /seven partial modes
and 33 unmeasured output columns. The direct incremental TA API stays 39 methods;
correlation callbacks retain full Python history and recompute through batch TA,
without bounded streaming qualification. Genuine semantics-29 ordinary and
affected correlation state/replay checkpoints are rejected before construction;
rebuild from authoritative supplied OHLCV. The 345 focused tests pass, including
prefix, preview, retention, restore and independent high-precision controls.
The full Windows gate passes **3,606 tests**, performance/stability, all capture
gates, build/Twine and nine installed workflows /55,075 points. Independent
installed specialist checks pass **2,444 tests** (2,392 plus 52 oscillator
controls), with nine workflows /55,075 points. The first full-gate failure was
one historical missing/flat assertion; the revised test verifies every retained
native row and all mapped batch/callback prefixes. Its failure log and the
successful retry are both retained. Full-gate, installed, final-wheel and
supplement terminal codes are explicitly zero. The final wheel updates README
metadata to semantics 30; all runtime/resource bytes match the tested wheel,
and its native assessment/workflows were rerun. Receipt:
`.tmp/tv-alignment-round38-20261002/paired-correlation-acceptance.json`.
General API/parameter/numerical coverage and practical impact remain unproved.
Goal stays active.

An independent follow-up diagnostic also reproduces a period-one public
variance/stdev residue in source and the installed rc25 wheel: maximum variance
3.553e-14, stdev 1.885e-7, and batch/prefix stdev disagreement 2.336e-7.
At that stage, direct native stdev period-one values had not been captured; the
observation did not alter the formal native corpus counts. Receipts:
`.tmp/tv-alignment-round38-20261002/next-source-stdev1.json` and
`next-installed-stdev1.json`. The rc26 investigation above addresses that boundary.

Results below are historical.

Six previously absent direction/percentile callback recipes now use the public
full-Python execution path with retained history and batch TA recomputation.
All 74 registered recipes /148 modes are measured, with zero absent modes and
seven partially mapped modes. The added 17,792 cells contain 11,725 active
agreements /6,067 both missing; all previous 323 differences remain unchanged.
Totals are **323 /83,513 active cells (0.387%)**, 119,302 numeric cells /35,789
both missing. Source declarations and static method leads explicitly distinguish
these recipes from direct incremental helpers; the declared 39-method direct API
is unchanged, and bounded streaming cost is unproved. Runtime stays rc24 /semantics
29. The full Windows gate passed 3,552 tests; independent installed-wheel checks
passed 2,294 tests and nine workflows /55,075 points. The 75 new controls cover
prefixes, preview/history isolation, local/replay/state restore and explicit
display/replay retention. Process handles expired during the app interruption;
complete stage logs and final acceptance receipts are retained without inventing
terminal exit codes. Fresh Chrome control initially failed after the approved
empty-window operation, then recovered after the browser plugin version changed.
This slice uses existing hash-verified native logs and claims no new capture.
Seven partial modes still contain 35 unmeasured output columns. Full
API/parameter/impact qualification remains incomplete; Goal stays active. Receipt:
`.tmp/tv-alignment-round36-20261002/paired-callback-coverage-acceptance.json`.
Results below are historical.

The rc24 /semantics-29 matrix investigation now includes twelve fixed rectangular
float products in two cycles/24 rows. Signed half-integers, six missing/zero
profiles, reverse transpose products, result/input detachment and copy/alias
reshape values add **1,728 numeric cells /1,052 active /676 both missing**, with
zero differences in both modes. Runtime implementation and semantics are unchanged.
Totals are **323 /71,788 active cells (0.450%)**, 101,510 numeric cells /29,722
both missing; 74 registered recipes /148 modes, 142 measured /6 unmapped /7
partial. The smaller rate comes from expanded samples; no existing difference
was repaired or excluded. Three native matrix dimension errors are preserved and
compared in both execution modes, outside numeric counts. Native execution aborts
on bar zero, so post-error atomicity is qualified only by independent Python
tests. The focused suite passed 244 tests, including 71 new specialist cases.
The full Windows gate passed **3,477 tests** and the actual retained rc24 wheel
passed **2,219 specialist tests**; both installed acceptances passed nine workflows
/55,075 points. The unchanged source and installed runtime trees, all prior
workloads and separate witnesses were verified in
`.tmp/tv-alignment-round35-20261002/paired-matrix-coverage-acceptance.json`.
The 323 remaining differences include 155 missing-value and 168 value differences
across 19 workload modes /75 output columns; downstream impact remains unproved.
Full declared scope and parameter coverage remain unproved; Goal stays active.
Results below are historical.

The semantics-29 empty-matrix-shape candidate (rc24) preserves zero-row width
through copy, snapshots, transpose, reshape, scalar/elementwise arithmetic and
matrix multiplication. Valid columns of 0xN matrices are empty arrays. Native
zero-term products retain shape and yield zeros, e.g. 3x0 multiplied by 0x2 gives
3x2. Stored width and row storage are validated before restore adoption, including
shared confirmed history. Genuine rc23 semantics-28 snapshots require rebuilding.
Eight fixed native shape transitions in two cycles/16 rows remove **196 numeric
differences** seen in both old source and the actual installed rc23 wheel.

Totals are **323 /70,736 active cells (0.457%)**, 99,782 numeric cells /29,046
both missing, 73 registered recipes /146 modes, 140 measured /6 unmapped /7
partial. Existing workload values and 323 differences are unchanged. New shape
output adds 1,152 numeric cells /1,108 active /44 both missing; repeated profiles
and missing/no-op cells do not establish full API/parameter coverage. Earlier
exact-text results remain 0 /256 and 0 /224, separate from numeric cells. The
focused suite passed 429 tests; the full Windows gate passed **3,403 tests**,
and an independent installed wheel passed **2,145 specialist tests**. Both passed
nine standalone workflows /55,075 points. Actual old/new installed runtime trees
and identical recipe/native hashes were verified in
`.tmp/tv-alignment-round34-20261002/paired-matrix-shape-acceptance.json`. Full matrix shapes, types, operands,
indices and rejection boundaries remain unqualified. Goal remains active.
Results below are historical.

The semantics-28 collection-string-extraction candidate (rc23) adds eight fixed
scalar string matrix/map profiles and two Boolean matrix constructors, repeated
in 16 native rows. On identical final recipes and native evidence the retained
rc22 wheel shows 32 numeric differences and 112 exact-text differences; the
source repair removes both. Boolean matrices default to false. String extraction
intent survives matrix rows/columns, copy, transpose, reshape and snapshots, and
map values, copy, bulk merge, clear/repopulation and snapshots. Successful string
writes establish the hint; rejected admissions leave it unchanged. Current and
confirmed-history hints are validated before restore adoption. Genuine rc22
semantics-27 snapshots are rejected; same-version continuation is tested.

Numeric totals are **323 /69,628 active cells (0.464%)**, 98,630 cells and 29,002
both missing. Existing workloads and their 323 differences are unchanged. The
registered corpus is 72 recipes /144 modes, 138 measured /6 unmapped /7 partial;
this is not declared API or parameter coverage. New text is **0 /224** exact
string differences; earlier array join text remains **0 /256**, kept separate
from numeric denominators. Empty shapes, reference-valued extraction, initial
all-missing generic map typing, complete types/bounds/formatting and the full
78-method collection surface remain unqualified. Goal stays active. The full
Windows gate passed **3,348 tests** and a separate installed wheel passed
**2,090 specialist tests**; both passed nine standalone workflows /55,075 points.
The focused suite passed 486 tests. Final source and installed runtime trees,
unchanged prior workloads, native hashes and old/new recipe hashes were verified.
The paired receipt is `.tmp/tv-alignment-round33-20261002/paired-collection-acceptance.json`.
Results below are historical.

The semantics-27 array-search/default/join candidate (rc22) passed **3,293
tests** in the full Windows gate and **2,035 specialist tests** in
a separate installed wheel. Both passed nine standalone workflows (55,075 points).
Native fixed profiles cover 16 float arrays, eight string arrays and two Boolean
constructors in two cycles /32 rows. Missing search no longer matches na; Boolean
arrays default to false; joins use an empty separator and native numeric text.
String construction intent survives copies, slices, preview/history and restore,
and is validated before adoption. Genuine rc21 semantics-26 snapshots are rejected.
All 112 new behavioral numeric gaps and 132 exact-text gaps are removed. The
numeric assessment still includes 16 new eight-decimal transport differences:
**323 /69,372 active cells (0.466%)**, with existing 307 unchanged. Totals:
98,374 numeric cells /29,002 both missing; 71 recipes /142 modes, 136 measured,
6 unmapped /7 partial. **0 /256 exact-string differences** are kept separate from
numeric denominators. The text verifier rejects incomplete or disagreed JSON
before execution. Full bounds, types, nonfinite and formatting coverage, including
string intent through other collections, remain unqualified. Default budgets
remain unlimited; full alignment is unproved. Results below are historical.

The semantics-26 atomic-map-merge candidate (rc21) passed **3,253 tests**
in the full Windows gate and **1,995 specialist tests** in a
separate installed wheel. Both passed nine standalone workflows (55,075 points).
Sixteen native scalar map cases in two cycles /32 rows add 2,496 output cells:
1,524 active agreements and 972 both missing. Existing reports are unchanged;
differences remain **307 /67,856 active cells (0.452%)**. The lower rate reflects
new coverage, not removal of those differences. Totals: 96,646 cells /28,790
both missing; 70 recipes /140 modes, 134 measured /6 unmapped /7 partial.
Bulk merges now validate all values and final capacity before mutation, retaining
insertion order. Capacity, depth and recursive-value rejection leave the target
unchanged. Nine independent persistent-state controls cover preview/history and
local/replay/state continuation; these do not enlarge the official denominator.
Genuine installed rc20 semantics-25 snapshots are rejected. Default budgets
remain unlimited. Scalar int-key cases do not prove full key/type/reference or
native-error coverage. Full alignment remains unproved. Results below are historical.

The semantics-25 connected-array-slice candidate (rc20) passed **3,209 tests**
in the complete Windows gate and **1,951 specialist tests** in a
separate installed wheel. Both passed nine standalone workflows (55,075 points).
Sixteen native mutation cases in two cycles /32 rows qualify parent/nested
window connections, structural edits, reordering and truncation/regrowth.
All 348 new slice gaps are removed; prior non-slice records are unchanged.
On identical final oracle/recipe hashes, differences fall from 655 /66,388
to **307 /66,332 active cells (0.463%)**; 56 false nonmissing cells become missing.
Totals: 94,150 cells /27,818 both missing; 69 recipes /138 modes, 132 measured,
6 unmapped and 7 partial. Persistent-state controls validate preview/history
isolation, graph continuation and retained-parent budget enforcement. Genuine
installed rc19 semantics-24 snapshots are rejected. Copies remain detached.
Current and confirmed-history slice storage is validated before adoption;
malformed parent types, bounds and recursive chains are rejected without
changing the healthy session. Six malformed-state controls pass; all 419
specialist source tests pass. This validation leaves native outputs unchanged.
Default budgets remain unlimited. Slice bounds, reference types, maps and full
API/parameter coverage remain unqualified. Results below are historical.

The semantics-24 numeric-matrix candidate (rc19) passed **3,163 tests**
in the complete Windows gate and **1,867 specialist tests** in a
separate installed wheel. Both passed nine standalone workflows (55,075 points).
Eight native 2x2 numeric cases in two cycles /16 rows qualify missing arithmetic
and in-place reshape to 1x4/4x1, including aliases and scalar copy witnesses.
Pyne add/sub map to Pine's two-operand sum/diff; Pyne aggregate sum and the
reshape same-object return are Python extensions. All 420 new matrix gaps are
removed on identical oracle/recipe hashes; existing non-matrix records are unchanged.
Genuine installed rc18 semantics-23 snapshots are rejected. Three additional
persistent matrix controls validate history, preview isolation and restore.
Current counts: 92,230 cells /27,054 both missing; **307 /65,176 active cells
(0.471%)**. There are 68 recipes /136 modes: 130 measured, 6 unmapped and
7 partially mapped. Full collections, shape/type and API/parameter qualification
remain open. Full-scope acceptance is unproved. Results below are historical.

The semantics-23 numeric-array candidate (rc18) passed **3,125 tests**
in the complete Windows gate and **1,829 specialist tests** in a
separate installed wheel. Each passed nine standalone workflows (55,075 points).
Eight native fixed array cases run in two cycles (16 rows); 29 output columns
per mode remove all 384 newly exposed array gaps. Numeric missing placement and
descending equal-value index reversal now align; failed sorting is atomic.
Genuine installed rc17 semantics-22 snapshots are rejected; same-version
preview/restore continuation passes. Existing non-array assessments are unchanged.
On identical oracle/recipe hashes, differences fall from 691 /63,896 to
**307 /63,872 active cells (0.481%)**; 24 false nonmissing cells become missing.
There are 90,566 cells /26,694 both missing, 67 recipes /134 modes: 128 measured,
6 unmapped, 7 measured modes partially mapped. This is corpus coverage;
full collections, string ordering, API and parameter qualification remain open.
Full-scope acceptance remains unproved. Results below are historical.

The 2026-10-02 measurement audit observes successfully executed callback plots,
including dynamic all-missing outputs that retain no curve. Four existing
18-row columns add 72 both-missing cells; no active agreement is added.
Current evidence has 66 recipes/132 modes: 126 measured, 6 unmapped and
7 measured modes partially mapped. Total cells are 89,638; both-missing cells
are 26,430. Active cells/differences remain **307 /63,208 (0.486%)**. Source
and installed rc17 wheel agree; each passed 88 observation/report tests.
Runtime and oracle identities are unchanged. Static direct-API scope leads
do not establish parameter coverage. Full-scope acceptance remains unproved.
Earlier matrix observations below retain their historical counting results.

The semantics-22 entry close-phase candidate passed **3,085 tests** in
the complete Windows gate and **1,750 specialist tests** in a
separate installed rc17 wheel. Both passed nine standalone workflows (55,075
points). On identical 66-recipe evidence, differences fall from 1,665 /63,286
to **307 /63,208 active cells (0.486%)**; both-missing cells are 26,358. All
selected matrix strategy columns and four after-command witnesses now align.
Seven market amendment controls pass 84 prefixes and 105 preview/snapshot
continuations. Entry staging honors callback process_orders_on_close; broader
market order/close/exit/reversal/risk and default callback timing remain
unqualified. Full-scope acceptance is still unproven. Gates below are historical.
The corpus has 132 modes: 126 measured, 6 unmapped, and 9 measured modes
partially mapped. Historical workload-count prose mixed counting units; current
workloadCoverage fields are authoritative and do not measure API coverage.

The semantics-21 stable-replay candidate passed **2,891 tests** in the
complete Windows gate and **1,556 specialist tests** in a separate
installed rc16 wheel. Both passed nine standalone workflows (55,075 points).
The same 66-recipe assessment (126 measured modes; 6 unmapped) exposes **1,665 / 63,286 active cells (2.631%)**,
plus 16 separate after-command state gaps. Sorting by submission time removes
an accidental match; unchanged inactive commands now preserve results. Native
market execution stages and full-scope acceptance remain unresolved. Gates
below belong to historical candidates.

The semantics-20 pending-order candidate passed **2,857 tests** in the
complete Windows gate and **1,499 specialist tests** in a separate
installed rc15 wheel. Both passed nine standalone workflows (55,075 points);
numeric and error witness results agree. Gates below are historical candidates.

The semantics-19 pending-direction candidate passed **2,708 tests** in
the complete Windows gate and **1,350 specialist tests** in a separate
installed rc14 wheel. Both passed nine standalone workflows (55,075 points);
numeric and error witness results agree. Caught-error state preservation and
native cancel continuation are verified. Gates below are historical candidates.

The semantics-18 same-ID pending-entry candidate passed **2,671 tests**
in the full Windows gate and **1,313 specialist tests** in a separate
installed rc13 wheel. Both passed nine standalone workflows (55,075 points);
all native workload results agree. The following gate is historical semantics 17.

The semantics-17 stop-limit candidate passed the complete Windows gate:
**2,579 tests**, performance/stability, capture diagnostics, build/Twine and nine
installed workflows (55,075 points). A separate installed rc12 wheel passed
**1,221 specialist tests**, the same workflows, and an identical native workload
assessment. All 17 pending-entry captures align in both modes, including
stop-limit activation and later price paths. Equal-distance path ties remain
unqualified. These checks do not prove full-scope native compatibility or
complete the active Goal.

The working checkout is development candidate **0.4.1rc17**, computation semantics
**22**. Corrections cover public missing-observation sums, carried-pending batch timing, strategy live-slot admission and residual lot averages,
missing-percentile order state, Keltner EMA widths, WMA/HMA/nested WMA gap windows, CMO missing momentum and
zero denominators, and Stochastic missing extrema and last-value retention.
Published 0.4.0 retains semantics **5** and the release evidence above. Six fresh
32-row TradingView Pine probes substantiate these corrections; they are pytest
workload evidence separate from the 58 capture-family cases below. Three further
probes (88 rows) cover extrema gap resets, earliest-tie positions and normal-input
percentile controls. See [extrema acceptance](../development/extrema_boundaries_acceptance_zh.md).
Version-16 and older snapshots must be rebuilt from authoritative OHLCV, not relabeled. See
[weighted-window acceptance](../development/weighted_boundaries_acceptance_zh.md).
See also [oscillator acceptance and remaining differences](../development/oscillator_boundaries_acceptance_zh.md).
Stochastic retains Pyne's available-history startup; native dataset-origin runs
wait for their initial window. The historical semantics-6 correlation contract
retained complete paired windows and differed on missing/flat native inputs;
semantics 30 now qualifies those retained columns with independent observation
windows, while shifted and large-offset native arithmetic gaps remain counted.
The previous semantics-6 candidate passed the Windows full gate: 1,350 tests, performance/stability,
all 58 stored capture-family comparisons, build/Twine, and nine installed-wheel
workflows with 55,075 comparison points. An additional installed-wheel run passed
149 fresh-oracle and snapshot checks. The preceding semantics-7 candidate passed
the complete Windows gate with 1,441 tests, performance/stability, all 58 stored
capture-family comparisons, build/Twine and the same nine installed-wheel
workflows (55,075 comparison points). The retained candidate wheel also passed
240 fresh-oracle/snapshot tests and the nine workflows independently. Details
are recorded in the extrema acceptance report. This evidence does not claim a
published release or unclosed-bar tick parity. Batch extrema startup and native
infinity-containing percentile inputs remain outside native qualification.

The continuing official-alignment Goal is **active; small differences are not
proved**. The preceding semantics-20 assessment measured **987 differences / 60,990 active cells (1.618%)** across 74 registered workloads. Same-ID pending order replacement and cancel-group reassignment probes now match in both modes. The retained rc14 baseline on this identical expanded evidence had 1,517 / 61,042 active cells (2.485%). A new cancel-before-direction-change native control matches in both modes; the lower rate reflects additional matching samples, not a runtime correction. The earlier four market/order amendment captures exposed 818 differences; repeated order now aligns, leaving 680 market/price replacement differences. The direction-change runtime-error witness now rejects with the expected cause in both modes; runtime errors remain separate from numeric denominators. The previous 56-workload result was 307 / 55,952 active cells (0.549%). Same-ID pending entry replacement removes the 322 amendment/duplicate-entry differences observed in the retained rc12 baseline (629 / 55,998 active cells). The earlier 20 pending-entry captures align in both modes; the four additional amendment cases remain different. The preceding 50-workload assessment had 307 / 54,370 active cells (0.565%). Seventeen pending-entry cases, including two-stage stop-limit activation and post-activation price paths in both directions, match their complete captured state/holding columns. The retained rc11 baseline on identical native evidence had 1,531 differences / 54,522 active cells (2.808%). Both-missing cells are separate (26,272 in the expanded assessment); removing false non-empty outputs accounts for the changed denominator. Full-scope acceptance remains unproven. The preceding semantics-12 assessment measured **273 differences / 37,458 active
cells (0.729%)** in 24 registered workloads, with batch and mapped callback modes
counted separately. All 62,766 output cells are accounted for; the 25,308 cells
where both outputs are missing do not inflate the agreement denominator. On the
same inputs and declared columns, the real installed rc6 runtime has 13,411
differences. These selected samples do not qualify the entire supported scope.
A broader diagnostic counts startup and reference-only columns rather
than excluding them: after the foundation correction, the original selected
scope has 252 differing cells out of 8,513 active output cells (2.960%). Expanded
percentile diagnostics previously measured 1,810 differing cells out of 14,083
active cells across 21 workloads (12.852%). The semantics-11 Keltner correction
and its matrix measured 1,842 differing cells out of 16,257 active cells
across 22 workloads. The subsequent controlled percentile-history probe expands
measurement to **4,897 differences / 21,132 active cells across 23 workloads**.
The increase adds previously unmeasured cases, without changing computation.
The matched 480-cell default Keltner comparison falls from
234 differences to zero. Raw-value comparison also exposes 92 existing TA-chain
output-rounding differences at its 1e-9 tolerance; these were hidden by rounding
the official reference to eight decimals. Scope expansion and comparator changes
are not a whole-product estimate. Native recipes
mention all 55 declared batch TA methods; recipe presence is not behavior or
parameter qualification. Three new native probes substantiate corrected pivot
tie/gap/full-span behavior; two further probes confirm rising/falling valid-adjacent
comparison windows. No scalar incremental TA helper is added for these functions. The older TA
capture family now reports one disclosed chart-history startup difference, not
zero differences. See the [assessment and acceptance gaps](../development/official_alignment_goal_zh.md).

Two new 32-row percentile probes test native missing sorting, 23 source/period
combinations, five percentages, and an independent insertion formula. The latter
is rejected by 188 of 3,680 linear-percentile cells. This rejected rule remains a counterexample.
All 230 native matrix output columns remain measured. Source and independently
installed rc5 runtime reports agree; both environments pass 77 current diagnostic
checks. This diagnostic round changes neither computation semantics nor the TA
capability surface, and does not claim a new complete Windows gate run.

A further 64-row probe supplies four different earlier histories followed by
identical inputs. Among 1,340 same-time, same-parameter, identical-complete-window
groups, native outputs differ in 16 groups. This isolates a dependency on history
outside the current window; it does not identify the replacement algorithm.
All 120 native output columns, including failures, are measured. Source and the
independently installed rc6 wheel each pass **94** diagnostic checks and produce
identical assessment reports. This round keeps computation semantics 11 and
does not rerun the complete Windows gate.

The subsequent missing-percentile correction retains rolling order state through
gaps and qualifies all 16,512 outputs from those four probes. Before collecting a
new native holdout, the candidate rule was frozen; its 96 rows, periods 5/9/17 and
fractional percentages add 16,128 previously unseen output cells with zero
differences. The combined 32,640 native cells are also checked at prefix boundaries.
Generic Python callbacks preserve preview isolation and local/replay/state snapshot
continuation. Real semantics-11 artifacts from the old installed rc6 wheel are
retained and rejected; no snapshot is relabeled. Complete finite arrays retain
the Fenwick path. Missing arrays use O(n*period) list updates; infinity-containing
arrays retain their prior Python-only contract. Qualification does not add scalar
incremental TA capabilities or establish tick, request or strategy parity.

The retained semantics-12 wheel passed **389** affected specialist checks and
nine installed workflows (**55,075 points**); its full diagnostic report agrees
with source apart from the import path. Build and Twine passed. Complete Windows
gate qualification passed **1,919 tests**, performance and stability checks,
all stored capture comparisons with the previously disclosed TA startup
difference, build/Twine and the nine installed workflows (55,075 points).

The semantics-13 strategy candidate passed the complete Windows gate with
**2,090 tests**, performance/stability, stored captures with the same disclosed
TA startup difference, build/Twine and nine installed workflows (55,075 points).
A separately retained rc8 wheel passed **683** affected specialist checks and
the nine workflows again. The five new native strategy probes qualify 3,040
outputs in each mapped mode; 161 source specialist checks cover prefixes,
preview/restore and independent lot arithmetic. Source and installed assessment
reports agree except for the import path. Real semantics-12 snapshots are rejected.
This is local candidate qualification; whole-scope small differences remain unproved.

The semantics-14 carried-pending candidate passed the complete Windows gate with
**2,114 tests**, performance/stability, unchanged stored captures (one previously
disclosed TA startup difference), build/Twine and nine installed workflows
(55,075 points). A separately retained rc9 wheel passed **720** affected tests
and the same nine workflows. Both source and installed assessments agree apart
from import path: the OCA trigger-bar timeline matches all 88 cells in each mode,
removing ten former batch differences. This qualifies the captured quantities
and counts, not all pending-entry admission or intrabar paths. Actual installed
rc8 semantics-13 snapshots are retained and rejected by semantics 14.

The semantics-15 public sum candidate passed the complete Windows gate with
**2,161 tests**, performance/stability, unchanged stored captures with the same
disclosed TA startup difference, build/Twine and nine installed workflows
(55,075 points). The retained rc10 wheel passed **797** specialist tests and
those workflows independently. Three previously omitted native workloads now
have complete output mappings. On identical measured recipe/oracle hashes,
rc9 has 359 differences and rc10 has 307; 52 sum/formula differences are fixed,
while 34 newly counted startup differences remain. Native sum qualification is
positive length 3 on the stored oscillator probe, not all lengths or inputs.
Actual installed rc9 semantics-14 snapshots are retained and rejected.

The preceding semantics-8 candidate passed the complete Windows gate: **1,578 tests**,
performance/stability checks, request/strategy capture comparisons, TA capture
qualification with one exact disclosed difference, build/Twine and nine installed
workflows checking 55,075 points. An independently retained wheel passed **196**
pivot/assessment/snapshot tests plus the same nine workflows. No publication or
commit is implied by this local qualification.

The preceding semantics-9 candidate passed **1,621 tests**, all Windows gate checks,
build/Twine and nine installed workflows (55,075 points). The independently
retained wheel passed **239** direction/pivot/assessment/snapshot tests and the
nine workflows again. The 15 registered workload recipes measure 186 differences
in 5,935 active cells; API recipe presence remains 40/55. These counts do not prove
whole-scope small differences, so the official-alignment Goal remains active.

The foundation semantics-10 candidate passed **1,711 tests**, all Windows gate checks,
build/Twine and nine installed workflows (55,075 points). Its separately retained
wheel passed **329** foundation/direction/pivot/assessment/snapshot checks and the
nine workflows again. Native recipes now mention **55/55** batch methods; the
18 registered workloads measure **252 differences / 8,513 active cells**. This
includes the direct native KC-width and Donchian startup differences. Cross/cum
and OBV gap defects are corrected. Full behavior/parameter and other-domain
coverage remain unproved, so the Goal remains active.

The semantics-11 Keltner candidate passed **1,819 tests**, the complete Windows
gate, build/Twine and nine installed workflows (55,075 points). Its separately
retained wheel passed **289** Keltner/foundation/percentile/report/snapshot tests
and those nine workflows. Source and installed official diagnostic reports agree.
The matched default Keltner calls improve from 234 differences to zero in 480
cells; the broader 22-workload assessment still has 1,842 differences in 16,257
active cells. Whole-scope small differences remain unproved; the Goal is active.

## Repository Evidence Snapshot

Run `python scripts/project_status.py --check` to verify this block. When capture
metadata or the package version changes, run
`python scripts/project_status.py --write` and review the resulting status change.

<!-- BEGIN GENERATED PROJECT STATUS -->
<!-- Generated by scripts/project_status.py; do not edit this block by hand. -->

Package version from `pyproject.toml`: **0.4.1**

| Capture family | Captured | Not captured | Missing | Parity assertions | Priority captured |
| --- | ---: | ---: | ---: | ---: | ---: |
| Request | 21/21 | 0 | 0 | 21/21 | 8/8 |
| Strategy | 27/27 | 0 | 0 | 27/27 | 10/10 |
| TA | 10/10 | 0 | 0 | 10/10 | 1/1 |
| **Total** | **58/58** | **0** | **0** | **58/58** | **19/19** |

These counts come directly from the request, strategy, and TA status `build_report()` functions. `Captured` means checked-in TradingView capture metadata exists; `parity assertions` means those records are configured for parity comparison. Numeric comparison is performed by the separate capture-diff quality gates, so this table does not extend compatibility claims beyond the listed fixtures and cases.

<!-- END GENERATED PROJECT STATUS -->

## Verified Capabilities

- **Batch indicator execution:** OHLCV series, history references, missing-value
  semantics, explicit state, TA helpers, parameters, plots, drawings, and signals
  execute through the Python package API and produce structured host-facing output.
- **Host-backed multi-context requests:** `request.security()` and
  `request.security_lower_tf()` support provider-supplied OHLCV, callable requested
  contexts, tuples, alignment options, metadata, capabilities, caching, and
  structured diagnostics across the captured contract surface.
- **Deterministic strategy replay:** entries, orders, exits, closes, cancellation,
  stop/limit handling, OCA behavior, pyramiding, costs, margin admission, risk
  rules, trade ledgers, summaries, and lifecycle events are available for OHLCV
  replay across the captured contract surface.
- **Incremental host sessions:** hosts can seed history, process temporary preview
  updates and confirmed bars, preserve explicit state, update supported incremental
  TA/drawings/strategy state, call the two supported `request.*` families, emit
  Render IR v2, use rolling retention plus process-local or bounded portable
  checkpoints, and share bounded TTL/LRU sessions through an in-process manager.
- **Mode-aware capability discovery:** `pn.runtime_capabilities()` and
  `pn.schema()["runtimeCapabilities"]` distinguish batch from incremental TA and
  lifecycle support; validation rejects statically visible unsupported
  incremental calls before bar processing.
- **Static script preflight:** `pn.inspect_script()` and `pyne inspect` report a
  source hash, mode-aware requirements, compatibility diagnostics, host needs,
  pinned libraries, and resource hints without executing or echoing source.
- **Expanded incremental TA:** 39 scalar helpers now include `hma`, `dmi`,
  `adx`, `sar`, `mfi`, `vwap`, `barssince`, `valuewhen`, the three cross
  predicates, and the later demand-led `change`, `highestbars`, `lowestbars`,
  `pivothigh`, `pivotlow`, `tr`, `cum`, `swma`, `alma`, `dev`, `bb`, and
  `pivot_point_levels` members, with batch/incremental parity and
  portable-restore coverage.
- **Batch/incremental parity kit:** hosts and contributors can run normalized,
  assertion-ready semantic comparisons without depending on the test runner.
- **Stable integration surfaces:** the package exposes versioned output, parameter,
  request-provider, and strategy-report schemas together with CLI validation and
  process execution controls.
- **Bounded execution trace v2:** opt-in batch and incremental traces disclose
  redacted lifecycle, request, strategy, output, state, script-defined events,
  hierarchical timings, and slow spans under a strict event budget; preview
  events remain isolated from committed sessions.
- **Output schema v2:** `plotcandle`, linefill and polyline objects, and merged
  table cells have explicit contracts. Version 1 remains a declared fallback
  for hosts and scripts that stay within its surface.
- **Pinned external-library adapter:** nine reviewed `TradingView/ta/10` members
  add dynamic-length `ema2`, `rma2`, and `atr2` to percentage/CAGR,
  since-condition extrema, up/down volume, and cumulative volume delta. Only
  volume members require authoritative host lower-timeframe OHLCV; unknown
  libraries fail closed.
- **Measured Pine migration inventory:** `scripts/pine_corpus_audit.py` inventories
  an external Pine corpus without executing or copying source, classifies live
  runtime/host/render boundaries, and keeps API-analogue counts distinct from
  source-level compatibility.

The detailed per-feature evidence and known differences remain in the
[Pine-like API matrix](pine_like_api_matrix.md). Host contracts are documented in
the [request API](../api/request.md), [strategy API](../api/strategy.md), and
[incremental runtime guide](../concepts/incremental_runtime.md). Corpus-based
migration evidence is documented separately in the
[Pine corpus compatibility audit](pine_corpus_compatibility.md).

## Explicit Boundaries

- **Language boundary:** Pyne executes Python scripts. It does not parse, compile,
  interpret, or directly run TradingView `.pine` source files.
- **Semantic boundary:** Python `if`, ternary expressions, and assignment do not
  automatically acquire Pine's per-bar behavior. Scripts use explicit helpers such
  as `when()`, `switch()`, and state cells. Computed request expressions use
  `lambda ctx: ...` rather than capture of an already evaluated Python expression.
- **Request boundary:** the core package requires a host data provider and currently
  implements the two request families named above. Nested requests and the wider
  Pine request families are outside the current surface.
- **Host-product boundary:** Pyne does not include a market-data service, database,
  chart renderer, parameter UI, alert delivery service, user/account system, or
  exchange/broker connector.
- **Strategy boundary:** replay is deterministic and bar-based. It is not a broker
  simulator and does not model an order book, queue position, tick path, real
  partial fills, broker margin calls, or other unavailable intrabar facts.
- **Incremental lifecycle boundary:** shared session managers and opaque state
  snapshots remain process-local. Portable replay v1 can cross processes by
  replaying complete bounded history; typed-state v2 can restore an allowlisted
  runtime graph without replay history. Neither embeds providers or replaces
  host-owned distributed coordination. The incremental callback surface is not
  automatic parity with every batch API.
- **Security boundary:** `safe` and `research` restrict the Python environment but
  are not a complete multi-tenant sandbox. Untrusted scripts require process or
  container/operating-system isolation appropriate to the host's threat model.
- **Compatibility boundary:** the generated capture totals establish evidence only
  for the checked-in fixtures and cases. They do not claim exhaustive Pine API or
  market-scenario compatibility.

## Completed 0.3.0 Development History

The stable-delivery work now includes a real ADX/DI source migration with 80
TradingView-captured market bars, timestamped batch/incremental prefix comparisons,
preview isolation and typed-state continuation. Inspector v2 exposes the existing
advisory migration diagnostics without turning heuristics into capability blocks.
See [migration acceptance](../development/adx_migration_acceptance_zh.md) and the
[delivery ledger](../development/stable_delivery_zh.md). The MPL-2.0 derivative
fixtures remain outside the installed runtime package. The bounded 1/4/8-session,
4096-bar capacity run passed with archived raw events and independently recomputed
statistics; see [capacity acceptance](../development/capacity_acceptance_zh.md).
This is a measured workload range, not a production SLA. Release qualification
completed as recorded in the release readiness report above.

Linux qualification exposed weighted-seed BLAS dispatch overhead and an offline
venv dependency-path gap. Both have focused fixes without relaxed budgets. The
weighted reduction changes unrounded accumulation order, so computation semantics
is now **3** and version-2 snapshots require rebuilding. See
[Linux candidate repairs](../development/linux_candidate_repairs_zh.md);
the combined candidate subsequently passed local and hosted release qualification.

The next acceptance slice is now implemented as five first-party whole-script
workloads: chained TA, multi-context requests, cache/state, drawings, and strategy
lifecycle. It exercises repeated preview/restore, bounded retention, 256-bar
continuation and failure recovery. A separate 40-row TradingView Pine v6 capture
checks the chained TA workload in both execution modes. This capture is covered
by pytest and is not included in the generated capture-family totals above.
See [whole-script acceptance](../development/semantic_workload_acceptance_zh.md)
for evidence, the single-bar HTF confirmation repair, and replay-v1 limitations.

A second slice adds Pine v6 EMA/MACD/RSI boundary and smoothing-composition captures.
It corrects non-missing EMA seeding, sparse EMA/MACD/RSI output and flat RSI, with
checkpoint tests at seed and gap boundaries. The shared EMA path is also checked
against captured batch TSI. See [TA boundary acceptance](../development/ta_boundary_acceptance_zh.md);
these pytest-based captures are separate from the generated totals above.

The third slice verifies native Supertrend warmup (retaining its first zero),
repairs VWMA's independent non-missing observation windows, and fixes incremental
market `strategy.order` OCA effects and filled-sibling lifecycle handling. It has
native/function-formula TA evidence and a strategy capture with reachable
non-OCA and pending OCA controls, exercised by 36 additional tests. See
[trend/volume/OCA acceptance](../development/trend_volume_oca_acceptance_zh.md).

A fourth slice aligns SMA/stdev/variance/BB observation windows and shares stable
incremental moments. Its 30 cases cover native capture, classified high-offset
numeric differences, 9,000-update streams, checkpoints and the previous VWMA
SMA-ratio composition. Two captured high-offset dispersion columns are explicitly
reference-only; Pyne preserves its stable batch arithmetic instead of claiming
parity for them. See [rolling statistics acceptance](../development/rolling_statistics_acceptance_zh.md).

The consolidation slice adds independent snapshot semantics identity. Local,
replay-v1 and typed-state-v2 restore reject legacy/unmarked or incompatible
snapshots with `PYNE_SNAPSHOT_SEMANTICS_MISMATCH`; rebuilding from authoritative
OHLCV is required. Real pre-fix artifacts from `64eb354` exercise the upgrade
boundary. See [snapshot upgrade acceptance](../development/snapshot_semantics_acceptance_zh.md).

Whole-script performance now has a reproducible six-workload, three-age,
three-repeat local baseline with raw timing and allocation samples. Restore and
continuation checks passed. That baseline exposed growing request diagnostic
history despite fixed chart retention. The following slice scopes diagnostics to
the current bar, discloses discarded history and advances snapshot semantics to 2.
See [diagnostic retention acceptance](../development/request_diagnostic_retention_zh.md)
and the historical
[performance baseline](../development/semantic_workload_performance_zh.md).

The following request optimization adds indexed cache interval lookup and avoids
ineffective preview traversal into the already-shared request facade. Nine paired
old/new workload cases retain identical output digests; 1024-bar preview median
paired ratio is 0.440 on the measured host, at a small index memory cost. Cache
budgets are unchanged and semantics-2 portable snapshots remain compatible. See
[paired request acceptance](../development/request_index_preview_zh.md).

The `0.2.0rc1` closure slice is implemented in the repository: package version,
current-status generation, historical-plan routing, local/CI contract checks,
capture parity gates, and distribution smoke checks are now one release-candidate
boundary. No tag, upload, or public release is implied by this repository state.

Earlier `0.3.0rc2` development slices added execution/session cache isolation,
typed provider errors with a reusable conformance kit, incremental TTL/LRU
retention, process-local and portable snapshot/restore, incremental request
support, Render IR v2, batch/incremental parity tooling, multi-session
performance/stability gates, and the first pinned external-library adapter.
The source candidate also includes mode-aware capability discovery, early
incremental diagnostics, Inspector v2 directory and migration manifests, 39
incremental TA helpers, a nine-member pinned library surface, typed-state
portable snapshots, bounded execution trace v2 with opt-in per-span events, and
paired raw-sample restore/trace performance evidence. Typed-state restore
rejects adversarial graph payloads and is covered by repeated long-session
restore testing.
The large plot and TA implementations are split into focused internal modules
without changing established public entry points.

1. **Historical local acceptance:** the `0.3.0rc2` source tree was locally accepted after
   two full `scripts/check.ps1` runs, artifact metadata validation, and an
   isolated installed-wheel smoke that rejects imports escaping its temporary
   environment. This is not a release claim; publishing, tag, remote matrix CI,
   and promoting RC to stable remain a later explicit decision.
2. **Measured expansion:** the frozen 104-file Pine corpus and
   [capability demand backlog](../development/capability_demand_backlog_zh.md)
   currently show no unexplained Runtime core gap and no P0 Incremental TA
   implement item. Phase 4 therefore does not add Incremental helpers; later TA
   or pinned-library additions still require a realtime workload plus parity
   fixtures.

The local wheel, clean-process CLI inspection, typed-state restore, v2 session,
capture parity, and packaged examples are this repository's release gates.
Product-specific bridges, workbenches, data brokers, candidate locks, and
end-to-end adoption tests belong to independent adapter repositories; their
status is not a Pyne Runtime release claim.

Each slice must preserve the existing batch API and output schemas, remain
fail-closed at host boundaries, and pass the full release gate before the next
slice begins.

## Status Interpretation

A capability belongs in the verified section only when the repository has an
implemented public path plus tests or contract fixtures supporting the claim. A
known difference belongs in the boundary section even when a nearby subset works.
The full release gate, including capture-diff comparison, tests, packaging, and
installation smoke checks, remains the acceptance authority for a release.
