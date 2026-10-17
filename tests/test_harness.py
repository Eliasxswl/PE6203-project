"""Offline regressions for the execution-only repair."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mcp.types import CallToolResult, TextContent
from custom.agents.SimpleOpenAIAgent import ChatModel
from custom.agents.tool_results import MAX_VISIBLE_CHARS, visible_result
from custom.experiment.testing import Message, Response

TEMP_ROOT = Path(__file__).resolve().parents[1] / ".runtime"

def tool_reply(name="write", arguments="{}", content=None):
    return Response(Message(content, [SimpleNamespace(id="call_1", function=SimpleNamespace(name=name, arguments=arguments))]))


class HarnessTests(unittest.TestCase):
    def agent(self, responses, caller=None, cap=11):
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(side_effect=responses))))
        agent = ChatModel(client=client, model_name="offline", max_round=cap, tool_server_map={"write": "files"},
                          tool_caller=caller or Mock(return_value=CallToolResult(content=[TextContent(type="text", text="written")])) )
        return agent, client.chat.completions.create

    def test_completed_write_stops_without_a_synthetic_user_demand(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            output = Path(directory) / "logs_tasks.md"
            def write(*_):
                output.write_text("- [ ] Check disk space\n- [ ] Investigate database\n", encoding="utf-8")
                return CallToolResult(content=[TextContent(type="text", text="Two tasks added")])
            caller = Mock(side_effect=write)
            agent, requests = self.agent([tool_reply(), Response(Message("Two tasks added successfully."))], caller)
            answer, messages, stopped, exceeded = agent.run_with_server("Create follow-up tasks")
            self.assertEqual(caller.call_count, 1)
            self.assertEqual(requests.call_count, 2)
            self.assertTrue(stopped)
            self.assertFalse(exceeded)
            self.assertEqual(answer, "Two tasks added successfully.")
            self.assertEqual(sum(m["role"] == "user" for m in messages), 1)
            self.assertIn("Check disk", output.read_text(encoding="utf-8"))

    def test_finish_marker_cannot_discard_requested_tools(self):
        caller = Mock(return_value=CallToolResult(content=[]))
        agent, requests = self.agent([tool_reply(content="[FINISH] writing"), Response(Message("done"))], caller)
        self.assertTrue(agent.run_with_server("write")[2])
        caller.assert_called_once()
        self.assertEqual(requests.call_count, 2)

    def test_empty_length_and_refusal_are_distinct_and_not_retried(self):
        for reason, content, expected in [(None, None, "empty_response"), ("length", "partial", "model_length_limit"),
                                          ("content_filter", None, "model_refusal")]:
            with self.subTest(reason=reason):
                response = Response(Message(content))
                response.choices[0].finish_reason = reason
                agent, calls = self.agent([response], cap=1)
                answer, _, stopped, exceeded = agent.run_with_server("write")
                self.assertEqual(agent.stop_reason, expected)
                self.assertFalse(stopped)
                self.assertFalse(exceeded)
                self.assertEqual(calls.call_count, 1)
                self.assertEqual(answer, content or "")
        response = Response(Message())
        response.choices[0].message.refusal = "Cannot comply"
        agent, _ = self.agent([response])
        self.assertEqual(agent.run_with_server("write")[0], "Cannot comply")
        self.assertEqual(agent.stop_reason, "model_refusal")

    def test_length_limited_tool_arguments_are_not_executed(self):
        response = tool_reply(arguments='{"incomplete":')
        response.choices[0].finish_reason = "length"
        caller = Mock()
        agent, _ = self.agent([response], caller)
        agent.run_with_server("write")
        caller.assert_not_called()
        self.assertEqual(agent.stop_reason, "model_length_limit")

    def test_serialized_tool_calls_are_rejected_as_an_incompatible_response(self):
        response = Response(Message('{"tool_calls": []}'))
        response.choices[0].finish_reason = "tool_calls"
        agent, calls = self.agent([response])
        self.assertFalse(agent.run_with_server("write")[2])
        self.assertEqual(agent.stop_reason, "execution_failed")
        self.assertEqual(calls.call_count, 1)

    def test_provider_failure_is_an_execution_failure_not_a_final_answer(self):
        agent, calls = self.agent([TimeoutError("provider timeout")])
        self.assertFalse(agent.run_with_server("write")[2])
        self.assertEqual(agent.stop_reason, "execution_failed")
        self.assertTrue(agent.execution_error["unknown_outcome"])
        self.assertEqual(calls.call_count, 1)

    def test_mcp_result_preserves_long_text_structure_and_error_status(self):
        result = CallToolResult(isError=True, content=[TextContent(type="text", text="x" * 700 + "important tail")],
                                structuredContent={"task_id": "123", "reason": "rejected"})
        caller = Mock(return_value=result)
        agent, _ = self.agent([tool_reply(), Response(Message("Unable to write"))], caller)
        _, messages, _, _ = agent.run_with_server("write")
        visible = json.loads(next(m["content"] for m in messages if m["role"] == "tool"))
        self.assertTrue(visible["isError"])
        self.assertEqual(visible["structuredContent"]["task_id"], "123")
        self.assertIn("important tail", visible["content"][0]["text"])
        self.assertEqual(agent.raw_tool_trace[0]["response"], result.model_dump(mode="json", exclude_none=True))

    def test_oversized_results_are_bounded_valid_json_with_explicit_truncation(self):
        result = {"isError": True, "structuredContent": {"data": '\\"你好' * 20000}}
        for limit in (512, MAX_VISIBLE_CHARS):
            text = visible_result(result, max_chars=limit)
            self.assertLessEqual(len(text), limit)
            bounded = json.loads(text)
            self.assertTrue(bounded["truncated"])
            self.assertTrue(bounded["isError"])
            self.assertEqual(len(bounded["sha256"]), 64)

    def test_tool_argument_mistake_remains_visible_feedback(self):
        agent, _ = self.agent([tool_reply(arguments="{bad"), Response(Message("Could not write"))])
        _, messages, stopped, _ = agent.run_with_server("write")
        self.assertTrue(stopped)
        self.assertIsNone(agent.execution_error)
        self.assertTrue(json.loads(next(m["content"] for m in messages if m["role"] == "tool"))["isError"])


if __name__ == "__main__":
    unittest.main()
