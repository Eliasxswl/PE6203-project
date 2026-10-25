"""Objective success needs a real correct-file read, not claims or nearby evidence."""
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from custom.experiment.causal import SERVER, build_procedure, generated_reference, normalize, outcome
from custom.experiment.testing import Message, Response
from custom.experiment.selection import ROOT


class CausalTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / '.runtime')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.target = self.root / 'nested' / 'target.txt'

    def call(self, path=None, response=None, tool='read_text_file'):
        return {'tool_call_id': 'observed-read', 'semantic_identity': SERVER + '::' + tool,
                'arguments': json.dumps({'path': str(path or self.target)}),
                'response': response or {'isError': False, 'content': [{'type': 'text', 'text': 'unique-payload'}]}}

    def test_actual_read_of_exact_target_is_success(self):
        assert outcome([self.call()], self.target, 'unique-payload')['success']

    def test_other_file_with_same_contents_is_not_success(self):
        assert not outcome([self.call(self.root / 'wrong.txt')], self.target, 'unique-payload')['success']

    def test_correct_path_but_wrong_contents_is_not_success(self):
        assert not outcome([self.call()], self.target, 'different-payload')['success']

    def test_failed_read_or_search_result_is_not_success(self):
        failed = self.call(response={'isError': True, 'content': [{'type': 'text', 'text': 'unique-payload'}]})
        assert not outcome([failed], self.target, 'unique-payload')['success']
        assert not outcome([self.call(tool='search_files')], self.target, 'unique-payload')['success']
        assert not outcome([], self.target, 'unique-payload')['success']

    def test_bad_arguments_cannot_be_treated_as_a_read(self):
        call = self.call()
        call['arguments'] = '{'
        assert not outcome([call], self.target, 'unique-payload')['success']

    def test_normalization_preserves_evidence_without_private_root(self):
        source = {'message': str(self.root / 'nested'), 'steps': [self.root.as_posix() + '/target']}
        result = normalize(source, self.root)
        assert result == {'message': '${WORKSPACE}' + str(self.root / 'nested')[len(str(self.root)):],
                          'steps': ['${WORKSPACE}/target']}

    def test_empty_or_unverified_knowledge_is_rejected(self):
        calls = [{'tool_call_id': 'failed'}, {'tool_call_id': 'miss'}, {'tool_call_id': 'success'}]
        case = {'keyword': 'private-training-key', 'content': 'private-training-payload'}
        with self.assertRaisesRegex(ValueError, 'empty library'):
            generated_reference([], calls, {'verified_read_call_ids': ['success']}, case, {})
        record = [{'value': {'evidence_call_ids': ['failed', 'invented']}}]
        with self.assertRaisesRegex(ValueError, 'unobserved'):
            generated_reference(record, calls, {'verified_read_call_ids': ['success']}, case, {})

    def test_both_error_and_recovery_evidence_are_required(self):
        calls = [{'tool_call_id': 'failed'}, {'tool_call_id': 'miss'}, {'tool_call_id': 'success'}]
        record = [{'value': {'evidence_call_ids': ['failed', 'miss']}}]
        with self.assertRaisesRegex(ValueError, 'both failure'):
            generated_reference(record, calls, {'verified_read_call_ids': ['success']},
                                {'keyword': 'training-key', 'content': 'training-payload'}, {})

    def test_generated_prompt_uses_callable_names_without_training_constants(self):
        calls = [{'tool_call_id': 'failed'}, {'tool_call_id': 'miss'}, {'tool_call_id': 'success'}]
        case = {'keyword': 'training-key', 'content': 'training-payload'}
        record = [{'value': {'evidence_call_ids': ['failed', 'success'], 'content': 'Use fs::read.'}}]
        rendered = generated_reference(record, calls, {'verified_read_call_ids': ['success']},
                                       case, {'fs::read': {'name': 'read_api'}})
        self.assertIn('read_api', rendered)
        self.assertNotIn('fs::read', rendered)
        record[0]['value']['content'] = 'Use training-key'
        with self.assertRaisesRegex(ValueError, 'practice constant'):
            generated_reference(record, calls, {'verified_read_call_ids': ['success']}, case, {})

    def builder(self, content):
        requests, closed = [], []
        def create(**kwargs):
            requests.append(kwargs)
            return Response(Message(content))
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
                                 close=lambda: closed.append(True))
        return client, requests, closed

    def test_builder_uses_one_json_request_and_includes_tool_catalog(self):
        record = {'tool_ids': ['fs::read'], 'content': 'Read discovered paths.', 'applicability': 'Failed lookup',
                  'failed_assumption': 'One failed path does not prove absence', 'corrective_actions': ['Search recursively'],
                  'verification': 'Read exact returned path', 'evidence_call_ids': ['failed', 'success']}
        client, requests, closed = self.builder(json.dumps(record))
        with patch('custom.experiment.causal.make_client', return_value=client):
            learned, journal = build_procedure({'agent_model': 'test'}, {'observed_calls': []},
                {'fs::read': {'name': 'read_api'}}, self.root / 'build.json')
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]['response_format'], {'type': 'json_object'})
        self.assertNotIn('tools', requests[0])
        self.assertIn('catalog', requests[0]['messages'][0]['content'])
        self.assertIn('Do not return a JSON Schema', requests[0]['messages'][0]['content'])
        self.assertEqual(learned[0]['value'], record)
        self.assertEqual(closed, [True])

    def test_builder_does_not_repair_or_retry_invalid_output(self):
        client, requests, closed = self.builder('{"content":"first","content":"second"}')
        with patch('custom.experiment.causal.make_client', return_value=client):
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                build_procedure({'agent_model': 'test'}, {}, {}, self.root / 'invalid.json')
        self.assertEqual(len(requests), 1)
        self.assertEqual(closed, [True])
        self.assertEqual(json.loads((self.root / 'invalid.json').read_text(encoding='utf-8'))['status'], 'rejected')
