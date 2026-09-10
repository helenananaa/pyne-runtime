# Diagnose and Fix a Script

Start with ordinary standalone execution. No mode switch is required for pandas,
Python imports, classes, large inputs or long computations:

```python
import pyne_runtime as pn
result = pn.run(script, data)
if not result.ok:
    print(result.code, result.error, result.hint)
```

Use the same settings for validation and execution when selecting a restricted
policy. CLI users can likewise pass the same `--security-mode` and
`--allowed-import` options to `validate` and `run`.

| What you see | What to do |
| --- | --- |
| `PYNE_RESOURCE_LIMIT_EXCEEDED` | Increase the explicit budget or use `None`; do not switch permission modes |
| `PYNE_OUTPUT_LIMIT_EXCEEDED` | Increase/remove the relevant output budget, or select an appropriate output scope |
| `PYNE_IMPORT_BLOCKED` | Check the selected import policy; standalone full Python remains available |
| `PYNE_STATE_CONTRACT_ERROR` | Use incremental state/callback patterns, or ordinary batch execution |
| `PYNE_SESSION_FAILED` | Fix the original callback failure and restore a valid checkpoint or rebuild |

For live scripts, check the intended operation before preparing a long run:

```bash
pyne validate indicator.py --runtime-mode incremental
pyne validate indicator.py --target preview
pyne validate indicator.py --target snapshot
```

A module-level class can work in ordinary computation yet be unsuitable for
preview or snapshots. These commands identify simple retained-class cases with
line numbers. They do not execute code, fetch providers or prove dynamic object
graphs valid. Deleted/overwritten classes and dynamic callback assignments are
not rejected merely because a class/function definition appeared in the source.

If an environment variable enabled a limit that you do not want:

```bash
pyne run indicator.py --ohlcv bars.csv --limit max_bars=none --timeout-seconds none
```

When exporting CSV, only the selected plot names must be unique; unknown names
report the available choices. Use JSON for drawings and strategy reports. A failed
calculation with `--out` leaves the previous JSON/CSV result file untouched and
prints the error to stderr. Fix the script or configuration, then run it again.

See [error codes](../reference/error_codes.md), [execution policies](../concepts/security_modes.md)
and [CLI reference](../reference/cli.md) for the complete contracts.
