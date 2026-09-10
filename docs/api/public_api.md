# Public API

Pyne Runtime keeps a small public API surface at the package root.

Stable imports:

```python
import pyne_runtime as pn

pn.run
pn.read_ohlcv
pn.from_pandas
pn.validate
pn.schema
pn.runtime_capabilities
pn.capability_diagnostics
pn.inspect_script
pn.inspect_path
pn.__version__

pn.PyneData
pn.PyneBarState
pn.PyneIncrementalBarState
pn.PyneResult
pn.PyneSettings
pn.PyneResourceLimitError
pn.PyneStateContractError
pn.PyneSecurityError
pn.PyneSeries
pn.PyneStateNamespace
pn.PyneVar
pn.PyneRuntime
pn.PyneIncrementalSession
pn.PyneIncrementalSessionSnapshot
pn.PynePortableSnapshotError
pn.PyneIncrementalSessionCapacityError
pn.PyneIncrementalSessionManager
pn.SharedPyneIncrementalSession
pn.IncrementalParityDifference
pn.IncrementalParityReport
pn.run_incremental_parity
pn.SymbolInfo
pn.TimeframeInfo
pn.SessionInfo
pn.SessionNamespace
pn.ArrayNamespace
pn.MapNamespace
pn.MatrixNamespace
pn.OrderNamespace
pn.PyneArray
pn.PyneMap
pn.PyneMatrix
pn.array_namespace
pn.map_namespace
pn.matrix_namespace
pn.order_namespace
pn.Color
pn.color
pn.PyneMath
pn.PineLibraryDescriptor
pn.PineLibraryRegistry
pn.SUPPORTED_PINE_LIBRARIES
pn.TRADINGVIEW_TA_10
pn.StringNamespace
pn.string_namespace
pn.TickerNamespace
pn.TimeNamespace
pn.ObjectRef
pn.DataProvider
pn.LowerTimeframeSeries
pn.OHLCVBar
pn.REQUEST_METADATA_KEY_ALIASES
pn.REQUEST_METADATA_SESSION_KEYS
pn.REQUEST_METADATA_SYMBOL_KEYS
pn.REQUEST_METADATA_TIMEFRAME_KEYS
pn.REQUEST_API_VALUES
pn.REQUEST_SECURITY_API
pn.REQUEST_SECURITY_CAPABILITY_ALIASES
pn.REQUEST_SECURITY_LOWER_TF_API
pn.REQUEST_SECURITY_LOWER_TF_CAPABILITY_ALIASES
pn.RequestCapabilities
pn.RequestCapabilityProvider
pn.RequestMetadata
pn.RequestMetadataProvider
pn.RequestSessionMetadata
pn.RequestSymbolMetadata
pn.RequestTimeframeMetadata
pn.PyneInvalidSymbolError
pn.PyneProviderError
pn.PyneProviderCapabilityError
pn.PyneProviderDataError
pn.PyneProviderMetadataError
pn.PyneRequestError
pn.RequestProviderErrorCategory
pn.ProviderConformanceCheck
pn.ProviderConformanceReport
pn.run_data_provider_conformance
pn.assert_data_provider_conformance
pn.RequestEvalContext
pn.RequestModule
pn.barmerge
pn.BarMergeNamespace
pn.StrategyModule
pn.PyneExecutionScope
pn.pyne_cache
pn.PyneTraceRecorder

pn.execute_pyne_script
pn.execute_pyne_script_in_process
pn.is_incremental_pyne_script
```

Version constants:

```python
pn.__version__
pn.PYNE_INPUT_SCHEMA_VERSION
pn.PYNE_INCREMENTAL_SNAPSHOT_VERSION
pn.PYNE_INCREMENTAL_PORTABLE_SNAPSHOT_FORMAT
pn.PYNE_INCREMENTAL_PORTABLE_SNAPSHOT_VERSION
pn.PYNE_OUTPUT_SCHEMA_VERSION
pn.PYNE_PARAM_SCHEMA_VERSION
pn.PYNE_REQUEST_PROVIDER_SCHEMA_VERSION
pn.PYNE_STRATEGY_REPORT_SCHEMA_VERSION
pn.PYNE_RUNTIME_CAPABILITIES_SCHEMA_VERSION
pn.PYNE_TRACE_SCHEMA_VERSION
pn.PYNE_SCRIPT_INSPECTION_SCHEMA_VERSION
pn.PYNE_SCRIPT_DIRECTORY_INSPECTION_SCHEMA_VERSION
pn.BATCH_TA_CAPABILITIES
pn.INCREMENTAL_TA_CAPABILITIES
pn.na
pn.nz
pn.fixnan
```

`PyneSeries` is the script-facing series value used for Pine-like history references such as `close[1]`.
`pn.na` is the callable missing-value sentinel also injected into scripts as `na`.
`pn.nz` and `pn.fixnan` expose the same missing-value helpers available to
scripts as `nz()` and `fixnan()`.
`PyneBarState` is the batch-runtime namespace type behind script-level `barstate.*` flags.
`PyneVar` and `PyneStateNamespace` power script-level `var()` / `pyne.var()` state cells.
`PyneIncrementalSession`, `PyneIncrementalSessionSnapshot`,
`PyneIncrementalSessionManager`, `PyneIncrementalSessionCapacityError`,
`SharedPyneIncrementalSession`, `PyneIncrementalBarState`, and
`is_incremental_pyne_script()` are host-facing helpers for confirmed/preview
bar workflows. `PYNE_INCREMENTAL_SNAPSHOT_VERSION` versions opaque
process-local checkpoints. `snapshot_portable()` and
`from_portable_snapshot()` provide versioned, checksummed replay-v1 and
typed-state-v2 formats; `PYNE_INCREMENTAL_PORTABLE_SNAPSHOT_*` and
`PYNE_INCREMENTAL_PORTABLE_STATE_SNAPSHOT_*` identify them.
The typed-state identifiers are also exported explicitly as
`pn.PYNE_INCREMENTAL_PORTABLE_STATE_SNAPSHOT_FORMAT` and
`pn.PYNE_INCREMENTAL_PORTABLE_STATE_SNAPSHOT_VERSION`.
`PynePortableSnapshotError` reports fail-closed portability or restore contract
violations. `run_incremental_parity()` returns an
`IncrementalParityReport` containing structured
`IncrementalParityDifference` records for batch/incremental semantic drift.
`SymbolInfo`, `TimeframeInfo`, `SessionInfo`, and `SessionNamespace` back the
script-level `syminfo`, `timeframe`, and `session` namespaces.
`ArrayNamespace`, `MapNamespace`, `MatrixNamespace`, `OrderNamespace`,
`PyneArray`, `PyneMap`, `PyneMatrix`, and the lowercase namespace singletons
back the script-level `array`, `map`, `matrix`, and `order` APIs.
`Color`, `color`, `PyneMath`, `StringNamespace`, `string_namespace`,
`TickerNamespace`, `TimeNamespace`, and `ObjectRef` support script-facing
color, math, string, ticker, time, and drawing-object helpers.
`PineLibraryDescriptor`, `PineLibraryRegistry`, `SUPPORTED_PINE_LIBRARIES`,
and `TRADINGVIEW_TA_10` describe the fail-closed pinned external-library
adapter surface.
`DataProvider` is the host protocol for `request.security()` market data access.
`LowerTimeframeSeries` is the grouped result object returned by
`request.security_lower_tf()`.
`OHLCVBar`, `REQUEST_METADATA_KEY_ALIASES`,
`REQUEST_METADATA_SESSION_KEYS`, `REQUEST_METADATA_SYMBOL_KEYS`,
`REQUEST_METADATA_TIMEFRAME_KEYS`, `REQUEST_API_VALUES`,
`REQUEST_SECURITY_API`, `REQUEST_SECURITY_CAPABILITY_ALIASES`,
`REQUEST_SECURITY_LOWER_TF_API`,
`REQUEST_SECURITY_LOWER_TF_CAPABILITY_ALIASES`, `RequestCapabilities`,
`RequestMetadata`, and related provider protocols are typing helpers for host
data adapters.
`PyneInvalidSymbolError` is the provider-side signal used by
`ignore_invalid_symbol=True`.
`PyneProviderError` and its capability, data, and metadata subclasses provide
typed provider-side failure signals. `RequestProviderErrorCategory` is the
stable machine-readable category enum. The conformance report and helper
functions let host adapters test the complete provider boundary without taking
a dependency on a specific Python test runner.
`PyneRequestError` is the stable runtime request error type used by host-backed
request adapters.
`RequestEvalContext` is the calculation-only context passed to `request.security()` expression thunks.
`pn.barmerge` exposes Pine-like request alignment constants such as
`pn.barmerge.gaps_on` and `pn.barmerge.lookahead_off`.
`BarMergeNamespace` is the concrete namespace type behind `pn.barmerge`.
`StrategyModule` is the script-level `strategy.*` event namespace.
`PyneExecutionScope` lets a host intentionally share script cache state across
multiple inline executions. By default each batch execution and each
incremental session owns an isolated scope. `pyne_cache` remains the
package-level service for explicit host cache management; it is not the cache
injected into ordinary script executions.
`runtime_capabilities()` returns the versioned batch/incremental capability
contract also embedded in `pn.schema()`. `capability_diagnostics()` is the
lower-level mode-aware diagnostic helper used by `pn.validate()` and
incremental session preparation. `BATCH_TA_CAPABILITIES` and
`INCREMENTAL_TA_CAPABILITIES` are the stable tuple views used in that contract.
`pn.inspect_script()` and `pn.PYNE_SCRIPT_INSPECTION_SCHEMA_VERSION` define the
non-executing static preflight report. `PyneTraceRecorder` and
`PYNE_TRACE_SCHEMA_VERSION` define the bounded trace document attached under
`result.meta["trace"]` when tracing is enabled.

Internal helpers and non-exported functions are not part of the compatibility contract.

`PyneResult` also exposes convenience helpers for common series access:

```python
result.series_names
result.get_series("Close")
result.values("Close")
result.latest("Close")
```

## Validate for a use case

```python
pn.validate(script, settings=settings, runtime_mode="incremental")
pn.validate(script, settings=settings, target="preview")
pn.validate(script, settings=settings, target="snapshot")
```

Validation does not run the script or fetch data. `target` implies incremental
execution and identifies statically visible module-class state that cannot be
isolated/restored. Overwritten or deleted classes are not rejected; dynamic
callback/global construction is left to runtime checks. An empty diagnostic
list does not certify dynamic closures, object graphs, providers or successful
execution. Ordinary batch classes remain supported.

Direct resource/state exceptions expose `.code` and `.hint`. The descriptive
`PyneResourceLimitError` and `PyneStateContractError` remain subclasses of
`PyneSecurityError` for existing exception handlers. Use specific codes for user
messages rather than displaying every legacy-base exception as a security failure.
