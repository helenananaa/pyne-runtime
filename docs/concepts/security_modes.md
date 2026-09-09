# Security Modes

Pyne has three security modes:

- `safe`: blocks imports and uses a restricted builtins set.
- `research`: allows imports from an explicit allowlist.
- `unsafe`: allows full Python builtins and imports.

Safe mode is a restricted execution environment, not a strong multi-tenant sandbox.

Process execution always uses the ``spawn`` start method. It can hard-kill a
worker after ``timeout_seconds``. Inline execution applies ``timeout_seconds``
only as a best-effort Unix main-thread timer; it cannot hard-kill a script on
Windows or a non-main thread. ``PyneSettings(require_hard_timeout=True)`` is
rejected with ``executor_mode='inline'`` because that path cannot deliver a
process-style hard timeout. Unsafe mode still exposes dangerous builtins, but
the injected ``__builtins__`` mapping is a copy so a script cannot overwrite
the host interpreter's builtin table through that mapping.

Example:

```python
import pyne_runtime as pn

settings = pn.PyneSettings(security_mode="research", allowed_imports=("math",))
result = pn.run("import math\nplot([math.sqrt(x) for x in close])", data, settings=settings)
```

