# `ta` API

The `ta` namespace is injected into scripts.

Development semantics 37 corrects DMI initialization: its smoothed true-range
denominator skips the first bar, which has no previous close. Public TR and ATR
retain their first-bar high-low fallback. Direct built-in TradingView captures
cover 64 initial monthly and weekly bars, DMI lengths 3 and 7, and ADX smoothing
lengths 3 and 7. They do not qualify every missing-OHLC or parameter combination.
Genuine semantics-36 state and replay snapshots are rejected before session
construction; rebuild from authoritative caller-supplied OHLCV.

Development semantics 36 makes `ta.rma` and `ctx.ta.rma(...).update(...)` emit
missing output on missing input while preserving the smoothing accumulator.
Missing observations do not advance the seed count or restart the average;
the next present input continues from the previous state. A native 64-bar
holdout covers five periods, leading gaps, missing runs, flat segments and
ordinary regime changes alongside EMA and RSI. ATR and DMI keep their previous
composition-specific missing-output behavior, which this holdout does not qualify.
Genuine semantics-34 and intermediate semantics-35 snapshots
require rebuilding from authoritative caller-supplied OHLCV; they are rejected
before session construction. The independent capture does not qualify every
recursive-TA input or parameter combination.

Batch and incremental SMA(1) return the latest present observation exactly;
leading missing values remain unready and later missing values carry that
observation. This single-observation identity avoids cumulative subtraction
roundoff. Multi-observation rolling arithmetic still has measured native
large-offset differences; output display precision does not hide them.

`pivothigh`/`pivotlow` confirm after the requested right span and require a full
left/right startup span. Equal extrema are allowed on the left and rejected on
the right; comparison stops at the nearest missing sample on each side. These
rules match three independent native probes in batch and incremental execution
and change computation semantics to 8. See
[official alignment evidence](../development/official_alignment_goal_zh.md).

`rising`/`falling` use the latest `period` valid adjacent comparisons. A comparison
with either input missing does not enter or advance that window; it does not
compare across the gap. Until enough valid comparisons exist, the result is false.
All observed comparisons must be strict; equal inputs are false observations.
These are batch helpers and remain available to ordinary Python computations.
Native/formula controls and generic Python replay checks substantiate semantics 9.

`cum` emits no value on a missing input but retains the sum for the next present
input. `obv` uses cumulative signed adjacent-close change times volume and follows
that same missing-output rule. Crossing helpers compare the current pair against
the last pair where both operands were present. `cross` requires strict sign
reversal; `crossover`/`crossunder` allow the previous pair to be equal. Missing
current pairs emit false without replacing that prior pair. Native and independent
formula evidence substantiate these semantics-10 corrections in both modes.

`keltner` defaults to EMA middle plus/minus EMA-smoothed true-range width in
computation semantics 11. The first true range is missing, since there is no prior
close. The return order remains `(upper, middle, lower)`. `source=` selects the
middle input independently of OHLC; `use_true_range=False` selects high-minus-low
width. The multiplier must be positive. Fifteen native cases and independent
EMA controls cover these options, including missing sources. Select
`width_smoothing="atr"` explicitly to retain the earlier ATR-width formula;
that option requires true range. This remains a batch helper; ordinary Python
callbacks may invoke it without adding a scalar incremental TA capability.

Development semantics 34 makes batch rolling-sum fallback admission causal:
later small values, cancellation or overflow cannot select a different algorithm
for an earlier output. Incremental SMA and Bollinger middle values maintain an
exact sum of finite present observations, independently of the centered variance
state. This preserves small tails after a large historical level and finite
means when the unnormalized sum exceeds binary64 range. Genuine semantics-33
snapshots require rebuilding from authoritative caller-supplied OHLCV.
The new 96-row native history probe retains official large-prefix arithmetic
residues as strict disagreements; these runtime consistency repairs do not
establish numerical equivalence with every native accumulation history.

Common helpers:

Development semantics 30 computes `correlation` from independent non-missing
observation windows for each input and their product. Around gaps these windows
can describe different bars, so the output can exceed `[-1, 1]`. A ready zero
numerator and zero standard-deviation denominator returns zero; a nonzero
numerator with zero denominator remains missing. Coherent finite windows retain
centered Pearson arithmetic for large-offset stability. Native large-offset and
selected shifted-input rounding disagreements remain counted in the alignment
report; this is not bit-for-bit numerical equivalence across every scale.
Fresh native arithmetic decomposition retains 64 rows and eight correlation
cases. The guarded raw-moment formula matches all 512 native results, while
unguarded and scaled-sum formulas have counterexamples. Logged operands and
primitive products round-trip exactly; separate native newest/oldest/Kahan/
Neumaier/paired folds still disagree with native SMA at periods 3 and 7.
This explains a finite native branch but does not qualify a Pyne replacement:
the current kernel remains unchanged and every new runtime disagreement is
counted. Run `scripts/correlation_arithmetic_diagnostic.py` to reproduce the
explanation and rejected alternatives without inflating runtime agreement.
There is no declared direct `ctx.ta.correlation` helper; a full-Python callback
may call the batch calculation with retained history.

```python
ta.sma(close, 20)
ta.ema(close, 20)
ta.wma(close, 20)
ta.vwma(close, 20)
ta.vwap(close)
ta.hma(close, 20)
ta.swma(close)
ta.alma(close, 20, 0.85, 6)
ta.rsi(close, 14)
ta.cmo(close, 14)
ta.wpr(14)
ta.tsi(close, 25, 13)
ta.macd(close, 12, 26, 9)
ta.mom(close, 10)
ta.linreg(close, 20, 0)
ta.correlation(close, open, 20)
ta.stoch(close, high, low, 14)
ta.cci(close, 20)
ta.mfi(close, 14)
ta.dmi(14, 14)
ta.sar(0.02, 0.02, 0.2)
ta.supertrend(3, 10)
ta.bb(close, 20, 2)
ta.dev(close, 20)
ta.variance(close, 20)
ta.percentile_nearest_rank(close, 20, 50)
ta.percentile_linear_interpolation(close, 20, 50)
ta.atr(14)
ta.highest(close, 20)
ta.lowest(close, 20)
ta.highestbars(close, 20)
ta.lowestbars(close, 20)
ta.barssince(close > open)
ta.valuewhen(close > open, close, 0)
ta.cross(a, b)
ta.crossover(a, b)
ta.crossunder(a, b)
```

Several helpers are also exposed as top-level script functions, such as `cross()`, `crossover()`, `crossunder()`, `highest()`, and `lowest()`.

`ta.bb(source, length, mult)` follows Pine's tuple order:
`middle, upper, lower = ta.bb(close, 20, 2)`.

`ta.vwap()` supports Pine's anchored overloads:

```python
session_vwap = ta.vwap(hlc3)
anchored_vwap = ta.vwap(close, timeframe.change("1W"))
value, upper, lower = ta.vwap(close, timeframe.change("1D"), 2.0)
```

When `anchor` is explicit, output stays `na` until the first true anchor and
then resets on every later true value. Without an explicit anchor, Pyne uses
recurring host `session.isfirstbar` markers when available; otherwise it uses
daily boundaries in `syminfo.timezone`. The v4 spelling `vwap(source)` is also
available as a top-level alias.

VWAP has deterministic semantic unit tests, including reset and weighted
standard-deviation behavior, but it is not yet part of the nine imported
TradingView TA capture fixtures. Its broader numerical parity therefore
remains best-effort until a dedicated capture is added.

`ta.pivot_point_levels(type, anchor, developing=False)` returns a `PyneArray`
containing eleven chart-aligned series in Pine order:
`P, R1, S1, R2, S2, R3, S3, R4, S4, R5, S5`.

```python
levels = ta.pivot_point_levels("Traditional", timeframe.change("1W"))
pivot = array.get(levels, 0)
r1 = array.get(levels, 1)
plot(pivot, "Weekly P")
plot(r1, "Weekly R1")
```

With `developing=False`, a true anchor calculates levels from the completed
period and holds them until the next anchor. With `developing=True`, levels
recalculate from the current partial period on each bar, starting at bar zero
when no anchor has occurred. Supported types are `Traditional`, `Fibonacci`,
`Woodie`, `Classic`, `DM`, and `Camarilla`. As in Pine, Woodie cannot be
combined with developing levels. Formula and reset semantics have deterministic
tests, but no imported TradingView capture fixture yet.

Several context-aware helpers also follow Pine's argument order:
`ta.stoch(source, high, low, length)`, `ta.cci(source, length)`,
`ta.mfi(source, length)`, and `ta.supertrend(factor, atrPeriod)`.

`ta.highestbars(source, length)` and `ta.lowestbars(source, length)` return the
negative bars-back offset to the earliest occurrence of the highest or lowest
value in the rolling window. Missing source resets extrema windows; after the
initial lookback span, its bars-back output is `0` while its value is missing.
For valid input, `0` means the current bar is the selected extreme. Batch and
incremental extrema and Stoch wait the initial lookback span. Missing input
clears extrema candidates without restarting that dataset-origin clock. Stoch
holds its last computed value on missing input or a flat denominator after
readiness; it cannot fabricate a value before readiness. Retained native logs
are compared from the first bar, including missing masks and timestamps.
Sparse imported chart-window records have 32 unresolved startup conflicts;
their earlier history is not independently retained. These remain counted.
See [extrema acceptance](../development/extrema_boundaries_acceptance_zh.md).

Percentiles wait for a complete bar span. Finite inputs use rank selection and
Hazen linear interpolation. Missing inputs retain rolling order-update state:
missing slots append at the end, expired missing slots are removed by their bar,
and expired numeric slots are removed from the rightmost equal value. A numeric
replacement moves from that slot, crossing missing entries; downward moves cross
equal entries, upward moves stop on equality. Thus identical current windows may
produce different values after different earlier histories. Missing slots at the
selected/interpolated positions produce missing output.

Four native fixtures and a separate frozen-model holdout qualify 32,640 output
cells, including fractional percentages and periods 5/9/17. The older insertion
formula remains rejected by 188 of 3,680 cells. Complete finite arrays retain
O(n log n) Fenwick computation; missing arrays use O(n*period) list updates and
O(period) order state. Arrays containing infinity retain the prior Python-only
complete-window contract; native infinity parity is not established. No scalar
incremental percentile helper is declared; generic Python callbacks can replay
these batch functions.
See [official alignment evidence](../development/official_alignment_goal_zh.md).

`ta.barssince(condition)` returns the number of bars since the condition was
last true. `ta.valuewhen(condition, source, occurrence)` returns the source
value from the most recent matching condition, or an older match when
`occurrence` is greater than zero.

TA helpers are series-aware, so history references compose naturally:

```python
plot(ta.mom(close[1], 10), "Shifted Momentum")
marker(ta.cross(close, ta.sma(close, 20)), text="Cross")
```

## Golden Coverage

The TA golden suite includes deterministic fixtures for core moving averages,
Wilder smoothing, RSI, rolling extremes, bars-back extreme offsets,
`barssince()`, `valuewhen()`, MACD, Bollinger Bands, ATR, ALMA, DMI, and
Parabolic SAR, HMA, SWMA, CMO, Williams %R, TSI, rolling percentiles, mean
absolute deviation, variance, stochastic, CCI, MFI, VWMA, and Supertrend.
Anchored VWAP is covered by deterministic runtime tests but is intentionally
not counted in that imported-capture list.

`ta.macd()` follows Pine's tuple shape: MACD line, signal line, and histogram,
where histogram is `macd_line - signal_line`. The signal line starts after the
first `signal` non-`na` MACD-line observations, which need not be contiguous.

## EMA, MACD and RSI Missing Values

The 2026-09-07 Pine v6 captures fix these semantics in batch and incremental mode:

- EMA seeds with the mean of the first `period` non-missing observations,
  including when leading or internal missing values interrupt the seed window.
- A missing EMA input produces a missing output at that position. Its previous
  recursive state is retained for the next present input; no stale value is
  emitted on the gap itself. MACD and its signal EMA follow the same rule.
- RSI requires `period` present adjacent-bar changes. Missing source values and
  the first source after each gap cannot produce a change, so both positions
  emit missing output without advancing Wilder averages.
- After warmup, all-flat RSI (zero average gain and loss) is 100, all-gain RSI
  is 100, and all-loss RSI is 0, matching the captured Pine v6 behavior.

Incremental helpers return `None` for missing outputs; batch arrays contain NaN.
Plot transport omits those points and rounds present values to eight decimals.
The capture tests compare timestamps as well as numbers, including the omissions.

The shared batch EMA kernel also feeds nested RSI-to-EMA smoothing and TSI;
these composition paths have a separate external capture. Incremental TSI remains
outside the declared surface. See [boundary acceptance](../development/ta_boundary_acceptance_zh.md)
for source scripts, raw evidence, tests and upgrade implications.

## VWMA and Supertrend Boundary Evidence

VWMA maintains independent windows of the last `period` non-missing
`source * volume` and volume observations. Both windows must be ready; a
non-positive denominator produces missing output. Missing price samples do not
become zero contributions to a fixed bar window. Because the two windows may
cover different timestamps, the result is not necessarily a weighted average of
paired prices from the last `period` chart bars.

This is verified against native Pine v6 `ta.vwma` for missing price inputs and
against its explicit SMA-ratio formula for custom missing volume. The latter is
formula evidence, not a claim that Pine's built-in volume was overridden. Batch
and incremental paths use the same observation-window contract.

Native Pine v6 `ta.supertrend(2, 3)` and `ta.supertrend(2, 1)` both emit 0 for
the first line point and +1 direction in the captured first-bar context. This
counterintuitive behavior is intentionally retained. See the
[trend/volume/OCA acceptance report](../development/trend_volume_oca_acceptance_zh.md).

## SMA, Dispersion and Bollinger Windows

SMA, variance, standard deviation and Bollinger Bands now use the last `period`
non-missing observations. Once ready, a missing input retains the current result;
leading/all-missing inputs remain missing until enough observations arrive.
Sample variance at period 1 remains missing. `bb` keeps `(middle, upper, lower)`;
incremental `boll` keeps its legacy `(upper, middle, lower)` order.

Under computation semantics 31, a ready finite period-one population variance
and standard deviation are exactly zero. The mean is exactly the latest present
observation, so period-one BB middle/upper/lower coincide with it. Missing inputs
carry that ready result; leading/all-missing input remains missing. The retained
native probe covers eight ordinary, fractional, missing and large-offset profiles
with all 48 outputs counted at absolute tolerance 1e-8. Python infinity and
extreme exponent controls are tested separately and do not establish native parity.

Incremental helpers share centered rolling moments with periodic rebasing, instead
of subtracting raw price-squared totals. This follows the existing stable batch
numeric contract. A new native Pine v6 capture validates ordinary-range windows
and classifies two high-offset columns as **reference-only**: Pine reported
variance 0 or 128 around 1e9 for samples whose centered variance is single-digit.
Pyne uses centered-arithmetic evidence for these columns and explicitly does not
claim numeric parity there. See [rolling statistics acceptance](../development/rolling_statistics_acceptance_zh.md).

All 10 committed TA capture fixtures keep a `pine_equivalent` script beside
the Pyne script and contain imported TradingView output. The parity gate
currently checks 104 plots and 1,353 points with one disclosed chart-history
startup difference and 32 unresolved unexpected startup differences after the
dataset-origin readiness correction. Their original source/log and prior
history are not independently retained. The capture parity gate fails, and
these imported records cannot qualify the current candidate. This evidence
applies to the captured inputs and configured tolerances; behavior outside
those fixtures remains best-effort and should add a new capture before a
broader parity claim is made.

Six retained native direction/percentile fixtures also have complete generic
Python callbacks importing `pyne_runtime.ta.TaModule`. They retain source history
and recompute batch arrays on each bar. Native output, preview isolation,
confirmed history and local/replay/state continuation are measured for those
fixtures; explicit display/replay retention keeps computation history separate.
The route does not add `ctx.ta.rising`, `ctx.ta.falling` or direct percentile step
helpers to the declared 39-method incremental API. Full-history recomputation and
current-state growth remain unbounded; a shorter display/replay history does not
make this computation a bounded streaming helper. Default budgets remain `None`.

