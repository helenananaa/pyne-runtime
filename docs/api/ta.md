# `ta` API

The `ta` namespace is injected into scripts.

Common helpers:

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
number of bars back to the most recent highest or lowest value in the rolling
window. A return value of `0` means the current bar is the extreme.

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

Incremental helpers share centered rolling moments with periodic rebasing, instead
of subtracting raw price-squared totals. This follows the existing stable batch
numeric contract. A new native Pine v6 capture validates ordinary-range windows
and classifies two high-offset columns as **reference-only**: Pine reported
variance 0 or 128 around 1e9 for samples whose centered variance is single-digit.
Pyne uses centered-arithmetic evidence for these columns and explicitly does not
claim numeric parity there. See [rolling statistics acceptance](../development/rolling_statistics_acceptance_zh.md).

All 10 committed TA capture fixtures keep a `pine_equivalent` script beside
the Pyne script and contain imported TradingView output. The parity gate
currently checks 104 plots and 1,353 points with zero differences. This evidence
applies to the captured inputs and configured tolerances; behavior outside
those fixtures remains best-effort and should add a new capture before a
broader parity claim is made.

