# PyneRuntime

`PyneRuntime` is the reusable execution class for standalone and hosted use.
`pn.run()` defaults to unrestricted local Python execution with no deadline or
input/output quota; optional limits and process execution are caller policy.

```python
import pyne_runtime as pn

runtime = pn.PyneRuntime(settings=pn.PyneSettings(security_mode="safe"))
result = runtime.execute(script, ohlcv, params={})
```

Most users should call `pn.run()`. Hosts can use `PyneRuntime` when they need a persistent runtime object or explicit settings.

