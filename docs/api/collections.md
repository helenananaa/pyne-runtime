# Collections API

Pyne exposes Pine-like mutable collections as script globals. The currently
supported namespaces are `array.*`, `map.*`, and `matrix.*`.

Collections have no default capacity or nesting-depth quota. Callers may opt into
`PyneSettings` array/map/matrix/depth limits; `None` means unlimited.
Exceeding a configured limit returns `PYNE_SECURITY_ERROR`.

Pyne arrays are Python objects created by `array.new_*()` or `array.from_*()`.
They can be used with Pine-style namespace functions:

```python
values = array.new_float(2, 1.0)
array.push(values, close[1])
last = array.get(values, -1)
```

They also expose Python-style methods for package users:

```python
values = array.from_values(1, 2, 3)
values.push(4)
average = values.avg()
```

Use `snapshot()` when a script needs a mutation boundary for nested
collections. It recursively snapshots nested `array`, `map`, and `matrix`
values, so later mutations to the live collection do not affect the snapshot.

Collections can store stable script values: scalars, `na`, series values,
colors, drawing object handles, and nested `array`/`map`/`matrix` values.
Callable objects and Python modules are rejected because they are executable
runtime values rather than serializable script state. Recursive collection
values, such as an array that stores itself directly or through another
collection, are also rejected because they cannot be safely snapshotted or
serialized.

In incremental scripts, `ctx.state()` cells keep committed snapshot history.
When a state cell stores an array, map, or matrix, `cell[1]` returns the
previous confirmed bar's collection snapshot. Mutating the current collection
does not mutate that historical snapshot:

```python
def on_bar(ctx, bar):
    values = ctx.state("values", array.new())
    previous = values[1]
    array.push(values.value, bar.close)
    previous_size = array.size(previous) if previous is not None else 0
    ctx.plot("Previous Size", previous_size)
```

## Constructors

- `array.new(size=0, initial_value=None)`
- `array.new_float(size=0, initial_value=None)`
- `array.new_int(size=0, initial_value=None)`
- `array.new_bool(size=0, initial_value=False)`
- `array.new_string(size=0, initial_value=None)`
- `array.new_color(size=0, initial_value=None)`
- `array.new_line(size=0, initial_value=None)`
- `array.new_label(size=0, initial_value=None)`
- `array.new_box(size=0, initial_value=None)`
- `array.from_values(*values)`
- `array.from_list(values)`

Pine's `array.from(...)` name cannot be written as normal Python syntax because
`from` is a Python keyword, so Pyne exposes `array.from_values(...)` and
`array.from_list(...)` instead.

Array constructor sizes must be non-negative.

## Mutations And Accessors

- `array.size(arr)`
- `array.get(arr, index)`
- `array.first(arr)`
- `array.last(arr)`
- `array.set(arr, index, value)`
- `array.push(arr, value)`
- `array.pop(arr)`
- `array.unshift(arr, value)`
- `array.shift(arr)`
- `array.insert(arr, index, value)`
- `array.remove(arr, index)`
- `array.clear(arr)`
- `array.copy(arr)`
- `array.snapshot(arr)`
- `array.slice(arr, index_from, index_to=None)`
- `array.fill(arr, value, index_from=0, index_to=None)`
- `array.reverse(arr)`
- `array.sort(arr, order=None, reverse=False)`
- `array.sort_indices(arr, order=None, reverse=False)`

Negative indexes are accepted as Python-friendly shorthand for positions from
the end, so `array.get(values, -1)` returns the latest item.
`array.pop()` and `array.shift()` reject empty arrays with actionable runtime
errors.

`array.slice()` returns a connected index window into its parent. Writes and
reordering affect the same elements in both arrays. Insertions and removals
through a slice change its range and the parent; nested slices preserve this
connection. Direct parent edits retain the slice's index range. Shortening the
parent reduces the visible size; regrowth restores visibility within that range.
`array.copy()` detaches the array structure, while `snapshot()` also freezes
nested values. Preview and local/state checkpoints preserve live connections;
confirmed history remains isolated. Slice growth checks every parent budget,
and retained-state accounting includes the hidden parent graph. Defaults remain
unlimited. Restore validates slice parent types, bounds and parent chains before
adoption, including slices in shared confirmed history. Python-friendly slice
bound normalization is a separate extension;
the native `array_slice_reference` probe qualifies 16 fixed valid mutation cases,
not every bound, type or collection API.

`array.sort()` accepts Pine-like `order.ascending` / `order.descending`
constants. `array.sort_indices()` returns a new array of original indexes in
sorted-value order without mutating the source array. The existing
Python-friendly `reverse=True` keyword remains available.

Numeric arrays sort missing values (`None` or floating-point NaN) after numbers
in ascending order and before numbers in descending order. Ascending index
ordering preserves original positions for equal values; descending
`sort_indices()` reverses that entire permutation, including equal values and
missing values. Sorting incomparable payloads raises before changing the array.
The native `array_missing_sort` probe qualifies eight numeric cases, including
duplicates, missing values, empty arrays and a singleton. It does not establish
string collation, arbitrary payload ordering or full collection API coverage.

## Search And Reduction

- `array.includes(arr, value)`
- `array.indexof(arr, value)`
- `array.lastindexof(arr, value)`
- `array.join(arr, separator="")`
- `array.sum(arr)`
- `array.avg(arr)`
- `array.min(arr)`
- `array.max(arr)`

Numeric reducers skip `na` values and non-numeric payloads. They return `None`
when no numeric values are available, which serializes as `na` in normal Pyne
plot output.

Search helpers do not match a missing value, including `None` and numeric NaN:
`includes()` returns false, and both index helpers return -1. Other values retain
their normal equality comparison. Boolean constructors default to `False`;
passing an explicit `None` remains a Python payload extension.

`join()` defaults to an empty separator. String arrays convert missing elements
to empty strings; numeric arrays convert them to `NaN`. String construction
intent is inferred from initial string values or set by `new_string()`, and is
preserved by copying, slicing, snapshot history, previews and local/state
restores. It does not restrict Python payload types. Restores reject a missing or
malformed intent field before adoption. Finite float values retain a fractional
digit for whole numbers, use uppercase scientific notation outside
`[0.001, 10000000)`, and normalize signed zero to `0.0`.
The native `array_search_fill_join` probe qualifies 16 fixed float profiles,
eight string cases and two Boolean construction cases. Raw joined text is checked
exactly, separately from numeric plots; the plots retain their eight-decimal
transport differences. Arbitrary types, nonfinite payloads, all float rounding
boundaries and additional collection type combinations remain unqualified.
Eight scalar matrix/map extraction profiles are qualified separately below. Native `array.join()` accepts integer, float and string arrays;
other Python payloads continue to use their string representation as an extension.

## Maps

Pyne maps are mutable key/value containers created by `map.new()`,
`map.from_values()`, or `map.from_dict()`.

```python
levels = map.new()
map.put(levels, "fast", 10)
map.put(levels, "slow", 20)
slow = map.get(levels, "slow")
```

Python-style object methods are also available:

```python
weights = map.from_values("fast", 2, "slow", 4)
copy = weights.copy()
copy.put("signal", 8)
keys = copy.keys()
```

Supported map helpers:

- `map.new()`
- `map.from_values(key1, value1, ...)`
- `map.from_dict(values)`
- `map.copy(m)`
- `map.size(m)`
- `map.put(m, key, value)`
- `map.put_all(m, other)`
- `map.get(m, key, default=None)`
- `map.contains(m, key)`
- `map.remove(m, key)`
- `map.clear(m)`
- `map.keys(m)`
- `map.snapshot(m)`
- `map.values(m)`

`map.keys()` and `map.values()` return `PyneArray` instances, so they can be
used directly with `array.*` helpers such as `array.join(map.keys(m), ",")` or
`array.sum(map.values(m))`.

Maps preserve insertion order. Replacing an existing key keeps its position;
removing and reinserting it appends it after the surviving keys. `put_all()`
overwrites existing values in place in that order and appends new keys in the
source's order. The entire merge is validated before committing: a capacity,
depth or recursive-value rejection leaves the destination unchanged.
`copy()`, `keys()` and `values()` detach container structure; scalar edits to
those results do not update the original map. Reference-valued payloads remain
shallow references, while `snapshot()` recursively isolates collection values.
The native `map_scalar_mutation` probe qualifies 16 fixed cases using integer
keys and scalar float/missing values. It does not qualify all key types,
reference-valued payloads, native error behavior or every collection API.

Map keys must be scalar hashable values. Collection objects such as `PyneArray`,
`PyneMap`, and `PyneMatrix` are supported as stored values, but not as keys.

## Matrices

Pyne matrices are mutable two-dimensional containers created by `matrix.new_*()`
or `matrix.from_rows()`.

```python
m = matrix.new_float(2, 3, 0.0)
matrix.set(m, 0, 1, 2.0)
cell = matrix.get(m, 0, 1)
```

Python-style object methods are also available:

```python
m = matrix.from_rows([[1, 2], [3, 4]])
t = m.transpose()
total = m.sum()
```

Supported matrix helpers:

- `matrix.new(rows=0, columns=0, initial_value=None)`
- `matrix.new_float(rows=0, columns=0, initial_value=None)`
- `matrix.new_int(rows=0, columns=0, initial_value=None)`
- `matrix.new_bool(rows=0, columns=0, initial_value=False)`
- `matrix.new_string(rows=0, columns=0, initial_value=None)`
- `matrix.new_color(rows=0, columns=0, initial_value=None)`
- `matrix.from_rows(rows)`
- `matrix.copy(m)`
- `matrix.snapshot(m)`
- `matrix.rows(m)`
- `matrix.columns(m)`
- `matrix.elements_count(m)`
- `matrix.get(m, row, column)`
- `matrix.set(m, row, column, value)`
- `matrix.fill(m, value)`
- `matrix.row(m, row)`
- `matrix.col(m, column)`
- `matrix.transpose(m)`
- `matrix.reshape(m, rows, columns)`
- `matrix.add(left, right)`
- `matrix.sub(left, right)`
- `matrix.mult(left, right)`
- `matrix.sum(m)`
- `matrix.avg(m)`
- `matrix.min(m)`
- `matrix.max(m)`

`matrix.row()` and `matrix.col()` return `PyneArray` instances. `matrix.add()`
and `matrix.sub()` support matching matrix dimensions. `matrix.mult()` supports
scalar multiplication and matrix multiplication.

Matrix row and column counts must be non-negative. `matrix.from_rows()` rejects
ragged row shapes, and `matrix.reshape()` must keep the same element count.

`matrix.reshape()` changes the referenced matrix after validating the new
shape; aliases see the changed dimensions. Pyne returns that same matrix for
Python chaining. Copies and earlier confirmed snapshots keep their own shapes.

Numeric `matrix.add()` and `matrix.sub()` correspond to Pine's two-operand
`matrix.sum()` and `matrix.diff()`. Pyne's one-operand `matrix.sum()` is an
aggregate extension, not Pine's matrix addition operation. Elementwise arithmetic
propagates missing operands; a matrix-product cell is missing if any term in
its dot product is missing, including multiplication by zero. Other product
cells remain computable. The `matrix_missing_reshape` native probe qualifies
eight fixed 2x2 numeric cases and reshape to 1x4/4x1; broader shape, type and
collection API coverage remains unqualified.


Boolean matrices default to false; explicit `None` remains a Python extension.
String matrices retain conversion intent from `new_string()`, initial strings,
`from_rows()` strings or successful string writes. Scalar rows and columns are
separate arrays, preserving this intent after every element becomes missing;
copy, transpose, reshape, snapshot and incremental history/restore preserve it.

Maps infer string value conversion intent from initial values or successful
string writes. Missing overwrites, removals, clear/repopulation, copy, snapshot,
`put_all()` and `values()` preserve it; scalar extracted values are detached.
Rejected admissions do not change the hint. An initially all-missing generic map
has no inferable string intent; broader typing and reference-valued behavior are
unqualified. Hints do not impose homogeneous Python payload types. Restore
rejects malformed hints before adopting current state or confirmed history.

The native `collection_string_extraction` probe qualifies eight fixed scalar
string matrix/map profiles, two Boolean matrix constructors and detached scalar
extractions. Its 224 exact text cells in two execution modes are counted
separately from 256 numeric output cells, and separately from the existing
256 native array-join text cells. Complete collection type, shape, bounds and
mixed-payload qualification remains outstanding.


Matrices retain both dimensions even with no elements: `new_float(0, 3)` has
zero rows and three columns, and its valid columns are empty arrays. Copy,
snapshot, transpose, reshape, scalar/elementwise arithmetic and matrix product
preserve the resulting shape. A 3x0 matrix multiplied by a 0x2 matrix produces a
3x2 zero matrix, subject to the selected result cell budget. Failed reshape and
product admission leave input matrices unchanged. Restores reject missing,
invalid or inconsistent stored width, including in confirmed history, before
adoption. `from_rows([])` has shape 0x0 because no width can be inferred.

The native `matrix_empty_shapes` probe qualifies eight fixed shape transitions
in two cycles/16 rows, including 0x0, 0x3, 3x0, 1x0 and a 2x2 control, scalar
arithmetic and degenerate matrix products. It measures 1,152 numeric output
cells across batch and incremental modes; absent row/column and product values
are retained as missing, separately from active comparisons. It does not qualify
all matrix shapes, types, operands, extraction indices or rejection boundaries.

The `matrix_rectangular_products` native probe adds twelve fixed float profiles:
six finite rectangular products and six missing/zero profiles, repeated in 24
rows. It also checks `transpose(B) * transpose(A)`, detached result mutations,
and copied/aliased reshapes. Its 1,728 numeric cells in two modes have zero
differences; 676 both-missing cells remain separate from active comparisons.
Three native dimension-error witnesses establish rejection for one multiplication
and two elementwise shape mismatches. Native errors stop execution; independent
Python tests verify caught-error operand preservation, preview isolation,
confirmed history and restore continuation. These samples do not qualify all
matrix types, dimensions, numerical conditioning or invalid inputs.
