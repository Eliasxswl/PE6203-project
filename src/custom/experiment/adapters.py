"""Role 1 registration point; semantic knowledge never contains transport routes."""
from copy import deepcopy
from dataclasses import asdict, dataclass
import importlib
import json
import math
import time


def stage_catalog(catalog, config, stage):
    """Preserve upstream DESC overlays as public environment information, not a strategy update."""
    from .selection import ROOT, read_json
    result = deepcopy(catalog)
    if config.get("mode") == "offline" or stage == "original" or config["runtime"].get("catalog_source") == "live":
        return result
    runtime = config["runtime"]
    if runtime.get("metadata_verified") is not True:
        raise ValueError("Verify the stage/evolution mapping before using evolved catalogs")
    for path in runtime["evolution_files"][stage]:
        for server, evolution in read_json(ROOT / path).items():
            if evolution.get("mutation_type") != "DESC":
                continue
            for name, changes in evolution.items():
                key = server + "::" + name
                if key not in result or not isinstance(changes, dict):
                    continue
                tool = result[key]
                description = changes.get("tool", {}).get("modified_description")
                if description is not None:
                    tool["description"] = description
                for parameter in changes.get("parameters", []):
                    parameter_name = parameter["parameter_name"]
                    properties = tool["inputSchema"].get("properties", {})
                    # Preserve the upstream nested-schema handling for these official servers.
                    if server == "@sylphlab/pdf-reader-mcp" and name == "read_pdf" and parameter_name in ("path", "url", "pages"):
                        properties = properties.get("sources", {}).get("items", {}).get("properties", {})
                    elif server == "@tsmztech/mcp-server-salesforce" and parameter_name in ("name", "where", "orderBy", "limit"):
                        properties = properties.get("objects", {}).get("items", {}).get("properties", {})
                    elif server == "@itseasy21/mcp-knowledge-graph":
                        properties = properties.get("relations", {}).get("items", {}).get("properties", {})
                    if parameter_name in properties:
                        properties[parameter_name]["description"] = parameter["modified_description"]
    return result


@dataclass
class UpdateResult:
    knowledge: dict
    changed_entries: list
    explanation: str
    elapsed_seconds: float = 0.0
    api_calls: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    api_cost: float | None = None
    cost_currency: str | None = None
    cost_basis: str | None = None


def no_model_usage():
    """An observed zero, distinct from a legacy plugin's unreported usage."""
    return {"api_calls": 0, "input_tokens": 0, "output_tokens": 0,
            "api_cost": 0, "cost_currency": None, "cost_basis": "No model requests"}


REGISTRY = {}


def register(name, implementation):
    if name in REGISTRY or name in ("no_update", "full_rewrite"):
        raise ValueError(f"Cannot replace a registered strategy: {name}")
    if not callable(implementation):
        raise ValueError("Strategy implementation must be callable")
    REGISTRY[name] = implementation


def load_plugins(config):
    for module in config.get("strategy_plugins", []):
        try:
            importlib.import_module(module)
        except ImportError as exc:
            raise ValueError(f"Cannot import strategy plugin: {module}") from exc
    available = {"no_update", "full_rewrite"} | set(REGISTRY)
    missing = set(config["strategies"]) - available
    if missing:
        raise ValueError(f"Strategy not implemented: {sorted(missing)}; no substitution is allowed")


def semantic(catalog):
    return {key: {field: deepcopy(tool[field]) for field in
                  ("server", "name", "description", "inputSchema")}
            for key, tool in catalog.items()}


def _template_description(tool):
    """Lossy rebuild: derive a minimal description from the input schema only.

    The curated natural-language description (semantics, constraints, usage
    notes, examples) is discarded; only parameter names survive. This models a
    full rewrite that rebuilds every tool entry from structural schema without
    preserving curated knowledge, so unchanged tools can be damaged.
    """
    schema = tool.get("inputSchema") or {}
    props = schema.get("properties") or {}
    if props:
        params = ", ".join(props.keys())
        return f"Call {tool['name']} with parameters: {params}."
    return f"Call {tool['name']} with no parameters."


def update(strategy, knowledge, old_tools, new_tools, context):
    started = time.perf_counter()
    before = deepcopy(knowledge)
    if strategy == "no_update":
        result = UpdateResult(deepcopy(before), [], "Retain Early semantic knowledge", **no_model_usage())
    elif strategy == "full_rewrite":
        rebuilt = semantic(new_tools)
        for tool in rebuilt.values():
            tool["description"] = _template_description(tool)
        changed = sorted(key for key in before.keys() | rebuilt.keys() if before.get(key) != rebuilt.get(key))
        usage = no_model_usage()
        usage["cost_basis"] = f"Deterministic template rewrite of all {len(rebuilt)} tool descriptions; no model requests"
        result = UpdateResult(rebuilt, changed,
                              "Rebuild all tool knowledge from current catalog via schema-derived template descriptions",
                              **usage)
    else:
        result = REGISTRY[strategy](deepcopy(before), semantic(old_tools), semantic(new_tools), deepcopy(context))
        if not isinstance(result, UpdateResult):
            raise ValueError("Strategy must return UpdateResult")
    if any(key != tool["server"] + "::" + tool["name"] for key, tool in result.knowledge.items()):
        raise ValueError("Knowledge must use server::tool identity keys")
    if any("remote_name" in tool or "meta" in tool for tool in result.knowledge.values()):
        raise ValueError("Transport routing cannot be stored in strategy knowledge")
    result.elapsed_seconds = time.perf_counter() - started
    for field in ("api_calls", "input_tokens", "output_tokens"):
        value = getattr(result, field)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f"Update {field} must be a nonnegative integer or null")
    if result.api_cost is not None:
        if type(result.api_cost) not in (int, float) or not math.isfinite(result.api_cost) or result.api_cost < 0:
            raise ValueError("Update api_cost must be finite and nonnegative or null")
        if not result.cost_basis or (result.api_cost > 0 and not result.cost_currency):
            raise ValueError("Reported update cost needs a basis and positive cost needs a currency")
    for field in ("cost_currency", "cost_basis"):
        if getattr(result, field) is not None and not isinstance(getattr(result, field), str):
            raise ValueError(f"Update {field} must be a string or null")
    payload = asdict(result)
    json.dumps(payload, allow_nan=False)
    return payload


def agent_tools(knowledge, catalog, servers):
    """Give duplicate tool names stable API-safe aliases without changing their meaning."""
    import hashlib
    import re
    tools, routing = [], {}
    scoped = [key for key, tool in knowledge.items() if tool["server"] in servers]
    counts = {}
    for key in scoped:
        name = knowledge[key]["name"]
        counts[name] = counts.get(name, 0) + 1
    for key in sorted(scoped):
        tool = deepcopy(knowledge[key])
        name = tool["name"]
        compatible = bool(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name))
        alias = name if counts[name] == 1 and compatible else re.sub(r"[^A-Za-z0-9_-]", "_", name)[:45] + "_" + hashlib.sha256(key.encode()).hexdigest()[:12]
        if alias in routing:
            alias = "tool_" + hashlib.sha256(key.encode()).hexdigest()[:48]
        if alias in routing:
            raise ValueError("Unresolvable API tool alias collision")
        tool["name"] = alias
        tool["meta"] = {"benchmark_remote_name": catalog.get(key, {}).get("remote_name") or "missing:" + key,
                        "benchmark_semantic_identity": key}
        tools.append(tool)
        routing[alias] = tool["server"]
    return tools, routing
