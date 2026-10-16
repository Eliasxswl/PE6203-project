"""Offline acceptance of protocol, fault isolation, recovery, and Windows spawn."""
from copy import deepcopy
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from custom.experiment import adapters
from custom.experiment.__main__ import execute, specifications, validate
from custom.experiment.core import run_episode
from custom.experiment.errors import Cancelled, CheckpointFailure, ExecutionFailure, ToolMistake
from custom.experiment.results import Store, atomic_json, create, identity, writer_lock, aggregate_records, safe_error
from custom.experiment.runtime import LiveRuntime, OwnedJob, prepare_config, policy_for
from custom.experiment.selection import ROOT, STAGES, digest, fingerprints, load_config, read_json, tasks, select
from custom.experiment.testing import OfflineClient, OfflineRuntime, Response, Message, catalog_for


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / ".runtime")
        self.directory = Path(self.temporary.name)
        fixture = self.directory / "fixtures"
        fixture.mkdir()
        (fixture / "unchanged.txt").write_bytes(b"official fixture bytes\r\n")
        self.config = load_config(ROOT / "config/experiment.json")
        self.config.update(mode="offline", fixtures=str(fixture), strategies=["full_rewrite"],
                           task_count=10, agent_repeats=3)
        self.task_list = [{"idx": idx, "question": "Read the fixture and finish.",
                           "servers": {"@modelcontextprotocol/server-filesystem": ["read_file"]}}
                          for idx in range(10)]

    def tearDown(self):
        self.temporary.cleanup()

    def store(self, config=None):
        config = config or self.config
        path = create(config, self.task_list, fingerprints(config))
        self.addCleanup(self.remove_owned, path)
        return Store(path)

    def remove_owned(self, path):
        import shutil
        path = Path(path).resolve()
        self.assertTrue(path.is_relative_to(ROOT / ".runtime"))
        shutil.rmtree(path)

    def run_one(self, store, strategy="full_rewrite", repeat=0):
        available = specifications(store, self.config, self.task_list)
        spec = next((s for s in available if s["strategy"] == strategy and s["repeat"] == repeat), None)
        if spec is None:
            return
        run_episode(spec, store.apply)

    def test_selection_is_frozen_and_validated_without_reference_leakage(self):
        config = deepcopy(self.config)
        config["selection_file"] = str(self.directory / "selected.json")
        selected = select(config)
        self.assertEqual(len(selected), 10)
        self.assertEqual(selected, [t["idx"] for t in tasks(config)])
        self.assertTrue(all(set(t) == {"idx", "question", "servers"} for t in tasks(config)))
        with self.assertRaises(ValueError):
            select(config)
        payload = read_json(config["selection_file"])
        payload["samples"][1] = payload["samples"][0]
        atomic_json(config["selection_file"], payload)
        with self.assertRaises(ValueError):
            tasks(config)
        payload["samples"][1] = {"idx": 999999}
        atomic_json(config["selection_file"], payload)
        with self.assertRaises(ValueError):
            tasks(config)

    def test_unavailable_strategy_fails_before_clients(self):
        config = deepcopy(self.config)
        config["strategies"] = ["selective_patch"]
        with patch("custom.experiment.core.make_client") as client:
            with self.assertRaises(ValueError):
                validate(config)
            client.assert_not_called()

    def test_formal_plan_has_two_baselines_and_900_judge_slots(self):
        config = {**self.config, "strategies": ["no_update", "full_rewrite"]}
        store = self.store(config)
        rows = list(store.records["trajectories"].values())
        self.assertEqual(len(rows), 180)
        self.assertEqual(sum(len(row["judge_attempts"]) for row in rows), 900)
        with self.assertRaises(ValueError):
            adapters.load_plugins({**config, "strategies": ["upstream_baseline"]})

    def test_five_task_one_repeat_pilot_has_30_trajectories_and_150_slots(self):
        config = {**self.config, "task_count": 5, "agent_repeats": 1,
                  "strategies": ["no_update", "full_rewrite"]}
        task_list = self.task_list[:5]
        path = create(config, task_list, fingerprints(config))
        self.addCleanup(self.remove_owned, path)
        store = Store(path)
        rows = list(store.records["trajectories"].values())
        self.assertEqual(len(rows), 30)
        self.assertEqual(sum(len(row["judge_attempts"]) for row in rows), 150)
        self.assertEqual(len(specifications(store, config, task_list)), 2)
        for spec in specifications(store, config, task_list):
            run_episode(spec, store.apply)
        self.assertTrue(all(row["status"] == "completed"
                            for row in store.records["trajectories"].values()))

    def test_pilot_selection_size_and_repeat_validation(self):
        config = {**self.config, "task_count": 5,
                  "selection_file": str(self.directory / "selected.json")}
        self.assertEqual(len(select(config)), 5)
        self.assertEqual(len(tasks(config)), 5)
        for key in ("task_count", "agent_repeats"):
            for invalid in (0, -1, True, 1.5):
                path = self.directory / "invalid.json"
                atomic_json(path, {**config, key: invalid})
                with self.assertRaisesRegex(ValueError, key):
                    load_config(path)

    def test_model_connectivity_check_is_separate_from_formal_results(self):
        from custom.experiment.checks import check_models
        from unittest.mock import Mock
        client = Mock()
        client.chat.completions.create.side_effect = [
            Response(Message(tool_calls=[type("Call", (), {"id":"ping", "function":type("Function", (), {
                "name":"connectivity_ping", "arguments":"{}"})()})()])),
            Response(Message("pong")),
            Response(Message(json.dumps({"task_fulfillment":8,"grounding":8,"planning_and_efficiency":8})))
        ]
        with patch("custom.experiment.checks.make_client", return_value=client):
            result = check_models(self.config)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(client.chat.completions.create.call_count, 3)
        kwargs = client.chat.completions.create.call_args.kwargs
        if self.config.get("judge_thinking"):
            self.assertEqual(kwargs["extra_body"], {"thinking":{"type": self.config["judge_thinking"]}})
        else:
            self.assertNotIn("extra_body", kwargs)

    @unittest.skipUnless(os.name == "nt", "Windows import compatibility")
    def test_windows_loader_preserves_archived_imports(self):
        import shutil
        node = shutil.which("node")
        if not node:
            self.skipTest("Node is not installed")
        module = self.directory / "import-target.mjs"
        module.write_text("export default 17;", encoding="utf-8")
        code = "const m = await import(" + json.dumps(str(module)) + "); console.log(m.default);"
        output = subprocess.check_output([node, "--import",
            (ROOT / "src/custom/experiment/windows-loader.mjs").as_uri(),
            "--input-type=module", "-e", code], text=True)
        self.assertEqual(output.strip(), "17")

    def test_unverified_live_mapping_fails_without_constructing_clients(self):
        config = deepcopy(self.config)
        config["mode"] = "live"
        config["task_count"] = len(read_json(ROOT / config["selection_file"])["samples"])
        config["runtime"]["catalog_source"] = "evolution_overlay"
        with patch("custom.experiment.core.make_client") as client:
            with self.assertRaisesRegex(ValueError, "verified, explicit"):
                validate(config)
            client.assert_not_called()

    def test_public_description_overlay_does_not_update_stale_knowledge(self):
        metadata = self.directory / "evolution.json"
        atomic_json(metadata, {"@modelcontextprotocol/server-filesystem": {
            "mutation_type": "DESC", "read_file": {"tool": {"modified_description": "New official description"}}}})
        early = catalog_for(self.config, self.task_list, "original")
        config = deepcopy(self.config)
        config.update(mode="live")
        config["runtime"].update(catalog_source="evolution_overlay", metadata_verified=True, evolution_files={"original": [], "iter3": [str(metadata)], "iter5": [str(metadata)]})
        current = adapters.stage_catalog(early, config, "iter3")
        key = next(iter(early))
        self.assertEqual(current[key]["description"], "New official description")
        self.assertNotEqual(early[key]["description"], current[key]["description"])
        stale = adapters.update("no_update", adapters.semantic(early), early, current, {})
        self.assertEqual(stale["knowledge"][key]["description"], early[key]["description"])

    def test_strategies_keep_semantics_separate_from_routes(self):
        early = catalog_for(self.config, self.task_list, "original")
        evolved_config = {**self.config, "mock": {"rename_tools": True}}
        late = catalog_for(evolved_config, self.task_list, "iter3")
        initial = adapters.semantic(early)
        retained = adapters.update("no_update", initial, early, late, {})
        rewritten = adapters.update("full_rewrite", initial, early, late, {})
        self.assertEqual(retained["knowledge"], initial)
        self.assertNotEqual(rewritten["knowledge"], initial)
        retained["knowledge"][next(iter(initial))]["description"] = "changed copy"
        self.assertNotEqual(retained["knowledge"], initial)
        tools, _ = adapters.agent_tools(initial, late, ["@modelcontextprotocol/server-filesystem"])
        self.assertTrue(tools[0]["meta"]["benchmark_remote_name"].startswith("missing:"))

    def test_duplicate_and_invalid_api_names_keep_distinct_semantic_routes_for_judge(self):
        from custom.experiment.core import judge_prompt
        catalog = {server + "::read": {"server": server, "name": "read", "description": server,
                    "inputSchema": {}, "remote_name": "route:" + server} for server in ("one", "two")}
        catalog["one::invalid.name"] = {"server": "one", "name": "invalid.name", "description": "invalid API characters",
                                       "inputSchema": {}, "remote_name": "route:invalid"}
        tools, _ = adapters.agent_tools(adapters.semantic(catalog), catalog, ["one", "two"])
        self.assertEqual(len({tool["name"] for tool in tools}), 3)
        import re
        self.assertTrue(all(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", tool["name"]) for tool in tools))
        mapping = {tool["name"]: tool["meta"]["benchmark_semantic_identity"] for tool in tools}
        messages = [
                    {"role": "system", "content": "system"}, {"role": "user", "content": "question"},
                    {"role": "assistant", "tool_calls": [{"id": str(i), "function": {"name": tool["name"], "arguments": "{}"}}
                     for i, tool in enumerate(tools)]}]
        row = {"answer": "done", "trajectory_messages": messages, "tool_identities": mapping}
        before = deepcopy(messages)
        prompt = judge_prompt({"question": "question", "servers": {"one": [], "two": []}}, row, catalog, [0, 1, 2])
        self.assertIn('Call one::read(', prompt)
        self.assertIn('Call two::read(', prompt)
        self.assertEqual(row["trajectory_messages"], before)

    def test_plugin_source_change_is_in_the_resume_fingerprint(self):
        module = self.directory / "fixture_strategy_plugin.py"
        module.write_text("VALUE = 1\n", encoding="utf-8")
        sys.path.insert(0, str(self.directory))
        self.addCleanup(sys.path.remove, str(self.directory))
        self.addCleanup(sys.modules.pop, "fixture_strategy_plugin", None)
        config = {**self.config, "strategy_plugins": ["fixture_strategy_plugin"]}
        before = fingerprints(config)
        module.write_text("VALUE = 2\n", encoding="utf-8")
        self.assertNotEqual(before["code"], fingerprints(config)["code"])

    def test_role_one_contract_with_offline_fixture(self):
        name = "test_selective_patch"
        def implementation(knowledge, old_tools, new_tools, context):
            knowledge["new::tool"] = {"server": "new", "name": "tool", "description": "patched", "inputSchema": {}}
            return adapters.UpdateResult(knowledge, ["new::tool"], "Offline Role 1 contract fixture")
        adapters.register(name, implementation)
        self.addCleanup(adapters.REGISTRY.pop, name)
        result = adapters.update(name, {}, {}, {}, {})
        self.assertEqual(result["changed_entries"], ["new::tool"])
        self.assertEqual(result["knowledge"]["new::tool"]["description"], "patched")

    def test_round_boundary_uses_exact_cap_and_completion_is_not_exhaustion(self):
        from custom.agents.SimpleOpenAIAgent import ChatModel
        from types import SimpleNamespace
        client = OfflineClient(self.config, "budget")
        tool_reply = Response(Message(tool_calls=[SimpleNamespace(id="call", function=SimpleNamespace(name="read", arguments="{}"))]))
        with patch.object(client.chat.completions, "create", side_effect=[tool_reply, Response(Message("done"))]) as call:
            agent = ChatModel(client=client, model_name="offline", tools=[], tool_server_map={"read": "files"},
                              tool_caller=lambda *_: "read", max_round=2)
            _, _, finished, exceeded = agent.run_with_server("question")
        self.assertEqual(call.call_count, 2)
        self.assertTrue(finished)
        self.assertFalse(exceeded)
        with patch.object(client.chat.completions, "create", return_value=tool_reply) as call:
            agent = ChatModel(client=client, model_name="offline", tools=[], tool_server_map={"read": "files"},
                              tool_caller=lambda *_: "read", max_round=2)
            _, _, finished, exceeded = agent.run_with_server("question")
        self.assertEqual(call.call_count, 2)
        self.assertFalse(finished)
        self.assertTrue(exceeded)

    def test_manifest_and_rows_preserve_execution_protocol(self):
        from custom.experiment.results import PROTOCOL
        store = self.store()
        self.run_one(store)
        self.assertEqual(store.manifest["harness_protocol"], PROTOCOL)
        row = store.records["trajectories"][identity("full_rewrite", "original", 0, 0)]
        self.assertEqual(row["harness_protocol"], PROTOCOL)
        self.assertEqual(row["stop_reason"], "final_response")

    def test_one_failed_run_is_recorded_and_not_judged_or_retried(self):
        key = identity("full_rewrite", "original", 0, 0)
        self.config["mock"] = {"fail_trajectories": [key], "judge_fail_slots": [0, 2]}
        store = self.store()
        self.run_one(store)
        bad = store.records["trajectories"][key]
        good = store.records["trajectories"][identity("full_rewrite", "original", 1, 0)]
        self.assertEqual(bad["status"], "execution_failed")
        self.assertEqual(len(bad["agent_attempts"]), 1)
        self.assertTrue(all(a["status"] == "not_attempted" for a in bad["judge_attempts"]))
        self.assertEqual(good["status"], "completed")
        self.assertEqual([a["status"] for a in good["judge_attempts"]], ["failed", "completed", "failed", "completed", "completed"])
        self.assertEqual(good["score"]["task_fulfillment"], 8)
        self.assertGreater(len(json.dumps(good["raw_tool_trace"][0]["response"])), 900)
        visible = next(m["content"] for m in good["trajectory_messages"] if m["role"] == "tool")
        self.assertGreater(len(json.loads(visible)["content"][0]["text"]), 900)
        self.assertFalse(json.loads(visible)["isError"])
        before = deepcopy(store.records["trajectories"])
        self.run_one(store)
        self.assertEqual(store.records["trajectories"], before)

    def test_tool_semantic_failure_remains_scored(self):
        self.config.update(strategies=["no_update", "full_rewrite"], mock={"rename_tools": True})
        store = self.store()
        self.run_one(store, "no_update")
        self.run_one(store, "full_rewrite")
        stale = store.records["trajectories"][identity("no_update", "iter3", 0, 0)]
        fresh = store.records["trajectories"][identity("full_rewrite", "iter3", 0, 0)]
        self.assertEqual(stale["status"], "completed")
        self.assertEqual(stale["score"]["task_fulfillment"], 3)
        self.assertEqual(fresh["score"]["task_fulfillment"], 8)

    def test_rpc_parameter_errors_are_agent_feedback_and_transport_errors_exclude_execution(self):
        from mcp.shared.exceptions import McpError
        from mcp.types import ErrorData
        from custom.agents.SimpleOpenAIAgent import ChatModel
        runtime = LiveRuntime(self.config, "original", ["one"])
        runtime.url = "offline://must-not-connect"
        with patch.object(runtime, "_session_request", new_callable=AsyncMock) as request:
            with self.assertRaises(ToolMistake):
                runtime.call("route", [])
            request.assert_not_called()
        error = McpError(ErrorData(code=-32602, message="Obsolete parameter", data={"field": "old_name"}))
        catalog = {"one::read": {"server": "one", "name": "read", "description": "Read",
                    "inputSchema": {}, "remote_name": "route"}}
        tools, routing = adapters.agent_tools(adapters.semantic(catalog), catalog, ["one"])
        with patch.object(runtime, "_session_request", new_callable=AsyncMock, side_effect=error):
            agent = ChatModel(model_name="offline", client=OfflineClient(self.config, "rpc"), tools=tools,
                              tool_server_map=routing, tool_caller=runtime.call)
            answer, messages, finished, exceeded = agent.run_with_server("question")
        self.assertIsNone(agent.execution_error)
        self.assertTrue(finished)
        self.assertEqual(agent.raw_tool_trace[0]["protocol_error"]["code"], -32602)
        with patch.object(runtime, "_session_request", new_callable=AsyncMock, side_effect=TimeoutError("transport unavailable")):
            with self.assertRaises(ExecutionFailure) as raised:
                runtime.call("route", {})
        saved = safe_error(raised.exception)
        self.assertTrue(saved["unknown_outcome"])
        self.assertEqual(saved["cause"]["type"], "TimeoutError")

    def test_model_and_judge_timeouts_are_unknown_without_replay_or_top_up(self):
        store = self.store()
        spec = specifications(store, self.config, self.task_list)[0]
        target = identity("full_rewrite", "original", 0, 0)
        original = OfflineClient.create
        def timeout(client, **kwargs):
            if client.key == target:
                raise TimeoutError("Injected model timeout")
            if "tools" not in kwargs:
                raise TimeoutError("Injected judge timeout")
            return original(client, **kwargs)
        with patch.object(OfflineClient, "create", timeout):
            run_episode(spec, store.apply)
        bad = store.records["trajectories"][target]
        self.assertEqual(bad["agent_attempts"][0]["status"], "outcome_unknown")
        good_agent = store.records["trajectories"][identity("full_rewrite", "original", 1, 0)]
        self.assertTrue(all(a["status"] == "outcome_unknown" for a in good_agent["judge_attempts"]))
        self.assertIsNone(good_agent["score"])
        with patch("custom.experiment.core.make_client") as client:
            self.run_one(store)
            client.assert_not_called()

    def test_interrupted_agent_is_unknown_and_remaining_tasks_resume(self):
        key = identity("full_rewrite", "original", 0, 0)
        self.config["mock"] = {"interrupt_trajectories": [key]}
        store = self.store()
        with self.assertRaises(Cancelled):
            self.run_one(store)
        store = Store(store.path)
        store.recover(reason="test_interruption")
        self.assertEqual(store.records["trajectories"][key]["status"], "outcome_unknown")
        self.run_one(store)
        self.assertEqual(len(store.records["trajectories"][key]["agent_attempts"]), 1)
        self.assertEqual(store.records["trajectories"][identity("full_rewrite", "original", 1, 0)]["status"], "completed")

    def test_partial_judge_resume_skips_completed_failed_and_unknown_slots(self):
        store = self.store()
        self.run_one(store)
        key = identity("full_rewrite", "original", 0, 0)
        row = store.records["trajectories"][key]
        row.update(status="running", score=None)
        row["judge_attempts"][1].update(status="failed", error={"type": "test"})
        row["judge_attempts"][2]["status"] = "started"
        row["judge_attempts"][3] = {"slot": 3, "status": "pending"}
        row["judge_attempts"][4] = {"slot": 4, "status": "pending"}
        agent_before = deepcopy(row["agent_attempts"])
        store.save()
        store = Store(store.path)
        store.recover()
        with patch("custom.experiment.testing.OfflineClient.create", autospec=True, return_value=Response(Message(json.dumps({s: 7 for s in ("task_fulfillment", "grounding", "planning_and_efficiency")})))) as call:
            self.run_one(store)
        row = store.records["trajectories"][key]
        self.assertEqual(call.call_count, 2)
        self.assertEqual(row["agent_attempts"], agent_before)
        self.assertEqual(row["judge_attempts"][2]["status"], "outcome_unknown")
        self.assertAlmostEqual(row["score"]["task_fulfillment"], 22 / 3)

    def test_checkpoint_failure_never_dispatches_a_request(self):
        store = self.store()
        spec = specifications(store, self.config, self.task_list)[0]
        def fail(event):
            if event["kind"] == "trajectory":
                raise OSError("disk failure")
            store.apply(event)
        with patch("custom.experiment.core.make_client") as client:
            with self.assertRaises(CheckpointFailure):
                run_episode(spec, fail)
            client.assert_not_called()

    def test_private_fixture_and_backend_state_reset(self):
        original = (Path(self.config["fixtures"]) / "unchanged.txt").read_bytes()
        for _ in range(2):
            with OfflineRuntime(self.config, "original", self.task_list[0]["servers"], task_list=self.task_list) as runtime:
                self.assertEqual((runtime.workspace / "unchanged.txt").read_bytes(), original)
                runtime.call("mock:read", {})
                runtime.call("mock:read", {})
                self.assertEqual(read_json(runtime.directory / "state.json")["calls"], 2)
                (runtime.workspace / "unchanged.txt").write_text("mutated", encoding="utf-8")
        self.assertEqual((Path(self.config["fixtures"]) / "unchanged.txt").read_bytes(), original)
        with self.assertRaises(ExecutionFailure):
            policy_for("unknown_external_database", self.config)

    def test_taskmanager_state_is_accessible_to_filesystem_inside_the_same_trajectory(self):
        directory = self.directory / "owned-runtime"
        directory.mkdir()
        entry = self.directory / "frozen-entry.js"
        entry.write_text("// Offline launcher fixture; never executed.\n", encoding="utf-8")
        local = self.directory / "local.json"
        servers = ["@modelcontextprotocol/server-filesystem", "@kazuph/mcp-taskmanager"]
        atomic_json(local, {"mcpServers": {server: {"command": "node", "args": [str(entry)]} for server in servers}})
        config = deepcopy(self.config)
        config["runtime"]["configs"]["original"] = str(local)
        path, workspace = prepare_config(config, "original", servers, directory)
        prepared = read_json(path)["mcpServers"]
        state = Path(prepared[servers[1]]["env"]["TASK_MANAGER_FILE_PATH"])
        self.assertTrue(state.is_relative_to(workspace))
        self.assertEqual(Path(prepared[servers[0]]["args"][-1]), workspace)

    @unittest.skipUnless(os.name == "nt", "Windows sharing violations")
    def test_transient_windows_replace_retries_only_the_same_checkpoint(self):
        target = self.directory / "checkpoint.json"
        error = PermissionError("Injected sharing violation")
        error.winerror = 32
        original = os.replace
        failures = [error, error]
        def replace_file(source, destination):
            if failures:
                raise failures.pop()
            return original(source, destination)
        with patch("custom.experiment.results.os.replace", side_effect=replace_file) as replace:
            atomic_json(target, {"safe": True})
        self.assertEqual(replace.call_count, 3)
        self.assertEqual(read_json(target), {"safe": True})

    def test_shared_early_knowledge_is_identical_and_defensively_copied(self):
        self.config["strategies"] = ["no_update", "full_rewrite"]
        store = self.store()
        frozen_specs = specifications(store, self.config, self.task_list)
        frozen = deepcopy(store.records["initial_snapshot"])
        self.run_one(store, "no_update")
        self.run_one(store, "full_rewrite")
        first = store.records["episodes"]["no_update/0"]["stages"]["original"]["knowledge"]
        second = store.records["episodes"]["full_rewrite/0"]["stages"]["original"]["knowledge"]
        self.assertEqual(first, second)
        first[next(iter(first))]["description"] = "mutated copy"
        self.assertEqual(store.records["initial_snapshot"], frozen)
        self.assertNotEqual(first, second)

    def test_parent_hard_crash_releases_writer_and_resume_does_not_replay(self):
        store = self.store()
        payload = self.directory / "crash-input.json"
        atomic_json(payload, {"config": self.config, "tasks": self.task_list, "experiment": str(store.path)})
        code = '''
import json, os, sys
from custom.experiment.__main__ import execute
from custom.experiment.results import Store
payload = json.load(open(sys.argv[1], encoding="utf-8"))
original = Store.apply
def apply(self, event):
    original(self, event)
    if event["kind"] == "trajectory" and any(a["status"] == "started" for a in event["record"]["agent_attempts"]):
        os._exit(24)
Store.apply = apply
execute(payload["config"], payload["tasks"], payload["experiment"])
'''
        crashed = subprocess.run([sys.executable, "-c", code, str(payload)], cwd=ROOT,
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(crashed.returncode, 24, crashed.stderr)
        loaded = Store(store.path)
        self.assertEqual(loaded.records["status"], "running")
        first = identity("full_rewrite", "original", 0, 0)
        self.assertEqual(loaded.records["trajectories"][first]["agent_attempts"][0]["status"], "started")
        # Reclaim only the fake runtime proven by this interrupted row's prompt.
        import re
        prompt = loaded.records["trajectories"][first]["trajectory_messages"][0]["content"]
        workspace = Path(re.search(r'workspace prefix "([^"]+)"', prompt).group(1))
        self.addCleanup(self.remove_owned, workspace.parent)
        execute(self.config, self.task_list, store.path)
        recovered = Store(store.path)
        self.assertEqual(recovered.records["trajectories"][first]["status"], "outcome_unknown")
        self.assertEqual(len(recovered.records["trajectories"][first]["agent_attempts"]), 1)
        self.assertTrue(any(e["kind"] == "unclean_stop_detected" for e in recovered.records["events"]))
        self.assertEqual(recovered.records["trajectories"][identity("full_rewrite", "iter5", 9, 2)]["status"], "completed")

    def test_single_writer_redaction_and_resume_fingerprint_guard(self):
        store = self.store()
        with writer_lock(store.path):
            with self.assertRaises(ValueError):
                with writer_lock(store.path):
                    pass
        with patch.dict(os.environ, {"BIGMODEL_API_KEY": "test-private-secret-value"}):
            store.event("test", error="Bearer test-private-secret-value", api_key="another-private-value")
        text = (store.path / "records.json").read_text(encoding="utf-8")
        self.assertNotIn("test-private-secret-value", text)
        self.assertNotIn("another-private-value", text)
        changed = {**self.config, "agent_temperature": .3}
        with self.assertRaises(ValueError):
            execute(changed, self.task_list, store.path)

    def test_ecs_uses_upstream_population_stdev_and_missing_stages_are_excluded(self):
        store = self.store()
        for stage, value in zip(STAGES, [8, 5, 2]):
            row = store.records["trajectories"][identity("full_rewrite", stage, 0, 0)]
            row.update(status="completed", score={s: value for s in ("task_fulfillment", "grounding", "planning_and_efficiency")})
        aggregate = aggregate_records(store.records["trajectories"])
        self.assertEqual(aggregate["ecs"]["full_rewrite"]["matched_task_repeats"], 1)
        self.assertAlmostEqual(aggregate["ecs"]["full_rewrite"]["value"], 5 - statistics.pstdev([8, 5, 2]))
        self.assertEqual(aggregate["groups"]["full_rewrite/original"]["valid"], 1)

    def test_serial_spawn_equivalence_and_no_calls_on_completed_resume(self):
        serial = self.store()
        parallel = self.store()
        parallel.manifest["execution"] = {"parallel": True, "workers": 2}
        atomic_json(parallel.path / "experiment.json", parallel.manifest)
        _, serial_aggregate = execute(self.config, self.task_list, serial.path)
        _, parallel_aggregate = execute(self.config, self.task_list, parallel.path, True, 2)
        self.assertEqual(serial_aggregate, parallel_aggregate)
        self.assertEqual(sum(group["valid"] for group in serial_aggregate["groups"].values()), 90)
        with patch("custom.experiment.core.make_client") as client:
            execute(self.config, self.task_list, serial.path)
            client.assert_not_called()
        loaded = Store(parallel.path)
        self.assertEqual(len(loaded.records["trajectories"]), 90)
        self.assertTrue(all(len(row["judge_attempts"]) == 5 for row in loaded.records["trajectories"].values()))

    def test_one_episode_uses_multiple_task_workers_and_preserves_private_knowledge(self):
        self.config.update(task_count=3, agent_repeats=1)
        self.task_list = self.task_list[:3]
        store = self.store()
        store.manifest["execution"] = {"parallel": True, "workers": 2}
        atomic_json(store.path / "experiment.json", store.manifest)
        execute(self.config, self.task_list, store.path, True, 2)
        loaded = Store(store.path)
        early = [r for r in loaded.records["trajectories"].values() if r["identity"]["stage"] == "original"]
        self.assertEqual(len({r["agent_worker_pid"] for r in early}), 2)
        self.assertEqual(len({r["knowledge_sha256"] for r in early}), 1)
        self.assertTrue(all(r["status"] == "completed" for r in loaded.records["trajectories"].values()))
        self.assertEqual(sum(len(r["judge_attempts"]) for r in loaded.records["trajectories"].values()), 45)

    def test_parallel_policy_rejects_shared_web_writes_and_undeclared_resources(self):
        config = deepcopy(self.config)
        config["runtime"]["policies"]["shared-web"] = {"kind": "workspace", "reviewed": True,
            "reason": "Test fixture", "concurrency": "exclusive", "external_mutation": True,
            "shared_resources": ["website:test"]}
        with self.assertRaisesRegex(ExecutionFailure, "External writes"):
            policy_for("shared-web", config)
        config["mode"] = "live"
        config["runtime"]["policies"]["shared-web"].pop("external_mutation")
        config["runtime"]["policies"]["shared-web"].pop("shared_resources")
        with self.assertRaisesRegex(ValueError, "shared_resources"):
            execute(config, [{"idx": 0, "servers": {"shared-web": []}}], parallel=True, workers=2)

    def test_spawn_worker_crash_is_local_and_unstarted_work_remains_resumable(self):
        key = identity("full_rewrite", "original", 0, 0)
        self.config["mock"] = {"worker_crash_on": [key]}
        store = self.store()
        store.manifest["execution"] = {"parallel": True, "workers": 2}
        atomic_json(store.path / "experiment.json", store.manifest)
        execute(self.config, self.task_list, store.path, True, 2)
        loaded = Store(store.path)
        self.assertEqual(loaded.records["trajectories"][key]["status"], "outcome_unknown")
        self.assertTrue(any(e["kind"] == "worker_crash" for e in loaded.records["events"]))
        self.assertEqual(loaded.records["trajectories"][identity("full_rewrite", "iter5", 9, 2)]["status"], "completed")
        execute(self.config, self.task_list, store.path, True, 2)
        loaded = Store(store.path)
        self.assertEqual(loaded.records["trajectories"][identity("full_rewrite", "original", 1, 0)]["status"], "completed")
        self.assertEqual(len(loaded.records["trajectories"][key]["agent_attempts"]), 1)

    @unittest.skipUnless(os.name == "nt", "Windows Job Object ownership")
    def test_owned_job_kills_its_process_without_stopping_unrelated_process(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], creationflags=subprocess.CREATE_NO_WINDOW)
        unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            job = OwnedJob()
            job.assign(child.pid)
            job.close()
            child.wait(timeout=5)
            self.assertIsNone(unrelated.poll())
        finally:
            for process in (child, unrelated):
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
