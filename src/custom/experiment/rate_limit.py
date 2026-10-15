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
            stream.seek(0, 2)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
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
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    def call(self, function, **kwargs):
        with self.lock():
            state = read_json(self.path) if self.path.exists() else {
                "next_allowed": 0, "overload_level": 0, "success_streak": 0}
            delay = max(0, state["next_allowed"] - self.clock())
            dispatch_id = uuid.uuid4().hex
            if delay:
                self.emit({"kind": "request_wait", "seconds": delay,
                           "model": kwargs["model"], "dispatch_id": dispatch_id})
                self.pause(delay)
            self.check_cancel()
            # A crashed owner leaves a conservative lease for an in-flight request.
            state["next_allowed"] = self.clock() + self.recovery_timeout + self.policy["minimum_interval"]
            atomic_json(self.path, state)
            self.emit({"kind": "request_dispatched", "model": kwargs["model"],
                       "dispatch_id": dispatch_id})
            try:
                response = function(**kwargs)
            except Exception as exc:
                if getattr(exc, "status_code", None) == 429:
                    state["overload_level"] = min(state["overload_level"] + 1, 16)
                    state["success_streak"] = 0
                    delay = min(self.policy["maximum_cooldown"],
                                self.policy["overload_cooldown"] * 2 ** (state["overload_level"] - 1))
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
                    self.emit({"kind": "request_cooldown", "seconds": delay,
                               "http_status": 429, "model": kwargs["model"], "dispatch_id": dispatch_id})
                else:
                    delay = self.policy["minimum_interval"]
                state["next_allowed"] = self.clock() + delay
                atomic_json(self.path, state)
                raise
            else:
                state["success_streak"] += 1
                if state["success_streak"] >= self.policy["recovery_successes"]:
                    state["overload_level"] = max(0, state["overload_level"] - 1)
                    state["success_streak"] = 0
                delay = self.policy["minimum_interval"]
                if state["overload_level"]:
                    delay = max(delay, min(self.policy["maximum_cooldown"],
                        self.policy["overload_cooldown"] * 2 ** (state["overload_level"] - 1)) / 2)
                state["next_allowed"] = self.clock() + delay
                atomic_json(self.path, state)
                return response


class ControlledClient:
    def __init__(self, client, config, endpoint, credential, cancel=None, emit=None):
        self.client, self.config = client, config
        # Hash the credential only for local scope; never store the credential itself.
        self.scope = digest([endpoint, digest(credential), config["request_policy"]])
        self.cancel, self.emit = cancel, emit
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        gate = RequestGate(ROOT / ".runtime/experiments/rate-limits" /
                           (digest([self.scope, kwargs["model"]]) + ".json"),
                           self.config["request_policy"], self.cancel, self.emit,
                           recovery_timeout=self.config["runtime"]["model_timeout"])
        return gate.call(self.client.chat.completions.create, **kwargs)

    def __getattr__(self, name):
        return getattr(self.client, name)
