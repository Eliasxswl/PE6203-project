"""Single-writer checkpoints, conservative recovery, and matched aggregation."""
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import time
import uuid

from .selection import ROOT, STAGES, annotations, digest, read_json

PROTOCOL = "shared_early_v1"
SCHEMA = 1
SCORES = ("task_fulfillment", "grounding", "planning_and_efficiency")
TERMINAL = {"completed", "execution_failed", "interrupted", "outcome_unknown"}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def safe_error(error, depth=0):
    name, module = type(error).__name__, type(error).__module__
    unknown = bool(getattr(error, "unknown_outcome", False)) or isinstance(error, (TimeoutError, ConnectionError))
    if module.startswith(("openai", "httpx", "anyio")) and name in {
        "APIConnectionError", "APITimeoutError", "ReadTimeout", "ConnectTimeout", "WriteTimeout",
        "ConnectError", "ReadError", "WriteError", "RemoteProtocolError", "EndOfStream",
        "BrokenResourceError", "ClosedResourceError"}:
        unknown = True
    result = {"type": name, "message": str(error), "unknown_outcome": unknown}
    protocol = getattr(error, "error", None)
    if hasattr(protocol, "model_dump"):
        result["protocol_error"] = protocol.model_dump(mode="json")
    response = getattr(error, "response", None)
    if response is not None:
        result["http_status"] = getattr(response, "status_code", None)
    if depth < 4:
        cause = error.__cause__
        if cause is not None and cause is not error:
            result["cause"] = safe_error(cause, depth + 1)
            result["unknown_outcome"] |= result["cause"]["unknown_outcome"]
        nested = getattr(error, "exceptions", [])
        if nested:
            result["causes"] = [safe_error(child, depth + 1) for child in nested]
            result["unknown_outcome"] |= any(child["unknown_outcome"] for child in result["causes"])
    return result


def redact(value, secrets=None):
    if secrets is None:
        secrets = [v for k, v in os.environ.items() if len(v) >= 8 and
                   any(part in k.upper() for part in ("API_KEY", "TOKEN", "SECRET", "PASSWORD"))]
    if isinstance(value, dict):
        return {k: "[REDACTED]" if k.lower() in ("api_key", "authorization", "access_token", "password", "secret")
                else redact(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~-]+", r"\1[REDACTED]", value)
        value = re.sub(r"(?i)(authorization\s*:\s*)[^\r\n]+", r"\1[REDACTED]", value)
    return value


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(redact(value), stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Windows readers/indexers can briefly deny rename sharing. Retry only the
        # same checkpoint; no model/tool request is dispatched before it succeeds.
        for retry in range(8):
            try:
                os.replace(temporary, path)
                break
            except PermissionError as exc:
                if os.name != "nt" or getattr(exc, "winerror", None) not in (5, 32, 33) or retry == 7:
                    raise
                time.sleep(min(.01 * 2 ** retry, .1))
        if os.name != "nt":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def writer_lock(path):
    """OS locks release on process death; no stale PID file needs deleting."""
    lock_path = ROOT / ".runtime/experiments/locks" / (digest(str(Path(path).resolve())) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("Another writer owns this experiment") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def identity(strategy, stage, task_id, repeat):
    return f"{strategy}/{stage}/{task_id}/{repeat}"


def episode_id(strategy, repeat):
    return f"{strategy}/{repeat}"


def create(config, task_list, fingerprints, parallel=False, workers=1, warnings=None):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    operator = git("config", "user.name")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", operator).strip(" .") or "operator"
    output_root = ROOT / ".runtime/experiments/offline-results" if config.get("mode") == "offline" else ROOT / "results"
    experiment = output_root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ_") + name)
    experiment.mkdir(parents=True, exist_ok=False)
    records = {"schema_version": SCHEMA, "status": "prepared", "events": [], "episodes": {},
               "trajectories": {}, "aggregate": {}, "initial_snapshot": None}
    for strategy in config["strategies"]:
        for repeat in range(config["agent_repeats"]):
            records["episodes"][episode_id(strategy, repeat)] = {"stages": {}, "status": "pending"}
            for stage in STAGES:
                for task in task_list:
                    key = identity(strategy, stage, task["idx"], repeat)
                    records["trajectories"][key] = {
                        "identity": {"strategy": strategy, "stage": stage, "task_id": task["idx"], "repeat": repeat},
                        "status": "pending", "agent_status": "pending", "agent_attempts": [],
                        "tool_attempts": [],
                        "judge_attempts": [{"slot": i, "status": "pending"} for i in range(5)],
                        "errors": [], "raw_tool_trace": [], "trajectory_messages": [], "score": None}
    # One source per task/repeat. References carry scores/status, never duplicate
    # requests, traces or usage. Prefer the unchanged baseline as the source owner.
    owner = "no_update" if "no_update" in config["strategies"] else config["strategies"][0]
    for row in records["trajectories"].values():
        ident = row["identity"]
        if ident["stage"] == STAGES[0] and ident["strategy"] != owner:
            row["shared_from"] = identity(owner, STAGES[0], ident["task_id"], ident["repeat"])
            row["judge_attempts"] = []
    from .readiness import environment, preparation, source_state
    state = source_state()
    manifest = {"schema_version": SCHEMA, "harness_protocol": PROTOCOL, "operator": operator, "created_at": utc_now(),
                **state, "environment": environment(config),
                "preparation": preparation(config, warnings or (), state=state, task_list=task_list),
                "task_definitions": deepcopy(task_list), "task_annotations": annotations(config),
                "fingerprints": fingerprints, "settings": config, "selected_ids": [t["idx"] for t in task_list],
                "execution": {"parallel": parallel, "workers": workers},
                "analysis": {"classification_reference": STAGES[0], "comparison_strategy": "no_update"},
                "shared_early": {"owner_strategy": owner, "scope": "task_and_repeat", "judge_slots_per_source": 5},
                "logical_conditions": [r["identity"] for r in records["trajectories"].values()],
                "planned_jobs": [r["identity"] for r in records["trajectories"].values() if not r.get("shared_from")]}
    atomic_json(experiment / "experiment.json", manifest)
    atomic_json(experiment / "records.json", records)
    return experiment


class Store:
    def __init__(self, experiment):
        self.path = Path(experiment).resolve()
        self.manifest = read_json(self.path / "experiment.json")
        self.records = read_json(self.path / "records.json")
        if self.records["schema_version"] != SCHEMA or self.manifest["schema_version"] != SCHEMA:
            raise ValueError("Unsupported result schema")

    def save(self):
        self.sync_shared()
        atomic_json(self.path / "records.json", self.records)

    def sync_shared(self):
        """Publish source outcomes atomically, including partial/failure states."""
        rows = self.records["trajectories"]
        for row in rows.values():
            source_key = row.get("shared_from")
            if not source_key:
                continue
            source = rows[source_key]
            ident, source_ident = row["identity"], source["identity"]
            if (source.get("shared_from") or ident["stage"] != STAGES[0]
                    or source_ident["stage"] != STAGES[0]
                    or any(ident[field] != source_ident[field] for field in ("task_id", "repeat"))):
                raise ValueError("Invalid shared Early source")
            for field in ("status", "agent_status", "score", "score_exclusion_reason", "knowledge_sha256"):
                if field in source:
                    row[field] = deepcopy(source[field])
                else:
                    row.pop(field, None)

    def event(self, kind, **data):
        self.records["events"].append({"kind": kind, "time": utc_now(), **redact(data)})
        self.save()

    def apply(self, event):
        kind = event["kind"]
        if kind == "trajectory":
            self.records["trajectories"][event["key"]] = deepcopy(redact(event["record"]))
        elif kind == "stage":
            self.records["episodes"][event["episode"]]["stages"][event["stage"]] = deepcopy(redact(event["snapshot"]))
        elif kind == "episode":
            self.records["episodes"][event["episode"]]["status"] = event["status"]
        elif kind == "initial_snapshot":
            self.records["initial_snapshot"] = deepcopy(redact(event["snapshot"]))
        else:
            self.records["events"].append({"time": utc_now(), **redact(event)})
        self.save()

    def recover(self, episode=None, reason="unclean_stop", trajectory=None):
        changed = False
        for key, row in self.records["trajectories"].items():
            if row.get("shared_from"):
                continue
            if trajectory is not None and key != trajectory:
                continue
            ident = row["identity"]
            if episode and episode_id(ident["strategy"], ident["repeat"]) != episode:
                continue
            for attempt in row["agent_attempts"] + row["judge_attempts"] + row.get("tool_attempts", []):
                if attempt["status"] == "started":
                    attempt.update(status="outcome_unknown", error={"type": reason, "message": "No durable completion"})
                    changed = True
            if row["status"] == "running" and row["agent_status"] != "completed":
                unknown = any(a["status"] == "outcome_unknown" for a in row["agent_attempts"] + row.get("tool_attempts", []))
                row.update(status="outcome_unknown" if unknown else "interrupted", agent_status="interrupted",
                           score_exclusion_reason=reason)
                row["errors"].append({"type": reason, "message": "Interrupted trajectory is not replayed"})
                for attempt in row["judge_attempts"]:
                    if attempt["status"] == "pending":
                        attempt["status"] = "not_attempted"
                changed = True
            elif row["status"] == "running":
                # Agent already completed; remaining unstarted judge slots are resumable.
                changed = True
        for eid, entry in self.records["episodes"].items():
            if episode and eid != episode:
                continue
            for stage, snapshot in entry["stages"].items():
                if snapshot["status"] == "updating":
                    snapshot.update(status="failed", error={"type": reason, "message": "Knowledge update outcome unknown"})
                    changed = True
        if changed:
            self.event("recovery", episode=episode, reason=reason)
        return changed

    def summarize(self):
        self.sync_shared()
        aggregate = aggregate_records(self.records["trajectories"])
        aggregate["update_costs"] = update_costs(self.records.get("episodes", {}))
        from .evidence import catalog_evidence
        evidence = catalog_evidence(self.records, self.manifest.get("task_definitions", []))
        aggregate["recovery_retention"] = cohort_scores(self.records["trajectories"],
            self.manifest.get("task_annotations", {}), evidence)
        aggregate["completion"] = completion(self.records)
        self.records["aggregate"] = aggregate
        self.save()
        return aggregate


def aggregate_records(rows):
    groups = {}
    for row in rows.values():
        group = row["identity"]["strategy"] + "/" + row["identity"]["stage"]
        groups.setdefault(group, []).append(row)
    output = {"groups": {}, "ecs": {}, "paired": {}, "paired_ecs": {}}
    for group, records in groups.items():
        scores = [r["score"] for r in records if r.get("score") is not None]
        counts = Counter(r["status"] for r in records)
        output["groups"][group] = {"planned": len(records), "valid": len(scores), "statuses": dict(counts),
                                    "independent_trajectories": sum(not r.get("shared_from") for r in records),
                                    "shared_references": sum(bool(r.get("shared_from")) for r in records),
                                    "excluded": len(records) - len(scores),
                                    "means": {s: sum(score[s] for score in scores) / len(scores) if scores else None
                                              for s in SCORES},
                                    "judge_statuses": dict(Counter(a["status"] for r in records for a in r["judge_attempts"]))}
    strategies = sorted({r["identity"]["strategy"] for r in rows.values()})
    for strategy in strategies:
        matched = {}
        for r in rows.values():
            ident = r["identity"]
            if ident["strategy"] == strategy and r.get("score") is not None:
                matched.setdefault((ident["task_id"], ident["repeat"]), {})[ident["stage"]] = r["score"]["task_fulfillment"]
        complete = [list(stage_scores.values()) for stage_scores in matched.values() if set(stage_scores) == set(STAGES)]
        # Upstream uses population variance for exactly the three version conditions.
        output["ecs"][strategy] = {"matched_task_repeats": len(complete),
                                     "identities": [list(k) for k, v in sorted(matched.items()) if set(v) == set(STAGES)],
                                     "value": statistics.mean(statistics.mean(v) - statistics.pstdev(v) for v in complete)
                                     if complete else None}
    planned = {(r["identity"]["task_id"], r["identity"]["repeat"]) for r in rows.values()}
    indexed = {(r["identity"]["strategy"], r["identity"]["stage"], r["identity"]["task_id"], r["identity"]["repeat"]): r
               for r in rows.values()}
    common_ecs, excluded = [], []
    for task_id, repeat in sorted(planned):
        missing = [{"strategy": strategy, "stage": stage,
                    "reason": indexed.get((strategy, stage, task_id, repeat), {}).get("score_exclusion_reason", "no_valid_score")}
                   for strategy in strategies for stage in STAGES
                   if indexed.get((strategy, stage, task_id, repeat), {}).get("score") is None]
        if missing:
            excluded.append({"task_id": task_id, "repeat": repeat, "missing": missing})
        else:
            common_ecs.append((task_id, repeat))
    output["paired_ecs"] = {"matched": len(common_ecs), "identities": [list(k) for k in common_ecs],
        "excluded": excluded, "values": {strategy: statistics.mean(
            statistics.mean(v) - statistics.pstdev(v) for v in (
                [indexed[(strategy, stage, task_id, repeat)]["score"]["task_fulfillment"] for stage in STAGES]
                for task_id, repeat in common_ecs)) if common_ecs else None for strategy in strategies}}
    for stage in STAGES:
        by_strategy = {s: {(r["identity"]["task_id"], r["identity"]["repeat"]): r["score"]
                           for r in rows.values() if r["identity"]["strategy"] == s
                           and r["identity"]["stage"] == stage and r.get("score") is not None}
                       for s in strategies}
        common = set.intersection(*(set(v) for v in by_strategy.values())) if by_strategy else set()
        output["paired"][stage] = {"matched": len(common), "identities": [list(k) for k in sorted(common)],
                                    "means": {s: {dim: statistics.mean(scores[k][dim] for k in common) if common else None
                                                   for dim in SCORES} for s, scores in by_strategy.items()}}
    return output


def update_costs(episodes):
    """Count each episode transition once, never once per trajectory."""
    groups = {}
    for eid, episode in episodes.items():
        strategy = eid.rsplit("/", 1)[0]
        for stage in STAGES[1:]:
            snapshot = episode.get("stages", {}).get(stage, {})
            groups.setdefault(strategy + "/" + stage, []).append(snapshot)
    result = {}
    for group, snapshots in groups.items():
        summary = {"planned_updates": len(snapshots), "statuses": dict(Counter(s.get("status", "pending") for s in snapshots))}
        for field in ("elapsed_seconds", "api_calls", "input_tokens", "output_tokens"):
            known = [s[field] for s in snapshots if s.get(field) is not None]
            summary[field] = {"reported": len(known), "unreported": len(snapshots) - len(known),
                              "total_reported": sum(known) if known else None}
        costs = [s for s in snapshots if s.get("api_cost") is not None]
        currencies = {s.get("cost_currency") for s in costs if s["api_cost"] != 0}
        # Unknown or mixed currencies must never silently become a single money total.
        summary["api_cost"] = {"reported": len(costs), "unreported": len(snapshots) - len(costs),
            "total_reported": sum(s["api_cost"] for s in costs) if costs and len(currencies) <= 1 else None,
            "currency": next(iter(currencies)) if len(currencies) == 1 else None,
            "bases": sorted({s["cost_basis"] for s in costs if s.get("cost_basis")}),
            "mixed_currencies": len(currencies) > 1}
        result[group] = summary
    return result


def cohort_scores(rows, annotations, evidence):
    from .evidence import confirmed_label
    output = {"status": "not_configured" if not annotations else "pending", "transitions": {},
              "reference_stage": STAGES[0], "comparison_strategy": "no_update",
              "delta": "Same-version TF minus No Update TF on common valid task/repeat pairs; not a success rate or task-success validator."}
    strategies = sorted({r["identity"]["strategy"] for r in rows.values()})
    indexed = {(r["identity"]["strategy"], r["identity"]["stage"], r["identity"]["task_id"], r["identity"]["repeat"]): r
               for r in rows.values()}
    planned = sorted({(r["identity"]["task_id"], r["identity"]["repeat"]) for r in rows.values()})
    for stage in STAGES[1:]:
        groups = {"changed": [], "retention": []}
        excluded = []
        for task_id, repeat in planned:
            labels, reasons = [], []
            if "no_update" not in strategies:
                reasons.append({"strategy": "no_update", "reason": "comparison_strategy_not_configured"})
            for strategy in strategies:
                label, reason = confirmed_label(annotations, evidence, episode_id(strategy, repeat), stage, task_id)
                if reason:
                    reasons.append({"strategy": strategy, "reason": reason})
                else:
                    labels.append(label)
                if indexed.get((strategy, stage, task_id, repeat), {}).get("score") is None:
                    reasons.append({"strategy": strategy, "reason": "no_paired_valid_scores"})
            if reasons:
                excluded.append({"task_id": task_id, "repeat": repeat, "reasons": reasons})
            elif labels:
                groups[labels[0]["cohort"]].append((task_id, repeat))
        output["transitions"][stage] = {"reference_stage": STAGES[0], "excluded": excluded}
        for cohort, common in groups.items():
            output["transitions"][stage][cohort] = {"matched": len(common), "identities": [list(k) for k in common],
                "mean_tf_delta_vs_no_update": {strategy: statistics.mean(
                    indexed[(strategy, stage, task_id, repeat)]["score"]["task_fulfillment"]
                    - indexed[("no_update", stage, task_id, repeat)]["score"]["task_fulfillment"]
                    for task_id, repeat in common) if common else None for strategy in strategies}}
    if annotations:
        output["status"] = "available" if any(v[c]["matched"] for v in output["transitions"].values()
                                               for c in ("changed", "retention")) else "pending"
    return output


def completion(records):
    logical = list(records["trajectories"].values())
    rows = [r for r in logical if not r.get("shared_from")]
    judge_statuses = Counter(a["status"] for r in rows for a in r["judge_attempts"])
    score_count = sum(r.get("score") is not None for r in rows)
    status = records["status"]
    exit_code = 0 if status in ("completed", "completed_with_warnings") else 3 if status in (
        "completed_with_failures", "partial") else 2
    return {"status": status, "exit_code": exit_code, "planned_trajectories": len(rows),
            "logical_conditions": len(logical), "shared_early_references": len(logical) - len(rows),
            "scored_logical_conditions": sum(r.get("score") is not None for r in logical),
            "scored_trajectories": score_count, "judge_statuses": dict(judge_statuses),
            "judge_slots": sum(judge_statuses.values()), "valid_judge_slots": judge_statuses["completed"],
            "formal_acceptance": "not_assessed"}
