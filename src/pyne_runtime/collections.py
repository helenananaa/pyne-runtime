"""Pine-like mutable collection helpers."""
from __future__ import annotations

from collections.abc import MutableSequence, Sized
import math
from types import ModuleType
from typing import Any, Iterable

import numpy as np

from .security import PyneResourceLimitError, PyneStateContractError
from ._collection_copy import deepcopy_collection
from ._collection_snapshot import snapshot_collection
from .values import is_na_value


class OrderNamespace:
    """Pine-like sort order constants."""

    ascending = "ascending"
    descending = "descending"


class PyneArray:
    """Mutable Pine-like array value."""

    def __init__(
        self,
        values: Iterable[Any] | None = None,
        *,
        max_size: int | None = None,
        max_depth: int | None = None,
    ) -> None:
        self._max_size = _normalize_limit(max_size)
        self._max_depth = _normalize_limit(max_depth)
        self._values = _array_values(values, self._max_size)
        # Retain string construction intent even when every value is missing.
        # This is a conversion hint, not a restriction on Python payload types.
        self._string_values = any(isinstance(item, str) for item in self._values)
        _enforce_limit("array size", len(self._values), self._max_size)
        for item in self._values:
            _validate_collection_assignment(self, item, self._max_depth)

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self):
        return iter(self._values)

    def __repr__(self) -> str:
        return f"PyneArray({self._values!r})"

    def __deepcopy__(self, memo: dict[int, Any]) -> PyneArray:
        return _deepcopy_collection(self, memo)

    def to_list(self) -> list[Any]:
        return list(self._values)

    def copy(self) -> PyneArray:
        result = PyneArray(self._values, max_size=self._max_size, max_depth=self._max_depth)
        result._string_values = self._string_values
        return result

    def snapshot(self) -> PyneArray:
        return _snapshot_array(self, set())

    def size(self) -> int:
        return len(self._values)

    def get(self, index: int) -> Any:
        return self._values[_resolve_index(index, len(self._values))]

    def first(self) -> Any:
        return self.get(0)

    def last(self) -> Any:
        return self.get(-1)

    def set(self, index: int, value: Any) -> None:
        _validate_collection_assignment(self, value, self._max_depth)
        self._values[_resolve_index(index, len(self._values))] = value

    def push(self, value: Any) -> None:
        _enforce_limit("array size", len(self._values) + 1, self._max_size)
        _validate_collection_assignment(self, value, self._max_depth)
        self._values.append(value)

    def pop(self) -> Any:
        if not self._values:
            raise IndexError("array.pop() cannot pop from an empty array")
        return self._values.pop()

    def unshift(self, value: Any) -> None:
        _enforce_limit("array size", len(self._values) + 1, self._max_size)
        _validate_collection_assignment(self, value, self._max_depth)
        self._values.insert(0, value)

    def shift(self) -> Any:
        if not self._values:
            raise IndexError("array.shift() cannot shift from an empty array")
        return self._values.pop(0)

    def insert(self, index: int, value: Any) -> None:
        idx = int(index)
        if idx < 0 or idx > len(self._values):
            raise IndexError(f"array index {idx} is out of bounds")
        _enforce_limit("array size", len(self._values) + 1, self._max_size)
        _validate_collection_assignment(self, value, self._max_depth)
        self._values.insert(idx, value)

    def remove(self, index: int) -> Any:
        return self._values.pop(_resolve_index(index, len(self._values)))

    def clear(self) -> None:
        self._values.clear()

    def includes(self, value: Any) -> bool:
        return any(_values_equal(item, value) for item in self._values)

    def indexof(self, value: Any) -> int:
        for idx, item in enumerate(self._values):
            if _values_equal(item, value):
                return idx
        return -1

    def lastindexof(self, value: Any) -> int:
        for idx in range(len(self._values) - 1, -1, -1):
            if _values_equal(self._values[idx], value):
                return idx
        return -1

    def slice(self, index_from: int, index_to: int | None = None) -> PyneArray:
        start = int(index_from)
        stop = None if index_to is None else int(index_to)
        start, stop, _ = slice(start, stop).indices(len(self._values))
        window = PyneArray(max_size=self._max_size, max_depth=self._max_depth)
        window._values = _ArraySliceStorage(self, start, max(start, stop))
        window._string_values = self._string_values
        return window

    def fill(self, value: Any, index_from: int = 0, index_to: int | None = None) -> None:
        _validate_collection_assignment(self, value, self._max_depth)
        start = max(int(index_from), 0)
        stop = len(self._values) if index_to is None else min(int(index_to), len(self._values))
        for idx in range(start, stop):
            self._values[idx] = value

    def reverse(self) -> None:
        self._values.reverse()

    def sort(self, order: str | None = None, *, reverse: bool = False) -> None:
        descending = _sort_descending(order, reverse)
        # Sort a temporary list so incomparable valid collection values cannot
        # partially mutate the array when Python raises a comparison error.
        ordered = sorted(self._values, key=_array_sort_key, reverse=descending)
        self._values[:] = ordered

    def sort_indices(self, order: str | None = None, *, reverse: bool = False) -> PyneArray:
        descending = _sort_descending(order, reverse)
        indices = sorted(range(len(self._values)), key=lambda index: _array_sort_key(self._values[index]))
        if descending:
            # Native descending indices reverse the ascending permutation,
            # including the original indices within equal/missing values.
            indices.reverse()
        return PyneArray(indices, max_size=self._max_size, max_depth=self._max_depth)

    def join(self, separator: str = "") -> str:
        return str(separator).join(_array_join_value(item, self._string_values) for item in self._values)

    def sum(self) -> float | None:
        numbers = _numeric_values(self._values)
        return float(sum(numbers)) if numbers else None

    def avg(self) -> float | None:
        numbers = _numeric_values(self._values)
        return float(sum(numbers) / len(numbers)) if numbers else None

    def min(self) -> float | None:
        numbers = _numeric_values(self._values)
        return float(min(numbers)) if numbers else None

    def max(self) -> float | None:
        numbers = _numeric_values(self._values)
        return float(max(numbers)) if numbers else None


class _ArraySliceStorage(MutableSequence):
    """A fixed index window; edits through this window resize its own range."""

    def __init__(self, parent: PyneArray, start: int, stop: int) -> None:
        self.parent = parent
        self.start = start
        self.stop = stop

    def __len__(self) -> int:
        parent, windows = self._root_path()
        length = len(parent._values)
        for window in reversed(windows):
            length = max(min(window.stop, length) - window.start, 0)
        return length

    def _root_path(self) -> tuple[PyneArray, list[_ArraySliceStorage]]:
        windows = [self]
        seen = {id(self)}
        parent = self.parent
        while isinstance(parent._values, _ArraySliceStorage):
            window = parent._values
            if id(window) in seen:
                raise PyneStateContractError("recursive array slice storage is unsupported")
            seen.add(id(window))
            windows.append(window)
            parent = window.parent
        return parent, windows

    def __repr__(self) -> str:
        return repr(list(self))

    def __deepcopy__(self, memo: dict[int, Any]) -> _ArraySliceStorage:
        return _deepcopy_collection(self, memo)

    def __getitem__(self, index: Any) -> Any:
        if isinstance(index, slice):
            return [self[idx] for idx in range(*index.indices(len(self)))]
        idx = _resolve_index(index, len(self))
        parent, windows = self._root_path()
        return parent._values[idx + sum(window.start for window in windows)]

    def __setitem__(self, index: Any, value: Any) -> None:
        if isinstance(index, slice):
            indices = list(range(*index.indices(len(self))))
            values = list(value)
            if len(indices) != len(values):
                raise ValueError("array slice replacement must preserve size")
        else:
            indices, values = [_resolve_index(index, len(self))], [value]
        parent, windows = self._root_path()
        # Validate every affected owner before any replacement, including root
        # budgets and hidden slice-parent references that could form a cycle.
        for window in windows:
            for item in values:
                _validate_collection_assignment(window.parent, item, window.parent._max_depth)
        offset = sum(window.start for window in windows)
        for idx, item in zip(indices, values, strict=True):
            parent._values[offset + idx] = item

    def __delitem__(self, index: Any) -> None:
        if isinstance(index, slice):
            indices = list(range(*index.indices(len(self))))
            for idx in sorted(indices, reverse=True):
                self.__delitem__(idx)
            return
        idx = _resolve_index(index, len(self))
        parent, windows = self._root_path()
        parent.remove(idx + sum(window.start for window in windows))
        for window in windows:
            window.stop -= 1

    def insert(self, index: int, value: Any) -> None:
        idx = max(0, min(int(index), len(self)))
        parent, windows = self._root_path()
        for window in windows:
            idx += window.start
            owner = window.parent
            if idx < 0 or idx > len(owner):
                raise IndexError(f"array index {idx} is out of bounds")
            _enforce_limit("array size", len(owner) + 1, owner._max_size)
            _validate_collection_assignment(owner, value, owner._max_depth)
        parent._values.insert(idx, value)
        for window in windows:
            window.stop += 1

    def clear(self) -> None:
        del self[:]


class PyneMap:
    """Mutable Pine-like key/value map."""

    def __init__(
        self,
        values: dict[Any, Any] | None = None,
        *,
        max_size: int | None = None,
        array_max_size: int | None = None,
        max_depth: int | None = None,
    ) -> None:
        self._max_size = _normalize_limit(max_size)
        self._array_max_size = _normalize_limit(array_max_size)
        self._max_depth = _normalize_limit(max_depth)
        self._values: dict[Any, Any] = {}
        for key, value in dict(values or {}).items():
            _validate_map_key(key)
            _validate_collection_assignment(self, value, self._max_depth)
            self._values[key] = value
        _enforce_limit("map size", len(self._values), self._max_size)
        self._string_values = any(isinstance(item, str) for item in self._values.values())

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self):
        return iter(self._values)

    def __repr__(self) -> str:
        return f"PyneMap({self._values!r})"

    def __deepcopy__(self, memo: dict[int, Any]) -> PyneMap:
        return _deepcopy_collection(self, memo)

    def to_dict(self) -> dict[Any, Any]:
        return dict(self._values)

    def copy(self) -> PyneMap:
        result = PyneMap(
            self._values,
            max_size=self._max_size,
            array_max_size=self._array_max_size,
            max_depth=self._max_depth,
        )
        result._string_values = self._string_values
        return result

    def snapshot(self) -> PyneMap:
        return _snapshot_map(self, set())

    def size(self) -> int:
        return len(self._values)

    def put(self, key: Any, value: Any) -> None:
        _validate_map_key(key)
        if key not in self._values:
            _enforce_limit("map size", len(self._values) + 1, self._max_size)
        _validate_collection_assignment(self, value, self._max_depth)
        self._values[key] = value
        self._string_values = self._string_values or isinstance(value, str)

    def put_all(self, other: PyneMap) -> None:
        source = _map(other)
        incoming = source.to_dict()
        merged = dict(self._values)
        for key, value in incoming.items():
            _validate_map_key(key)
            _validate_collection_assignment(self, value, self._max_depth)
            merged[key] = value
        _enforce_limit("map size", len(merged), self._max_size)
        # Validate the whole operation before replacing the mapping. Existing
        # keys keep their positions and new keys follow the source's order.
        self._values = merged
        self._string_values = self._string_values or source._string_values

    def get(self, key: Any, default: Any = None) -> Any:
        _validate_map_key(key)
        return self._values.get(key, default)

    def contains(self, key: Any) -> bool:
        _validate_map_key(key)
        return key in self._values

    def remove(self, key: Any) -> Any:
        _validate_map_key(key)
        return self._values.pop(key, None)

    def clear(self) -> None:
        self._values.clear()

    def keys(self) -> PyneArray:
        return PyneArray(
            self._values.keys(),
            max_size=self._array_max_size,
            max_depth=self._max_depth,
        )

    def values(self) -> PyneArray:
        result = PyneArray(
            self._values.values(),
            max_size=self._array_max_size,
            max_depth=self._max_depth,
        )
        result._string_values = self._string_values
        return result


class PyneMatrix:
    """Mutable Pine-like two-dimensional matrix."""

    def __init__(
        self,
        rows: int = 0,
        columns: int = 0,
        initial_value: Any = None,
        *,
        max_cells: int | None = None,
        array_max_size: int | None = None,
        max_depth: int | None = None,
    ) -> None:
        self._max_cells = _normalize_limit(max_cells)
        self._array_max_size = _normalize_limit(array_max_size)
        self._max_depth = _normalize_limit(max_depth)
        row_count = _matrix_dimension(rows, "matrix rows")
        column_count = _matrix_dimension(columns, "matrix columns")
        _enforce_limit("matrix cells", row_count * column_count, self._max_cells)
        _validate_collection_assignment(self, initial_value, self._max_depth)
        self._values = [
            [initial_value for _ in range(column_count)]
            for _ in range(row_count)
        ]
        self._string_values = isinstance(initial_value, str)
        self._column_count = column_count

    @classmethod
    def from_rows(
        cls,
        rows: Iterable[Iterable[Any]],
        *,
        max_cells: int | None = None,
        array_max_size: int | None = None,
        max_depth: int | None = None,
    ) -> PyneMatrix:
        normalized_limit = _normalize_limit(max_cells)
        values = _matrix_rows(rows, normalized_limit)
        if values:
            width = len(values[0])
            if any(len(row) != width for row in values):
                raise ValueError("matrix rows must all have the same length")
        cell_count = len(values) * (len(values[0]) if values else 0)
        normalized_depth = _normalize_limit(max_depth)
        _enforce_limit("matrix cells", cell_count, normalized_limit)
        for row in values:
            for item in row:
                _validate_stored_value(item)
                _enforce_acyclic_collection_value(item)
                _enforce_child_depth(item, normalized_depth)
        matrix = cls(
            max_cells=normalized_limit,
            array_max_size=array_max_size,
            max_depth=normalized_depth,
        )
        matrix._values = values
        matrix._column_count = len(values[0]) if values else 0
        matrix._string_values = any(isinstance(item, str) for row in values for item in row)
        return matrix

    def __repr__(self) -> str:
        return f"PyneMatrix({self._values!r})"

    def __deepcopy__(self, memo: dict[int, Any]) -> PyneMatrix:
        return _deepcopy_collection(self, memo)

    def to_list(self) -> list[list[Any]]:
        return [list(row) for row in self._values]

    def copy(self) -> PyneMatrix:
        result = PyneMatrix.from_rows(
            self._values,
            max_cells=self._max_cells,
            array_max_size=self._array_max_size,
            max_depth=self._max_depth,
        )
        result._string_values = self._string_values
        result._column_count = self._column_count
        return result

    def snapshot(self) -> PyneMatrix:
        return _snapshot_matrix(self, set())

    def rows(self) -> int:
        return len(self._values)

    def columns(self) -> int:
        return self._column_count

    def elements_count(self) -> int:
        return self.rows() * self.columns()

    def get(self, row: int, column: int) -> Any:
        row_idx, column_idx = self._resolve_cell(row, column)
        return self._values[row_idx][column_idx]

    def set(self, row: int, column: int, value: Any) -> None:
        row_idx, column_idx = self._resolve_cell(row, column)
        _validate_collection_assignment(self, value, self._max_depth)
        self._values[row_idx][column_idx] = value
        self._string_values = self._string_values or isinstance(value, str)

    def fill(self, value: Any) -> None:
        _validate_collection_assignment(self, value, self._max_depth)
        for row_idx in range(self.rows()):
            for column_idx in range(self.columns()):
                self._values[row_idx][column_idx] = value
        self._string_values = self._string_values or isinstance(value, str)

    def row(self, row: int) -> PyneArray:
        row_idx = _resolve_index(row, self.rows(), name="matrix row")
        result = PyneArray(
            self._values[row_idx],
            max_size=self._array_max_size,
            max_depth=self._max_depth,
        )
        result._string_values = self._string_values
        return result

    def col(self, column: int) -> PyneArray:
        column_idx = _resolve_index(column, self.columns(), name="matrix column")
        result = PyneArray(
            (row[column_idx] for row in self._values),
            max_size=self._array_max_size,
            max_depth=self._max_depth,
        )
        result._string_values = self._string_values
        return result

    def transpose(self) -> PyneMatrix:
        result = PyneMatrix.from_rows(
            zip(*self._values) if self.rows() else [[] for _ in range(self.columns())],
            max_cells=self._max_cells,
            array_max_size=self._array_max_size,
            max_depth=self._max_depth,
        )
        result._string_values = self._string_values
        result._column_count = self.rows()
        return result

    def reshape(self, rows: int, columns: int) -> PyneMatrix:
        row_count = _matrix_dimension(rows, "matrix rows")
        column_count = _matrix_dimension(columns, "matrix columns")
        flat = [item for row in self._values for item in row]
        if row_count * column_count != len(flat):
            raise ValueError("matrix.reshape() cannot change element count")
        _enforce_limit("matrix cells", row_count * column_count, self._max_cells)
        rebuilt = [
            flat[idx * column_count:(idx + 1) * column_count]
            for idx in range(row_count)
        ]
        reshaped = PyneMatrix.from_rows(
            rebuilt,
            max_cells=self._max_cells,
            array_max_size=self._array_max_size,
            max_depth=self._max_depth,
        )
        # Native reshape changes the referenced matrix. Validate the rebuilt
        # shape first, then commit so aliases observe the same atomic mutation.
        self._values = reshaped._values
        self._column_count = column_count
        return self

    def add(self, other: Any) -> PyneMatrix:
        return self._binary(other, lambda left, right: left + right)

    def sub(self, other: Any) -> PyneMatrix:
        return self._binary(other, lambda left, right: left - right)

    def mult(self, other: Any) -> PyneMatrix:
        if isinstance(other, PyneMatrix):
            return self._matrix_mult(other)
        return self._binary(other, lambda left, right: left * right)

    def sum(self) -> float | None:
        return _sum_values(self._flatten())

    def avg(self) -> float | None:
        numbers = _numeric_values(self._flatten())
        return float(sum(numbers) / len(numbers)) if numbers else None

    def min(self) -> float | None:
        numbers = _numeric_values(self._flatten())
        return float(min(numbers)) if numbers else None

    def max(self) -> float | None:
        numbers = _numeric_values(self._flatten())
        return float(max(numbers)) if numbers else None

    def _resolve_cell(self, row: int, column: int) -> tuple[int, int]:
        return (
            _resolve_index(row, self.rows(), name="matrix row"),
            _resolve_index(column, self.columns(), name="matrix column"),
        )

    def _flatten(self) -> list[Any]:
        return [item for row in self._values for item in row]

    def _binary(self, other: Any, op: Any) -> PyneMatrix:
        if isinstance(other, PyneMatrix):
            if self.rows() != other.rows() or self.columns() != other.columns():
                raise ValueError("matrix dimensions must match")
            values = [
                [_matrix_element_op(self._values[row][column], other._values[row][column], op)
                 for column in range(self.columns())]
                for row in range(self.rows())
            ]
        else:
            values = [[_matrix_element_op(item, other, op) for item in row] for row in self._values]
        result = PyneMatrix.from_rows(
            values,
            max_cells=self._max_cells,
            array_max_size=self._array_max_size,
            max_depth=self._max_depth,
        )
        result._column_count = self.columns()
        return result

    def _matrix_mult(self, other: PyneMatrix) -> PyneMatrix:
        if self.columns() != other.rows():
            raise ValueError("matrix dimensions are incompatible for multiplication")
        _enforce_limit("matrix cells", self.rows() * other.columns(), self._max_cells)
        values: list[list[Any]] = []
        for row in range(self.rows()):
            output_row = []
            for column in range(other.columns()):
                total: float | None = 0.0
                for idx in range(self.columns()):
                    left = self._values[row][idx]
                    right = other._values[idx][column]
                    if is_na_value(left) or is_na_value(right):
                        total = None
                        break
                    total += float(left) * float(right)
                output_row.append(total)
            values.append(output_row)
        result = PyneMatrix.from_rows(
            values,
            max_cells=self._max_cells,
            array_max_size=self._array_max_size,
            max_depth=self._max_depth,
        )
        result._column_count = other.columns()
        return result


class ArrayNamespace:
    """Pine-like ``array.*`` namespace."""

    def __init__(self, *, max_size: int | None = None, max_depth: int | None = None) -> None:
        self._max_size = _normalize_limit(max_size)
        self._max_depth = _normalize_limit(max_depth)

    def new(self, size: int = 0, initial_value: Any = None) -> PyneArray:
        size_count = _array_size(size)
        _enforce_limit("array size", size_count, self._max_size)
        return PyneArray(
            (initial_value for _ in range(size_count)),
            max_size=self._max_size,
            max_depth=self._max_depth,
        )

    def new_float(self, size: int = 0, initial_value: float | None = None) -> PyneArray:
        return self.new(size, initial_value)

    def new_int(self, size: int = 0, initial_value: int | None = None) -> PyneArray:
        return self.new(size, initial_value)

    def new_bool(self, size: int = 0, initial_value: bool | None = False) -> PyneArray:
        return self.new(size, initial_value)

    def new_string(self, size: int = 0, initial_value: str | None = None) -> PyneArray:
        result = self.new(size, initial_value)
        result._string_values = True
        return result

    def new_color(self, size: int = 0, initial_value: str | None = None) -> PyneArray:
        return self.new(size, initial_value)

    def new_line(self, size: int = 0, initial_value: Any = None) -> PyneArray:
        """Create an array intended for line object references."""
        return self.new(size, initial_value)

    def new_label(self, size: int = 0, initial_value: Any = None) -> PyneArray:
        """Create an array intended for label object references."""
        return self.new(size, initial_value)

    def new_box(self, size: int = 0, initial_value: Any = None) -> PyneArray:
        """Create an array intended for box object references."""
        return self.new(size, initial_value)

    def from_values(self, *values: Any) -> PyneArray:
        return PyneArray(values, max_size=self._max_size, max_depth=self._max_depth)

    def from_list(self, values: Iterable[Any]) -> PyneArray:
        return PyneArray(values, max_size=self._max_size, max_depth=self._max_depth)

    def copy(self, arr: PyneArray) -> PyneArray:
        return _array(arr).copy()

    def snapshot(self, arr: PyneArray) -> PyneArray:
        return _array(arr).snapshot()

    def size(self, arr: PyneArray) -> int:
        return _array(arr).size()

    def get(self, arr: PyneArray, index: int) -> Any:
        return _array(arr).get(index)

    def first(self, arr: PyneArray) -> Any:
        return _array(arr).first()

    def last(self, arr: PyneArray) -> Any:
        return _array(arr).last()

    def set(self, arr: PyneArray, index: int, value: Any) -> None:
        _array(arr).set(index, value)

    def push(self, arr: PyneArray, value: Any) -> None:
        _array(arr).push(value)

    def pop(self, arr: PyneArray) -> Any:
        return _array(arr).pop()

    def unshift(self, arr: PyneArray, value: Any) -> None:
        _array(arr).unshift(value)

    def shift(self, arr: PyneArray) -> Any:
        return _array(arr).shift()

    def insert(self, arr: PyneArray, index: int, value: Any) -> None:
        _array(arr).insert(index, value)

    def remove(self, arr: PyneArray, index: int) -> Any:
        return _array(arr).remove(index)

    def clear(self, arr: PyneArray) -> None:
        _array(arr).clear()

    def includes(self, arr: PyneArray, value: Any) -> bool:
        return _array(arr).includes(value)

    def indexof(self, arr: PyneArray, value: Any) -> int:
        return _array(arr).indexof(value)

    def lastindexof(self, arr: PyneArray, value: Any) -> int:
        return _array(arr).lastindexof(value)

    def slice(self, arr: PyneArray, index_from: int, index_to: int | None = None) -> PyneArray:
        return _array(arr).slice(index_from, index_to)

    def fill(
        self,
        arr: PyneArray,
        value: Any,
        index_from: int = 0,
        index_to: int | None = None,
    ) -> None:
        _array(arr).fill(value, index_from, index_to)

    def reverse(self, arr: PyneArray) -> None:
        _array(arr).reverse()

    def sort(self, arr: PyneArray, order: str | None = None, *, reverse: bool = False) -> None:
        _array(arr).sort(order, reverse=reverse)

    def sort_indices(
        self,
        arr: PyneArray,
        order: str | None = None,
        *,
        reverse: bool = False,
    ) -> PyneArray:
        return _array(arr).sort_indices(order, reverse=reverse)

    def join(self, arr: PyneArray, separator: str = "") -> str:
        return _array(arr).join(separator)

    def sum(self, arr: PyneArray) -> float | None:
        return _array(arr).sum()

    def avg(self, arr: PyneArray) -> float | None:
        return _array(arr).avg()

    def min(self, arr: PyneArray) -> float | None:
        return _array(arr).min()

    def max(self, arr: PyneArray) -> float | None:
        return _array(arr).max()


class MapNamespace:
    """Pine-like ``map.*`` namespace."""

    def __init__(
        self,
        *,
        max_size: int | None = None,
        array_max_size: int | None = None,
        max_depth: int | None = None,
    ) -> None:
        self._max_size = _normalize_limit(max_size)
        self._array_max_size = _normalize_limit(array_max_size)
        self._max_depth = _normalize_limit(max_depth)

    def new(self) -> PyneMap:
        return PyneMap(
            max_size=self._max_size,
            array_max_size=self._array_max_size,
            max_depth=self._max_depth,
        )

    def from_values(self, *items: Any) -> PyneMap:
        if len(items) % 2 != 0:
            raise ValueError("map.from_values() expects key/value pairs")
        result = PyneMap(
            max_size=self._max_size,
            array_max_size=self._array_max_size,
            max_depth=self._max_depth,
        )
        for idx in range(0, len(items), 2):
            result.put(items[idx], items[idx + 1])
        return result

    def from_dict(self, values: dict[Any, Any]) -> PyneMap:
        return PyneMap(
            values,
            max_size=self._max_size,
            array_max_size=self._array_max_size,
            max_depth=self._max_depth,
        )

    def copy(self, m: PyneMap) -> PyneMap:
        return _map(m).copy()

    def snapshot(self, m: PyneMap) -> PyneMap:
        return _map(m).snapshot()

    def size(self, m: PyneMap) -> int:
        return _map(m).size()

    def put(self, m: PyneMap, key: Any, value: Any) -> None:
        _map(m).put(key, value)

    def put_all(self, m: PyneMap, other: PyneMap) -> None:
        _map(m).put_all(other)

    def get(self, m: PyneMap, key: Any, default: Any = None) -> Any:
        return _map(m).get(key, default)

    def contains(self, m: PyneMap, key: Any) -> bool:
        return _map(m).contains(key)

    def remove(self, m: PyneMap, key: Any) -> Any:
        return _map(m).remove(key)

    def clear(self, m: PyneMap) -> None:
        _map(m).clear()

    def keys(self, m: PyneMap) -> PyneArray:
        return _map(m).keys()

    def values(self, m: PyneMap) -> PyneArray:
        return _map(m).values()


class MatrixNamespace:
    """Pine-like ``matrix.*`` namespace."""

    def __init__(
        self,
        *,
        max_cells: int | None = None,
        array_max_size: int | None = None,
        max_depth: int | None = None,
    ) -> None:
        self._max_cells = _normalize_limit(max_cells)
        self._array_max_size = _normalize_limit(array_max_size)
        self._max_depth = _normalize_limit(max_depth)

    def new(self, rows: int = 0, columns: int = 0, initial_value: Any = None) -> PyneMatrix:
        return PyneMatrix(
            rows,
            columns,
            initial_value,
            max_cells=self._max_cells,
            array_max_size=self._array_max_size,
            max_depth=self._max_depth,
        )

    def new_float(
        self,
        rows: int = 0,
        columns: int = 0,
        initial_value: float | None = None,
    ) -> PyneMatrix:
        return self.new(rows, columns, initial_value)

    def new_int(
        self,
        rows: int = 0,
        columns: int = 0,
        initial_value: int | None = None,
    ) -> PyneMatrix:
        return self.new(rows, columns, initial_value)

    def new_bool(
        self,
        rows: int = 0,
        columns: int = 0,
        initial_value: bool | None = False,
    ) -> PyneMatrix:
        return self.new(rows, columns, initial_value)

    def new_string(
        self,
        rows: int = 0,
        columns: int = 0,
        initial_value: str | None = None,
    ) -> PyneMatrix:
        result = self.new(rows, columns, initial_value)
        result._string_values = True
        return result

    def new_color(
        self,
        rows: int = 0,
        columns: int = 0,
        initial_value: str | None = None,
    ) -> PyneMatrix:
        return self.new(rows, columns, initial_value)

    def from_rows(self, rows: Iterable[Iterable[Any]]) -> PyneMatrix:
        return PyneMatrix.from_rows(
            rows,
            max_cells=self._max_cells,
            array_max_size=self._array_max_size,
            max_depth=self._max_depth,
        )

    def copy(self, m: PyneMatrix) -> PyneMatrix:
        return _matrix(m).copy()

    def snapshot(self, m: PyneMatrix) -> PyneMatrix:
        return _matrix(m).snapshot()

    def rows(self, m: PyneMatrix) -> int:
        return _matrix(m).rows()

    def columns(self, m: PyneMatrix) -> int:
        return _matrix(m).columns()

    def elements_count(self, m: PyneMatrix) -> int:
        return _matrix(m).elements_count()

    def get(self, m: PyneMatrix, row: int, column: int) -> Any:
        return _matrix(m).get(row, column)

    def set(self, m: PyneMatrix, row: int, column: int, value: Any) -> None:
        _matrix(m).set(row, column, value)

    def fill(self, m: PyneMatrix, value: Any) -> None:
        _matrix(m).fill(value)

    def row(self, m: PyneMatrix, row: int) -> PyneArray:
        return _matrix(m).row(row)

    def col(self, m: PyneMatrix, column: int) -> PyneArray:
        return _matrix(m).col(column)

    def transpose(self, m: PyneMatrix) -> PyneMatrix:
        return _matrix(m).transpose()

    def reshape(self, m: PyneMatrix, rows: int, columns: int) -> PyneMatrix:
        return _matrix(m).reshape(rows, columns)

    def add(self, left: PyneMatrix, right: Any) -> PyneMatrix:
        return _matrix(left).add(right)

    def sub(self, left: PyneMatrix, right: Any) -> PyneMatrix:
        return _matrix(left).sub(right)

    def mult(self, left: PyneMatrix, right: Any) -> PyneMatrix:
        return _matrix(left).mult(right)

    def sum(self, m: PyneMatrix) -> float | None:
        return _matrix(m).sum()

    def avg(self, m: PyneMatrix) -> float | None:
        return _matrix(m).avg()

    def min(self, m: PyneMatrix) -> float | None:
        return _matrix(m).min()

    def max(self, m: PyneMatrix) -> float | None:
        return _matrix(m).max()


def _array(value: PyneArray) -> PyneArray:
    if not isinstance(value, PyneArray):
        raise TypeError("array.* expects a PyneArray created by array.new_*()")
    return value


def _map(value: PyneMap) -> PyneMap:
    if not isinstance(value, PyneMap):
        raise TypeError("map.* expects a PyneMap created by map.new()")
    return value


def _matrix(value: PyneMatrix) -> PyneMatrix:
    if not isinstance(value, PyneMatrix):
        raise TypeError("matrix.* expects a PyneMatrix created by matrix.new_*()")
    return value


def _resolve_index(index: int, length: int, *, name: str = "array index") -> int:
    idx = int(index)
    if idx < 0:
        idx = length + idx
    if idx < 0 or idx >= length:
        raise IndexError(f"{name} {int(index)} is out of bounds")
    return idx


def _matrix_dimension(value: int, label: str) -> int:
    normalized = int(value)
    if normalized < 0:
        raise ValueError(f"{label} must be non-negative")
    return normalized


def _array_size(value: int) -> int:
    normalized = int(value)
    if normalized < 0:
        raise ValueError("array size must be non-negative")
    return normalized


def _array_values(values: Iterable[Any] | None, max_size: int | None) -> list[Any]:
    if values is None:
        return []
    if max_size is None:
        return list(values)
    if isinstance(values, Sized):
        _enforce_limit("array size", len(values), max_size)
    result: list[Any] = []
    for item in values:
        _enforce_limit("array size", len(result) + 1, max_size)
        result.append(item)
    return result


def _matrix_rows(rows: Iterable[Iterable[Any]], max_cells: int | None) -> list[list[Any]]:
    if max_cells is None:
        return [list(row) for row in rows]
    values: list[list[Any]] = []
    cells = 0
    width: int | None = None
    for row in rows:
        current: list[Any] = []
        for item in row:
            _enforce_limit("matrix cells", cells + 1, max_cells)
            current.append(item)
            cells += 1
        if width is not None and len(current) != width:
            raise ValueError("matrix rows must all have the same length")
        width = len(current)
        values.append(current)
    return values


def _normalize_limit(limit: int | None) -> int | None:
    if limit is None:
        return None
    return max(int(limit), 1)


def _enforce_limit(label: str, size: int, limit: int | None) -> None:
    if limit is not None and size > limit:
        raise PyneResourceLimitError(f"{label} {size} exceeds limit {limit}")


def _validate_map_key(key: Any) -> None:
    if isinstance(key, (PyneArray, PyneMap, PyneMatrix)):
        raise ValueError("map keys must be scalar hashable values; collection keys are unsupported")
    try:
        hash(key)
    except TypeError as exc:
        raise ValueError("map key must be hashable") from exc


def _validate_stored_value(value: Any) -> None:
    if is_na_value(value):
        return
    if isinstance(value, ModuleType) or callable(value):
        raise ValueError(
            "collection values must be stable script values; "
            "callable and module values are unsupported"
        )


def _validate_collection_assignment(
    container: PyneArray | PyneMap | PyneMatrix,
    value: Any,
    max_depth: int | None,
) -> None:
    _validate_stored_value(value)
    _enforce_no_recursive_collection_value(container, value)
    _enforce_child_depth(value, max_depth)


def _enforce_acyclic_collection_value(value: Any) -> None:
    if _collection_has_cycle(value):
        raise PyneStateContractError("recursive collection values are unsupported")


def _enforce_no_recursive_collection_value(
    container: PyneArray | PyneMap | PyneMatrix,
    value: Any,
) -> None:
    if _collection_references(value, id(container)) or _collection_has_cycle(value):
        raise PyneStateContractError("recursive collection values are unsupported")


def _deepcopy_collection(value: Any, memo: dict[int, Any]) -> Any:
    return deepcopy_collection(value, memo, owned_types=(PyneArray, PyneMap, PyneMatrix, _ArraySliceStorage),
                               matrix_type=PyneMatrix)


def _snapshot_value(value: Any, seen: set[int]) -> Any:
    return snapshot_collection(value, seen, collection_types=(PyneArray, PyneMap, PyneMatrix),
                               enforce_limit=_enforce_limit, validate_key=_validate_map_key,
                               validate_value=_validate_stored_value)


def _snapshot_array(value: PyneArray, seen: set[int]) -> PyneArray:
    return _snapshot_value(value, seen)


def _snapshot_map(value: PyneMap, seen: set[int]) -> PyneMap:
    return _snapshot_value(value, seen)

def _snapshot_matrix(value: PyneMatrix, seen: set[int]) -> PyneMatrix:
    return _snapshot_value(value, seen)

def _enforce_child_depth(value: Any, limit: int | None) -> None:
    if limit is None:
        return
    depth = 1 + _collection_depth(value)
    if depth > limit:
        raise PyneResourceLimitError(f"collection nesting depth {depth} exceeds limit {limit}")


def _collection_children(value: Any, *, include_slice_parent: bool = False):
    if isinstance(value, PyneArray):
        if include_slice_parent and isinstance(value._values, _ArraySliceStorage):
            yield value._values.parent
        yield from value.to_list()
    elif isinstance(value, PyneMap):
        yield from value.to_dict().values()
    elif isinstance(value, PyneMatrix):
        for row in value.to_list():
            yield from row


def _collection_depth(value: Any, seen: set[int] | None = None) -> int:
    return _graph_depth(value, set(seen or ()), {})


def _graph_depth(value: Any, active: set[int], heights: dict[int, int]) -> int:
    if not isinstance(value, (PyneArray, PyneMap, PyneMatrix)):
        return 0
    identity = id(value)
    if identity in active:
        return 1
    if identity in heights:
        return heights[identity]
    active.add(identity)
    frames = [[identity, iter(_collection_children(value)), 0]]
    while frames:
        frame = frames[-1]
        try:
            child = next(frame[1])
        except StopIteration:
            height = 1 + frame[2]
            heights[frame[0]] = height
            active.remove(frame[0])
            frames.pop()
            if frames:
                frames[-1][2] = max(frames[-1][2], height)
            continue
        if not isinstance(child, (PyneArray, PyneMap, PyneMatrix)):
            continue
        child_id = id(child)
        if child_id in active:
            frame[2] = max(frame[2], 1)
        elif child_id in heights:
            frame[2] = max(frame[2], heights[child_id])
        else:
            active.add(child_id)
            frames.append([child_id, iter(_collection_children(child)), 0])
    return heights[identity]


def _collection_references(value: Any, target_id: int, seen: set[int] | None = None) -> bool:
    visited = set(seen or ())
    pending = [value]
    while pending:
        current = pending.pop()
        if not isinstance(current, (PyneArray, PyneMap, PyneMatrix)):
            continue
        identity = id(current)
        if identity == target_id:
            return True
        if identity in visited:
            continue
        visited.add(identity)
        pending.extend(_collection_children(current, include_slice_parent=True))
    return False


def _collection_has_cycle(value: Any, path: set[int] | None = None) -> bool:
    if not isinstance(value, (PyneArray, PyneMap, PyneMatrix)):
        return False
    active, complete = set(path or ()), set()
    identity = id(value)
    if identity in active:
        return True
    active.add(identity)
    frames = [(identity, iter(_collection_children(value)))]
    while frames:
        try:
            child = next(frames[-1][1])
        except StopIteration:
            identity, _ = frames.pop()
            active.remove(identity)
            complete.add(identity)
            continue
        if not isinstance(child, (PyneArray, PyneMap, PyneMatrix)):
            continue
        identity = id(child)
        if identity in active:
            return True
        if identity not in complete:
            active.add(identity)
            frames.append((identity, iter(_collection_children(child))))
    return False


def _max_collection_depth(values: Iterable[Any], seen: set[int] | None = None) -> int:
    active, heights = set(seen or ()), {}
    return max((_graph_depth(value, active, heights) for value in values), default=0)


def _numeric_values(values: Iterable[Any]) -> list[float]:
    numbers: list[float] = []
    for item in values:
        if is_na_value(item):
            continue
        try:
            numbers.append(float(item))
        except (TypeError, ValueError):
            continue
    return numbers


def _sum_values(values: Iterable[Any]) -> float | None:
    numbers = _numeric_values(values)
    return float(sum(numbers)) if numbers else None


def _sort_descending(order: str | None, reverse: bool) -> bool:
    if order is None:
        return bool(reverse)
    normalized = str(order).strip().lower()
    if normalized == OrderNamespace.ascending:
        return False
    if normalized == OrderNamespace.descending:
        return True
    raise ValueError("array.sort() order must be order.ascending or order.descending")


def _matrix_element_op(left: Any, right: Any, op: Any) -> Any:
    return None if is_na_value(left) or is_na_value(right) else op(left, right)


def _array_sort_key(value: Any) -> tuple[bool, Any]:
    missing = is_na_value(value)
    return missing, 0 if missing else value


def _values_equal(left: Any, right: Any) -> bool:
    if is_na_value(left) or is_na_value(right):
        return False
    return left == right


def _array_join_value(value: Any, string_values: bool) -> str:
    if is_na_value(value):
        return "" if string_values else "NaN"
    if isinstance(value, (float, np.floating)):
        number = float(value)
        if not math.isfinite(number):
            return str(number)  # Python-only nonfinite payload extension.
        if number == 0:
            return "0.0"
        if 0.001 <= abs(number) < 10_000_000:
            return np.format_float_positional(number, unique=True, trim="0")
        mantissa, exponent = np.format_float_scientific(number, unique=True, trim="0", exp_digits=1).split("e")
        return mantissa + "E" + str(int(exponent))
    return str(value)


order_namespace = OrderNamespace()
array_namespace = ArrayNamespace()
map_namespace = MapNamespace()
matrix_namespace = MatrixNamespace()
