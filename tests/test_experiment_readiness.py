"""Offline checks for member contracts, paired metrics and preparation evidence."""
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from custom.experiment import adapters
from custom.experiment.__main__ import main
from custom.experiment.checks import check_judge
from custom.experiment.evidence import archived_tasks, catalog_diff, catalog_evidence, validate_annotations
from custom.experiment.readiness import environment, preparation
from custom.experiment.results import (SCORES, Store, aggregate_records, atomic_json, completion,
                                       create, identity, update_costs, cohort_scores)
from custom.experiment.selection import ROOT, STAGES, fingerprints, load_config, read_json, tasks
from custom.experiment.testing import Message, Response


def tool(name="read", description="Read", schema=None):
    return {"server": "files", "name": name, "description": description,
            "inputSchema": schema or {"type": "object", "properties": {}}, "remote_name": "transient-route"}


def label(cohort="retention", types=None, status="confirmed"):
    return {"status": status, "reviewed_by": "Role 3",
            "transitions": {s: {"cohort": cohort, "change_types": types or [],
                                 "rationale": "Reviewed required tool definitions"} for s in STAGES[1:]}}


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".runtime")
        self.directory = Path(self.temp.name)
        self.config = load_config(ROOT / "config/experiment.json")
        self.config["mode"] = "offline"

    def tearDown(self):
        self.temp.cleanup()

    def store(self):
        path = create(self.config, tasks(self.config), fingerprints(self.config))
        self.addCleanup(self.remove_owned, path)
        return Store(path)

    def remove_owned(self, path):
        import shutil
        self.assertTrue(path.resolve().is_relative_to(ROOT / ".runtime"))
        shutil.rmtree(path)

    def test_baselines_report_zero_and_legacy_plugins_report_unknown(self):
        catalog = {"files::read": tool()}
        for strategy in ("no_update", "full_rewrite"):
            result = adapters.update(strategy, adapters.semantic(catalog), catalog, catalog, {})
            self.assertEqual(result["api_calls"], 0)
            self.assertEqual(result["input_tokens"], 0)
            self.assertEqual(result["api_cost"], 0)
        name = "readiness_legacy"
        adapters.register(name, lambda *_: adapters.UpdateResult({}, [], "legacy"))
        self.addCleanup(adapters.REGISTRY.pop, name)
        result = adapters.update(name, {}, {}, {}, {})
        self.assertIsNone(result["api_calls"])
        self.assertIsNone(result["api_cost"])

    def test_plugin_usage_round_trips_and_rejects_bad_or_unpriced_costs(self):
        name = "readiness_usage"
        result = adapters.UpdateResult({}, [], "metered", api_calls=2, input_tokens=15, output_tokens=6,
                                       api_cost=.01, cost_currency="CNY", cost_basis="Provider invoice")
        adapters.register(name, lambda *_: result)
        self.addCleanup(adapters.REGISTRY.pop, name)
        self.assertEqual(adapters.update(name, {}, {}, {}, {})["input_tokens"], 15)
        for field, value in (("api_calls", True), ("api_calls", -1), ("input_tokens", 1.5),
                             ("api_cost", float("nan")), ("cost_currency", None)):
            original = getattr(result, field)
            setattr(result, field, value)
            with self.assertRaises(ValueError):
                adapters.update(name, {}, {}, {}, {})
            setattr(result, field, original)

    def test_update_costs_count_transitions_once_and_keep_unknowns_and_currencies(self):
        episodes = {"patch/0": {"stages": {"iter3": {"status": "ready", "api_calls": 2,
                     "api_cost": 1, "cost_currency": "CNY", "cost_basis": "invoice"}}},
                    "patch/1": {"stages": {"iter3": {"status": "ready", "api_cost": 2,
                     "cost_currency": "USD", "cost_basis": "invoice"}}}}
        costs = update_costs(episodes)
        self.assertEqual(costs["patch/iter3"]["api_calls"], {"reported": 1, "unreported": 1, "total_reported": 2})
        self.assertIsNone(costs["patch/iter3"]["api_cost"]["total_reported"])
        self.assertTrue(costs["patch/iter3"]["api_cost"]["mixed_currencies"])
        self.assertIsNone(costs["patch/iter5"]["api_calls"]["total_reported"])

    def test_diff_ignores_routes_and_separates_nested_schema_descriptions(self):
        old = {"files::read": tool(schema={"type": "object", "properties": {
            "sources": {"type": "array", "items": {"type": "object", "properties": {
                "description": {"type": "string", "description": "Old text"}}}}}})}
        new = deepcopy(old)
        new["files::read"]["remote_name"] = "other-route"
        self.assertEqual(catalog_diff(old, new)["parameter"], [])
        child = new["files::read"]["inputSchema"]["properties"]["sources"]["items"]["properties"]["description"]
        child["description"] = "New text"
        diff = catalog_diff(old, new)
        self.assertEqual(diff["description"], ["files::read"])
        self.assertEqual(diff["parameter"], [])
        child["type"] = "integer"
        self.assertEqual(catalog_diff(old, new)["parameter"], ["files::read"])
        new["files::extra"] = tool("extra")
        del new["files::read"]
        self.assertEqual(catalog_diff(old, new)["added"], ["files::extra"])
        self.assertEqual(catalog_diff(old, new)["removed"], ["files::read"])

    def test_literal_json_values_are_not_schema_annotations(self):
        old = {"files::read": tool(schema={"const": {"description": "a"}})}
        new = deepcopy(old)
        new["files::read"]["inputSchema"]["const"]["description"] = "b"
        diff = catalog_diff(old, new)
        self.assertEqual(diff["parameter"], ["files::read"])
        self.assertEqual(diff["description"], [])

    def test_classification_is_validated_and_never_reaches_agent_tasks(self):
        path = self.directory / "selection.json"
        selection = read_json(ROOT / self.config["selection_file"])
        selection["samples"][0]["classification"] = label()
        atomic_json(path, selection)
        self.config["selection_file"] = str(path)
        self.assertTrue(all(set(t) == {"idx", "question", "servers"} for t in tasks(self.config)))
        for mutate in (lambda v: v.pop("reviewed_by"),
                       lambda v: v["transitions"]["iter3"].update(change_types=["parameter"]),
                       lambda v: v.update(transitions={"original": {}})):
            invalid = deepcopy(selection)
            mutate(invalid["samples"][0]["classification"])
            with self.assertRaises(ValueError):
                validate_annotations(invalid)

    def rows_and_evidence(self):
        rows, episodes = {}, {}
        task_list = [{"idx": idx, "servers": {"files": ["read"]}, "question": "Read"} for idx in (1, 2)]
        for strategy in ("no_update", "full_rewrite"):
            stages = {stage: {"status": "ready", "catalog": {"files::read": tool()}, "errors": {}} for stage in STAGES}
            episodes[strategy + "/0"] = {"stages": stages}
            for stage_index, stage in enumerate(STAGES):
                for idx in (1, 2):
                    score = (8 if idx == 1 else 2) + (1 if strategy == "full_rewrite" else 0)
                    key = identity(strategy, stage, idx, 0)
                    rows[key] = {"identity": {"strategy": strategy, "stage": stage, "task_id": idx, "repeat": 0},
                        "status": "completed", "score": {s: score for s in SCORES},
                        "judge_attempts": [{"status": "completed"} for _ in range(5)]}
        return rows, episodes, task_list

    def test_ecs_strategy_comparison_uses_one_cohort_across_all_versions(self):
        rows, _, _ = self.rows_and_evidence()
        rows[identity("full_rewrite", "iter3", 2, 0)].update(score=None, score_exclusion_reason="no_valid_judge_attempts")
        result = aggregate_records(rows)
        self.assertEqual(result["ecs"]["no_update"]["matched_task_repeats"], 2)
        self.assertEqual(result["ecs"]["full_rewrite"]["matched_task_repeats"], 1)
        self.assertEqual(result["paired_ecs"]["identities"], [[1, 0]])
        self.assertEqual(result["paired_ecs"]["values"], {"full_rewrite": 9, "no_update": 8})
        self.assertEqual(result["paired_ecs"]["excluded"][0]["missing"][0]["reason"], "no_valid_judge_attempts")

    def test_cohorts_require_confirmation_real_evidence_and_shared_scores(self):
        rows, episodes, task_list = self.rows_and_evidence()
        labels = {"1": label(), "2": label()}
        evidence = catalog_evidence({"episodes": episodes}, task_list)
        result = cohort_scores(rows, labels, evidence)
        self.assertEqual(result["transitions"]["iter3"]["retention"]["matched"], 2)
        deltas = result["transitions"]["iter3"]["retention"]["mean_tf_delta_vs_no_update"]
        self.assertEqual(deltas, {"no_update": 0, "full_rewrite": 1})
        labels["1"]["status"] = "draft"
        episodes["full_rewrite/0"]["stages"]["iter3"]["catalog"]["files::read"]["description"] = "Changed"
        evidence = catalog_evidence({"episodes": episodes}, task_list)
        result = cohort_scores(rows, labels, evidence)
        self.assertEqual(result["transitions"]["iter3"]["retention"]["matched"], 0)
        reasons = {r["reason"] for ex in result["transitions"]["iter3"]["excluded"] for r in ex["reasons"]}
        self.assertIn("classification_not_confirmed", reasons)
        self.assertIn("classification_conflicts_with_catalog", reasons)
        self.assertEqual(cohort_scores(rows, {}, evidence)["status"], "not_configured")

    def test_failed_or_missing_catalog_never_suggests_retention(self):
        _, episodes, task_list = self.rows_and_evidence()
        after = episodes["no_update/0"]["stages"]["iter3"]
        after.update(catalog={}, errors={"files": {"type": "Timeout"}})
        report = catalog_evidence({"episodes": episodes}, task_list)
        task = report["transitions"]["no_update/0"]["iter3"]["tasks"]["1"]
        self.assertEqual(task["status"], "unavailable")
        self.assertIsNone(task["suggested_change_types"])

    def test_late_classification_is_relative_to_early_even_without_middle_to_late_changes(self):
        rows, episodes, task_list = self.rows_and_evidence()
        for episode in episodes.values():
            for stage in STAGES[1:]:
                episode["stages"][stage]["catalog"]["files::read"]["description"] = "Changed once"
        labels = {str(idx): label("changed", ["description"]) for idx in (1, 2)}
        report = catalog_evidence({"episodes": episodes}, task_list)
        self.assertEqual(report["reference_stage"], "original")
        self.assertEqual(report["transitions"]["no_update/0"]["iter5"]["tasks"]["1"]["suggested_change_types"],
                         ["description"])
        # No previous-version TF is needed for a same-version comparison.
        rows[identity("full_rewrite", "iter3", 1, 0)]["score"] = None
        rows[identity("full_rewrite", "original", 1, 0)]["score"] = None
        result = cohort_scores(rows, labels, report)
        late = result["transitions"]["iter5"]["changed"]
        self.assertEqual(late["matched"], 2)
        self.assertEqual(late["mean_tf_delta_vs_no_update"], {"no_update": 0, "full_rewrite": 1})
        rows[identity("no_update", "iter5", 1, 0)]["score"] = None
        result = cohort_scores(rows, labels, report)
        self.assertEqual(result["transitions"]["iter5"]["changed"]["identities"], [[2, 0]])

    def test_recovery_without_no_update_reports_missing_comparator(self):
        rows, episodes, task_list = self.rows_and_evidence()
        rows = {key: row for key, row in rows.items() if row["identity"]["strategy"] != "no_update"}
        result = cohort_scores(rows, {"1": label(), "2": label()},
                               catalog_evidence({"episodes": episodes}, task_list))
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["transitions"]["iter5"]["retention"]["matched"], 0)
        self.assertIn("comparison_strategy_not_configured", {
            reason["reason"] for item in result["transitions"]["iter5"]["excluded"] for reason in item["reasons"]})

    def test_manifest_freezes_annotations_and_runtime_versions(self):
        selection = read_json(ROOT / self.config["selection_file"])
        selection["samples"][0]["classification"] = label()
        path = self.directory / "selection.json"
        atomic_json(path, selection)
        self.config["selection_file"] = str(path)
        store = self.store()
        selection["samples"][0].pop("classification")
        atomic_json(path, selection)
        idx = str(store.manifest["selected_ids"][0])
        self.assertEqual(store.manifest["task_annotations"][idx]["status"], "confirmed")
        self.assertIn("version", store.manifest["environment"]["python"])
        self.assertEqual(store.manifest["environment"]["tool_bundles"]["original"]["status"], "not_used_offline")
        self.assertEqual(store.manifest["task_definitions"], tasks(self.config))

    def test_archive_hashes_are_actual_bytes_and_missing_is_explicit(self):
        downloads = self.directory / "servers/downloads"
        downloads.mkdir(parents=True)
        (downloads / "original_servers.zip").write_bytes(b"frozen bundle fixture")
        config = {**self.config, "mode": "live"}
        with patch("custom.experiment.readiness.ROOT", self.directory):
            result = environment(config)
        self.assertEqual(result["tool_bundles"]["original"]["status"], "present")
        self.assertEqual(len(result["tool_bundles"]["original"]["sha256"]), 64)
        self.assertEqual(result["tool_bundles"]["iter3"]["status"], "missing")

    def test_preparation_reports_pending_without_approving_or_blocking_pilots(self):
        result = preparation(self.config, ["Unreviewed backend"], state={"revision": "abc", "dirty_source": True})
        self.assertTrue(result["dirty_source"])
        self.assertEqual(len(result["classification_pending_ids"]), self.config["task_count"])
        self.assertEqual(result["formal_acceptance"], "not_assessed")
        self.assertEqual(result["backend_policy_warnings"], ["Unreviewed backend"])

    def test_completion_distinguishes_unscored_runs_without_requiring_all_five_scores(self):
        rows, _, _ = self.rows_and_evidence()
        for status, expected in (("completed", 0), ("completed_with_warnings", 0), ("partial", 3),
                                 ("completed_with_failures", 3), ("invalidated", 2)):
            result = completion({"status": status, "trajectories": rows})
            self.assertEqual(result["exit_code"], expected)
            self.assertEqual(result["formal_acceptance"], "not_assessed")
        aggregate = {"groups": {}, "completion": {"status": "completed_with_failures", "exit_code": 3}}
        with patch("custom.experiment.__main__.execute", return_value=(self.directory, aggregate)), patch("sys.stdout", io.StringIO()):
            self.assertEqual(main(["run", "--offline"]), 3)

    def test_real_trajectory_judge_check_reuses_request_and_never_changes_results(self):
        store = self.store()
        key = next(iter(store.records["trajectories"]))
        store.records["trajectories"][key].update(agent_status="completed", trajectory_messages=[
            {"role": "system", "content": "system"}, {"role": "user", "content": "question"},
            {"role": "assistant", "content": "done"}], answer="done", judge_catalog={})
        store.save()
        before = (store.path / "records.json").read_bytes()
        client = Mock()
        client.chat.completions.create.side_effect = [Response(Message(json.dumps({s: 8 for s in SCORES}))),
                                                      Response(Message('{"task_fulfillment":100}'))]
        with patch("custom.experiment.checks.make_client", return_value=client):
            result = check_judge(self.config, store.path, key, attempts=2, provider_index=1)
        self.addCleanup(Path(result["report"]).unlink, missing_ok=True)
        self.assertEqual(result["valid"], 1)
        self.assertEqual(result["attempted"], 2)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["semantic_accuracy"], "not_validated")
        self.assertEqual(client.chat.completions.create.call_count, 2)
        self.assertEqual((store.path / "records.json").read_bytes(), before)
        report = read_json(result["report"])
        self.assertIn("raw", report["attempts"][1])
        self.assertEqual(client.chat.completions.create.call_args.kwargs["messages"][0]["role"], "user")

    def test_old_archive_requires_unchanged_task_source(self):
        source = self.directory / "tasks.json"
        atomic_json(source, [])
        manifest = {"settings": {"task_source": str(source)}, "selected_ids": [],
                    "fingerprints": {"sources": {str(source): "wrong-hash"}}}
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            archived_tasks(manifest)

    def test_judge_diagnostic_resolves_shared_early_without_changing_archive(self):
        store = self.store()
        alias_key, alias = next((key, row) for key, row in store.records["trajectories"].items()
                                if row.get("shared_from"))
        source_key = alias["shared_from"]
        store.records["trajectories"][source_key].update(agent_status="completed", answer="done", judge_catalog={},
            trajectory_messages=[{"role": "system", "content": "system"},
                                 {"role": "user", "content": "question"},
                                 {"role": "assistant", "content": "done"}])
        store.save()
        before = (store.path / "records.json").read_bytes()
        client = Mock()
        client.chat.completions.create.return_value = Response(Message(json.dumps({s: 8 for s in SCORES})))
        with patch("custom.experiment.checks.make_client", return_value=client):
            result = check_judge(self.config, store.path, alias_key)
        self.addCleanup(Path(result["report"]).unlink, missing_ok=True)
        report = read_json(result["report"])
        self.assertEqual(report["trajectory"], alias_key)
        self.assertEqual(report["source_trajectory"], source_key)
        self.assertEqual(result["valid"], 1)
        self.assertEqual(client.chat.completions.create.call_count, 1)
        self.assertEqual((store.path / "records.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
