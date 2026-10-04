"""Iterative snapshots of collection graphs, preserving their shared nodes."""
from __future__ import annotations

from typing import Any

from .security import PyneResourceLimitError, PyneStateContractError


def snapshot_collection(value: Any, seen: set[int], *, collection_types: tuple[type, ...],
                        enforce_limit, validate_key, validate_value) -> Any:
    # The public collection module supplies its types and admission functions;
    # graph traversal owns neither their definitions nor a persistent cache.
    PyneArray, PyneMap, PyneMatrix = collection_types
    if not isinstance(value, collection_types):
        return value

    def allocate(source):
        if isinstance(source, PyneArray):
            values = source.to_list()
            enforce_limit("array size", len(values), source._max_size)
            result = PyneArray(max_size=source._max_size, max_depth=source._max_depth)
            result._values = [None] * len(values)
            entries = enumerate(values)
        elif isinstance(source, PyneMap):
            values = source.to_dict()
            enforce_limit("map size", len(values), source._max_size)
            for key in values:
                validate_key(key)
            result = PyneMap(max_size=source._max_size,
                             array_max_size=source._array_max_size, max_depth=source._max_depth)
            entries = values.items()
        else:
            values = source.to_list()
            width = len(values[0]) if values else 0
            if any(len(row) != width for row in values):
                raise ValueError("matrix rows must all have the same length")
            enforce_limit("matrix cells", len(values) * width, source._max_cells)
            result = PyneMatrix(max_cells=source._max_cells,
                                array_max_size=source._array_max_size, max_depth=source._max_depth)
            result._values = [[None] * width for _ in values]
            result._column_count = source._column_count
            entries = (((row_index, column_index), item)
                       for row_index, row in enumerate(values)
                       for column_index, item in enumerate(row))
        result._string_values = source._string_values
        return result, iter(entries)

    def assign(target, key, child):
        if isinstance(target, PyneMatrix):
            row, column = key
            target._values[row][column] = child
        else:
            target._values[key] = child

    active = set(seen)
    root_id = id(value)
    if root_id in active:
        raise PyneStateContractError("recursive collection snapshots are not supported")
    root, entries = allocate(value)
    memo = {root_id: root}
    heights: dict[int, int] = {}
    active.add(root_id)
    # [source identity, detached target, entries, largest child height]
    frames = [[root_id, root, entries, 0]]
    while frames:
        frame = frames[-1]
        try:
            key, child = next(frame[2])
        except StopIteration:
            height = 1 + frame[3]
            limit = frame[1]._max_depth
            if limit is not None and height > limit:
                raise PyneResourceLimitError(
                    f"collection nesting depth {height} exceeds limit {limit}")
            heights[frame[0]] = height
            active.remove(frame[0])
            frames.pop()
            if frames:
                frames[-1][3] = max(frames[-1][3], height)
            continue
        validate_value(child)
        if not isinstance(child, collection_types):
            assign(frame[1], key, child)
            continue
        child_id = id(child)
        if child_id in active:
            raise PyneStateContractError("recursive collection snapshots are not supported")
        if child_id in memo:
            assign(frame[1], key, memo[child_id])
            frame[3] = max(frame[3], heights[child_id])
        else:
            target, entries = allocate(child)
            memo[child_id] = target
            assign(frame[1], key, target)
            active.add(child_id)
            frames.append([child_id, target, entries, 0])
    return root
