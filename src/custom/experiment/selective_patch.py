"""Deterministic Role 1 Selective Patch strategy.

The experiment runner owns stage ordering and passes defensive copies to this
plugin. This module compares the previous and current semantic catalogs, then
updates only the catalog fields whose values changed. It makes no model or
network requests.
"""
from copy import deepcopy

from . import adapters


def _pointer(parts):
    """Render a JSON Pointer-like path for readable audit records."""
    if not parts:
        return "/"
    return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def _operation(path, operation):
    return {"path": _pointer(path), "operation": operation}


def _patch_value(current, old, new, path=()):
    """Patch current according to the structural difference from old to new.

    Dictionaries are traversed recursively so unrelated schema fields retain
    their existing values. Lists and scalar values are atomic schema values:
    replacing them avoids inventing element identities.
    """
    if old == new:
        return deepcopy(current), []

    if isinstance(old, dict) and isinstance(new, dict):
        patched = deepcopy(current) if isinstance(current, dict) else deepcopy(old)
        operations = []
        for key in sorted(set(old) | set(new)):
            child_path = path + (key,)
            if key not in old:
                patched[key] = deepcopy(new[key])
                operations.append(_operation(child_path, "add"))
            elif key not in new:
                patched.pop(key, None)
                operations.append(_operation(child_path, "remove"))
            else:
                base = patched.get(key, old[key])
                patched_value, nested = _patch_value(base, old[key], new[key], child_path)
                patched[key] = patched_value
                operations.extend(nested)
        return patched, operations

    return deepcopy(new), [_operation(path, "replace")]


def _change_type(operations, tool_level=False):
    if tool_level:
        return "TOOL"
    description_change = any(
        part == "description"
        for operation in operations
        for part in operation["path"].split("/")[1:]
    )
    non_description_change = any(
        all(part != "description" for part in operation["path"].split("/")[1:])
        for operation in operations
    )
    if description_change and non_description_change:
        return "MIXED"
    if description_change:
        return "DESC"
    return "PARAM"


def _validate_catalog(catalog, label):
    if not isinstance(catalog, dict):
        raise ValueError(f"{label} must be a dictionary keyed by server::tool")
    for key, tool in catalog.items():
        if not isinstance(key, str) or not isinstance(tool, dict):
            raise ValueError(f"{label} has an invalid tool entry")
        required = {"server", "name", "description", "inputSchema"}
        missing = required - set(tool)
        if missing:
            raise ValueError(f"{label} entry {key!r} is missing {sorted(missing)}")
        if key != f"{tool['server']}::{tool['name']}":
            raise ValueError(f"{label} entry {key!r} does not match its server/name identity")


def _entry(tool_id, change_type, operations, reason):
    return {
        "tool_id": tool_id,
        "change_type": change_type,
        "operations": operations,
        "reason": reason,
    }


def selective_patch(knowledge, old_tools, new_tools, context):
    """Update only semantic entries that changed from old_tools to new_tools."""
    _validate_catalog(knowledge, "knowledge")
    _validate_catalog(old_tools, "old_tools")
    _validate_catalog(new_tools, "new_tools")

    patched = deepcopy(knowledge)
    changes = []
    old_ids, new_ids = set(old_tools), set(new_tools)

    for tool_id in sorted(new_ids - old_ids):
        patched[tool_id] = deepcopy(new_tools[tool_id])
        changes.append(_entry(
            tool_id, "TOOL", [_operation((), "add")],
            "Tool exists in the target catalog but not in the previous catalog.",
        ))

    for tool_id in sorted(old_ids - new_ids):
        patched.pop(tool_id, None)
        changes.append(_entry(
            tool_id, "TOOL", [_operation((), "remove")],
            "Tool exists in the previous catalog but not in the target catalog.",
        ))

    for tool_id in sorted(old_ids & new_ids):
        old, new = old_tools[tool_id], new_tools[tool_id]
        if old == new:
            continue

        current = patched.get(tool_id, deepcopy(old))
        updated = deepcopy(current)
        operations = []
        if old["description"] != new["description"]:
            updated["description"] = deepcopy(new["description"])
            operations.append(_operation(("description",), "replace"))
        schema, schema_operations = _patch_value(
            updated.get("inputSchema", old["inputSchema"]),
            old["inputSchema"],
            new["inputSchema"],
            ("inputSchema",),
        )
        updated["inputSchema"] = schema
        operations.extend(schema_operations)
        patched[tool_id] = updated
        changes.append(_entry(
            tool_id,
            _change_type(operations),
            operations,
            "Only the detected description and/or inputSchema differences were applied.",
        ))

    unchanged = len(old_ids & new_ids) - sum(
        1 for tool_id in old_ids & new_ids if old_tools[tool_id] != new_tools[tool_id]
    )
    stage = context.get("stage", "unknown") if isinstance(context, dict) else "unknown"
    type_counts = {kind: sum(entry["change_type"] == kind for entry in changes)
                   for kind in ("TOOL", "PARAM", "DESC", "MIXED")}
    count_summary = ", ".join(f"{kind}={count}" for kind, count in type_counts.items() if count)
    explanation = (
        f"Deterministic selective patch for target stage {stage}: "
        f"{len(changes)} changed entries ({count_summary or 'none'}); "
        f"{unchanged} unchanged shared entries preserved."
    )
    return adapters.UpdateResult(
        patched,
        changes,
        explanation,
        api_calls=0,
        input_tokens=0,
        output_tokens=0,
        api_cost=0,
        cost_currency=None,
        cost_basis="Deterministic local schema comparison; no model requests",
    )


if "selective_patch" not in adapters.REGISTRY:
    adapters.register("selective_patch", selective_patch)
