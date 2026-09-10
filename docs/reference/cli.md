# Command Line Interface

Pyne Runtime installs the `pyne` command.

The same CLI is also available with:

```bash
python -m pyne_runtime --version
```

## Run

The `new` command and CSV options below are available in development version
0.4.0; the published 0.3.0 wheel does not yet include them.

```bash
pyne new indicator.py --template trend
pyne run indicator.py --ohlcv bars.csv --time-unit ms --column time=timestamp --format csv --series "Fast EMA" --out result.csv
```

`new` ships `trend`, `volatility` and `state` templates and never overwrites a
file. Repeat `--column FIELD=HEADER` to map OHLCV headers, and repeat `--series`
to select ordered CSV columns. Output time is always Unix seconds. CSV contains
plotted series, with empty missing cells and no forward fill; use JSON for
drawings, signals and strategy reports. CSV mode writes execution diagnostics to
stderr. Failed executions with `--out` leave existing JSON and CSV files untouched
and write failure details to stderr. Only selected CSV curves need unique names;
unselected duplicate names do not block export. Exit codes
are 0 for success, 1 for script failure and 2 for input/selection errors.
See [CSV to realtime](../tutorials/csv_to_realtime.md) for full format semantics.

```bash
pyne run examples/ma_cross.py --ohlcv examples/sample_ohlcv.csv --out result.json
```

Parameter overrides can be passed one at a time:

```bash
pyne run examples/ma_cross.py --ohlcv examples/sample_ohlcv.csv --param Length=20 --param Enabled=true
```

Values are parsed as JSON when possible, so `true`, `false`, `null`, numbers, arrays, and objects keep their JSON types. Other values are kept as strings.

For automation, pass a JSON object directly or provide a path to a JSON file:

```bash
pyne run examples/ma_cross.py --ohlcv examples/sample_ohlcv.csv --params-json params.json
```

## Validate

```bash
pyne validate examples/ma_cross.py
```

Validation checks syntax, selected execution capabilities and the same import
policy used for running. It never executes the script. For example:

```bash
pyne validate indicator.py --security-mode research --allowed-import math
pyne run indicator.py --ohlcv bars.csv --security-mode research --allowed-import math
pyne validate indicator.py --runtime-mode incremental
pyne validate indicator.py --target preview
pyne validate indicator.py --target snapshot
```

Targets identify statically visible state boundaries; dynamic closures and
objects still require runtime validation. Missing callbacks get a direct
`on_bar(ctx, bar)` hint. Batch Python classes are not prohibited by these opt-in
checks.

## Configure or remove a budget

Both `run` and `validate` accept `--security-mode`, repeated `--allowed-import`,
`--timeout-seconds` and repeated `--limit NAME=VALUE`. Use PyneSettings field names:

```bash
pyne run indicator.py --ohlcv bars.csv --timeout-seconds none --limit max_bars=none
pyne run indicator.py --ohlcv bars.csv --limit max_output_points=2000000
```

These options override environment settings. Optional computation budgets accept
`none`; cache capacities require positive values. `--allowed-import` replaces the
research allowlist, and does not activate research mode by itself. Standalone
defaults remain full Python, inline execution, no deadline and no computation
quota. See [execution policies](../concepts/security_modes.md) for all fields.
Unknown limit names and invalid values return structured input errors with hints.

## Inspect

```bash
pyne inspect examples/ma_cross.py --runtime-mode incremental
```

Inspection prints the versioned static preflight manifest produced by
`pn.inspect_script()`. It does not execute the script or echo its source. The
manifest reports the source hash, selected runtime mode, required namespaces,
pinned external-library members, host capability requirements, resource hints,
and compatibility diagnostics. Omit `--runtime-mode` to use the declaration and
callback-based mode detector.

## Schema

```bash
pyne schema
```

The schema command prints the public input and output contracts.
