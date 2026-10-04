"""Object-graph isolation for previews and process-local session snapshots.

All roots in an operation share one deepcopy memo so mutable aliases and ordinary
script functions bind to the same copied graph. Session lifecycle and atomic
restore commits remain in ``session``; this module never imports that module.
"""

from __future__ import annotations

import builtins as python_builtins
import copy
from collections import deque
from collections.abc import Mapping
from types import BuiltinFunctionType, BuiltinMethodType, FunctionType, MethodType, ModuleType
from typing import Any, Callable, TypeVar

from ..cache import PyneCache
from ..security import PyneStateContractError
from .context import IncrementalContext
from .limits import StateCell, _StateHistory, _STATE_HISTORY_TOKEN, _state_payload_items
from .request import IncrementalRequestModule


_FunctionState = TypeVar("_FunctionState")


def _snapshot_user_globals(
    globals_values: Mapping[str, Any],
    *,
    base_values: Mapping[str, Any],
    prepared_values: Mapping[str, Any],
    memo: dict[int, Any],
    function_state_factory: Callable[..., _FunctionState],
) -> tuple[dict[str, Any], dict[str, _FunctionState]]:
    """Detach user values and function state without owning the snapshot schema."""
    values: dict[str, Any] = {}
    functions: dict[str, _FunctionState] = {}
    for name, value in globals_values.items():
        if name in base_values and value is base_values[name]:
            continue
        if (
            name in prepared_values
            and value is prepared_values[name]
            and (
                _is_deeply_immutable(value)
                or isinstance(
                    value,
                    (BuiltinFunctionType, BuiltinMethodType, MethodType, ModuleType),
                )
            )
        ):
            continue
        if isinstance(value, FunctionType):
            if value.__closure__:
                raise PyneStateContractError(
                    f"Incremental snapshot cannot safely restore closure: {name}"
                )
            functions[name] = function_state_factory(
                defaults=copy.deepcopy(value.__defaults__, memo),
                kwdefaults=copy.deepcopy(value.__kwdefaults__, memo),
                attributes=copy.deepcopy(value.__dict__, memo),
            )
            continue
        if isinstance(value, type):
            raise PyneStateContractError(
                f"Incremental snapshot cannot safely restore script class: {name}"
            )
        if isinstance(value, ModuleType):
            continue
        values[name] = copy.deepcopy(value, memo)
    return values, functions


def _is_deeply_immutable(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float, complex, str, bytes, range)):
        return True
    if isinstance(value, tuple | frozenset):
        return all(_is_deeply_immutable(item) for item in value)
    return False


def _clone_preview_cache(
    source_cache: PyneCache, *, memo: dict[int, Any] | None = None
) -> PyneCache:
    """Clone committed cache state for one isolated preview callback."""
    cloned = PyneCache(max_items=max(int(source_cache.stats()["maxItems"]), 1))
    memo = {} if memo is None else memo
    snapshot = source_cache.snapshot_state(memo=memo)
    # snapshot_state has already copied these roots. Keep them while adopting
    # the cache so callbacks, context attributes and cache aliases see one graph.
    for entry in snapshot.entries:
        memo[id(entry.value)] = entry.value
    cloned.restore_state(snapshot, memo=memo)
    return cloned


def _clone_preview_globals(
    values: Mapping[str, Any],
    *,
    script_globals: dict[str, Any],
    base_values: Mapping[str, Any],
    context: IncrementalContext | None = None,
) -> tuple[dict[str, Any], dict[int, Any]]:
    roots = (values, context)
    class_names = _script_class_names(roots, script_globals=script_globals)
    if class_names:
        names = ", ".join(class_names)
        raise PyneStateContractError(
            f"Incremental preview cannot safely isolate script classes: {names}. "
            "Keep preview state in module values or ctx.varip()."
        )

    script_functions = _collect_functions(roots, script_globals=script_globals)
    closure_names = sorted({func.__qualname__ for func in script_functions if func.__closure__})
    if closure_names:
        names = ", ".join(closure_names)
        raise PyneStateContractError(
            f"Incremental preview cannot safely isolate function closures: {names}. "
            "Keep preview state in module values or ctx.varip()."
        )

    base_functions = _collect_functions(base_values, script_globals=None)
    cloned_functions = script_functions | base_functions
    memo = _preview_copy_memo(roots)
    if context is not None:
        memo[id(context)] = object.__new__(type(context))
    clones = _allocate_function_clones(
        cloned_functions, memo=memo, script_globals=script_globals,
        target_globals=script_globals, allow_runtime_closures=True,
    )
    preview_globals = copy.deepcopy(dict(values), memo)
    _copy_function_state(clones, memo)
    return preview_globals, memo


def _allocate_function_clones(
    functions: Any,
    *,
    memo: dict[int, Any],
    script_globals: dict[str, Any] | None,
    target_globals: dict[str, Any],
    allow_runtime_closures: bool = False,
) -> list[tuple[FunctionType, FunctionType]]:
    clones: list[tuple[FunctionType, FunctionType]] = []
    for original in functions:
        if original.__closure__ and not (
            allow_runtime_closures and original.__globals__ is not script_globals
        ):
            raise PyneStateContractError(
                f"Incremental snapshot cannot safely restore closure: {original.__qualname__}"
            )
        function_globals = (
            target_globals if script_globals is None or original.__globals__ is script_globals
            else original.__globals__
        )
        cloned = FunctionType(
            original.__code__, function_globals,
            name=original.__name__, argdefs=None, closure=original.__closure__,
        )
        memo[id(original)] = cloned
        clones.append((original, cloned))
    return clones


def _copy_function_state(
    clones: list[tuple[FunctionType, FunctionType]], memo: dict[int, Any]
) -> None:
    for original, cloned in clones:
        try:
            cloned.__defaults__ = copy.deepcopy(original.__defaults__, memo)
            cloned.__kwdefaults__ = copy.deepcopy(original.__kwdefaults__, memo)
            cloned.__annotations__ = copy.deepcopy(original.__annotations__, memo)
            cloned.__dict__.update(copy.deepcopy(original.__dict__, memo))
        except Exception as exc:
            raise PyneStateContractError(
                "Incremental preview cannot isolate mutable function state: "
                f"{original.__qualname__}. Keep state in module values or ctx.varip()."
            ) from exc
        cloned.__doc__ = original.__doc__
        cloned.__module__ = original.__module__
        cloned.__qualname__ = original.__qualname__


def _preview_payload_items(values: Any) -> int:
    """Estimate deepcopy work before allocating a preview-global clone."""
    total = 0
    for value in values:
        if _is_deeply_immutable(value):
            continue
        total += _state_payload_items(value)
        if isinstance(value, FunctionType):
            total += _state_payload_items(value.__defaults__)
            total += _state_payload_items(value.__kwdefaults__)
            total += _state_payload_items(value.__dict__)
        elif hasattr(value, "__dict__"):
            total += _state_payload_items(vars(value))
    return total


def _preview_copy_memo(value: Any) -> dict[int, Any]:
    memo: dict[int, Any] = {}
    module_proxies: dict[int, _PreviewModuleProxy] = {}
    seen: set[int] = set()
    pending = [value]
    while pending:
        current = pending.pop()
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        if isinstance(current, ModuleType):
            proxy = module_proxies.setdefault(identity, _PreviewModuleProxy(current))
            memo[identity] = proxy
        elif type(current) is IncrementalRequestModule:
            # This exact runtime facade already shares itself in __deepcopy__.
            # Walking its provider/cache graph creates memo entries that copy
            # will never consume. Separately exposed user aliases are still walked.
            continue
        elif isinstance(
            current,
            (BuiltinFunctionType, BuiltinMethodType, FunctionType, MethodType, type),
        ):
            memo[identity] = current
        else:
            pending.extend(_copy_graph_children(current))
    return memo


def _collect_functions(
    value: Any,
    *,
    script_globals: dict[str, Any] | None,
    include_history: bool = False,
) -> set[FunctionType]:
    functions: set[FunctionType] = set()
    seen: set[int] = set()
    pending = [value]
    while pending:
        current = pending.pop()
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        if isinstance(current, FunctionType):
            if script_globals is None or current.__globals__ is script_globals:
                functions.add(current)
                pending.extend(current.__defaults__ or ())
                pending.extend((current.__kwdefaults__ or {}).values())
                pending.extend(current.__dict__.values())
            continue
        if isinstance(current, (ModuleType, type, BuiltinFunctionType, BuiltinMethodType)):
            continue
        pending.extend(_copy_graph_children(current, include_history=include_history))
    return functions


def _copy_graph_children(value: Any, *, include_history: bool = False) -> tuple[Any, ...]:
    if type(value) is IncrementalRequestModule:
        return ()
    if isinstance(value, IncrementalContext) and not include_history:
        return value.preview_copy_roots()
    if isinstance(value, StateCell):
        if include_history:
            history = object.__getattribute__(value, "_StateCell__history")
            return (value.value, *history._raw_slice(slice(None), _STATE_HISTORY_TOKEN))
        return (value.value,)
    if isinstance(value, _StateHistory):
        return tuple(value._raw_slice(slice(None), _STATE_HISTORY_TOKEN)) if include_history else ()
    if isinstance(value, Mapping):
        return (*value.keys(), *value.values())
    if isinstance(value, (list, tuple, set, frozenset, deque)):
        return tuple(value)
    if isinstance(value, (ModuleType, type, BuiltinFunctionType, BuiltinMethodType, MethodType)):
        return ()
    if hasattr(value, "__dict__"):
        return tuple(vars(value).values())
    return ()


def _script_class_names(
    value: Any,
    *,
    script_globals: dict[str, Any],
) -> list[str]:
    names: set[str] = set()
    seen: set[int] = set()
    pending = [value]
    while pending:
        current = pending.pop()
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        candidate = current if isinstance(current, type) else type(current)
        is_unregistered_builtin_class = (
            isinstance(current, type)
            and candidate.__module__ == "builtins"
            and getattr(python_builtins, candidate.__name__, None) is not candidate
        )
        if is_unregistered_builtin_class or _is_script_class(
            candidate,
            script_globals=script_globals,
        ):
            names.add(candidate.__qualname__)
            continue
        if isinstance(current, FunctionType):
            pending.extend(current.__defaults__ or ())
            pending.extend((current.__kwdefaults__ or {}).values())
            pending.extend(current.__dict__.values())
        else:
            pending.extend(_copy_graph_children(current))
    return sorted(names)


def _is_script_class(cls: type[Any], *, script_globals: dict[str, Any]) -> bool:
    for item in vars(cls).values():
        functions: tuple[Any, ...]
        if isinstance(item, (staticmethod, classmethod)):
            functions = (item.__func__,)
        elif isinstance(item, property):
            functions = (item.fget, item.fset, item.fdel)
        else:
            functions = (item,)
        if any(
            isinstance(func, FunctionType) and func.__globals__ is script_globals
            for func in functions
        ):
            return True
    return False


_RISKY_MODULE_CALLS = {
    "clear",
    "disable",
    "enable",
    "reset",
    "seed",
    "set_state",
    "setbufsize",
    "seterr",
    "seterrcall",
    "set_numeric_ops",
    "set_printoptions",
    "set_string_function",
}


class _PreviewModuleProxy:
    # Preserve the codec/export identity when moving the implementation;
    # this does not change or relabel computation semantics.
    __module__ = "pyne_runtime.incremental.session"

    __slots__ = ("_cache", "_module")

    def __init__(self, module: ModuleType) -> None:
        object.__setattr__(self, "_module", module)
        object.__setattr__(self, "_cache", {})

    def __getattribute__(self, name: str) -> Any:
        if name in {"_module", "_cache", "__dict__"}:
            raise PyneStateContractError(
                "Incremental preview cannot expose mutable external module state"
            )
        if name in {"__class__", "__repr__", "__getattr__", "__setattr__", "__delattr__"}:
            return object.__getattribute__(self, name)
        return object.__getattribute__(self, name)

    def __getattr__(self, name: str) -> Any:
        module = object.__getattribute__(self, "_module")
        cache = object.__getattribute__(self, "_cache")
        if name in cache:
            return cache[name]
        value = getattr(module, name)
        if isinstance(value, ModuleType):
            cloned: Any = _PreviewModuleProxy(value)
        elif callable(value):
            if name.lower() in _RISKY_MODULE_CALLS:
                raise PyneStateContractError(
                    "Incremental preview cannot call stateful external module API: "
                    f"{module.__name__}.{name}"
                )
            cloned = value
        elif _is_deeply_immutable(value):
            cloned = value
        else:
            try:
                cloned = copy.deepcopy(value, _preview_copy_memo(value))
            except Exception as exc:
                raise PyneStateContractError(
                    "Incremental preview cannot isolate external module attribute: "
                    f"{module.__name__}.{name}"
                ) from exc
        cache[name] = cloned
        return cloned

    def __setattr__(self, name: str, value: Any) -> None:
        module = object.__getattribute__(self, "_module")
        raise PyneStateContractError(
            f"Incremental preview cannot mutate external module state: {module.__name__}.{name}"
        )

    def __delattr__(self, name: str) -> None:
        self.__setattr__(name, None)

    def __repr__(self) -> str:
        module = object.__getattribute__(self, "_module")
        return f"<preview module proxy {module.__name__}>"


def _unisolatable_preview_globals(values: Mapping[str, Any]) -> list[str]:
    failed: list[str] = []
    for name, value in values.items():
        try:
            copy.deepcopy(value, _preview_copy_memo(value))
        except Exception:
            failed.append(name)
    return failed
