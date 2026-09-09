# Runtime Capabilities

Hosts should discover the runtime surface instead of assuming that batch and
incremental scripts expose the same functions.

```python
import pyne_runtime as pn

capabilities = pn.runtime_capabilities()
incremental_ta = capabilities["modes"]["incremental"]["ta"]
```

The returned document has its own `schemaVersion` and lists mode-specific TA,
request, strategy, drawing, callback, preview, and portable-snapshot support.
It also declares the pinned external-library registry, trace contract, language
boundary, and security boundary. The live member lists in that document are the
checked source of truth; prose inventories in the Incremental guide, API matrix,
and status page must match them rather than keep a second handwritten set.
Callers receive a defensive copy and may modify it without changing the runtime.

The same document is embedded in `pn.schema()["runtimeCapabilities"]`. Hosts
can therefore obtain one complete integration bundle through `pyne schema`.

For one script, use the non-executing inspection API before allocating a
session or requesting host data:

```python
report = pn.inspect_script(script, runtime_mode="incremental")
show_diagnostics(report["migration"]["diagnostics"])
if not report["compatibility"]["supported"]:
    show_diagnostics(report["compatibility"]["diagnostics"])
```

The report contains a SHA-256 source identity rather than source text, the
detected declaration and callbacks, TA/request/strategy/drawing requirements,
pinned-library members, member-specific host-data requirements, resource hints,
and dynamic-access uncertainties. It is a static Python-AST preflight, so it
does not execute the script and does not claim to resolve computed `getattr()`
or runtime-generated calls. Inspection does not guarantee that the script will
execute.

Heuristic Pine-to-Pyne migration hints from `pn.validate()` are advisory only.
They appear on `report["migration"]["diagnostics"]` and must not be treated as
capability blockers: `compatibility.supported` and
`migration.batchToIncremental` eligibility stay independent of those hints.
Legitimate scalar variables may shadow names such as `close`. Hosts must
display the advisory list separately from `compatibility.diagnostics`. Syntax
errors still report `PYNE_SYNTAX_ERROR` on compatibility, and the same
advisory list remains present on `migration.diagnostics`.

## Mode-Aware Validation

`pn.validate()` detects incremental mode from `indicator(...,
mode="incremental")` or an `on_bar()` callback. A host can also select the mode
explicitly:

```python
diagnostics = pn.validate(script, runtime_mode="incremental")
```

Statically discoverable unsupported calls such as `ctx.ta.tsi()` return a
`PYNE_UNSUPPORTED_FEATURE` diagnostic at the call site. Incremental session
preparation applies the same check before processing any bar. Dynamic Python
attribute construction cannot always be proven statically and can still fail
at runtime.

The capability schema is an implemented-surface contract, not a claim that
Pyne parses Pine source or provides exhaustive TradingView compatibility.
