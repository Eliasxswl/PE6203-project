"""Shared model admission and overload cooldown, without request retries."""
from contextlib import contextmanager
from email.utils import parsedate_to_datetime
import errno
import math
import os
from pathlib import Path
import time
from types import SimpleNamespace
import uuid

from .errors import Cancelled
from .results import atomic_json
from .selection import ROOT, digest, read_json


class RequestGate:
    def __init__(self, path, policy, cancel=None, emit=None, clock=time.time, sleep=time.sleep,
                 recovery_timeout=180):
        self.path = Path(path)
        self.policy, self.cancel = policy, cancel
        self.emit = emit or (lambda event: None)
        self.clock, self.sleep = clock, sleep
        self.recovery_timeout = recovery_timeout
        self.credential_id = "unspecified"

    def check_cancel(self):
        if self.cancel is not None and self.cancel.is_set():
            raise Cancelled()

    def pause(self, seconds):
        deadline = self.clock() + seconds
        while self.clock() < deadline:
            self.check_cancel()
            self.sleep(min(.2, max(0, deadline - self.clock())))
        self.check_cancel()

    @contextmanager
    def lock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix(".lock").open("a+b") as stream:
            while True:
                self.check_cancel()
                stream.seek(0)
                try:
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    self.pause(.2)
            try:
                # Initialize only after ownership: another Windows process may
                # already hold byte zero when a new file still appears empty.
                stream.seek(0, 2)
                if stream.tell() == 0:
                    stream.write(b"0")
                    stream.flush()
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    def call(self, function, **kwargs):
        from .errors import ExecutionFailure
        dispatch_id = uuid.uuid4().hex
        queued = self.clock()
        maximum = self.policy.get("max_concurrency", 1)
        # A byte-based upper bound is conservative for unknown provider tokenizers.
        import json
        upper_bound = len(json.dumps({k: kwargs[k] for k in ("messages", "tools") if k in kwargs},
                                     ensure_ascii=False).encode("utf-8")) + 2048
        long = upper_bound > self.policy.get("long_context_threshold", 8192)
        long_maximum = self.policy.get("long_context_concurrency", 1)
        while True:
            self.check_cancel()
            with self.lock():
                state = read_json(self.path) if self.path.exists() else {}
                now = self.clock()
                leases = {k: v for k, v in state.get("leases", {}).items() if v["expires"] > now}
                state["leases"] = leases
                if self.credential_id in state.get("blocked_credentials", {}):
                    raise ExecutionFailure("Provider credential blocked after balance/quota failure; check account resources")
                # Different configurations cannot increase the caps of active requests.
                cap = min([maximum] + [v["cap"] for v in leases.values()])
                long_cap = min([long_maximum] + [v["long_cap"] for v in leases.values()])
                limit = min(cap, state.get("adaptive_cap", cap))
                available = len(leases) < limit and (not long or sum(v["long"] for v in leases.values()) < long_cap)
                delay = max(0, state.get("next_allowed", 0) - now)
                if available and not delay:
                    leases[dispatch_id] = {"expires": now + self.recovery_timeout + 30,
                        "long": long, "cap": maximum, "long_cap": long_maximum}
                    state["next_allowed"] = now + self.policy["minimum_interval"]
                    atomic_json(self.path, state)
                    break
            self.pause(min(.2, delay) if delay else .05)
        wait_seconds = self.clock() - queued
        if wait_seconds:
            self.emit({"kind": "request_wait", "seconds": wait_seconds,
                       "model": kwargs["model"], "dispatch_id": dispatch_id})
        self.emit({"kind": "request_dispatched", "model": kwargs["model"],
                   "dispatch_id": dispatch_id, "long_context": long,
                   "input_token_upper_bound": upper_bound, "queue_seconds": wait_seconds})
        started = self.clock()
        try:
            result = function(**kwargs)
        except Exception as exc:
            body = getattr(exc, "body", None) or {}
            error = body.get("error", body) if isinstance(body, dict) else {}
            code = str(error.get("code", ""))
            with self.lock():
                state = read_json(self.path)
                state.setdefault("leases", {}).pop(dispatch_id, None)
                if code in ("1113", "1308", "1310"):
                    state.setdefault("blocked_credentials", {})[self.credential_id] = code
                elif getattr(exc, "status_code", None) == 429:
                    level = min(state.get("overload_level", 0) + 1, 16)
                    state.update(overload_level=level, success_streak=0,
                                 adaptive_cap=max(1, limit // 2))
                    delay = min(self.policy["maximum_cooldown"],
                                self.policy["overload_cooldown"] * 2 ** (level - 1))
                    # Jitter applies to the shared pause, never retries a failed request.
                    import random
                    delay *= random.uniform(1, 1.1)
                    retry_after = getattr(getattr(exc, "response", None), "headers", {}).get("retry-after")
                    if retry_after:
                        try:
                            advertised = float(retry_after)
                        except ValueError:
                            try:
                                advertised = parsedate_to_datetime(retry_after).timestamp() - self.clock()
                            except (ValueError, TypeError, OverflowError):
                                advertised = 0
                        if math.isfinite(advertised):
                            delay = max(delay, advertised)
                    state["next_allowed"] = max(state.get("next_allowed", 0), self.clock() + delay)
                    self.emit({"kind": "request_cooldown", "seconds": delay,
                               "http_status": 429, "provider_code": code,
                               "model": kwargs["model"], "dispatch_id": dispatch_id,
                               "concurrency_limit": state["adaptive_cap"]})
                atomic_json(self.path, state)
            self.emit({"kind": "request_finished", "dispatch_id": dispatch_id,
                       "model": kwargs["model"], "api_seconds": self.clock() - started,
                       "status": "failed", "provider_code": code})
            raise
        else:
            with self.lock():
                state = read_json(self.path)
                state.setdefault("leases", {}).pop(dispatch_id, None)
                state["success_streak"] = state.get("success_streak", 0) + 1
                if state["success_streak"] >= self.policy["recovery_successes"]:
                    state["adaptive_cap"] = min(maximum, state.get("adaptive_cap", maximum) + 1)
                    state["overload_level"] = max(0, state.get("overload_level", 0) - 1)
                    state["success_streak"] = 0
                atomic_json(self.path, state)
            self.emit({"kind": "request_finished", "dispatch_id": dispatch_id,
                       "model": kwargs["model"], "api_seconds": self.clock() - started, "status": "completed"})
            return result


class ControlledClient:
    def __init__(self, client, config, endpoint, credential, cancel=None, emit=None, quota_group="default"):
        self.client, self.config = client, config
        # Quotas belong to accounts/models, not keys or policy configurations.
        self.scope = digest([endpoint.rstrip("/"), quota_group])
        self.credential_id = digest(credential)
        self.cancel, self.emit = cancel, emit
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        gate = RequestGate(ROOT / ".runtime/experiments/rate-limits" /
                           (digest([self.scope, kwargs["model"]]) + ".json"),
                           self.config["request_policy"], self.cancel, self.emit,
                           recovery_timeout=self.config["runtime"]["model_timeout"])
        gate.credential_id = self.credential_id
        return gate.call(self.client.chat.completions.create, **kwargs)

    def __getattr__(self, name):
        return getattr(self.client, name)
