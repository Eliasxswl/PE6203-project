"""One frozen ID list and immutable official inputs."""
import hashlib
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[3]
STAGES = ("original", "iter3", "iter5")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def provider_options(config, role):
    value = config.get("providers", {}).get(role, {})
    return value if isinstance(value, list) else [value]


def provider_for(config, role, key):
    options = provider_options(config, role)
    if len(options) == 1:
        return options[0]
    parts = key.removesuffix("/judge").split("/")
    position = 0
    if len(parts) >= 4:
        task_id, repeat = int(parts[-2]), int(parts[-1])
        ids = [sample["idx"] for sample in read_json(ROOT / config["selection_file"])["samples"]]
        position = ids.index(task_id) + repeat
    # Assign by frozen task position/repeat, preserving the account across strategies/stages.
    return options[position % len(options)]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def file_hash(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def tree_hash(path):
    path = Path(path)
    if not path.is_dir():
        raise ValueError(f"Missing fixture directory: {path}")
    return digest({item.relative_to(path).as_posix(): file_hash(item)
                   for item in sorted(path.rglob("*")) if item.is_file()})


def load_config(path):
    path = Path(path).resolve()
    config = read_json(path)
    if not isinstance(config, dict):
        raise ValueError("Experiment configuration must be an object")
    allowed = {"selection_file", "selection_seed", "task_source", "candidate_source", "fixtures",
               "task_count", "agent_repeats", "judge_attempts_per_trajectory", "agent_model", "judge_model",
               "agent_temperature", "judge_temperature", "agent_max_tokens", "judge_max_tokens",
               "agent_thinking", "judge_thinking", "judge_output_mode", "request_policy", "providers",
               "round_policy", "max_requests", "stages", "strategies", "runtime", "mode",
               "mock", "strategy_plugins", "judge_failure_top_up", "automatic_api_retries", "memory", "agent_backend"}
    if set(config) - allowed:
        raise ValueError(f"Unknown configuration fields: {sorted(set(config) - allowed)}")
    if 'memory' in config:
        from .memory import validate_options
        validate_options(config['memory'])
    if config.get('agent_backend', 'legacy') not in ('legacy', 'langchain'):
        raise ValueError('agent_backend must be legacy or langchain')
    if config.get("mode", "live") not in ("live", "offline"):
        raise ValueError("mode must be live or offline")
    if config.get("judge_output_mode", "text") not in ("text", "json_object"):
        raise ValueError("judge_output_mode must be text or json_object; strict provider schema is not verified")
    if config.get("stages") != list(STAGES):
        raise ValueError("Stages must be original -> iter3 -> iter5")
    config.setdefault("task_count", 10)
    for key in ("task_count", "agent_repeats"):
        if type(config.get(key)) is not int or config[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    if config.get("judge_attempts_per_trajectory") != 5:
        raise ValueError("Use 5 judge slots per trajectory")
    if config.get("judge_failure_top_up", False) or config.get("automatic_api_retries", 0) != 0:
        raise ValueError("Retries and judge top-up must be disabled")
    policy = config.get("request_policy")
    if policy is not None:
        fields = {"minimum_interval", "overload_cooldown", "maximum_cooldown", "recovery_successes"}
        optional = {"max_concurrency", "long_context_concurrency", "long_context_threshold"}
        if not isinstance(policy, dict) or not fields <= set(policy) or set(policy) - fields - optional:
            raise ValueError("request_policy requires explicit interval, cooldowns, and recovery_successes")
        for key in fields - {"recovery_successes"}:
            if type(policy[key]) not in (int, float) or not (0 <= policy[key] <= 3600 if key == "minimum_interval" else 0 < policy[key] <= 3600):
                raise ValueError(f"Invalid request_policy {key}")
        if type(policy["recovery_successes"]) is not int or policy["recovery_successes"] < 1:
            raise ValueError("request_policy recovery_successes must be a positive integer")
        if not policy["minimum_interval"] <= policy["overload_cooldown"] <= policy["maximum_cooldown"]:
            raise ValueError("request_policy intervals must increase from minimum to maximum")
        for key in optional:
            if key in policy and (type(policy[key]) is not int or policy[key] < 1):
                raise ValueError(f"Invalid request_policy {key}")
        if policy.get("long_context_concurrency", 1) > policy.get("max_concurrency", 1):
            raise ValueError("request_policy long context cap exceeds overall cap")
    providers = config.get("providers", {})
    if not isinstance(providers, dict) or set(providers) - {"agent", "judge"}:
        raise ValueError("providers must contain agent/judge settings")
    import re
    entries = []
    for value in providers.values():
        if isinstance(value, list):
            if not value:
                raise ValueError("Provider pools must not be empty")
            entries.extend(value)
        else:
            entries.append(value)
    for provider in entries:
        if not isinstance(provider, dict) or set(provider) - {"api_key_env", "base_url_env", "quota_group"}:
            raise ValueError("Provider settings accept environment variable names and quota_group only")
        for key, value in provider.items():
            pattern = r"[A-Za-z0-9_-]{1,64}" if key == "quota_group" else r"[A-Z][A-Z0-9_]{0,63}"
            if not isinstance(value, str) or not re.fullmatch(pattern, value):
                raise ValueError(f"Invalid provider {key}")
    if config.get("round_policy") not in ("early_tool_count_plus_one", "fixed"):
        raise ValueError("Declare an early_tool_count_plus_one or fixed round policy")
    if config.get("round_policy") == "fixed" and (type(config.get("max_requests")) is not int
                                                  or config["max_requests"] < 1):
        raise ValueError("fixed round policy requires a positive max_requests")
    for key in ("agent_max_tokens", "judge_max_tokens"):
        if type(config.get(key)) is not int or config[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    for key in ("agent_temperature", "judge_temperature"):
        if type(config.get(key)) not in (int, float) or not 0 <= config[key] <= 2:
            raise ValueError(f"Invalid {key}")
    for key in ("agent_thinking", "judge_thinking"):
        if config.get(key) not in (None, "enabled", "disabled"):
            raise ValueError(f"Invalid {key}")
    if type(config.get("selection_seed")) is not int:
        raise ValueError("selection_seed must be an integer")
    if not isinstance(config.get("agent_model"), str) or not config["agent_model"]:
        raise ValueError("agent_model is required")
    if not isinstance(config.get("strategies"), list) or not config["strategies"]:
        raise ValueError("Declare at least one strategy")
    if any(not isinstance(name, str) or not name for name in config["strategies"]):
        raise ValueError("Strategy names must be nonempty strings")
    if not isinstance(config.get("judge_model", ""), str):
        raise ValueError("judge_model must be a string")
    if len(set(config["strategies"])) != len(config["strategies"]):
        raise ValueError("Duplicate strategies")
    runtime = config.get("runtime", {})
    runtime_allowed = {"configs", "policies", "connect_timeout", "read_timeout", "tool_timeout",
                       "startup_timeout", "shutdown_timeout", "model_timeout", "metadata_verified",
                       "evolution_files", "catalog_source", "keep_workspaces"}
    if runtime.get("catalog_source", "evolution_overlay") not in ("live", "evolution_overlay"):
        raise ValueError("Declare a live or evolution_overlay catalog source")
    if set(runtime) - runtime_allowed:
        raise ValueError("Unknown runtime fields; credentials belong in private local configuration")
    if type(runtime.get("keep_workspaces", False)) is not bool:
        raise ValueError("runtime keep_workspaces must be a boolean")
    for key in ("connect_timeout", "read_timeout", "tool_timeout", "startup_timeout",
                "shutdown_timeout", "model_timeout"):
        if type(runtime.get(key)) not in (int, float) or not 0 < runtime[key] <= 3600:
            raise ValueError(f"Invalid runtime {key}")
    return config


def inputs(config):
    records = read_json(ROOT / config["task_source"])
    candidates = read_json(ROOT / config["candidate_source"])["samples"]
    ids = [entry["idx"] for entry in candidates]
    if any(type(idx) is not int for idx in ids) or len(ids) != len(set(ids)):
        raise ValueError("Invalid candidate IDs")
    by_id = {record["idx"]: record for record in records}
    if len(by_id) != len(records) or not set(ids) <= set(by_id):
        raise ValueError("Invalid task-source identities")
    return by_id, sorted(ids)


def select(config):
    _, candidates = inputs(config)
    path = ROOT / config["selection_file"]
    if path.exists():
        raise ValueError("Selection is already frozen; edit the same ID list intentionally")
    selected = random.Random(config["selection_seed"]).sample(candidates, config["task_count"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump({"seed": config["selection_seed"], "candidate_order": "ascending_numeric",
                   "candidate_sha256": file_hash(ROOT / config["candidate_source"]),
                   "samples": [{"idx": idx} for idx in selected]}, stream, indent=2)
        stream.write("\n")
    return selected


def tasks(config):
    by_id, candidates = inputs(config)
    selection = read_json(ROOT / config["selection_file"])
    ids = [sample["idx"] for sample in selection["samples"]]
    count = config["task_count"]
    if len(ids) != count or any(type(idx) is not int for idx in ids) or len(set(ids)) != count:
        raise ValueError(f"Selection must contain exactly {count} distinct integer IDs")
    if not set(ids) <= set(candidates):
        raise ValueError("Selection contains IDs outside the upstream candidates")
    if "candidate_sha256" in selection and selection["candidate_sha256"] != file_hash(ROOT / config["candidate_source"]):
        raise ValueError("Candidate source changed after selection")
    from .evidence import validate_annotations
    validate_annotations(selection)
    # No reference tools calls, answers, trajectories, or evaluation fields cross this boundary.
    return [{"idx": idx, "question": by_id[idx]["question"], "servers": by_id[idx]["servers"]}
            for idx in ids]


def annotations(config):
    from .evidence import validate_annotations
    return validate_annotations(read_json(ROOT / config["selection_file"]))


def request_limit(config, task):
    if config["round_policy"] == "fixed":
        return config["max_requests"]
    # Preserve the upstream Early branch's effective budget when all specified tools exist.
    return max(10, 2 * sum(len(names) for names in task["servers"].values())) + 1


def fingerprints(config):
    paths = [config["task_source"], config["candidate_source"], config["selection_file"]]
    if 'memory' in config:
        paths += [config['memory']['artifact'], config['memory']['source']]
        paths += [name for name in ('requirements-memory.txt',) if (ROOT / name).exists()]
    paths += [p.relative_to(ROOT).as_posix() for p in (ROOT / "src/custom/data/mutation").rglob("evolution.json")]
    paths += [name for names in config["runtime"].get("evolution_files", {}).values() for name in names if name not in paths]
    paths += [f"servers/1mcp_config/{stage}/mcp.json" for stage in STAGES]
    paths += [f"servers/{stage}_servers/package-lock.json" for stage in STAGES
              if (ROOT / f"servers/{stage}_servers/package-lock.json").exists()]
    source = {name: file_hash(ROOT / name) for name in paths}
    source["fixtures"] = tree_hash(ROOT / config["fixtures"])
    if config.get("mode", "live") == "live":
        from custom.utils import model_config
        for role in ("agent", "judge"):
            for index, provider in enumerate(provider_options(config, role)):
                source[f"provider_endpoint:{role}:{index}"] = digest(model_config.role_base_url(role, provider))
        for stage, name in config["runtime"]["configs"].items():
            source[f"local_config:{stage}"] = file_hash(ROOT / name)
            local = read_json(ROOT / name)["mcpServers"]
            from .runtime import ALIASES
            required = {ALIASES.get(s, s) for task in tasks(config) for s in task["servers"]}
            for server in sorted(required & local.keys()):
                for argument in local[server].get("args", []):
                    path = Path(argument)
                    if path.is_absolute() and path.is_file():
                        source[f"tool_entry:{stage}:{server}:{path.name}"] = file_hash(path)
        for name in (".runtime/package-lock.json", ".runtime/node_modules/@1mcp/agent/package.json"):
            if (ROOT / name).is_file():
                source[name] = file_hash(ROOT / name)
    code_files = list((ROOT / "src/custom").rglob("*.py")) + list((ROOT / "custom").rglob("*.py"))
    code_files += list((ROOT / "src/custom/experiment").glob("*.mjs"))
    code_files += list((ROOT / "scripts").glob("*.py")) + list((ROOT / "scripts").glob("*.ps1"))
    code_files += [ROOT / "requirements-api.txt"]
    import importlib
    for name in config.get("strategy_plugins", []):
        module = importlib.import_module(name)
        origin = getattr(module, "__file__", None)
        if origin:
            path = Path(origin).resolve()
            code_files.append(path)
            # Include a plugin's local helper modules, without scanning the entire runtime.
            code_files += list(path.parent.glob("*.py") if path.parent == ROOT
                               else path.parent.rglob("*.py"))
    code = digest({p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else str(p): file_hash(p)
                   for p in sorted(set(code_files))})
    return {"config": digest(config), "sources": source, "code": code}
