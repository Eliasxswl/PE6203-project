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

from .selection import ROOT, STAGES, digest, read_json

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


def create(config, task_list, fingerprints, parallel=False, workers=1):
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
    manifest = {"schema_version": SCHEMA, "operator": operator, "created_at": utc_now(),
                "revision": git("rev-parse", "HEAD"), "dirty_source": bool(git("status", "--porcelain")),
                "fingerprints": fingerprints, "settings": config, "selected_ids": [t["idx"] for t in task_list],
                "execution": {"parallel": parallel, "workers": workers},
                "planned_jobs": [r["identity"] for r in records["trajectories"].values()]}
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
        atomic_json(self.path / "records.json", self.records)

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

    def recover(self, episode=None, reason="unclean_stop"):
        changed = False
        for key, row in self.records["trajectories"].items():
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
        aggregate = aggregate_records(self.records["trajectories"])
        self.records["aggregate"] = aggregate
        self.save()
        return aggregate


def aggregate_records(rows):
    groups = {}
    for row in rows.values():
        group = row["identity"]["strategy"] + "/" + row["identity"]["stage"]
        groups.setdefault(group, []).append(row)
    output = {"groups": {}, "ecs": {}, "paired": {}}
    for group, records in groups.items():
        scores = [r["score"] for r in records if r.get("score") is not None]
        counts = Counter(r["status"] for r in records)
        output["groups"][group] = {"planned": len(records), "valid": len(scores), "statuses": dict(counts),
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
                                     "value": statistics.mean(statistics.mean(v) - statistics.pstdev(v) for v in complete)
                                     if complete else None}
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
