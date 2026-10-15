"""Admission timing, shared ownership, and exact call counts without network."""
import json
import multiprocessing as mp
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from custom.experiment.errors import Cancelled
from custom.experiment.rate_limit import ControlledClient, RequestGate
from custom.experiment.selection import ROOT, load_config, read_json


POLICY = {"minimum_interval": 10, "overload_cooldown": 60,
          "maximum_cooldown": 300, "recovery_successes": 5}


class Clock:
    def __init__(self):
        self.value = 1000

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class Overloaded(Exception):
    status_code = 429


def shared_worker(path, ready, output):
    ready.wait()
    gate = RequestGate(path, {**POLICY, "minimum_interval": .03})
    def request(**kwargs):
        start = time.time()
        time.sleep(.05)
        return (start, time.time())
    output.put(gate.call(request, model="offline-test"))


class RateLimitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / ".runtime")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "gate.json"
        self.clock, self.events = Clock(), []
        self.gate = RequestGate(self.path, POLICY, clock=self.clock.now,
                                sleep=self.clock.sleep, emit=self.events.append)

    def test_interval_survives_client_recreation(self):
        request = Mock(return_value="ok")
        self.gate.call(request, model="test")
        another = RequestGate(self.path, POLICY, clock=self.clock.now, sleep=self.clock.sleep)
        another.call(request, model="test")
        self.assertAlmostEqual(self.clock.value, 1010)
        self.assertEqual(request.call_count, 2)

    def test_agent_and_judge_clients_share_gate_and_preserve_call_arguments(self):
        config = {"request_policy": POLICY, "runtime": {"model_timeout": 180}}
        actor, judge = Mock(), Mock()
        def gate(path, policy, cancel, emit, recovery_timeout):
            return RequestGate(path, policy, cancel, emit, clock=self.clock.now,
                               sleep=self.clock.sleep, recovery_timeout=recovery_timeout)
        with patch("custom.experiment.rate_limit.ROOT", Path(self.tmp.name)), \
             patch("custom.experiment.rate_limit.RequestGate", side_effect=gate):
            first = ControlledClient(actor, config, "offline://test", "synthetic-test-key")
            second = ControlledClient(judge, config, "offline://test", "synthetic-test-key")
            first.chat.completions.create(model="same-model", messages=[{"role": "user", "content": "actor"}])
            second.chat.completions.create(model="same-model", messages=[{"role": "user", "content": "judge"}])
            first.close()
            second.close()
        self.assertAlmostEqual(self.clock.value, 1010)
        actor.chat.completions.create.assert_called_once_with(model="same-model", messages=[{"role": "user", "content": "actor"}])
        judge.chat.completions.create.assert_called_once_with(model="same-model", messages=[{"role": "user", "content": "judge"}])
        actor.close.assert_called_once()
        judge.close.assert_called_once()

    def test_live_factory_records_key_and_keeps_failed_call_single(self):
        from custom.experiment.core import make_client
        config = load_config(ROOT / "config/experiment.json")
        client = Mock()
        client.chat.completions.create.side_effect = [Overloaded(), "ok"]
        def gate(path, policy, cancel, emit, recovery_timeout):
            return RequestGate(path, policy, cancel, emit, clock=self.clock.now,
                               sleep=self.clock.sleep, recovery_timeout=recovery_timeout)
        with patch("openai.OpenAI", return_value=client), \
             patch("custom.utils.model_config.api_key", return_value="synthetic-test-key"), \
             patch("custom.utils.model_config.base_url", return_value="offline://test"), \
             patch("custom.experiment.rate_limit.ROOT", Path(self.tmp.name)), \
             patch("custom.experiment.rate_limit.RequestGate", side_effect=gate):
            controlled = make_client(config, "strategy/stage/task/repeat", emit=self.events.append)
            with self.assertRaises(Overloaded):
                controlled.chat.completions.create(model="test")
            self.assertEqual(client.chat.completions.create.call_count, 1)
            self.assertEqual(controlled.chat.completions.create(model="test"), "ok")
        self.assertAlmostEqual(self.clock.value, 1060)
        self.assertTrue(all(e["request_key"] == "strategy/stage/task/repeat" for e in self.events))

    def test_overload_grows_cooldown_without_replaying_failed_calls(self):
        request = Mock(side_effect=Overloaded())
        for delay in (60, 120, 240, 300):
            with self.assertRaises(Overloaded):
                self.gate.call(request, model="test")
            state = read_json(self.path)
            self.assertAlmostEqual(state["next_allowed"] - self.clock.value, delay)
        self.assertEqual(request.call_count, 4)
        self.assertEqual(sum(e["kind"] == "request_dispatched" for e in self.events), 4)

    def test_five_judge_slots_still_issue_exactly_five_requests(self):
        request = Mock(side_effect=Overloaded())
        for slot in range(5):
            with self.assertRaises(Overloaded):
                self.gate.call(request, model="judge", slot=slot)
        self.assertEqual(request.call_count, 5)

    def test_recovery_requires_clean_successes(self):
        with self.assertRaises(Overloaded):
            self.gate.call(Mock(side_effect=Overloaded()), model="test")
        for _ in range(4):
            self.gate.call(Mock(return_value="ok"), model="test")
            state = read_json(self.path)
            self.assertEqual(state["overload_level"], 1)
            self.assertAlmostEqual(state["next_allowed"] - self.clock.value, 30)
        self.gate.call(Mock(return_value="ok"), model="test")
        state = read_json(self.path)
        self.assertEqual(state["overload_level"], 0)
        self.assertAlmostEqual(state["next_allowed"] - self.clock.value, 10)

    def test_retry_after_overrides_shorter_local_cooldown(self):
        error = Overloaded()
        error.response = Mock(headers={"retry-after": "180"})
        with self.assertRaises(Overloaded):
            self.gate.call(Mock(side_effect=error), model="test")
        self.assertAlmostEqual(read_json(self.path)["next_allowed"] - self.clock.value, 180)

    def test_dead_owner_leaves_lease_and_waits_before_next_dispatch(self):
        with self.assertRaises(SystemExit):
            self.gate.call(Mock(side_effect=SystemExit()), model="test")
        self.assertAlmostEqual(read_json(self.path)["next_allowed"], 1190)
        self.gate.call(Mock(return_value="ok"), model="test")
        self.assertAlmostEqual(self.clock.value, 1190)

    def test_cancelled_wait_does_not_send_request(self):
        self.gate.call(Mock(return_value="ok"), model="test")
        cancel = threading.Event()
        request = Mock()
        def sleep(seconds):
            self.clock.sleep(seconds)
            cancel.set()
        gate = RequestGate(self.path, POLICY, cancel=cancel, clock=self.clock.now, sleep=sleep)
        with self.assertRaises(Cancelled):
            gate.call(request, model="test")
        request.assert_not_called()

    def test_spawn_workers_share_single_admission(self):
        context = mp.get_context("spawn")
        ready, output = context.Event(), context.Queue()
        workers = [context.Process(target=shared_worker, args=(self.path, ready, output)) for _ in range(2)]
        try:
            for worker in workers:
                worker.start()
            ready.set()
            intervals = sorted(output.get(timeout=15) for _ in workers)
            self.assertGreaterEqual(intervals[1][0], intervals[0][1] + .02)
            for worker in workers:
                worker.join(10)
                self.assertEqual(worker.exitcode, 0)
        finally:
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                    worker.join(5)
            output.close()

    def test_invalid_policy_fails_configuration_validation(self):
        config = load_config(ROOT / "config/experiment.json")
        for replacement in ({}, {**POLICY, "minimum_interval": 0},
                            {**POLICY, "maximum_cooldown": 30}, {**POLICY, "recovery_successes": True}):
            path = Path(self.tmp.name) / "config.json"
            path.write_text(json.dumps({**config, "request_policy": replacement}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "request_policy"):
                load_config(path)
