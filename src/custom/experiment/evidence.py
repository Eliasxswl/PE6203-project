"""Read-only catalog evidence and Role 3 annotations; never Agent inputs."""
from copy import deepcopy

from .selection import STAGES, digest

CHANGE_TYPES = {"tool", "parameter", "description"}


def archived_tasks(manifest):
    """Old runs predate frozen task definitions; verify the source before reading it."""
    if "task_definitions" in manifest:
        return deepcopy(manifest["task_definitions"])
    from .selection import ROOT, file_hash, read_json
    source = manifest["settings"]["task_source"]
    expected = manifest.get("fingerprints", {}).get("sources", {}).get(source)
    if not expected or file_hash(ROOT / source) != expected:
        raise ValueError("Archived task definitions unavailable: original task-source fingerprint does not match")
    by_id = {task["idx"]: task for task in read_json(ROOT / source)}
    return [{field: by_id[idx][field] for field in ("idx", "question", "servers")}
            for idx in manifest["selected_ids"]]


def validate_annotations(selection):
    """Annotations remain in the existing frozen ID file; approval is explicit."""
    result = {}
    for sample in selection["samples"]:
        annotation = sample.get("classification")
        if annotation is None:
            continue
        if not isinstance(annotation, dict) or set(annotation) - {"status", "reviewed_by", "transitions"}:
            raise ValueError("Invalid task classification fields")
        status = annotation.get("status")
        if status not in ("draft", "confirmed"):
            raise ValueError("Classification status must be draft or confirmed")
        reviewer = annotation.get("reviewed_by")
        if reviewer is not None and (not isinstance(reviewer, str) or not reviewer.strip()):
            raise ValueError("Classification reviewed_by must be a nonempty name")
        if status == "confirmed" and not reviewer:
            raise ValueError("Confirmed classifications need reviewed_by")
        transitions = annotation.get("transitions")
        if not isinstance(transitions, dict) or set(transitions) - set(STAGES[1:]):
            raise ValueError("Classify transitions by destination: iter3 or iter5")
        for stage, label in transitions.items():
            if not isinstance(label, dict) or set(label) != {"cohort", "change_types", "rationale"}:
                raise ValueError("Each transition needs cohort, change_types and rationale")
            if label["cohort"] not in ("changed", "retention"):
                raise ValueError("Classification cohort must be changed or retention")
            types = label["change_types"]
            if (not isinstance(types, list) or any(not isinstance(t, str) or t not in CHANGE_TYPES for t in types)
                    or len(types) != len(set(types))):
                raise ValueError("change_types accepts distinct tool, parameter, description labels")
            if bool(types) != (label["cohort"] == "changed"):
                raise ValueError("Changed tasks need change_types; retention tasks must have none")
            if not isinstance(label["rationale"], str) or not label["rationale"].strip():
                raise ValueError("Classification rationale must be nonempty")
        result[str(sample["idx"])] = deepcopy(annotation)
    return result


def _schema_parts(schema):
    """Separate schema descriptions, preserving parameters literally named 'description'."""
    descriptions = {}
    maps = {"properties", "patternProperties", "$defs", "definitions", "dependentSchemas", "dependencies"}
    children = {"items", "additionalItems", "additionalProperties", "unevaluatedProperties", "unevaluatedItems",
                "propertyNames", "contains", "not", "if", "then", "else", "contentSchema",
                "allOf", "anyOf", "oneOf", "prefixItems"}

    def walk(node, path=()):
        if isinstance(node, list):
            return [walk(v, path + (i,)) for i, v in enumerate(node)]
        if not isinstance(node, dict):
            return deepcopy(node)
        result = {}
        for key, child in node.items():
            if key == "description":
                descriptions[str(path)] = deepcopy(child)
            elif key in maps and isinstance(child, dict):
                result[key] = {name: walk(v, path + (key, name)) for name, v in child.items()}
            elif key in children:
                result[key] = walk(child, path + (key,))
            else:
                result[key] = deepcopy(child)
        return result

    return walk(schema), descriptions


def catalog_diff(before, after):
    """Compare public semantics only; routes and runtime metadata are irrelevant."""
    from .adapters import semantic
    before, after = semantic(before), semantic(after)
    shared = before.keys() & after.keys()
    schemas_before = {k: _schema_parts(before[k]["inputSchema"]) for k in shared}
    schemas_after = {k: _schema_parts(after[k]["inputSchema"]) for k in shared}
    return {"before_sha256": digest(before), "after_sha256": digest(after),
            "added": sorted(after.keys() - before.keys()), "removed": sorted(before.keys() - after.keys()),
            "parameter": sorted(k for k in shared if schemas_before[k][0] != schemas_after[k][0]),
            "description": sorted(k for k in shared if before[k]["description"] != after[k]["description"]
                                  or schemas_before[k][1] != schemas_after[k][1])}


def catalog_evidence(records, task_list):
    from .runtime import ALIASES
    result = {}
    for eid, episode in records.get("episodes", {}).items():
        stages = episode.get("stages", {})
        result[eid] = {}
        for index, stage in enumerate(STAGES[1:], 1):
            before, after = stages.get(STAGES[index - 1], {}), stages.get(stage, {})
            if before.get("status") != "ready" or after.get("status") != "ready":
                result[eid][stage] = {"status": "unavailable", "tasks": {}}
                continue
            diff = catalog_diff(before["catalog"], after["catalog"])
            labels = {}
            for task in task_list:
                servers = {ALIASES.get(s, s) for s in task["servers"]}
                required = {ALIASES.get(s, s) + "::" + name for s, names in task["servers"].items() for name in names}
                errors = set(before.get("errors", {})) | set(after.get("errors", {}))
                present_servers = {v["server"] for v in before["catalog"].values()} | {
                    v["server"] for v in after["catalog"].values()}
                available = not (servers & errors) and servers <= present_servers
                changes = {"tool": sorted(required & (set(diff["added"]) | set(diff["removed"]))),
                           "parameter": sorted(required & set(diff["parameter"])),
                           "description": sorted(required & set(diff["description"]))}
                missing_both = sorted(required - before["catalog"].keys() - after["catalog"].keys())
                available = available and not missing_both
                labels[str(task["idx"])] = {"status": "available" if available else "unavailable",
                    "required_tool_changes": changes, "missing_in_both": missing_both,
                    "suggested_change_types": [kind for kind, keys in changes.items() if keys] if available else None}
            result[eid][stage] = {"status": "available", **diff, "tasks": labels}
    return {"scope": "Required tool descriptions and input schemas; unchanged definitions do not prove unchanged behavior.",
            "transitions": result}


def confirmed_label(annotations, evidence, eid, stage, task_id):
    annotation = annotations.get(str(task_id), {})
    if annotation.get("status") != "confirmed":
        return None, "classification_not_confirmed"
    label = annotation.get("transitions", {}).get(stage)
    if label is None:
        return None, "transition_not_classified"
    observed = evidence["transitions"].get(eid, {}).get(stage, {}).get("tasks", {}).get(str(task_id), {})
    if observed.get("status") != "available":
        return None, "catalog_evidence_unavailable"
    # Exact agreement prevents a retention label or an incomplete change label hiding a real definition change.
    if set(label["change_types"]) != set(observed["suggested_change_types"]):
        return None, "classification_conflicts_with_catalog"
    return label, None
