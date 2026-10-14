"""Standalone preflight evidence, never a formal strategy or trajectory."""
from datetime import datetime, timezone
from pathlib import Path
import json

from .core import make_client, runtime_for
from .results import SCORES, atomic_json, safe_error
from .runtime import ALIASES
from .selection import ROOT, STAGES


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
