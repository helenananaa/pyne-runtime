# Whole-script semantic workloads

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

## TradingView evidence

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
