# Request API

`request` is the Pine-like namespace for host-backed data requests.

Pyne does not fetch exchange or broker data by itself. The host application
provides a data provider, and Pyne owns deterministic alignment back to the
chart bars.

The public request API is stable through both `pyne_runtime.request` and the
package top level. These imports continue to work:

```python
from pyne_runtime.request import (
    DataProvider,
    LowerTimeframeSeries,
    OHLCVBar,
    PyneInvalidSymbolError,
    PyneRequestError,
    REQUEST_METADATA_KEY_ALIASES,
    REQUEST_METADATA_SESSION_KEYS,
    REQUEST_METADATA_SYMBOL_KEYS,
    REQUEST_METADATA_TIMEFRAME_KEYS,
    REQUEST_API_VALUES,
    REQUEST_SECURITY_API,
    REQUEST_SECURITY_CAPABILITY_ALIASES,
    REQUEST_SECURITY_LOWER_TF_API,
    REQUEST_SECURITY_LOWER_TF_CAPABILITY_ALIASES,
    RequestCapabilities,
    RequestEvalContext,
    RequestMetadata,
    RequestModule,
    barmerge,
)
```

## Data Provider

A provider implements `get_ohlcv(symbol, timeframe, start, end)`:

```python
import pyne_runtime as pn


class MyProvider:
    capabilities: pn.RequestCapabilities = {
        "request.security": True,
        "request.security_lower_tf": True,
    }

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
    ) -> list[pn.OHLCVBar]:
        if symbol not in self.supported_symbols:
            raise pn.PyneInvalidSymbolError(symbol)
        return [
            {"time": 1710000000, "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 100},
        ]
```

`start` and `end` are the actual inclusive fetch coordinates, not merely the
first and last chart opening timestamps. For a chart with `N` loaded bars, Pyne
initially requests:

```text
warmup_bars = max(N, largest direct field history offset)
start = max(0, chart_start - warmup_bars * requested_timeframe_seconds)
end = last chart bar close boundary
```

If that non-empty response contains fewer than `warmup_bars` actual bars before
`chart_start`, Pyne widens the lookback by a factor of four and retries. It can
widen at most six times, and stops earlier when the requirement is met,
`start` reaches zero, or the provider returns a valid empty list. This is a
bounded best effort: a long market closure, a listing boundary, or unavailable
archive data can still leave requested history unavailable. It is not an
unlimited-history promise.

If the requested timeframe cannot be parsed, observed chart spacing is used for
the initial warmup interval. A valid explicit `time_close` on the final chart
bar defines `end`; otherwise Pyne uses the last positive chart interval, with
the context's derived `time_close` as the single-bar fallback.

For `request.security_lower_tf()`, provider retrieval remains inclusive
`[start, end]`, while grouping uses the final half-open chart bucket
`[last_chart_open, end)`. A lower-timeframe bar opening exactly at `end` is
therefore not part of the last chart bar.

Pass it through `pn.run(..., data_provider=provider)` or
`PyneSettings(data_provider=provider)`. Both public entry points type the
argument as `DataProvider | None` for IDE and static checker support.

```python
result = pn.run(
    """
indicator("Higher TF", overlay=True)
higher_close = request.security("BTCUSDT", "1h", lambda ctx: ctx.close)
plot(higher_close, "1h Close")
""",
    chart_bars,
    data_provider=provider,
    executor_mode="inline",
)
```

When using the process executor, the provider must be pickleable. For local host
adapters with open sockets, database handles, or closures, prefer
`executor_mode="inline"`.

Within one script run, Pyne caches requested contexts by
`(symbol, timeframe, start, end)`. Repeated `request.security()` or
`request.security_lower_tf()` calls for the same requested context reuse the
same provider OHLCV response and requested metadata, while each expression is
still evaluated independently. Pyne does not cache provider data across
separate `pn.run()` executions.

The cache records the final adaptively widened range. If a range exhausts the
six-widening budget without enough pre-chart bars, the same or a smaller warmup
requirement reuses that result instead of repeating the widening sequence. A
larger requirement may continue widening from the cached range.

A legitimate empty provider result (`[]`) is still a successful requested
context: it is cached, records `bars=0`, and reports `status="ok"`. Only
`PyneInvalidSymbolError` converted by `ignore_invalid_symbol=True` reports
`status="ignoredInvalidSymbol"`; those ignored empty results are not cached.
For `request.security_lower_tf()`, `ignore_invalid_timeframe=True` can also
short-circuit an invalid non-lower requested timeframe into empty groups and
records `status="ignoredInvalidTimeframe"`.

Provider bars may arrive out of order. Pyne normalizes the requested context by
sorting returned bars by `time` before higher-timeframe alignment or
lower-timeframe grouping. Duplicate `time` values are allowed for
`request.security_lower_tf()` groups.

Successful request calls append host-facing diagnostics under
`result.meta["requestDiagnostics"]`. Each entry records `api`, `symbol`,
`timeframe`, `start`, `end`, returned `bars`, `cacheHit`,
`ignoreInvalidSymbol`, and `status`. Repeated calls for the same requested
context set `cacheHit=True`. The recorded `start` and `end` are the final actual
range after adaptive widening, not necessarily the initial calculated range.

Providers may optionally declare request capabilities with either a
`capabilities` attribute or a `capabilities()` method:

```python
class MyProvider:
    capabilities: pn.RequestCapabilities = {
        "request.security": True,
        "request.security_lower_tf": True,
    }

    def get_ohlcv(self, symbol, timeframe, start, end):
        ...
```

Accepted aliases:

- `request.security`, `security`, or `ohlcv` for `request.security()`
- `request.security_lower_tf`, `security_lower_tf`, or `lower_tf` for
  `request.security_lower_tf()`

If no capabilities are declared, Pyne assumes the provider can answer both
request types. If `capabilities` is `None`, Pyne treats the provider as
supporting no request capabilities. For dict capabilities, at least one matching
alias must be present and truthy. For list/set/tuple capabilities, the
capability must be present. If a `capabilities()` method or property raises,
Pyne returns `PYNE_RUNTIME_ERROR` with a request-capability-specific message.

Providers may also supply metadata for requested contexts. This is optional;
without it, Pyne uses the requested `symbol` as `syminfo.ticker` /
`syminfo.tickerid`, uses the requested `timeframe` as `timeframe.period`, and
derives session flags from requested bars.

```python
class MyProvider:
    def get_request_metadata(self, symbol: str, timeframe: str) -> pn.RequestMetadata:
        return {
            "syminfo": {
                "tickerid": "BINANCE:BTCUSDT",
                "mintick": 0.01,
                "currency": "USDT",
                "type": "crypto",
            },
            "timeframe": timeframe,
            "session": {"ismarket": True},
        }
```

The same metadata can be exposed as a `request_metadata` mapping or
`request_metadata(symbol, timeframe)` method. Accepted keys are `syminfo` or
`symbol_info`, `timeframe` or `timeframe_info`, and `session` or
`session_info`. Bar-level session flags in requested OHLCV rows still override
the provider-level session default.

The provider contract is also exposed through `pn.schema()["requestProvider"]`.
That schema lists the required `get_ohlcv(...)` method, required OHLCV fields,
stable request APIs under `supportedApis`, capability aliases, metadata keys,
requested-context cache semantics, and stable error categories.

`supportedApis` currently contains `request.security` and
`request.security_lower_tf`. Each entry records the canonical API name, provider
method, accepted capability aliases, result shape, and whether
invalid request contexts can be ignored.

## Provider Error Contract

Hosts can branch on `pn.schema()["requestProvider"]["schemaVersion"]` and
`pn.schema()["requestProvider"]["errorCategories"]` when displaying request
integration failures. Version 10 replaces message-fragment classification with
`pn.RequestProviderErrorCategory` and typed provider exceptions while preserving
the legacy `errors` mapping. Request provider failures also include the matching
category in `result.errorDetail["requestProviderCategory"]` and the failed
request coordinates in `result.errorDetail["requestProviderRequest"]`.

| Category | Code | Calls `get_ohlcv`? | Stable meaning |
| --- | --- | --- | --- |
| `missingProvider` | `PYNE_UNSUPPORTED_FEATURE` | No | No host data provider is configured. |
| `unsupportedCapability` | `PYNE_UNSUPPORTED_FEATURE` | No | Provider capabilities explicitly omit or disable the requested API. |
| `capabilityFailure` | `PYNE_RUNTIME_ERROR` | No | Capability declaration lookup raised unexpectedly. |
| `invalidSymbol` | `PYNE_INVALID_SYMBOL` | Yes | Provider raised `PyneInvalidSymbolError`; `ignore_invalid_symbol=True` returns `na` values for `request.security()` and empty groups for `request.security_lower_tf()`. |
| `providerFailure` | `PYNE_RUNTIME_ERROR` | Yes | `get_ohlcv(...)` raised an unexpected exception. |
| `invalidReturnType` | `PYNE_RUNTIME_ERROR` | Yes | `get_ohlcv(...)` returned `None` or a non-list value. |
| `invalidBarShape` | `PYNE_RUNTIME_ERROR` | Yes | Returned bars are not mappings or do not satisfy the OHLCV contract. |
| `invalidMetadata` | `PYNE_RUNTIME_ERROR` | Yes | Requested-context metadata is not a mapping. |
| `metadataFailure` | `PYNE_RUNTIME_ERROR` | Yes | Metadata lookup raised unexpectedly. |
| `expressionFailure` | `PYNE_RUNTIME_ERROR` | Yes | A callable request expression raised unexpectedly. |

`requestProviderRequest` contains `api`, `symbol`, `timeframe`, `start`, and
`end`, matching the provider range for the failed call. If a later adaptive
widening attempt fails, these coordinates identify that final attempted range.
The category table is contract-tested against both `request.security()` and
`request.security_lower_tf()` so host error handling can branch on the same
schema for either request API.

Provider code should raise `pn.PyneInvalidSymbolError(symbol)` for invalid
symbols. The exception exposes a stable `.symbol` attribute while preserving the
message passed to `Exception`. Provider adapters can raise
`PyneProviderCapabilityError`, `PyneProviderDataError`, or
`PyneProviderMetadataError` for typed failures at those boundaries. Runtime and
adapter errors use
`pn.PyneRequestError`, which exposes stable `.code`, `.category`, and
`.request_context` attributes. Hosts normally consume those fields through the
serialized `result.errorDetail` contract, but the exception attributes are
public for inline adapters and tests. Human-readable exception text is not a
classification contract.

## Provider Conformance Kit

`pn.run_data_provider_conformance(...)` checks capability declarations, OHLCV
shape, metadata normalization, runtime result shape, diagnostics, and optionally
typed invalid-symbol behavior. It returns a `ProviderConformanceReport` without
requiring pytest. `pn.assert_data_provider_conformance(...)` runs the same checks
and raises one compact `AssertionError`, which makes it convenient in any CI
test runner.

```python
pn.assert_data_provider_conformance(
    provider,
    chart_ohlcv=chart_bars,
    symbol="BTCUSDT",
    timeframe="5",
    lower_timeframe="1",
    invalid_symbol="NOT_A_REAL_SYMBOL",
)
```

For IDE and static typing support, Pyne exports provider typing helpers at both
`pyne_runtime.request` and the package top level:

- `OHLCVBar`: typed dictionary for provider-returned OHLCV rows.
- `REQUEST_SECURITY_API`, `REQUEST_SECURITY_LOWER_TF_API`, and
  `REQUEST_API_VALUES`: canonical stable request API names used by diagnostics,
  schema entries, and capability checks.
- `REQUEST_SECURITY_CAPABILITY_ALIASES`: accepted aliases for
  `request.security()` capability declarations.
- `REQUEST_SECURITY_LOWER_TF_CAPABILITY_ALIASES`: accepted aliases for
  `request.security_lower_tf()` capability declarations.
- `REQUEST_METADATA_SYMBOL_KEYS`, `REQUEST_METADATA_TIMEFRAME_KEYS`, and
  `REQUEST_METADATA_SESSION_KEYS`: accepted provider metadata keys for the
  corresponding requested-context metadata groups.
- `REQUEST_METADATA_KEY_ALIASES`: grouped metadata key aliases matching
  `pn.schema()["requestProvider"]["metadata"]["acceptedKeys"]`.
- `RequestCapabilities`: accepted capability declaration shapes.
- `RequestMetadata`: typed dictionary for requested-context metadata.
- `DataProvider`: protocol for objects passed to `pn.run(..., data_provider=...)`
  or `PyneSettings(data_provider=...)`.
- `RequestCapabilityProvider`: optional protocol for method-based capability
  declarations.
- `RequestMetadataProvider`: optional protocol for method-based metadata
  declarations.
- `RequestProviderErrorCategory`: stable typed category enum.
- `PyneProviderError` and its capability/data/metadata subclasses: typed
  provider-side failure signals.
- `ProviderConformanceReport`, `run_data_provider_conformance()`, and
  `assert_data_provider_conformance()`: reusable provider contract checks.

## `request.security`

```python
request.security(
    symbol,
    timeframe,
    expression,
    gaps="off",
    lookahead="off",
    ignore_invalid_symbol=False,
)
```

Supported now:

- `expression` as an OHLCV field series, such as `close`, `high`, or `hlc3`
- history references on fields, such as `close[1]`
- `expression` as a field name string, such as `"close"`
- `expression` as a callable thunk, such as `lambda ctx: ctx.ta.ema(ctx.close, 20)`
- tuple/multi-return expressions that can be unpacked in Python
- `gaps="off"` or `gaps=barmerge.gaps_off`: carry the latest requested value forward
- `gaps="on"` or `gaps=barmerge.gaps_on`: only emit values on exact requested bar timestamps
- `lookahead="off"` or `lookahead=barmerge.lookahead_off`: use the latest requested bar at or before each chart bar
- `lookahead="on"` or `lookahead=barmerge.lookahead_on`: use the next requested bar at or after each chart bar
- `ignore_invalid_symbol=True`: return `na` values when the provider raises
  `pn.PyneInvalidSymbolError`

Pyne also accepts the string aliases `"gaps_on"`, `"gaps_off"`,
`"lookahead_on"`, `"lookahead_off"`, `"barmerge.gaps_on"`,
`"barmerge.gaps_off"`, `"barmerge.lookahead_on"`, and
`"barmerge.lookahead_off"`. Unknown `gaps` or `lookahead` values return
`PYNE_UNSUPPORTED_FEATURE` before the provider is called.

String history references use non-negative bars-back offsets. For example,
`"close[1]"` is supported, while `"close[-1]"` is an unsupported forward
reference and returns `PYNE_UNSUPPORTED_FEATURE`.

## Expression Thunks

Python evaluates function arguments before `request.security()` receives them.
That means Pyne cannot capture this expression for recalculation in the
requested context:

```python
request.security("BTCUSDT", "1h", ta.ema(close, 20))  # unsupported
```

Use a callable expression thunk instead:

```python
higher_ema = request.security(
    "BTCUSDT",
    "1h",
    lambda ctx: ctx.ta.ema(ctx.close, 20),
)
```

The `ctx` object is a calculation-only requested context. It exposes:

- `ctx.open`, `ctx.high`, `ctx.low`, `ctx.close`, `ctx.volume`
- `ctx.time`, `ctx.time_close`, `ctx.bar_index`, `ctx.last_bar_index`, `ctx.barstate`
- `ctx.hl2`, `ctx.hlc3`, `ctx.ohlc4`, `ctx.hlcc4`
- `ctx.syminfo`, `ctx.timeframe_info`, `ctx.session`
- `ctx.ta`
- `ctx.when()`, `ctx.where()`, `ctx.switch()`

History references inside the thunk are applied in the requested context:

```python
higher_prev = request.security("BTCUSDT", "1h", lambda ctx: ctx.close[1])
```

Callable expressions may return a single series-like value, a scalar, or a tuple
of series-like values:

```python
higher_open, higher_close = request.security(
    "BTCUSDT",
    "1h",
    lambda ctx: (ctx.open, ctx.close),
)
```

Field tuples are also supported:

```python
higher_high, higher_low = request.security("BTCUSDT", "1h", ("high", "low"))
```

Dicts, object handles, and nested request outputs are rejected.

Unsupported for now:

- direct capture of already evaluated Python expressions, such as `ta.ema(close, 20)`
- nested request expressions
- provider-owned lookahead or gap semantics

If no data provider is configured, `request.security()` returns a
`PYNE_UNSUPPORTED_FEATURE` error.

If a provider raises `pn.PyneInvalidSymbolError`, the default behavior is a
`PYNE_INVALID_SYMBOL` error. With `ignore_invalid_symbol=True`, Pyne returns
`na` values for that request. Other provider exceptions are not treated as
invalid symbols; Pyne wraps them as `PYNE_RUNTIME_ERROR` with a
`request data provider failed` message.

If provider metadata is not a mapping, or a metadata callback raises, Pyne also
returns `PYNE_RUNTIME_ERROR` with a request-metadata-specific message.

## `request.security_lower_tf`

```python
request.security_lower_tf(
    symbol,
    timeframe,
    expression,
    ignore_invalid_symbol=False,
    ignore_invalid_timeframe=False,
)
```

`request.security_lower_tf()` requests lower-timeframe OHLCV from the same host
provider and returns an array-per-chart-bar object. Pyne evaluates the
expression in the requested lower-timeframe context, then groups requested bars
into chart-bar buckets using `[chart_time, next_chart_time)`.

Timeframe suffixes preserve case: lowercase `m` means minutes (`15m`), while
uppercase `M` means months (`1M`).

```python
lower = request.security_lower_tf("BTCUSDT", "1", lambda ctx: ctx.close)
plot(lower.size(), "Lower TF Count")
plot(lower.last(), "Lower TF Last Close")
plot(lower.max(), "Lower TF High")
```

Supported now:

- field expressions such as `close`, `"close"`, or `("high", "low")`
- callable thunks such as `lambda ctx: ctx.ta.sma(ctx.close, 3)`
- tuple/multi-return expressions
- bars-back on the grouped result, such as `lower[1].last()`
- `ignore_invalid_symbol=True`: return empty lower-timeframe groups when the
  provider raises `pn.PyneInvalidSymbolError`
- `ignore_invalid_timeframe=True`: return empty lower-timeframe groups when the
  requested timeframe is not lower than the chart timeframe and can be
  recognized from chart bar spacing

The returned object exposes:

- `.to_lists()`: Python lists of requested values per chart bar
- `.size()`: number of lower-timeframe bars per chart bar
- `.first(default=na)`: first grouped value per chart bar
- `.last(default=na)`: last grouped value per chart bar
- `.get(index, default=na)`: value at a zero-based index in each group
- `.sum(default=na)`, `.min(default=na)`, `.max(default=na)`, `.avg(default=na)`:
  numeric aggregations for each group

Provider capability negotiation uses the same mechanism described above. If the
provider explicitly disables lower-timeframe requests or omits the capability
from a list/set declaration, Pyne returns `PYNE_UNSUPPORTED_FEATURE` without
calling `get_ohlcv(...)`.

## Incremental Callbacks

Incremental scripts use the same provider, capability, metadata, and error
contract through `ctx.request`:

```python
def on_bar(ctx, bar):
    higher_close = ctx.request.security(
        "BTCUSDT", "60", lambda requested: requested.close
    )
    lower_closes = ctx.request.security_lower_tf(
        "BTCUSDT", "1", lambda requested: requested.close
    )
```

`ctx.request.security()` returns the value aligned to the current chart bar.
`ctx.request.security_lower_tf()` returns a `PyneArray` for the current chart
bar's lower-timeframe group. The session reuses authoritative provider ranges
across callbacks and fetches only uncovered ranges. Cached rows and covered
ranges are bounded by `request_cache_max_bars` and `cache_max_items`; dropping cache coverage
only causes a later authoritative refetch.

Successful calls publish the same typed entries under
`result.meta["requestDiagnostics"]`. Preview diagnostics remain isolated from
the committed result, while immutable provider evidence fetched by a preview
may warm the bounded session cache for the later confirmed callback.
Portable session snapshots never serialize a provider; provider-backed restore
must receive compatible `PyneSettings` or an explicit provider again.

## Golden Coverage

The request test suite includes deterministic fixtures and TradingView-backed
external captures for:

- higher-timeframe `gaps` and `lookahead` alignment
- history references evaluated in the requested context
- tuple field expressions and tuple callable thunks
- requested-context `time_close`, `session.*`, and `timeframe_info.*` isolation
  from chart metadata in both higher-timeframe and lower-timeframe requests
- lower-timeframe `[chart_time, next_chart_time)` grouping
- empty lower-timeframe buckets and aggregation defaults
- invalid-symbol ignore behavior and provider capability rejection before
  provider calls
- requested-context cache reuse within one script run and cache reset across
  separate `pn.run()` executions
- provider failure and provider metadata contract failures
- TradingView-backed request capture parity for `request.security()` and
  `request.security_lower_tf()` across HTF, LTF, same-timeframe, invalid
  symbol/timeframe ignore paths, requested-context metadata, timezone/session
  fields, lower-timeframe array helpers, and requested OHLCV field replay

The request capture gate currently keeps 21/21 fixtures in parity with
TradingView exports. The broader release gate also checks strategy and TA
TradingView-backed captures, so request changes are validated alongside the
host-facing strategy and indicator evidence.

## Internal Responsibilities

The request implementation is split into focused helpers while keeping the same
public namespace:

- `request.provider` defines the provider protocol, capability checks, and
    requested metadata defaults.
- `request.eval` owns `RequestEvalContext`, field lookup, history references,
    callable expression thunks, and expression-result normalization.
- `request.alignment` owns `barmerge` constants plus gaps/lookahead alignment.
- `request.lower_tf` owns lower-timeframe grouping and numeric aggregations.
- `request.errors` owns stable request exception types and error codes.
- `request.module` keeps the user-facing `RequestModule` facade, provider
    calls, requested-context caching, and error conversion.

This boundary keeps provider integration, expression evaluation, bar alignment,
and lower-timeframe grouping independently testable without changing script
syntax or result shape.
