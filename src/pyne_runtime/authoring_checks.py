"""Non-executing checks for explicitly selected incremental authoring targets."""

from __future__ import annotations

import ast
from typing import Any

from .errors import error_detail


VALIDATION_TARGETS = ("preview", "snapshot")


def target_diagnostics(
    script: str, *, runtime_mode: str | None, target: str | None
) -> list[dict[str, Any]]:
    if runtime_mode != "incremental" and target is None:
        return []
    tree = ast.parse(script)
    result = []
    # Dynamic callback assignments are left to execution; do not reject them on a guess.
    dynamic_namespace = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"exec", "globals", "locals"}
        for node in ast.walk(tree)
    )
    imported_callback = any(
        isinstance(node, ast.alias) and (node.asname or node.name) in {"on_bar", "*"}
        for node in ast.walk(tree)
    )
    binds_callback = (
        dynamic_namespace
        or imported_callback
        or any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "on_bar"
            or isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Store)
            and node.id == "on_bar"
            for node in ast.walk(tree)
        )
    )
    if not binds_callback:
        result.append(
            error_detail(
                "PYNE_UNSUPPORTED_FEATURE",
                "Incremental execution requires on_bar(ctx, bar).",
                hint="Define on_bar(ctx, bar), or use batch execution for a vectorized Python script.",
            )
        )
    if target is None or dynamic_namespace:
        return result
    classes: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes[node.name] = node
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            classes.pop(node.name, None)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            alias = value.id if isinstance(value, ast.Name) and value.id in classes else None
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for binding in targets:
                for part in ast.walk(binding):
                    if isinstance(part, ast.Name) and isinstance(part.ctx, ast.Store):
                        classes.pop(part.id, None)
                        if alias:
                            classes[part.id] = node
        elif isinstance(node, ast.Delete):
            for binding in node.targets:
                if isinstance(binding, ast.Name):
                    classes.pop(binding.id, None)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                classes.pop(alias.asname or alias.name.split(".")[0], None)
    for name, node in classes.items():
        result.append(
            error_detail(
                "PYNE_STATE_CONTRACT_ERROR",
                f"Module-level class '{name}' cannot be retained for incremental {target}.",
                line=node.lineno,
                column=node.col_offset + 1,
                hint="Keep state in ctx.state()/ctx.varip() and use top-level functions. "
                "Ordinary batch Python classes remain supported.",
            )
        )
    return result
