"""Official loop integration: real message protocol, caps, errors and strategy boundaries."""
from copy import deepcopy
from importlib.util import find_spec
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from custom.experiment.errors import ExecutionFailure, ToolMistake
from custom.experiment.selection import ROOT, load_config, read_json
from custom.experiment.testing import Message, Response


@unittest.skipUnless(find_spec('langchain') is not None, 'Optional LangChain environment is not installed')
class LangChainAgentTests(unittest.TestCase):
    def agent(self, limit=4, caller=None, tool_name='read_document'):
        from custom.agents.LangChainAgent import ChatModel
        messages = []
        def create(**kwargs):
            messages.append(deepcopy(kwargs))
            if len(messages) == 1:
                return Response(Message(tool_calls=[SimpleNamespace(id='real-call',
                    function=SimpleNamespace(name=tool_name, arguments='{"path":"notes.txt"}'))]))
            return Response(Message('Observed completion'))
        client = SimpleNamespace(api_key='test-only', base_url='http://unused.invalid/v1',
                                 chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        tool = {'name': 'read_document', 'description': 'Read an existing document.',
                'inputSchema': {'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path']},
                'meta': {'benchmark_semantic_identity': 'demo::read_document', 'benchmark_remote_name': 'transport-read'}}
        calls, events = [], []
        def invoke(remote, args):
            calls.append((remote, args))
            if caller:
                return caller(remote, args)
            return {'isError': False, 'content': [{'type': 'text', 'text': 'real-observed-data'}]}
        agent = ChatModel(model_name='unused-test-model', client=client, tools=[tool], max_round=limit,
            tool_caller=invoke, event_callback=lambda k, p: events.append((k, deepcopy(p))), workspace_root=ROOT)
        return agent, messages, calls, events

    def test_official_loop_dispatches_tools_and_returns_full_protocol(self):
        agent, requests, calls, events = self.agent()
        answer, transcript, stop, exceeded = agent.run_with_server('Read the notes.')
        self.assertIsNone(agent.execution_error)
        self.assertEqual(answer, 'Observed completion')
        self.assertEqual(calls, [('transport-read', {'path': 'notes.txt'})])
        self.assertEqual([m['role'] for m in transcript], ['system', 'user', 'assistant', 'tool', 'assistant'])
        self.assertIn('real-observed-data', requests[1]['messages'][-1]['content'])
        self.assertEqual(agent.request_count, 2)
        self.assertEqual(len(agent.raw_tool_trace), 1)

    def test_empty_terminal_response_is_preserved_but_not_completed(self):
        agent, requests, calls, events = self.agent()
        def empty(**kwargs):
            requests.append(deepcopy(kwargs))
            return Response(Message(''))
        agent.client.chat.completions.create = empty
        agent.run_with_server('Read the notes.')
        self.assertIsNotNone(agent.execution_error)
        self.assertIn('empty assistant response', agent.execution_error['message'])
        self.assertEqual(len(requests), 1)
        self.assertEqual(calls, [])
        self.assertEqual(sum(k == 'model_completed' for k, _ in events), 1)

    def test_empty_final_after_a_tool_does_not_erase_the_actual_execution(self):
        agent, requests, calls, events = self.agent()
        original = agent.client.chat.completions.create
        def final_empty(**kwargs):
            result = original(**kwargs)
            if len(requests) > 1:
                result.choices[0].message.content = ''
            return result
        agent.client.chat.completions.create = final_empty
        agent.run_with_server('Read the notes.')
        self.assertIsNotNone(agent.execution_error)
        self.assertEqual(len(requests), 2)
        self.assertEqual(len(agent.raw_tool_trace), 1)
        self.assertEqual(calls, [('transport-read', {'path': 'notes.txt'})])

    def test_request_limit_prevents_an_extra_model_dispatch(self):
        agent, requests, calls, events = self.agent(limit=1)
        answer, transcript, _, exceeded = agent.run_with_server('Read the notes.')
        self.assertIsNone(agent.execution_error)
        self.assertTrue(exceeded)
        self.assertEqual(agent.stop_reason, 'model_request_limit')
        self.assertEqual(len(requests), 1)
        self.assertEqual(transcript[-1]['role'], 'tool')

    def test_semantic_tool_error_is_feedback_not_execution_failure(self):
        def rejected(*args):
            raise ToolMistake('Wrong argument; correct the path.')
        agent, requests, calls, events = self.agent(caller=rejected)
        agent.run_with_server('Read the notes.')
        self.assertIsNone(agent.execution_error)
        self.assertIn('Wrong argument', requests[1]['messages'][-1]['content'])
        self.assertTrue(agent.raw_tool_trace[0]['response']['isError'])

    def test_transport_failure_is_not_silently_scored_as_a_tool_mistake(self):
        def failed(*args):
            raise ExecutionFailure('MCP transport disconnected', unknown_outcome=True)
        agent, requests, calls, events = self.agent(caller=failed)
        agent.run_with_server('Read the notes.')
        self.assertTrue(agent.execution_error['unknown_outcome'])
        self.assertEqual(len(requests), 1)

    def test_unknown_tool_is_feedback_without_transport_dispatch(self):
        agent, requests, calls, events = self.agent(tool_name='unknown_tool')
        agent.run_with_server('Read the notes.')
        self.assertIsNone(agent.execution_error)
        self.assertEqual(calls, [])
        self.assertEqual(len(requests), 2)
        self.assertIn('unknown_tool', requests[1]['messages'][-1]['content'])

    def test_memory_context_is_preserved_in_execution_and_audit(self):
        agent, requests, calls, events = self.agent()
        agent.messages[0]['content'] += '\nVerified reference: follow returned paths.'
        _, transcript, _, _ = agent.run_with_server('Read the notes.')
        self.assertIn('Verified reference', requests[0]['messages'][0]['content'])
        self.assertIn('Verified reference', transcript[0]['content'])

    def test_existing_three_strategies_run_all_versions_with_the_official_loop(self):
        from custom.experiment.__main__ import execute
        from custom.experiment.results import Store
        with tempfile.TemporaryDirectory(dir=ROOT / '.runtime') as tmp:
            fixture = Path(tmp) / 'fixtures'
            fixture.mkdir()
            (fixture / 'notes.txt').write_text('Frozen fixture', encoding='utf-8')
            config = load_config(ROOT / 'config/langchain-minimal.json')
            config.update(mode='offline', agent_repeats=1, fixtures=str(fixture), mock={'rename_tools': True})
            idx = read_json(ROOT / config['selection_file'])['samples'][0]['idx']
            task = {'idx': idx, 'question': 'Read the frozen fixture.',
                    'servers': {'@modelcontextprotocol/server-filesystem': ['read_file']}}
            path, aggregate = execute(config, [task])
            rows = Store(path).records['trajectories']
            self.assertEqual(len(rows), 9)
            independent = [r for r in rows.values() if not r.get('shared_from')]
            self.assertEqual(len(independent), 7)
            self.assertTrue(all(r['status'] == 'completed' and r['score'] is not None for r in independent))
            self.assertTrue(all(len(r['judge_attempts']) == 5 for r in independent))
            self.assertEqual(rows[f'full_rewrite/iter3/{idx}/0']['score'],
                             rows[f'selective_patch/iter3/{idx}/0']['score'])
            self.assertLess(rows[f'no_update/iter3/{idx}/0']['score']['task_fulfillment'],
                            rows[f'full_rewrite/iter3/{idx}/0']['score']['task_fulfillment'])
