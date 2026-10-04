"""Iterative deep copies of owned collection nodes and their internal storage."""
from __future__ import annotations

import copy
from collections import deque
from typing import Any


def _attributes(value):
    attributes = dict(vars(value))
    for cls in type(value).__mro__:
        slots = cls.__dict__.get("__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        for name in slots:
            if name in {"__dict__", "__weakref__"}:
                continue
            if name.startswith("__") and not name.endswith("__"):
                name = f"_{cls.__name__.lstrip('_')}{name}"
            if hasattr(value, name):
                attributes[name] = getattr(value, name)
    return attributes


def deepcopy_collection(value: Any, memo: dict[int, Any], *, owned_types: tuple[type, ...],
                        matrix_type: type) -> Any:
    if id(value) in memo:
        return memo[id(value)]
    nodes, storages = [], []
    pending, seen = [value], set()

    def allocate_storage(source):
        if id(source) not in memo:
            target = [] if isinstance(source, list) else {}
            memo[id(source)] = target
            storages.append((source, target))

    # Allocate the complete owned graph before copying leaf payloads. Ordinary
    # deepcopy then resolves all collection links from the caller's memo,
    # including links inside Python containers and aliases in callback globals.
    while pending:
        current = pending.pop()
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        if isinstance(current, owned_types):
            if identity in memo:
                continue
            target = object.__new__(type(current))
            memo[identity] = target
            attributes = _attributes(current)
            nodes.append((current, target, attributes))
            storage = attributes.get("_values")
            if isinstance(storage, (list, dict)):
                allocate_storage(storage)
                if isinstance(current, matrix_type):
                    for row in storage:
                        if isinstance(row, list):
                            allocate_storage(row)
            pending.extend(attributes.values())
        elif isinstance(current, dict):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, (list, tuple, set, frozenset, deque)):
            pending.extend(current)

    for source, target in storages:
        if isinstance(source, list):
            target.extend(copy.deepcopy(item, memo) for item in source)
        else:
            for key, item in source.items():
                target[copy.deepcopy(key, memo)] = copy.deepcopy(item, memo)
    for source, target, attributes in nodes:
        for name, item in attributes.items():
            object.__setattr__(target, name, copy.deepcopy(item, memo))
    # Match deepcopy's source lifetime convention for nodes whose links were
    # handled directly instead of recursively entering the standard dispatcher.
    sources = memo.setdefault(id(memo), [])
    sources.extend(source for source, _ in storages)
    sources.extend(source for source, _, _ in nodes)
    return memo[id(value)]
