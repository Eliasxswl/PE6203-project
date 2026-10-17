"""Standalone preflight evidence, never a formal strategy or trajectory."""
from datetime import datetime, timezone
from pathlib import Path
from copy import deepcopy
import json
import time

from .core import judge_prompt, make_client, parse_judge, request_judge, runtime_for
from .results import PROTOCOL, SCORES, Store, atomic_json, safe_error
from .runtime import ALIASES
from .selection import ROOT, STAGES, digest, file_hash, provider_options


def check_judge(config, experiment, trajectory, attempts=1, provider_index=0):
    """Explicit diagnostic only: replay an archived trajectory, never execute tools."""
    from .evidence import archived_tasks
    if type(attempts) is not int or not 1 <= attempts <= 5:
        raise ValueError("Use 1 to 5 diagnostic attempts")
    options = provider_options(config, "judge")
    if not 0 <= provider_index < len(options):
        raise ValueError("Judge provider index is outside the configured pool")
    effective = deepcopy(config)
    effective.setdefault("providers", {})["judge"] = options[provider_index]
    store = Store(experiment)
    row = store.records["trajectories"].get(trajectory)
    source_trajectory = row.get("shared_from", trajectory) if row else trajectory
    if source_trajectory != trajectory:
        row = store.records["trajectories"][source_trajectory]
    if row is None or row.get("agent_status") != "completed" or not row.get("trajectory_messages"):
        raise ValueError("Select an archived trajectory whose Agent completed with saved messages")
    if "judge_catalog" not in row:
        raise ValueError("Archived trajectory has no saved Judge catalog")
    task = next(t for t in archived_tasks(store.manifest) if t["idx"] == row["identity"]["task_id"])
    order = [0, 1, 2]
    prompt = judge_prompt(task, row, row["judge_catalog"], order)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = ROOT / ".runtime/experiments/checks" / ("judge-" + stamp + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    result = {"purpose": "actual_trajectory_judge_compatibility", "semantic_accuracy": "not_validated",
        "source_experiment": str(store.path), "trajectory": trajectory, "source_trajectory": source_trajectory,
        "source_records_sha256": file_hash(store.path / "records.json"),
        "source_harness_protocol": store.manifest.get("harness_protocol"),
        "request_harness_protocol": PROTOCOL,
        "prompt_sha256": digest(prompt), "prompt_characters": len(prompt), "dimension_order": order,
        "provider_index": provider_index, "model": config.get("judge_model") or config["agent_model"],
        "temperature": config["judge_temperature"], "max_tokens": config["judge_max_tokens"],
        "thinking": config.get("judge_thinking"), "attempts": [], "status": "running"}
    atomic_json(path, result)
    client = None
    try:
        client = make_client(effective, "preflight/judge", role="judge")
        for slot in range(attempts):
            attempt = {"slot": slot, "status": "started"}
            result["attempts"].append(attempt)
            atomic_json(path, result)
            started = time.perf_counter()
            try:
                response = request_judge(client, effective, prompt)
                raw = response.choices[0].message.content or ""
                attempt.update(raw=raw, usage=response.usage.model_dump() if response.usage else None)
                attempt.update(result=parse_judge(raw), status="completed")
            except Exception as exc:
                error = safe_error(exc)
                attempt.update(status="outcome_unknown" if error["unknown_outcome"] else "failed", error=error)
            attempt["elapsed_seconds"] = time.perf_counter() - started
            atomic_json(path, result)
        result["status"] = "passed" if all(a["status"] == "completed" for a in result["attempts"]) else "failed"
    except Exception as exc:
        result.update(status="failed", error=safe_error(exc))
    finally:
        if client is not None:
            try:
                client.close()
            except Exception as exc:
                result.update(status="failed", cleanup_error=safe_error(exc))
        atomic_json(path, result)
    return {"status": result["status"], "purpose": result["purpose"], "semantic_accuracy": "not_validated",
            "attempted": len(result["attempts"]), "valid": sum(a["status"] == "completed" for a in result["attempts"]),
            "provider_index": provider_index, "model": result["model"], "report": str(path)}


def check_models(config):
    client = make_client(config, "preflight")
    try:
        options = {"model": config["agent_model"], "temperature": config["agent_temperature"],
                   "max_tokens": config["agent_max_tokens"]}
        if config.get("agent_thinking"):
            options["extra_body"] = {"thinking": {"type": config["agent_thinking"]}}
        messages = [{"role": "user", "content": "Call connectivity_ping with no arguments."}]
        tool = {"type": "function", "function": {"name": "connectivity_ping",
            "description": "A local connectivity check returning pong.",
            "parameters": {"type": "object", "properties": {}}}}
        response = client.chat.completions.create(messages=messages, tools=[tool], **options)
        message = response.choices[0].message
        if not message.tool_calls or any(c.function.name != "connectivity_ping" for c in message.tool_calls):
            raise ValueError("Model did not produce the expected tool call")
        messages.append(message.model_dump(exclude_none=True))
        for call in message.tool_calls:
            if json.loads(call.function.arguments) != {}:
                raise ValueError("Invalid connectivity tool arguments")
            messages.append({"role": "tool", "tool_call_id": call.id, "content": "pong"})
        response = client.chat.completions.create(messages=messages, tools=[tool], **options)
        if not response.choices[0].message.content:
            raise ValueError("Model did not return text after tool feedback")
        judge = {"model": config.get("judge_model") or config["agent_model"],
                 "temperature": config["judge_temperature"], "max_tokens": config["judge_max_tokens"]}
        if config.get("judge_thinking"):
            judge["extra_body"] = {"thinking": {"type": config["judge_thinking"]}}
        client.close()
        client = make_client(config, "preflight/judge", role="judge")
        response = client.chat.completions.create(messages=[{"role": "user", "content":
            "For a connectivity test, return only a JSON object with the integer 8 for each key: "
            + ", ".join(SCORES)}], **judge)
        from custom.analysis.answer.evaluation import extract_json_from_markdown
        score = extract_json_from_markdown(response.choices[0].message.content or "")
        if not isinstance(score, dict) or any(type(score.get(s)) is not int or score[s] != 8 for s in SCORES):
            raise ValueError("Judge did not return the expected scoring JSON")
        return {"status": "passed", "requests": 3, "agent_model": config["agent_model"],
                "judge_model": judge["model"]}
    except Exception as exc:
        return {"status": "failed", "error": safe_error(exc)}
    finally:
        client.close()


def check(config, task_list, requested_servers=None, requested_stage=None, skip_models=False):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = ROOT / ".runtime/experiments/checks" / (stamp + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    result = {"purpose": "preflight_only", "catalog_source": config["runtime"].get("catalog_source"),
              "servers": {}, "models": None, "status": "running"}
    servers = sorted({ALIASES.get(s, s) for t in task_list for s in t["servers"]})
    if requested_servers:
        requested = {ALIASES.get(s, s) for s in requested_servers}
        if not requested <= set(servers):
            raise ValueError("The requested server is outside the frozen selection")
        servers = sorted(requested)
    for stage in ([requested_stage] if requested_stage else STAGES):
        for server in servers:
            key = stage + "/" + server
            try:
                with runtime_for(config, stage, [server], task_list, None) as runtime:
                    result["servers"][key] = {"status": "passed", "tool_count": len(runtime.catalog),
                                               "catalog": runtime.catalog}
            except Exception as exc:
                result["servers"][key] = {"status": "failed", "error": safe_error(exc)}
            atomic_json(path, result)
    result["models"] = {"status": "not_requested"} if skip_models else check_models(config)
    result["status"] = "passed" if (skip_models or result["models"]["status"] == "passed") and all(
        row["status"] == "passed" for row in result["servers"].values()) else "failed"
    result["report"] = str(path)
    atomic_json(path, result)
    return {k: v for k, v in result.items() if k != "servers"} | {
        "servers": {k: {f: v for f, v in row.items() if f != "catalog"} for k, row in result["servers"].items()}}
