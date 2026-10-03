# External Pine libraries

Pyne does not download or execute arbitrary Pine libraries. Each supported
dependency is a pinned, reviewed Python adapter and unknown identifiers fail
closed with `PYNE_UNSUPPORTED_FEATURE`.

The current registry exposes one project-required adapter:

```python
tv_ta = pine_library("TradingView/ta/10")
adaptive_ema = tv_ta.ema2(close, dynamic_length)
adaptive_rma = tv_ta.rma2(close, dynamic_length)
adaptive_atr = tv_ta.atr2(dynamic_length)
up, down, delta = tv_ta.requestUpAndDownVolume("1")
opening, high, low, current = tv_ta.requestVolumeDelta("1", "1D")
```

The pinned adapter is currently a batch-runtime surface. Its explicit nine-member
allowlist is `atr2()`, `cagr()`, `changePercent()`, `ema2()`, `highestSince()`,
`lowestSince()`, `requestUpAndDownVolume()`, `requestVolumeDelta()`, and
`rma2()`. `ema2`, `rma2`, and `atr2` accept a per-bar numeric smoothing length;
invalid non-positive or non-finite lengths reset the recursive value to `na`.

The two volume functions require a host data provider with
`request.security_lower_tf` capability. It categorizes each authoritative
intrabar by comparing its close with its open, returns positive up volume,
negative down volume, and their net delta for every chart bar. Flat intrabars
use the previous valid intrabar close to determine polarity.
`requestVolumeDelta()` additionally accumulates delta within the requested
period and returns opening, highest, lowest, and current CVD values. Empty
intrabar groups remain `na`; the runtime never estimates them from chart OHLCV.

`cagr()` returns `na` until the exit time is reached and for spans shorter than
one day. The pure series members do not require a provider.

Host code can inspect `pn.SUPPORTED_PINE_LIBRARIES`. Each descriptor exposes
both the union `data_requirements` and `requirements_for(members)` so a host can
allocate lower-timeframe access only for the selected volume functions.
`pn.inspect_script()` applies the same member-level rule before execution.
Adding another adapter requires a pinned library identifier, an explicit member
allowlist, semantic tests, and member-specific data requirements.

The identifier is intentionally pinned to `TradingView/ta/10`; newer upstream
library revisions are not silently substituted. These adapters are local,
reviewed implementations. A checked-in 16-bar TradingView capture now parity
gates dynamic `ema2`, `rma2`, and `atr2` together with pivot and traditional
pivot-level behavior: 8 plotted series and 78 checked points currently report
one disclosed pivot startup-context difference and zero unexpected differences.
The raw first pivot remains in the capture and diagnostic difference count.
This evidence applies only to the captured cases and does not promote
the pinned adapter beyond its explicit batch-only allowlist.
