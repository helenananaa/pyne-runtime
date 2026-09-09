<h1 align="center">Pyne Runtime</h1>

<p align="center"><strong>Write trading logic in Python. Think in bars. Ship chart-ready output.</strong></p>

<p align="center">
  A Pine-inspired runtime for OHLCV indicators, deterministic strategies,<br>
  multi-timeframe data, and realtime host sessions&mdash;without leaving Python.
</p>

<p align="center">
  <a href="https://github.com/helenananaa/pyne-runtime/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/helenananaa/pyne-runtime/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python 3.11, 3.12, and 3.13" src="https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-3776AB?logo=python&logoColor=white">
  <img alt="Project status: 0.3.0 release candidate pending qualification, not publicly released" src="https://img.shields.io/badge/status-0.3.0%20RC%20pending%20qualification-F59E0B">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-2563EB"></a>
</p>

<p align="center">
  <a href="docs/quickstart.md">Quickstart</a> &middot;
  <a href="examples/README.md">Examples</a> &middot;
  <a href="docs/index.md">Documentation</a> &middot;
  <a href="https://github.com/helenananaa/pyne-runtime/releases">Releases</a> &middot;
  <a href="docs/reference/current_status.md">Current status</a> &middot;
  <a href="docs/reference/pine_like_api_matrix.md">API matrix</a>
</p>

---

If you have ever wanted chart-script ergonomics without giving up Python, this
is the missing layer. Pyne Runtime brings the bar-by-bar mental model and
chart-oriented APIs that make Pine-style scripting productive into a normal
Python package. Give it OHLCV data and a Python script; get back versioned,
structured output for charts, scanners, notebooks, research tools, or your own
trading application.

```text
OHLCV + host data provider
            │
            ▼
   Pine-like Python script  ──►  Pyne Runtime
                                      │
                                      └─► plots · markers · drawings · signals
                                          strategy reports · diagnostics
```

## See It in 60 Seconds

Pyne Runtime is distributed as a universal wheel on GitHub Releases. Pin the
release tag and exact asset when installing it into a host application:

```bash
python -m pip install "https://github.com/helenananaa/pyne-runtime/releases/download/v0.2.0rc1/pyne_runtime-0.2.0rc1-py3-none-any.whl"
pyne --version
```

Each release also includes the source distribution and `SHA256SUMS`. Host
applications should verify the pinned wheel hash before installation. The core
install depends only on NumPy; Pandas and Matplotlib integrations stay optional.

To run the repository examples, clone the matching tag and install the optional
development dependencies:

```bash
git clone --branch v0.2.0rc1 --depth 1 https://github.com/helenananaa/pyne-runtime.git
cd pyne-runtime
python -m pip install -e ".[dev,pandas]"
pyne run examples/ma_cross.py --ohlcv examples/sample_ohlcv.csv --out result.json
```

Or use the runtime directly from Python:

```python
import pyne_runtime as pn

bars = pn.read_ohlcv("examples/sample_ohlcv.csv")

result = pn.run(
    """
indicator("EMA Cross", overlay=True)

fast = ta.ema(close, 3)
slow = ta.ema(close, 5)

plot(fast, "Fast EMA", color=color.orange)
plot(slow, "Slow EMA", color=color.blue)
marker(crossover(fast, slow), text="Buy", color=color.green)
marker(crossunder(fast, slow), text="Sell", color=color.red)
""",
    bars,
    executor_mode="inline",  # convenient for trusted scripts and notebooks
)

if not result.ok:
    raise RuntimeError(result.error)

print(result.values("Fast EMA")[-3:])
print(result.output.keys())
```

That result is not a screenshot or an opaque callback. It is a host-facing
contract containing renderable series, markers, drawing objects, signals,
strategy state, request diagnostics, and schema versions.

## Why Pyne Runtime?

| You want | Pyne gives you |
| --- | --- |
| Familiar chart-script ergonomics | `ta.*`, history references such as `close[1]`, `input.*`, `plot()`, markers, colors, drawings, and explicit state |
| Python-native workflows | Lists, CSV, optional Pandas integration, normal Python files, tests, packaging, and the rest of the Python ecosystem |
| Multi-timeframe analysis | Host-backed `request.security()` and `request.security_lower_tf()` with alignment, tuples, metadata, caching, and structured diagnostics |
| Deterministic strategy research | Entries, orders, exits, OCA behavior, pyramiding, costs, risk rules, trade ledgers, and lifecycle reports over OHLCV bars |
| Realtime host integration | Incremental sessions with history seeding, isolated preview updates, confirmed-bar commits, snapshots, and shared session management |
| A stable renderer boundary | Versioned schemas for inputs, parameters, renderables, drawing events, request providers, and strategy reports |

Pyne does not force a chart UI, data vendor, database, or broker onto your
architecture. Your host owns those choices; the runtime owns deterministic
script execution and the contract between the script and the host.

## Pick Your Path

| Goal | Start here |
| --- | --- |
| Build your first indicator | [Quickstart](docs/quickstart.md) and [First Indicator](docs/tutorials/first_indicator.md) |
| Translate Pine-style ideas into Python | [Pine-to-Pyne Cookbook](docs/tutorials/pine_to_pyne_cookbook.md) |
| Use Pyne from a charting or research host | [Host Integration Guide](docs/tutorials/host_integration_guide.md) |
| Supply higher- or lower-timeframe data | [Host-Backed `request.security()`](docs/tutorials/host_request_security.md) |
| Process preview and confirmed realtime bars | [Incremental Runtime](docs/concepts/incremental_runtime.md) |
| Preflight a script or inspect decisions | [Runtime Capabilities](docs/api/capabilities.md), `pyne inspect`, and [Execution Trace](docs/concepts/execution_trace.md) |
| Consume every renderer and strategy field | [Output Schema](docs/reference/output_schema.md) |
| Explore runnable scripts | [Packaged Examples](examples/README.md) |

## Built on Verifiable Behavior

The repository does not treat API names alone as compatibility evidence. Its
release gate checks real output, package contracts, and installability.

| Evidence in the current `0.3.0` source candidate | Verified surface |
| --- | --- |
| TradingView-backed capture parity | Request **21/21**, Strategy **27/27**, and TA **10/10** captured cases, currently at **0 diff**; the external-library slice covers 8 plots and 78 checked points |
| Configured CI matrix | Linux, Windows, and macOS on Python 3.11, 3.12, and 3.13; current qualification status is recorded separately |
| Contract checks | Generated project status, output schemas, public imports, capture parity, and architecture boundaries |
| Runtime self-description | Static script inspection, versioned batch/incremental capabilities, early unsupported-call diagnostics, and bounded trace-v2 evidence |
| Distribution checks | Wheel and source build, metadata validation, clean installed-wheel smoke, CLI, and packaged examples |

Capture parity applies to the checked-in fixtures and cases; it is evidence for
that covered surface, not a claim of exhaustive Pine compatibility. See the
[Current Project Status](docs/reference/current_status.md) for the verified
capability boundary and the [Pine-Like API Matrix](docs/reference/pine_like_api_matrix.md)
for feature-level detail.

## Know the Boundaries

Pyne Runtime **0.3.0 is a local release candidate pending qualification, not a
publicly released package**. Current source evidence is candidate version
`0.3.0`. The verified GitHub Release remains `v0.2.0rc1` until
new release assets are published and verified. Stable support is the bounded compatibility
contract in this repository, not a claim of full Pine compatibility. It is a
host-embedded, Pine-like Python runtime for controlled integrations and trusted
scripts, not a complete trading platform.

- Pyne executes Python; it does not parse or run TradingView `.pine` source.
- Market data, storage, chart rendering, alerts, accounts, and broker or
  exchange connectivity belong to the host application.
- Strategy replay is deterministic and bar-based. It does not invent tick
  paths, order-book queue position, or real partial fills that OHLCV data does
  not contain.
- Multi-context requests require a host data provider; the core package does
  not silently fetch from an exchange.
- `safe` and `research` modes restrict the Python environment, but they are not
  a hardened multi-tenant sandbox. Isolate untrusted code at the process,
  container, or operating-system level.

These limits are deliberate: they keep the runtime composable, testable, and
honest about what its inputs can prove.

## CLI at a Glance

```bash
pyne --version
pyne validate examples/ma_cross.py
pyne run examples/ma_cross.py --ohlcv examples/sample_ohlcv.csv --out result.json
pyne schema
```

The same commands are available through `python -m pyne_runtime`.

## Documentation

- [Documentation Home](docs/index.md) — the complete guide and API map
- [Current Project Status](docs/reference/current_status.md) — what works now,
  what does not, and the evidence behind each claim
- [Public API](docs/api/public_api.md) — stable package-root imports
- [Compatibility](docs/reference/compatibility.md) — supported semantics and
  known differences
- [Schema Migrations](docs/reference/schema_migrations.md) — versioning rules
  for host-facing contracts
- [Quality Gates](docs/development/quality_gates.md) — local and release checks
- [Long-Term Direction](docs/development/python_package_long_term_plan_zh.md) —
  package maturity roadmap

Historical execution plans remain under `docs/development/`; they preserve how
earlier slices were delivered but do not override the current status page.

## Development

Install the editable package and development tools:

```bash
python -m pip install -e ".[dev,pandas]"
```

Run the complete repository gate before submitting changes:

```powershell
.\scripts\check.ps1
```

```bash
./scripts/check.sh
```

The gate covers compilation, linting, tests, capture parity, package builds,
metadata checks, and an offline installed-wheel smoke test. See
[Contributing Quality Gates](docs/development/quality_gates.md) and the
[Release Process](docs/reference/release_process.md) for details.

## License

Pyne Runtime is licensed under the [MIT License](LICENSE).
