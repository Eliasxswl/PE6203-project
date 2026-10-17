"""Serialization contract checks; scoring rubric and archived data stay unchanged."""
import json
import unittest
from unittest.mock import Mock

from custom.experiment.core import parse_judge, request_judge
from custom.experiment.judge_output import REASONS, SCHEMA, contract, request_options, validate_completion
from custom.experiment.results import SCORES
from custom.experiment.selection import ROOT, load_config
from custom.experiment.testing import Message, Response


class JudgeOutputTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT / "config/experiment.json")
        self.config["judge_output_mode"] = "json_object"
        self.valid = {**{s: 8 for s in SCORES}, **{s: "Evidence" for s in REASONS}}

    def test_valid_contract_accepts_minimum_and_maximum_scores(self):
        for score in (1, 10):
            value = {**self.valid, **{s: score for s in SCORES}}
            self.assertEqual(parse_judge(json.dumps(value), self.config), value)

    def test_rejects_invalid_score_types_and_range(self):
        for score in (0, 11, "8", True, 8.0, None):
            with self.subTest(score=score), self.assertRaises(ValueError):
                parse_judge(json.dumps({**self.valid, "task_fulfillment": score}), self.config)

    def test_rejects_missing_extra_or_wrongly_typed_fields(self):
        cases = [{k: v for k, v in self.valid.items() if k != "grounding_reasoning"},
                 {**self.valid, "extra": 1}, {**self.valid, "grounding_reasoning": []}]
        for value in cases:
            with self.assertRaises(ValueError):
                parse_judge(json.dumps(value), self.config)

    def test_rejects_malformed_json_markdown_and_duplicate_keys_without_repair(self):
        raw = json.dumps(self.valid)
        for value in (raw.replace('"Evidence",', '"Evidence"),', 1), "```json\n" + raw + "\n```",
                      raw[:-1] + ', "task_fulfillment": 1}', "Prefix " + raw):
            with self.assertRaises(ValueError):
                parse_judge(value, self.config)

    def test_legacy_mode_preserves_old_fenced_score_only_contract(self):
        value = {s: 8 for s in SCORES}
        self.assertEqual(parse_judge("```json\n" + json.dumps(value) + "\n```"), value)
        config = {**self.config, "judge_output_mode": "text"}
        self.assertEqual(request_options(config, "Original rubric")["messages"][0]["content"], "Original rubric")
        self.assertNotIn("response_format", request_options(config, "Original rubric"))

    def test_request_adds_only_serialization_contract_and_preserves_settings(self):
        client = Mock()
        config = {**self.config, "judge_thinking": "disabled"}
        request_judge(client, config, "Original rubric and task")
        options = client.chat.completions.create.call_args.kwargs
        self.assertEqual(client.chat.completions.create.call_count, 1)
        self.assertEqual(options["response_format"], {"type": "json_object"})
        self.assertTrue(options["messages"][0]["content"].startswith("Original rubric and task\n"))
        self.assertIn(json.dumps(SCHEMA), options["messages"][0]["content"])
        self.assertEqual(options["temperature"], config["judge_temperature"])
        self.assertEqual(options["max_tokens"], config["judge_max_tokens"])
        self.assertEqual(options["extra_body"], {"thinking": {"type": "disabled"}})
        self.assertFalse(contract(config)["server_strict_schema"])

    def test_request_failure_does_not_retry_or_silently_drop_format(self):
        client = Mock()
        client.chat.completions.create.side_effect = RuntimeError("Unsupported format")
        with self.assertRaises(RuntimeError):
            request_judge(client, self.config, "Original rubric")
        self.assertEqual(client.chat.completions.create.call_count, 1)

    def test_rejects_refusals_or_incomplete_responses(self):
        response = Response(Message(json.dumps(self.valid)))
        validate_completion(response, self.config)
        for reason in ("length", "content_filter", None):
            response.choices[0].finish_reason = reason
            with self.assertRaises(ValueError):
                validate_completion(response, self.config)
        response.choices[0].finish_reason = "stop"
        response.choices[0].message.refusal = "Refused"
        with self.assertRaises(ValueError):
            validate_completion(response, self.config)
