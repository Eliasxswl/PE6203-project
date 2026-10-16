"""Local provenance and preparation checks; no model or tool execution."""
import platform
import shutil
import subprocess

from .selection import ROOT, STAGES, annotations, file_hash

BUNDLE_SOURCE = "https://huggingface.co/datasets/anonymous2233/evol-servers/tree/main"


def source_state():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    return {"revision": git("rev-parse", "HEAD"), "dirty_source": bool(git("status", "--porcelain"))}


def environment(config):
    result = {"python": {"version": platform.python_version(), "implementation": platform.python_implementation()},
              "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
              "node": None, "tool_bundles": {}, "bundle_source_reference": BUNDLE_SOURCE,
              "bundle_scope": "Archive bytes only; local entry files are fingerprinted separately. Extraction equivalence is not certified."}
    node = shutil.which("node")
    if node:
        try:
            result["node"] = {"version": subprocess.check_output([node, "--version"], text=True, timeout=10).strip()}
        except (OSError, subprocess.SubprocessError) as exc:
            result["node"] = {"error": type(exc).__name__}
    for stage in STAGES:
        path = ROOT / "servers/downloads" / f"{stage}_servers.zip"
        row = {"path": path.relative_to(ROOT).as_posix()}
        if config.get("mode") == "offline":
            row["status"] = "not_used_offline"
        elif path.is_file():
            row.update(status="present", size_bytes=path.stat().st_size, sha256=file_hash(path))
        else:
            row["status"] = "missing"
        result["tool_bundles"][stage] = row
    return result


def preparation(config, warnings=(), state=None, task_list=None):
    state = source_state() if state is None else state
    labels = annotations(config)
    from .selection import tasks
    ids = [task["idx"] for task in (tasks(config) if task_list is None else task_list)]
    pending = [idx for idx in ids if labels.get(str(idx), {}).get("status") != "confirmed"
               or set(labels[str(idx)].get("transitions", {})) != set(STAGES[1:])]
    return {**state, "classification_pending_ids": pending,
            "bundle_archives_present": {stage: (ROOT / "servers/downloads" / f"{stage}_servers.zip").is_file()
                                        for stage in STAGES},
            "backend_policy_warnings": list(warnings),
            "formal_acceptance": "not_assessed",
            "remaining_review": ["Role 3 protocol/coverage/repeats approval", "Selected backends on the target machine",
                                 "Actual-trajectory Judge compatibility and scoring limitations"],
            "mode": config.get("mode", "live")}
