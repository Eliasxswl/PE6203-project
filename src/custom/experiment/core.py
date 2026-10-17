"""One ordered strategy/repeat episode; shared by serial and spawn execution."""
from copy import deepcopy
import json
import os
import random
import time

from . import adapters
from .errors import Cancelled, CheckpointFailure, ExecutionFailure
from .results import PROTOCOL, SCORES, TERMINAL, episode_id, identity, redact, safe_error, utc_now
from .runtime import ALIASES, LiveRuntime
from .selection import STAGES, digest, provider_for, request_limit


def runtime_for(config, stage, servers, task_list, cancel, owner_callback=None):
    if config.get("mode") == "offline":
        from .testing import OfflineRuntime
        return OfflineRuntime(config, stage, servers, cancel, task_list)
    return LiveRuntime(config, stage, servers, cancel, owner_callback)


def make_client(config, key, cancel=None, emit=None, role="agent"):
    if config.get("mode") == "offline":
        from .testing import OfflineClient
        return OfflineClient(config, key)
    import httpx
    from openai import OpenAI
    from custom.utils import model_config
    provider = provider_for(config, role, key)
    credential = model_config.role_api_key(role, provider)
    endpoint = model_config.role_base_url(role, provider)
    client = OpenAI(api_key=credential, base_url=endpoint, max_retries=0,
                  timeout=httpx.Timeout(config["runtime"]["model_timeout"], connect=config["runtime"]["connect_timeout"]))
    if config.get("request_policy"):
        from .rate_limit import ControlledClient
        event_sink = (lambda event: emit({**event, "request_key": key,
            "quota_group": provider.get("quota_group", "default"), "role": role})) if emit else None
        return ControlledClient(client, config, endpoint, credential, cancel, event_sink,
                                quota_group=provider.get("quota_group", "default"))
    return client


def judge_prompt(task, row, catalog, order):
    from custom.analysis.answer.evaluation import messages_to_string, truncate_tool_content
    from custom.prompt.eval_error_prompt import build_mcp_bench_judge_prompt
    from custom.utils.test_utils import format_tools_to_string
    descriptions = ""
    for original in task["servers"]:
        server = ALIASES.get(original, original)
        current = [{**tool, "name": key} for key, tool in catalog.items() if tool["server"] == server]
        descriptions += f"Tools for Server - {original}: \n{format_tools_to_string(current)}\n\n"
    visible = truncate_tool_content(row["trajectory_messages"])[2:]
    for message in visible:
        if message.get("tool_calls"):
            message["tool_calls"] = deepcopy(message["tool_calls"])
            for call in message["tool_calls"]:
                function = call.get("function", {})
                name = function.get("name")
                if name is not None:
                    function["name"] = row.get("tool_identities", {}).get(name, name)
    trajectory = messages_to_string(visible)
    return build_mcp_bench_judge_prompt(task["question"], descriptions, trajectory, row["answer"], dimension_order=tuple(order))


def request_judge(client, config, prompt):
    """Shared formal/diagnostic request; prompt and rubric remain unchanged."""
    return client.chat.completions.create(model=config.get("judge_model") or config["agent_model"],
        messages=[{"role": "user", "content": prompt}], temperature=config["judge_temperature"],
        max_tokens=config["judge_max_tokens"],
        **({"extra_body": {"thinking": {"type": config["judge_thinking"]}}}
           if config.get("judge_thinking") else {}))


def parse_judge(raw):
    from custom.analysis.answer.evaluation import extract_json_from_markdown
    result = extract_json_from_markdown(raw)
    if not isinstance(result, dict) or any(type(result.get(s)) is not int or not 1 <= result[s] <= 10 for s in SCORES):
        raise ValueError("Invalid or missing judge scores")
    return result


def initial_snapshot(config, task_list, emit):
    """Freeze one Early catalog for every strategy/repeat, without model calls."""
    snapshot = {"status": "updating", "before": {}, "catalog": {}, "errors": {}}
    emit({"kind": "initial_snapshot", "snapshot": snapshot})
    servers = sorted({ALIASES.get(s, s) for task in task_list for s in task["servers"]})
    for server in servers:
        try:
            with runtime_for(config, "original", [server], task_list, None,
                             lambda event: emit({**event, "episode": "initial"})) as runtime:
                snapshot["catalog"].update(runtime.catalog)
        except Exception as exc:
            snapshot["errors"][server] = safe_error(exc)
    snapshot.update(status="ready", knowledge=adapters.semantic(snapshot["catalog"]),
                    changed_entries=sorted(snapshot["catalog"]),
                    explanation="Shared frozen Early knowledge; each episode receives a defensive copy",
                    elapsed_seconds=0.0, **adapters.no_model_usage())
    emit({"kind": "initial_snapshot", "snapshot": snapshot})
    return snapshot


def run_episode(spec, emit, cancel=None, dispatch=None):
    config, task_list = spec["config"], spec["tasks"]
    strategy, repeat = spec["strategy"], spec["repeat"]
    eid = episode_id(strategy, repeat)
    snapshots = deepcopy(spec["episode"]["stages"])
    rows = deepcopy(spec["records"])
    adapters.load_plugins(config)
    knowledge, previous = {}, {}

    def check_cancel():
        if cancel and cancel.is_set():
            raise Cancelled()

    def send(event):
        check_cancel()
        event.setdefault("episode", eid)
        try:
            emit(redact(event))
        except (Cancelled, CheckpointFailure):
            raise
        except BaseException as exc:
            raise CheckpointFailure("Durable writer unavailable") from exc

    def save_row(key, row):
        row["updated_at"] = utc_now()
        send({"kind": "trajectory", "key": key, "record": row})

    send({"kind": "episode", "episode": eid, "status": "running"})
    for stage in STAGES:
        check_cancel()
        snapshot = snapshots.get(stage)
        if stage == "original" and snapshot is None:
            snapshot = deepcopy(spec["initial_snapshot"])
            send({"kind": "stage", "episode": eid, "stage": stage, "snapshot": snapshot})
            snapshots[stage] = deepcopy(snapshot)
        if snapshot is None:
            snapshot = {"status": "updating", "before": deepcopy(knowledge), "catalog": {}, "errors": {}}
            send({"kind": "stage", "episode": eid, "stage": stage, "snapshot": snapshot})
            # One service per server allows catalog failures to affect only dependent tasks.
            servers = sorted({ALIASES.get(s, s) for t in task_list for s in t["servers"]})
            for server in servers:
                check_cancel()
                try:
                    with runtime_for(config, stage, [server], task_list, cancel, send) as runtime:
                        snapshot["catalog"].update(runtime.catalog)
                except Exception as exc:
                    snapshot["errors"][server] = safe_error(exc)
            try:
                snapshot["catalog"] = adapters.stage_catalog(snapshot["catalog"], config, stage)
                snapshot["evolution_files"] = config["runtime"].get("evolution_files", {}).get(stage, [])
                if stage == "original":
                    result = {"knowledge": adapters.semantic(snapshot["catalog"]),
                              "changed_entries": sorted(snapshot["catalog"]),
                              "explanation": "Independent Early initial knowledge", "elapsed_seconds": 0.0,
                              **adapters.no_model_usage()}
                else:
                    result = adapters.update(strategy, knowledge, previous, snapshot["catalog"],
                                             {"stage": stage, "repeat": repeat})
                snapshot.update(status="ready", **result)
            except Exception as exc:
                snapshot.update(status="failed", error=safe_error(exc))
            send({"kind": "stage", "episode": eid, "stage": stage, "snapshot": snapshot})
            snapshots[stage] = deepcopy(snapshot)
        if snapshot["status"] == "ready":
            knowledge = deepcopy(snapshot["knowledge"])
            previous = deepcopy(snapshot["catalog"])
        else:
            # Never silently reuse or substitute a failed strategy update.
            for task in task_list:
                key = identity(strategy, stage, task["idx"], repeat)
                row = rows[key]
                if row["status"] == "pending":
                    row.update(status="execution_failed", agent_status="failed", score_exclusion_reason="knowledge_update_failed")
                    row["errors"].append(snapshot.get("error", {"type": "KnowledgeFailure", "message": "No valid knowledge snapshot"}))
                    for attempt in row["judge_attempts"]:
                        attempt["status"] = "not_attempted"
                    save_row(key, row)
            # Dependent later transitions cannot start from an uncommitted snapshot.
            for later in STAGES[STAGES.index(stage) + 1:]:
                snapshots[later] = {"status": "failed", "error": {"type": "KnowledgeFailure", "message": "Previous transition failed"}}
                send({"kind": "stage", "episode": eid, "stage": later, "snapshot": snapshots[later]})
            continue
        jobs = [{**spec, "task": task, "stage": stage, "snapshot": deepcopy(snapshot),
                 "knowledge": deepcopy(knowledge), "records": rows} for task in task_list
                if not rows[identity(strategy, stage, task["idx"], repeat)].get("shared_from")]
        if dispatch is None:
            for job in jobs:
                run_trajectory(job, send, cancel)
        else:
            dispatch(jobs)
    send({"kind": "episode", "episode": eid, "status": "completed"})


def run_trajectory(spec, emit, cancel=None):
    config, task_list = spec["config"], spec["tasks"]
    task, stage = spec["task"], spec["stage"]
    strategy, repeat = spec["strategy"], spec["repeat"]
    eid = episode_id(strategy, repeat)
    snapshot, knowledge = spec["snapshot"], spec["knowledge"]
    rows = deepcopy(spec["records"])

    def check_cancel():
        if cancel and cancel.is_set():
            raise Cancelled()

    def send(event):
        check_cancel()
        event.setdefault("episode", eid)
        try:
            emit(redact(event))
        except (Cancelled, CheckpointFailure):
            raise
        except BaseException as exc:
            raise CheckpointFailure("Durable writer unavailable") from exc

    def save_row(key, row):
        row["updated_at"] = utc_now()
        send({"kind": "trajectory", "key": key, "record": row})

    check_cancel()
    key = identity(strategy, stage, task["idx"], repeat)
    row = rows[key]
    if row.get("shared_from"):
        return
    if row["status"] in TERMINAL:
        return
    client = None
    agent = None
    started = time.perf_counter()
    try:
        if row["agent_status"] != "completed":
            row["agent_worker_pid"] = os.getpid()
            row.update(status="running", agent_status="running", started_at=utc_now(),
                       request_limit=request_limit(config, task), knowledge_sha256=digest(knowledge), harness_protocol=PROTOCOL)
            save_row(key, row)
            required = {ALIASES.get(s, s) for s in task["servers"]}
            unavailable = required & snapshot["errors"].keys()
            unavailable |= required & spec["initial_snapshot"]["errors"].keys()
            if unavailable:
                raise ExecutionFailure("Unavailable task servers: " + ", ".join(sorted(unavailable)))
            row["phase"] = "runtime_startup"
            startup_at = time.perf_counter()
            with runtime_for(config, stage, required, task_list, cancel, send) as runtime:
                row["runtime_startup_seconds"] = time.perf_counter() - startup_at
                # Reject catalog drift between stage discovery and trajectory reset.
                expected = {k: v for k, v in snapshot["catalog"].items() if v["server"] in required}
                current = adapters.stage_catalog(runtime.catalog, config, stage)
                if adapters.semantic(expected) != adapters.semantic(current):
                    raise ExecutionFailure("Tool catalog changed after the stage checkpoint")
                client = make_client(config, key, cancel, send)
                tools, routing = adapters.agent_tools(knowledge, runtime.catalog, required)
                row["tool_identities"] = {tool["name"]: tool["meta"]["benchmark_semantic_identity"] for tool in tools}
                if not tools:
                    raise ExecutionFailure("No initial semantic knowledge is available for this task")

                def on_agent_event(kind, payload):
                    check_cancel()
                    if kind == "model_start":
                        row["phase"] = "agent_model"
                        row["trajectory_messages"] = deepcopy(payload["messages"])
                        row["agent_attempts"].append({"status": "started", "started_at": utc_now()})
                    elif kind == "model_completed":
                        row["agent_attempts"][-1].update(status="completed", response=payload, completed_at=utc_now())
                    elif kind == "model_failed":
                        row["agent_attempts"][-1].update(status="outcome_unknown" if payload.get("unknown_outcome") else "failed",
                                                         error=payload, completed_at=utc_now())
                    elif kind == "tool_completed":
                        row.update(deepcopy(payload))
                        row["tool_attempts"][-1].update(status="completed", completed_at=utc_now())
                    elif kind == "tool_start":
                        row["phase"] = "tool"
                        row["trajectory_messages"] = deepcopy(payload["messages"])
                        row["tool_attempts"].append({"status": "started", "started_at": utc_now(),
                            "name": payload["name"], "arguments": payload["arguments"],
                            "tool_call_id": payload["tool_call_id"]})
                    elif kind == "tool_failed":
                        row["tool_attempts"][-1].update(status="outcome_unknown" if payload.get("unknown_outcome") else "failed",
                                                        error=payload, completed_at=utc_now())
                    save_row(key, row)

                from custom.agents.SimpleOpenAIAgent import ChatModel
                from custom.utils.test_utils import generate_tree_string
                agent = ChatModel(model_name=config["agent_model"], client=client, tools=tools,
                                  max_round=row["request_limit"], tool_server_map=routing,
                                  file_exists=generate_tree_string(str(runtime.workspace)), workspace_root=runtime.workspace,
                                  prompt_time=spec["prompt_time"], temperature=config["agent_temperature"],
                                  max_new_tokens=config["agent_max_tokens"], tool_caller=runtime.call,
                                  event_callback=on_agent_event, mcp_server_url=runtime.url,
                                  thinking=config.get("agent_thinking"))
                answer, messages, stop, exceeded = agent.run_with_server(task["question"])
                row.update(answer=answer, trajectory_messages=messages, raw_tool_trace=agent.raw_tool_trace,
                           stop=stop, exceeded=exceeded, stop_reason=agent.stop_reason,
                           agent_usage=agent.model_usage, request_count=agent.request_count,
                           agent_elapsed_seconds=agent.elapsed_seconds)
                if agent.execution_error:
                    row["errors"].append(agent.execution_error)
                    raise ExecutionFailure("Agent execution failed; see recorded request/transport error")
            row["agent_status"] = "completed"
            row["judge_catalog"] = deepcopy(expected)
            save_row(key, row)
        if spec.get("phase") == "agent":
            row["elapsed_seconds"] = row.get("elapsed_seconds", 0) + time.perf_counter() - started
            save_row(key, row)
            return
        if client is not None:
            client.close()
        client = make_client(config, key + "/judge", cancel, send, role="judge")
        row["judge_worker_pid"] = os.getpid()
        for attempt in row["judge_attempts"]:
            check_cancel()
            if attempt["status"] != "pending":
                continue
            seed = int(digest([config["selection_seed"], stage, task["idx"], repeat, attempt["slot"]])[:16], 16)
            order = random.Random(seed).sample([0, 1, 2], 3)
            prompt = judge_prompt(task, row, row["judge_catalog"], order)
            attempt.update(status="started", dimension_order=order, started_at=utc_now())
            row["phase"] = "judge"
            save_row(key, row)
            judge_started = time.perf_counter()
            try:
                if attempt["slot"] in config.get("mock", {}).get("judge_fail_slots", []) and config["mode"] == "offline":
                    raise ExecutionFailure("Injected judge failure")
                response = request_judge(client, config, prompt)
                raw = response.choices[0].message.content or ""
                attempt.update(raw=raw, usage=response.usage.model_dump() if response.usage else None)
                result = parse_judge(raw)
                attempt.update(status="completed", result=result)
            except Exception as exc:
                error = safe_error(exc)
                attempt.update(status="outcome_unknown" if error["unknown_outcome"] else "failed", error=error)
            attempt.update(elapsed_seconds=time.perf_counter() - judge_started, completed_at=utc_now())
            save_row(key, row)
        good = [a["result"] for a in row["judge_attempts"] if a["status"] == "completed"]
        row.update(status="completed", score={s: sum(a[s] for a in good) / len(good) for s in SCORES} if good else None)
        if not good:
            row["score_exclusion_reason"] = "no_valid_judge_attempts"
    except Exception as exc:
        row.update(status="execution_failed", agent_status="failed", score_exclusion_reason="execution_failure")
        row["errors"].append(safe_error(exc))
        if agent is not None:
            row.update(trajectory_messages=deepcopy(agent.messages), raw_tool_trace=deepcopy(agent.raw_tool_trace))
        for attempt in row["judge_attempts"]:
            if attempt["status"] == "pending":
                attempt["status"] = "not_attempted"
    finally:
        if client is not None:
            try:
                client.close()
            except Exception as exc:
                row["errors"].append({"phase": "client_cleanup", **safe_error(exc)})
    row["elapsed_seconds"] = row.get("elapsed_seconds", 0) + time.perf_counter() - started
    save_row(key, row)
