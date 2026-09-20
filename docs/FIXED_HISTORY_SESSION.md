# Fixed historical horizon sessions

This is historical execution with a fixed supplied OHLCV horizon, not a realtime append stream.
Only bars advanced to the cursor are evaluated; last-bar flags refer to the fixed full horizon.
The final output must match the original complete historical execution. Backwards movement uses
an explicit saved state or rebuild; input acquisition, processes and durable checkpoints belong to callers.

Use `from pyne_runtime.historical import HistoricalSession`; construct with `(source, bars, params=..., settings=...)`. `advance(target)` returns IncrementalPyneResult; `equity` contains observed native account points. `snapshot()`/`restore(snapshot)` preserve process-local state and reject mismatched horizon/cursor. Use only init/on_bar scripts. This wrapper has a distinct `pyne.fixed-history/1` contract and does not reinterpret portable realtime snapshots.
