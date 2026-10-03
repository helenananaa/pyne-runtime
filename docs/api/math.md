# `math` API

The `math` namespace is injected into scripts and accepts scalar values,
`PyneSeries`, NumPy arrays, and list-like values where applicable.

Common helpers:

```python
math.abs(close - open)
math.max(high, close, open)
math.min(low, close, open)
math.avg(open, high, low, close)
math.sum(close, 20)
math.round(close, 2)
math.round(close, precision=2)
math.trunc(close)
math.fixnan(close)
math.round_to_mintick(close)
math.random(0, 1, seed=42)
math.sqrt(close)
math.pow(close, 2)
math.sin(angle)
math.todegrees(angle)
math.toradians(degrees)
```

## Rolling Sum

For positive `length`, `math.sum(source, length)` sums the last `length`
non-missing observations. It waits for that many observations, skips `na`
samples, and retains the available sum on missing bars. The native oscillator
formula capture qualifies length 3 with consecutive and isolated gaps; other
lengths have independent Python boundary tests, not native parameter qualification.
Non-positive lengths retain the previous Python behavior and remain outside
this native qualification.
Warmup bars without enough non-missing observations are `na`.

```python
plot(math.sum(close, 20), "20-Sample Sum")
```

## Missing Values

`math.fixnan(source)` carries the latest non-`na` value forward through later
missing values. Leading `na` values remain missing because there is no previous
value to reuse.

## Mintick Rounding

`math.round_to_mintick(value)` rounds to the nearest multiple of
`syminfo.mintick`. Ties round upward, matching the Pine mental model.

```python
result = pn.run(
    script,
    bars,
    syminfo={"mintick": 0.25},
)
```

In incremental scripts, the same helper uses the `PyneSettings.syminfo` value
attached to the session.

## Random Values

`math.random(min, max, seed=None)` returns a value in `[min, max)`. Supplying a
seed makes the value deterministic for repeatable script runs.

Pyne exposes this as a Python runtime helper rather than TradingView's realtime
engine state, so host applications should treat unseeded values as ordinary
runtime randomness.

## Constants

Available constants:

- `math.pi`
- `math.e`
- `math.phi`
