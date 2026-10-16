"""Bounded local outcome evidence; never a task-success oracle."""
import hashlib
import os
import stat
from pathlib import Path

PROTOCOL = "minimal_repair_v2"
MAX_FILES = 1000
MAX_SCAN_BYTES = 16 * 1024 * 1024
MAX_FILE_BYTES = 1024 * 1024
MAX_CHANGED = 50
MAX_TEXT_CHARS = 4000
MAX_TOTAL_TEXT = 16000


def workspace_snapshot(workspace, include_text=False):
    workspace = Path(workspace)
    result = {"files": {}, "skipped": [], "complete": True}
    try:
        if workspace.is_symlink() or getattr(workspace, "is_junction", lambda: False)():
            return {**result, "complete": False, "skipped": [{"reason": "linked_workspace"}]}
        root = workspace.resolve()
        if not root.is_dir():
            return {**result, "complete": False, "skipped": [{"reason": "workspace_unavailable"}]}
    except (OSError, RuntimeError) as exc:
        return {**result, "complete": False, "skipped": [{"reason": type(exc).__name__}]}
    consumed = 0
    visited = 0
    def walk_error(error):
        result["complete"] = False
        result["skipped"].append({"reason": type(error).__name__})
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        safe_dirs = []
        for name in sorted(dirs):
            visited += 1
            if visited > MAX_FILES:
                return {**result, "complete": False, "skipped": result["skipped"] + [{"reason": "file_count_limit"}]}
            path = Path(directory) / name
            try:
                linked = path.is_symlink() or not path.resolve().is_relative_to(root) or getattr(path, "is_junction", lambda: False)()
            except (OSError, RuntimeError) as exc:
                result["skipped"].append({"path": path.relative_to(root).as_posix(), "reason": type(exc).__name__})
                result["complete"] = False
                continue
            if linked:
                result["skipped"].append({"path": path.relative_to(root).as_posix(), "reason": "linked_directory"})
                result["complete"] = False
            else:
                safe_dirs.append(name)
        dirs[:] = safe_dirs
        for name in sorted(files):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            visited += 1
            if visited > MAX_FILES:
                result["complete"] = False
                result["skipped"].append({"reason": "file_count_limit"})
                return result
            try:
                if path.is_symlink() or not path.resolve().is_relative_to(root):
                    raise ValueError("linked_file")
                info = path.stat()
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError("non_regular_file")
                size = info.st_size
                if size > MAX_FILE_BYTES or consumed + size > MAX_SCAN_BYTES:
                    raise ValueError("byte_limit")
                # Bounded reads also cover a file that grows after stat().
                with path.open("rb") as handle:
                    data = handle.read(min(MAX_FILE_BYTES, MAX_SCAN_BYTES - consumed) + 1)
                consumed += len(data)
                if len(data) > MAX_FILE_BYTES or consumed > MAX_SCAN_BYTES:
                    raise ValueError("byte_limit")
                entry = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                if include_text:
                    try:
                        text = data.decode("utf-8")
                        if "\x00" in text:
                            raise UnicodeError()
                        entry.update(text=text[:MAX_TEXT_CHARS], text_truncated=len(text) > MAX_TEXT_CHARS)
                    except UnicodeError:
                        entry["text_omitted"] = "non_text"
                result["files"][relative] = entry
            except (OSError, ValueError, RuntimeError) as exc:
                result["complete"] = False
                result["skipped"].append({"path": relative, "reason": str(exc) if isinstance(exc, ValueError) else type(exc).__name__})
    return result


def workspace_changes(before, after):
    changes, remaining = [], MAX_TOTAL_TEXT
    def unobserved(name, snapshot):
        return any(not item.get("path") or name == item["path"] or name.startswith(item["path"] + "/")
                   for item in snapshot["skipped"])
    for name in sorted(before["files"].keys() | after["files"].keys()):
        old, new = before["files"].get(name), after["files"].get(name)
        if old and new and old["sha256"] == new["sha256"]:
            continue
        if new is None and unobserved(name, after):
            continue  # A skipped file is not evidence of deletion.
        if old is None and unobserved(name, before):
            kind = "created_or_previously_unobserved"
        else:
            kind = "deleted" if new is None else "created" if old is None else "modified"
        entry = {"path": name, "change": kind, "before_sha256": old["sha256"] if old else None}
        if new:
            entry.update(new)
            if "text" in entry:
                text = entry["text"]
                entry["text"] = text[:remaining]
                entry["text_truncated"] |= len(text) > remaining
                remaining -= len(entry["text"])
        changes.append(entry)
    return {"scope": "private_workspace_only", "task_success": "not_determined",
            "changes": changes[:MAX_CHANGED], "changes_omitted": max(0, len(changes) - MAX_CHANGED),
            "before_complete": before["complete"], "after_complete": after["complete"],
            "skipped_before": before["skipped"], "skipped_after": after["skipped"]}
