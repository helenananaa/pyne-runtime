# Error Codes

Pyne errors use stable `code` values and structured `errorDetail` payloads.
When a failure comes from a host-backed `request.*` provider,
`errorDetail.requestProviderCategory` identifies the matching
`pn.schema()["requestProvider"]["errorCategories"]` entry, and
`errorDetail.requestProviderRequest` identifies the failed
`api/symbol/timeframe/start/end` request.

<a id="pyne-syntax-error"></a>

## PYNE_SYNTAX_ERROR

The script is not valid Python/Pyne syntax.

<a id="pyne-runtime-error"></a>

## PYNE_RUNTIME_ERROR

The script raised an exception while running, or a host request provider
callback such as `get_ohlcv()`, `capabilities()`, or request metadata failed.

<a id="pyne-import-blocked"></a>

## PYNE_IMPORT_BLOCKED

The selected security mode blocked an import.

<a id="pyne-timeout"></a>

## PYNE_TIMEOUT

The script exceeded its configured timeout.

<a id="pyne-output-limit-exceeded"></a>

## PYNE_OUTPUT_LIMIT_EXCEEDED

The script emitted too many output series or points.

<a id="pyne-invalid-ohlcv"></a>

## PYNE_INVALID_OHLCV

The input data is empty or does not satisfy the OHLCV contract.

<a id="pyne-invalid-symbol"></a>

## PYNE_INVALID_SYMBOL

The host data provider reported an invalid requested symbol. Use a supported
symbol or pass `ignore_invalid_symbol=True` when missing symbols are expected.

<a id="pyne-invalid-param"></a>

## PYNE_INVALID_PARAM

The provided parameter values are invalid. This is returned when an `input.*`
override has the wrong type, falls outside declared numeric bounds, is not in
declared `options`, names an unknown source, or passes an invalid timestamp.

<a id="pyne-migration-hint"></a>

## PYNE_MIGRATION_HINT

`pyne validate` found a syntactically valid Python expression that commonly
comes from Pine syntax but does not preserve Pine-like semantics in Python.
Follow the diagnostic hint or the Pine-to-Pyne cookbook.

<a id="pyne-length-mismatch"></a>

## PYNE_LENGTH_MISMATCH

Custom output arrays do not align with the OHLCV input length.

<a id="pyne-unsupported-feature"></a>

## PYNE_UNSUPPORTED_FEATURE

The script requested a feature not supported by this runtime.
This is also returned when `request.security()` is used without a configured
host data provider.

<a id="pyne-process-failed"></a>

## PYNE_PROCESS_FAILED

The process executor failed or exited unexpectedly.

<a id="pyne-security-error"></a>

## PYNE_SECURITY_ERROR

The selected security policy rejected the script.


<a id="pyne-resource-limit-exceeded"></a>

## PYNE_RESOURCE_LIMIT_EXCEEDED

An explicitly configured input, collection, window, state or work budget was
exceeded. This is not an import permission failure and the input may be valid.
Increase the relevant PyneSettings value or set an optional budget to `None`;
CLI users can pass `--limit NAME=none`. Common fields: `max_bars`, `max_array_size`,
`max_map_size`, `max_matrix_cells`, `max_collection_depth`, `max_window_size`.
Output capacity continues to use `PYNE_OUTPUT_LIMIT_EXCEEDED`.

<a id="pyne-state-contract-error"></a>

## PYNE_STATE_CONTRACT_ERROR

The requested operation cannot preserve incremental state or preview isolation,
for example retained script classes/closures, mutation of confirmed history,
recursive Pyne collections or a state helper outside a callback. Keep incremental
state in `ctx.state()`/`ctx.varip()` with top-level callbacks, or use batch Python
when preview/snapshot behavior is unnecessary. Use `pyne validate --target preview`
or `--target snapshot` to find statically visible cases before running.

<a id="pyne-session-failed"></a>

## PYNE_SESSION_FAILED

A previous callback failed after state might have changed. Fix the original
failure and create a session from a valid checkpoint or authoritative OHLCV.
Input admission errors alone do not invalidate a healthy session.

<a id="pyne-process-serialization-error"></a>

## PYNE_PROCESS_SERIALIZATION_ERROR

Explicit process execution requires pickle-serializable arguments and providers.
Use ordinary inline execution for local objects, or supply process-compatible
objects if process isolation is needed.

<a id="pyne-cli-input-error"></a>

## PYNE_CLI_INPUT_ERROR

A file, option, configuration value or output selection is invalid. The message
identifies the failing input; hints and `pyne run --help` / `pyne validate --help`
explain the next step. Unknown CSV series list available names.

## Diagnostic compatibility

This development candidate replaces generic `PYNE_SECURITY_ERROR` buckets for
resources and state contracts with the specific codes above. Input quota overflow
is no longer mislabeled `PYNE_INVALID_OHLCV`; drawing quota overflow uses
`PYNE_OUTPUT_LIMIT_EXCEEDED`. Payload shapes and computation semantics are unchanged.
Existing catches of `PyneSecurityError`/`RuntimeError` continue to work, while
code-based callers should recognize the new specific diagnostics.
