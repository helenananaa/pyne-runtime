"""Compare admitted parameter graphs without invoking user equality methods.

Recovery checks owned Python state, including slots, scalar subclass attributes,
NumPy storage, cycles and aliases. User ``__eq__`` implementations are neither a
computation identity nor a safe admission check.
"""
from __future__ import annotations

import struct
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from types import FunctionType, MemberDescriptorType, SimpleNamespace
from typing import Any

import numpy as np


_ATOMIC_TYPES = (type(None), bool, int, float, complex, str, bytes, range)


def instance_parameter_items(value: Any) -> list[tuple[tuple[Any, ...], Any]]:
    """Read actual instance storage, including inherited slots, without getters."""
    items: list[tuple[tuple[Any, ...], Any]] = []
    try:
        attributes = object.__getattribute__(value, "__dict__")
    except AttributeError:
        attributes = None
    if isinstance(attributes, dict):
        items.extend((("dict", name), item) for name, item in dict.items(attributes))
    for cls in type(value).__mro__:
        for name, descriptor in vars(cls).items():
            if not isinstance(descriptor, MemberDescriptorType):
                continue
            try:
                item = descriptor.__get__(value, type(value))
            except AttributeError:
                continue
            items.append((("slot", cls, name), item))
    return items


def parameter_array_items(value: np.ndarray) -> list[Any]:
    """Expose actual object references, excluding synthetic row containers."""
    items: list[Any] = []
    pending = [np.ndarray.view(value, np.ndarray)]
    while pending:
        plain = pending.pop()
        if plain.dtype.kind == "O":
            items.extend(plain.flat)
        elif plain.dtype.hasobject:
            pending.extend(np.ndarray.__getitem__(plain, name)
                           for name in plain.dtype.names or ())
    return items


def _atomic_payload(value: Any) -> Any:
    # Exact builtin operations bypass custom scalar subclass conversions.
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int.__int__(value)
    if isinstance(value, float):
        return struct.pack("!d", float.__float__(value))
    if isinstance(value, complex):
        number = complex.__complex__(value)
        return struct.pack("!dd", number.real, number.imag)
    if isinstance(value, str):
        return str.__str__(value)
    if isinstance(value, bytes):
        return bytes.__bytes__(value)
    if isinstance(value, range):
        return value.start, value.stop, value.step
    return None


@dataclass
class _Unordered:
    left: list[Any]
    right: list[Any]


def parameters_equal(left: Any, right: Any) -> bool:
    """Require the same state graph, without scalar/vector user comparisons.

    Set members are matched with explicit backtracking, so ambiguous equal-looking
    objects still preserve alias relationships to other roots. Normal ordered
    parameter graphs use one iterative traversal.
    """
    choices: list[tuple[list[Any], dict[int, int], dict[int, int]]] = [
        ([(left, right)], {}, {})
    ]
    # Array field views and converted scalar tuples are temporary graph roots.
    # Keep traversed values alive so their ids cannot be reused by later roots.
    keep_alive: list[Any] = []
    while choices:
        pending, forward, reverse = choices.pop()
        valid = True
        while pending and valid:
            task = pending.pop()
            if isinstance(task, _Unordered):
                if not task.left:
                    continue
                first, remaining = task.left[0], task.left[1:]
                for index, candidate in enumerate(task.right):
                    if type(first) is not type(candidate):
                        continue
                    branch = list(pending)
                    branch.append(_Unordered(remaining, task.right[:index] + task.right[index + 1:]))
                    branch.append((first, candidate))
                    choices.append((branch, dict(forward), dict(reverse)))
                valid = False
                break
            a, b = task
            if type(a) is not type(b):
                valid = False
                break
            if type(a) in _ATOMIC_TYPES:
                valid = _atomic_payload(a) == _atomic_payload(b)
                continue
            aid, bid = id(a), id(b)
            if aid in forward or bid in reverse:
                valid = forward.get(aid) == bid and reverse.get(bid) == aid
                continue
            forward[aid], reverse[bid] = bid, aid
            keep_alive.extend((a, b))
            if isinstance(a, np.ndarray):
                aa, bb = np.ndarray.view(a, np.ndarray), np.ndarray.view(b, np.ndarray)
                if aa.shape != bb.shape or aa.strides != bb.strides or aa.dtype != bb.dtype:
                    valid = False
                    break
                if aa.dtype.hasobject:
                    if aa.dtype.kind == "O":
                        pending.extend(zip(aa.flat, bb.flat))
                    else:
                        pending.extend((np.ndarray.__getitem__(aa, name),
                                        np.ndarray.__getitem__(bb, name))
                                       for name in aa.dtype.names or ())
                elif np.ndarray.tobytes(aa) != np.ndarray.tobytes(bb):
                    valid = False
                    break
            elif isinstance(a, np.generic):
                if a.dtype != b.dtype:
                    valid = False
                elif a.dtype.hasobject:
                    pending.append((np.generic.item(a), np.generic.item(b)))
                else:
                    valid = np.generic.tobytes(a) == np.generic.tobytes(b)
            elif isinstance(a, Mapping):
                # Canonical params retain order; scripts can observe that order.
                aa = list(dict.items(a)) if isinstance(a, dict) else list(a.items())
                bb = list(dict.items(b)) if isinstance(b, dict) else list(b.items())
                if len(aa) != len(bb):
                    valid = False
                    break
                for (akey, aval), (bkey, bval) in zip(aa, bb):
                    pending.extend(((akey, bkey), (aval, bval)))
            elif isinstance(a, (list, tuple, deque)):
                if len(a) != len(b) or isinstance(a, deque) and a.maxlen != b.maxlen:
                    valid = False
                    break
                pending.extend(zip(a, b))
            elif isinstance(a, (set, frozenset)):
                if len(a) != len(b):
                    valid = False
                    break
                pending.append(_Unordered(list(a), list(b)))
            elif isinstance(a, (bytearray, memoryview)):
                if isinstance(a, memoryview) and (a.format != b.format or a.shape != b.shape):
                    valid = False
                    break
                valid = bytes(a) == bytes(b)
            elif isinstance(a, _ATOMIC_TYPES):
                valid = _atomic_payload(a) == _atomic_payload(b)
            elif not _python_instance_type(type(a)):
                # An opaque native object can have hidden state. Never equate
                # different objects merely because no Python fields are visible.
                valid = a is b
                continue
            if not valid:
                break
            aa, bb = instance_parameter_items(a), instance_parameter_items(b)
            if len(aa) != len(bb):
                valid = False
                break
            for (akey, aval), (bkey, bval) in zip(aa, bb):
                if akey != bkey:
                    valid = False
                    break
                pending.append((aval, bval))
        if valid:
            return True
    return False


def _python_instance_type(cls: type) -> bool:
    for base in cls.__mro__:
        if base in (object, SimpleNamespace):
            continue
        if not base.__flags__ & (1 << 9):  # CPython heap type: Python class storage.
            return False
        for name in ("__new__", "__init__"):
            method = vars(base).get(name)
            if isinstance(method, staticmethod):
                method = method.__func__
            if method is not None and not isinstance(method, FunctionType):
                return False
    return True
