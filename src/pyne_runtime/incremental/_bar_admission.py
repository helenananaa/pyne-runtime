"""Detach supplied bar graphs before callbacks can mutate runtime state."""
from __future__ import annotations

import copy

from .bar import IncrementalBar, copy_bar_payload


def _plain_bar(item) -> bool:
    return type(item) is dict and all(
        type(key) is str and type(value) in (int, float, str, bool, type(None))
        for key, value in item.items()
    )


def copy_seed_inputs(items):
    # Plain standalone CSV data needs only fresh row dictionaries. General
    # Python payloads share one memo so aliases across supplied rows survive.
    if all(_plain_bar(item) for item in items):
        return [item.copy() for item in items]
    return copy.deepcopy(items)


def admit_bar(item, *, is_confirmed: bool = True) -> IncrementalBar:
    bar = IncrementalBar.from_dict(item, is_confirmed=is_confirmed)
    bar.raw = copy_bar_payload(bar.raw)
    return bar


def replay_input(bar: IncrementalBar, *, complete: bool, budget: int | None, count: int):
    if not complete or budget is not None and count >= budget:
        return None
    return copy_bar_payload(bar.raw)
