# Repository Scope

This repository builds and ships the standalone `pyne-runtime` Python package. Although the package is developed primarily for use by CandleScope, it is not a CandleScope host-integration repository.

## Ownership boundary

`pyne-runtime` owns:

- Pyne/Pine language parsing, validation, semantics, and execution.
- Runtime state and package-level execution contracts.
- Stable, host-agnostic public APIs and capability declarations.
- Generic extension points, protocols, callbacks, and execution-context abstractions that allow a host to supply capabilities.
- Standalone package tests, build artifacts, installation checks, and documentation.

The host or a separate adapter layer owns:

- CandleScope-specific integration and orchestration.
- Market-data acquisition, subscriptions, storage, and cache integration.
- Chart, UI, WebSocket, HTTP, broker, account, and order-management integration.
- Host permissions, process lifecycle, deployment, and host-specific configuration.
- Mapping CandleScope services and domain objects onto the generic interfaces exposed by `pyne-runtime`.

## Dependency direction

The dependency direction is always:

```text
CandleScope or another host -> host adapter -> pyne-runtime
```

`pyne-runtime` must not import CandleScope modules or depend on CandleScope services, schemas, configuration, lifecycle, transport, UI, broker, or storage implementations.

## Change-review rules

- Keep the installed wheel independently usable and testable without CandleScope.
- Do not add CandleScope-specific adapters, conditionals, configuration keys, domain objects, or orchestration to this repository.
- A host need does not by itself justify host-specific code here. Extract only the smallest genuinely reusable, host-agnostic contract required by the runtime.
- Generic interfaces may describe what a host can provide, but implementations that connect those interfaces to CandleScope belong outside this repository.
- Package tests must use host-neutral fixtures or test doubles. CandleScope end-to-end, chart, broker, and service-integration tests belong to the host or adapter project.
- When a requested change crosses this boundary, stop and identify the runtime-side contract separately from the host-side implementation before editing.

## Snapshot compatibility

- Incompatible changes to incremental committed state or replay semantics must bump `INCREMENTAL_SEMANTICS_VERSION` in `incremental/checkpoint.py`, with upgrade rejection and same-version continuation tests.
- Keep computation semantics identity separate from package and wire-format versions. Never relabel old snapshots to bypass incompatibility; document rebuilding from authoritative host-supplied OHLCV.
