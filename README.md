<h1 align="center">Pyne Runtime</h1>

<p align="center"><strong>Pine-inspired computation. Native Python.</strong></p>

<p align="center">
  Compute indicators, replay strategies, and process realtime bars.<br>
  Start with OHLCV data or embed Pyne in your application.
</p>

<p align="center">
  <a href="https://github.com/helenananaa/pyne-runtime/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/helenananaa/pyne-runtime/actions/workflows/ci.yml/badge.svg"></a>
  <a href="#quickstart"><img alt="Development line: 0.4" src="https://img.shields.io/badge/development-0.4-0d9488"></a>
  <img alt="Python 3.11, 3.12, and 3.13" src="https://img.shields.io/badge/python-3.11%20%E2%80%93%203.13-3776ab">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-64748b"></a>
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> &middot;
  <a href="examples/README.md">Examples</a> &middot;
  <a href="docs/index.md">Documentation</a> &middot;
  <a href="https://github.com/helenananaa/pyne-runtime/releases">Releases</a>
</p>


Write Python scripts with Pine-inspired APIs such as `ta.sma`, `input`, and
`plot`. Supply OHLCV data from Python or CSV and receive named series, drawings,
signals, and strategy reports. The package runs independently with NumPy as its
only core dependency; applications can supply additional data and rendering.

The **0.4 development line** makes standalone execution ordinary Python: run in
the caller process with full imports and no default deadline or computation
quotas. Hosts explicitly choose isolation, restricted imports, and resource
budgets when embedding the runtime.

Pyne executes **Python**, with explicit helpers and state for bar-based logic.
TradingView `.pine` source requires translation.

## Quickstart

Use the current development checkout on Python 3.11–3.13:

```bash
python -m pip install -e .
```

> **Version status:** this README describes the 0.4 development direction.
> The current checkout identifies itself as 0.4.0; the latest published
> release is 0.3.0. The standalone defaults and new CLI workflows below require
> this development checkout. Version metadata and release publication remain
> separate from this documentation update.

Copy this into a Python file or notebook and run it. All input data is included:

```python
import pyne_runtime as pn

bars = [
    {"time": 1704067200 + i * 60, "open": c - 1, "high": c + 1,
     "low": c - 2, "close": c, "volume": 1000}
    for i, c in enumerate([100, 102, 104, 106, 108])
]

result = pn.run(
    '''
indicator("Moving average", overlay=True)
plot(ta.sma(close, 3), "SMA")
''',
    bars,
)
if not result.ok:
    raise RuntimeError(result.error)

print(result.values("SMA")[-3:])
```

```text
[102.0, 104.0, 106.0]
```

The first two bars warm up the three-bar average. `plot` records a named output
series that you can inspect, export, or pass to your own renderer.

**Use your own data:** replace `bars` with `pn.read_ohlcv("bars.csv")`.
The default columns are `time,open,high,low,close,volume`.
See the [quickstart guide](docs/quickstart.md) for CLI and parameter examples.

### Create a script and export CSV

With your own `bars.csv`, generate an editable indicator and run it:

```bash
pyne new trend.py --template trend
pyne inspect trend.py --runtime-mode incremental
pyne run trend.py --ohlcv bars.csv --format csv --out indicators.csv
```

Templates cover trend, volatility, and explicit state. Use the same callback
script for historical data and realtime sessions. CSV options support column
mapping, seconds or milliseconds, and selected plot names; failed calculations
preserve existing output files. See [CSV to realtime](docs/tutorials/csv_to_realtime.md)
and [diagnose a script](docs/tutorials/diagnose_script.md).

<details>
<summary>Need the published stable release instead?</summary>

Version 0.3.0 has different execution defaults and does not include the new
template/export workflow above. Install its pinned wheel:

```bash
python -m pip install "https://github.com/helenananaa/pyne-runtime/releases/download/v0.3.0/pyne_runtime-0.3.0-py3-none-any.whl"
```

Use the [0.3.0 documentation](https://github.com/helenananaa/pyne-runtime/tree/v0.3.0/docs)
for that version's API and commands.

</details>

## What you can build

| Task | Runtime support |
| --- | --- |
| **Indicators and scanners** | TA helpers, history references, parameters, explicit state, plots, drawings, and signals |
| **Strategy research** | Deterministic OHLCV replay with orders, exits, costs, risk rules, and trade reports |
| **Multi-timeframe analysis** | Provider-backed `request.security()` and `request.security_lower_tf()` with alignment and diagnostics |
| **Realtime applications** | History seeding, isolated preview updates, confirmed-bar commits, bounded retention, and snapshot recovery |

Batch and incremental modes have declared capability sets. Use
[`pn.runtime_capabilities()`](docs/api/capabilities.md) and
[`pyne inspect`](docs/reference/cli.md) to check a script's requirements before
integrating it.

## Start standalone. Integrate when ready.

**For script authors:** calculate from CSV or Python data, inspect results in a
notebook, and build reusable indicators. Begin with the
[first indicator tutorial](docs/tutorials/first_indicator.md),
[runnable examples](examples/README.md), or the
[Pine-to-Pyne cookbook](docs/tutorials/pine_to_pyne_cookbook.md).

**For application developers:** embed Pyne behind your adapter. Your application
supplies data, renders output, and owns persistence and process lifecycle; Pyne
owns script computation and versioned output contracts. Start with the
[host integration guide](docs/tutorials/host_integration_guide.md), then explore
[data providers](docs/tutorials/host_request_security.md),
[realtime sessions](docs/concepts/incremental_runtime.md), and
[session recovery](docs/tutorials/session_recovery.md).

## Reliability and compatibility

The **0.3.0 release** is backed by source and installed-wheel checks on Windows,
Linux, and macOS across Python 3.11, 3.12, and 3.13. Release qualification includes
independent package installation, representative full-script workflows,
snapshot continuation, preview isolation, and bounded performance checks.
See the [release acceptance record](docs/development/release_readiness_zh.md)
for results, workload limits, and the retained macOS performance rerun.

Checked-in TradingView reference captures cover 21 request, 27 strategy, and
10 TA cases, with zero differences in the release capture gates. Compatibility
applies to those cases and the documented feature surface. The
[current status](docs/reference/current_status.md) and
[API matrix](docs/reference/pine_like_api_matrix.md) describe that scope.

Those release results describe **0.3.0**, not qualification of the current
development tree. Check the
[current status](docs/reference/current_status.md) for development evidence.

Current incremental computation semantics is **5**. Older incompatible snapshots
require rebuilding from authoritative OHLCV; changing operational budgets alone
does not require recalculation when existing state fits the selected policy.
Restored objects adopt that policy. Read the
[compatibility policy](docs/reference/compatibility.md),
[schema migrations](docs/reference/schema_migrations.md), and
[changelog](CHANGELOG.md) when upgrading.

Release assets include a wheel, source archive, and `SHA256SUMS`.
Pin the version and verify the wheel checksum for reproducible deployments.

### Execution boundaries

Standalone calls default to full Python in the caller process, with no execution
deadline or computation quotas. Hosts select restricted execution and resource
budgets explicitly; see [execution policies](docs/concepts/security_modes.md).
`None` means unlimited computation budgets. Input admission, retained history,
and replay recording are independent settings; bounded caches can evict
recoverable entries without rejecting valid computation.

- Python control flow follows Python semantics. Use the documented helpers and
  callback/state patterns for per-bar behavior.
- Multi-timeframe requests need a data provider. Market feeds, chart UI, alerts,
  accounts, and broker connectivity belong to the application.
- Strategy replay uses OHLCV bars; it cannot establish intrabar tick paths,
  order-book queue position, or real partial fills.
- `safe` and `research` modes restrict the Python environment. Untrusted scripts
  additionally require host-managed process or operating-system isolation.

## Documentation and contributing

Browse the [documentation index](docs/index.md) for tutorials and API guides,
the [public API](docs/api/public_api.md) for supported imports, and the
[output schema](docs/reference/output_schema.md) for integration contracts.
Report reproducible bugs through [GitHub Issues](https://github.com/helenananaa/pyne-runtime/issues).

From a source checkout, install the development tools:

```bash
python -m pip install -e ".[dev,pandas]"
```

Run `./scripts/check.ps1` on Windows or `./scripts/check.sh` on Linux/macOS.
The full gate covers lint, tests, capture parity, builds, metadata, and isolated
wheel installation. See [quality gates](docs/development/quality_gates.md) and
the [release process](docs/reference/release_process.md) for details.

## License

[MIT](LICENSE).
