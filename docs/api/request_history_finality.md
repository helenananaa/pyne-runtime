# Optional request history finality

An incremental provider can opt into `RequestHistoryFinalityProvider`, exported
by both `pyne_runtime` and `pyne_runtime.request`:

```python
def get_finalized_through(self, symbol: str, timeframe: str) -> int | None:
    return self.complete_immutable_history_watermark(symbol, timeframe)
```

The return value is an **inclusive bar opening-time coordinate in Unix seconds**.
For the supplied symbol and timeframe, the provider promises that every future
`get_ohlcv()` response includes all rows in the fetched range opening at or before
the watermark. Their data is complete and immutable, and a coordinate that has
no row cannot later receive one. This is a promise about actual provider history,
including gaps, trading breaks and listing boundaries. It is not inferred from
the newest observed row, current clock, nominal timeframe or chart progress.
Python integers, including negative Unix timestamps, are supported; booleans,
floats, strings and other values are not watermarks. `None` means no promise.

Only supply this method when the data source can uphold both completeness and
immutability. A source that permits delayed historical rows or historical
corrections must keep its watermark below those coordinates. To retract a prior
promise, return `None` or a lower watermark **before** returning the revised
history. Data availability, acquisition, finality decisions and any exchange
or host integration remain the provider's responsibility.

The runtime samples the optional method on incremental provider reads. It
records absence only within successfully fetched ranges intersecting the
watermark and the safely ended requested history. Advancing the watermark does
not retroactively certify a previously incomplete response: newly finalized
coordinates must be fetched once before their gaps are cached. Later callbacks
can therefore fetch only an expanding or changing tail, even with sparse
timestamps or entirely empty finalized history.
When a watermark is available, ended rows above it also remain refreshable;
their earlier close does not certify a provider's incomplete or revisable
history. Enabling a promise after prior unpromised reads first refetches those
observations instead of treating them as already certified.

Requested bars that are active at the callback time always refresh, including
previews and the closing callback. A future watermark cannot freeze them.
An explicit valid `time_close` takes precedence over a nominal duration. For
calendar periods, tick periods and unknown durations, the runtime does not
cache absence; rows with an explicit ended `time_close` can be reused only
within a provider's completeness and immutability promise.
Without an explicit close, fixed intraday periods use their nominal duration.

Without the method, or with `None`, each evaluation refreshes the requested
range. An ended observation alone cannot prove that its timestamp group is
complete: another legitimate row with the same opening time may arrive later.
Repeated requests may reuse the requested context within a callback, while
later callbacks refetch the range. This permits both delayed historical arrivals
and additional duplicate-time rows to become visible.
The optional contract changes retrieval reuse, not expression alignment.

A withdrawn or regressed watermark, an invalid return value, a noncallable
attribute, or an exception while reading finality discards the affected
context's rows and coverage. That read falls back to conservative retrieval.
It does not fail a healthy computation because optional optimization metadata
is unavailable. Normal `get_ohlcv()` failures retain the established request
error behavior. The next valid declaration may enable caching again after a
fresh response. A backwards callback clock also discards derived cache evidence
so formerly ended rows refresh when they become active.

`ctx.request.cache_stats()` retains `series`, `bars`, `coveredRanges` and
`fetches`, and adds:

- `finalityFallbacks`: number of invalid or withdrawn finality observations
  that triggered conservative retrieval during this runtime's lifetime.
- `finalizedThrough`: a list of `{symbol, timeframe, time}` declarations bound
  to retained cache contexts. These are provider promises, not claims that all
  coordinates up to that timestamp have already been fetched. Active bars can
  remain refreshable even below a declared future watermark.

The row budget `request_cache_max_bars` and coverage budget `cache_max_items`
remain recoverable cache limits. Eviction removes rows, coverage and their
associated watermark together; the current request still returns its fetched
rows. Finality declarations and negative coverage are derived operational
state, excluded from committed state snapshots. A new restored session checks
the selected provider again and rebuilds its cache; replay restoration can
repopulate it while replaying. Previews may share finalized evidence but do not
change committed calculation results.
