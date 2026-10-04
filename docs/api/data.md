# PyneData

`PyneData` is a lightweight OHLCV container.

Create it from Python objects:

```python
data = pn.PyneData.from_ohlcv(items)
```

Create it from CSV:

```python
data = pn.read_ohlcv("bars.csv")
```

Create it from Pandas:

```python
data = pn.from_pandas(df)
```

Input admission is unlimited by default. Select a budget explicitly when loading:

```python
data = pn.read_ohlcv("bars.csv", max_bars=10000)
data = pn.PyneData.from_ohlcv(items, max_bars=10000)
data = pn.from_pandas(df, max_bars=10000)
```

`PyneData.from_csv()` accepts the same keyword. Iterables and CSV stop after
reading at most one row beyond the limit, before normalizing that excess row.
Oversized existing `PyneData` and DataFrames are rejected before copying their
records. Loader rejection raises `PyneResourceLimitError`; `pn.run()` uses the
selected `PyneSettings.max_bars` and returns `PYNE_RESOURCE_LIMIT_EXCEEDED`.
The CLI applies its selected `--limit max_bars=...` during CSV loading.
These input limits are independent of retained history and replay recording.

Optional `time_close` data can be supplied through OHLCV dicts, CSV column maps,
or Pandas column mapping:

```python
data = pn.from_pandas(df, time_close="close_time")
```

Methods:

- `to_ohlcv()`
- `to_pandas()`
- `column(name)`
- `head(n=5)`
- `tail(n=5)`

Convenience properties:

- `columns`
- `first`
- `last`
- `time_range`

Column names can also be accessed with item syntax:

```python
closes = data["close"]
close_times = data["time_close"]
first_bar = data[0]
first_ten = data[:10]
```
