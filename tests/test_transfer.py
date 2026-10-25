"""Independent splits, production presentation, evidence gates and complete-case comparisons."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from custom.experiment import memory
from custom.experiment.selection import ROOT, digest, file_hash
from custom.experiment.transfer import CONDITIONS, cases, retain_templates, irrelevant_reference, render_rule, substitute, summarize, validate_rule
from custom.experiment.causal import SERVER


def entry():
    return {'id': 'learned', 'case_id': 'practice', 'value': {
        'tool_ids': ['fs::read'], 'content': 'Use a discovered path with fs::read.',
        'applicability': 'Unknown path or failed lookup.', 'failed_assumption': 'A guessed path is correct.',
        'corrective_actions': ['Discover the actual file', 'Read its returned path'],
        'verification': 'Read the intended contents.', 'evidence_call_ids': ['error', 'read']}}


class TransferTests(unittest.TestCase):
    def test_heldout_varies_filename_position_extension_depth_and_observability(self):
        definitions = cases()
        training = [c for c in definitions if c['split'] == 'practice']
        heldout = [c for c in definitions if c['split'] == 'heldout']
        self.assertEqual((len(training), len(heldout)), (3, 8))
        self.assertFalse({c['keyword'] for c in training} & {c['keyword'] for c in heldout})
        self.assertFalse({c['content'] for c in training} & {c['content'] for c in heldout})
        self.assertEqual(sum(c['cohort'] == 'discovery' for c in heldout), 6)
        self.assertEqual({c['cohort'] for c in heldout}, {'discovery', 'known_path', 'visible_tree'})
        self.assertTrue(any(Path(c['relative_path']).name.startswith(c['keyword']) for c in heldout))
        self.assertTrue(any(not Path(c['relative_path']).name.startswith(c['keyword']) for c in heldout))
        self.assertGreaterEqual(len({Path(c['relative_path']).suffix for c in heldout}), 4)
        self.assertTrue(any('/' not in c['relative_path'] for c in heldout))

    def test_trial_reference_matches_real_memory_rendering(self):
        value = entry()
        response = {'isError': False}
        case = {'id': 'practice', 'required_success_tool': 'fs::read', 'forbidden_constants': [], 'trace': [
            {'tool_call_id': 'error', 'semantic_identity': 'fs::read', 'response': {'isError': True}},
            {'tool_call_id': 'read', 'semantic_identity': 'fs::read', 'response': response,
             'verification': {'kind': 'exact_file_read', 'response_sha256': digest(response)}}]}
        catalog = {'fs::read': {'server': 'fs', 'name': 'read_api'}}
        with tempfile.TemporaryDirectory(dir=ROOT / '.runtime') as tmp:
            p = Path(tmp)
            source = {'origin': 'independent_verified_recovery_practice', 'catalog': catalog, 'cases': [case]}
            (p / 'source.json').write_text(json.dumps(source), encoding='utf-8')
            artifact = {'protocol': 'verified_tool_recovery_k0_v1', 'catalog': catalog, 'memories': [value],
                'memory_sha256': digest([value]), 'source_sha256': file_hash(p / 'source.json')}
            (p / 'k0.json').write_text(json.dumps(artifact), encoding='utf-8')
            config = {'memory': {'artifact': str(p / 'k0.json'), 'source': str(p / 'source.json'), 'inject': True, 'context_chars': 8000}}
            actual, _ = memory.render(config, catalog, {'fs'}, p)
            self.assertEqual(actual, render_rule([value], catalog).replace('${WORKSPACE}', p.as_posix()))
            self.assertNotIn('evidence_call_ids', actual)
            self.assertNotIn('fs::read', actual)

    def test_irrelevant_control_preserves_json_structure_and_character_length(self):
        catalog = {'fs::read': {'name': 'read_api'}}
        target = len(render_rule([entry()], catalog)) + 200
        context = irrelevant_reference(target, catalog)
        self.assertEqual(len(context), target)
        data = json.loads(context[len(memory.REFERENCE_PREFIX):])
        self.assertEqual(data['tools'], ['read_api'])
        self.assertIn('corrective_actions', data['guidance'])

    def test_new_rule_must_cite_all_verified_practice_boundaries(self):
        e = entry()
        observed = [{'case': 'practice-middle', 'observed_calls': [
            {'tool_call_id': 'error', 'response': {'isError': True}},
            {'tool_call_id': 'read', 'response': {'isError': False}}], 'verified_read_call_ids': ['read']},
            {'case': 'practice-known', 'observed_calls': [{'tool_call_id': 'direct', 'response': {'isError': False}}],
             'verified_read_call_ids': ['direct']}]
        with self.assertRaisesRegex(ValueError, 'boundary'):
            validate_rule([e], observed, {'fs::read': {}}, [])
        e['value']['evidence_call_ids'].append('direct')
        validate_rule([e], observed, {'fs::read': {}}, [])
        e['value']['content'] = 'Use PRIVATE-PRACTICE-TOKEN'
        with self.assertRaisesRegex(ValueError, 'practice constant'):
            validate_rule([e], observed, {'fs::read': {}}, [{'keyword': 'private-practice-token', 'content': 'private-payload'}])

    def test_provider_failure_is_not_a_false_task_loss_or_empty_knowledge_tie(self):
        rows = []
        for c in CONDITIONS:
            rows.append({'condition': c, 'case': 'a', 'repeat': 0, 'cohort': 'discovery', 'status': 'completed',
                         'outcome': {'success': True, 'task_success': c in ('new_rule', 'old_rule')}})
            rows.append({'condition': c, 'case': 'b', 'repeat': 0, 'cohort': 'known_path',
                         'status': 'failed' if c == 'new_rule' else 'completed',
                         'outcome': {'success': False, 'task_success': False}})
        result = summarize(rows, 2, None)
        self.assertEqual(result['paired']['no_rule']['all'], {'pairs': 1, 'new_successes': 1, 'other_successes': 0, 'wins': 1, 'losses': 0})
        self.assertEqual(result['paired']['no_rule']['easy_controls']['pairs'], 0)
        rejected = summarize([r for r in rows if r['condition'] != 'new_rule'], 2, {'type': 'Rejected'})
        self.assertEqual(rejected['conditions']['new_rule']['executed'], 0)
        self.assertEqual(rejected['paired']['no_rule']['all']['pairs'], 0)

    def test_template_validation_uses_fresh_heldout_names(self):
        old = [c for c in cases() if c['split'] == 'heldout']
        fresh = [c for c in cases(True) if c['split'] == 'heldout']
        self.assertFalse({c['keyword'] for c in old} & {c['keyword'] for c in fresh})
        self.assertFalse({c['content'] for c in old} & {c['content'] for c in fresh})

    def test_retention_uses_goal_success_instead_of_protocol_success(self):
        training = [c for c in cases(True) if c['split'] == 'practice']
        evidence = []
        for c in training:
            target = '${WORKSPACE}/' + c['relative_path']
            read_response = {'isError': False, 'content': [{'type': 'text', 'text': c['content']}]}
            calls = [
                {'tool_call_id': c['id'] + '-1', 'semantic_identity': SERVER + '::search_files',
                 'arguments': json.dumps({'path': '${WORKSPACE}', 'pattern': '**/' + c['keyword'] + '*.txt'}),
                 'response': {'isError': False, 'content': [{'type': 'text', 'text': 'No matches found'}]}},
                {'tool_call_id': c['id'] + '-2', 'semantic_identity': SERVER + '::search_files',
                 'arguments': json.dumps({'path': '${WORKSPACE}', 'pattern': '**/*' + c['keyword'] + '*'}),
                 'response': {'isError': False, 'content': [{'type': 'text', 'text': target}]}},
                {'tool_call_id': c['id'] + '-3', 'semantic_identity': SERVER + '::read_text_file',
                 'arguments': json.dumps({'path': target}), 'response': read_response,
                 'verification': {'response_sha256': digest(read_response)}}]
            evidence.append({'case': c['id'], 'observed_calls': calls, 'verified_read_call_ids': [c['id'] + '-3']})
        catalog = {SERVER + '::search_files': {}, SERVER + '::read_text_file': {}}
        with tempfile.TemporaryDirectory(dir=ROOT / '.runtime') as tmp:
            actual = retain_templates(evidence, catalog, training, Path(tmp) / 'valid.json')
            self.assertEqual(actual[0]['arguments']['pattern'], '**/*${KEYWORD}*')
            self.assertEqual(actual[1]['arguments']['path'], '${DISCOVERED_PATH}')
            self.assertEqual(actual[0]['evidence_call_ids'], ['practice-middle-2', 'practice-extension-2'])
            evidence[0]['observed_calls'][1]['response']['content'][0]['text'] = 'No matches found'
            with self.assertRaisesRegex(ValueError, 'No observed successful search'):
                retain_templates(evidence, catalog, training, Path(tmp) / 'invalid.json')

    def test_templates_are_visible_but_provenance_ids_are_not_in_actor_context(self):
        value = entry()
        value['value']['tool_call_templates'] = [{'tool_id': 'fs::read', 'arguments': {'path': '${DISCOVERED_PATH}'}, 'evidence_call_ids': ['read']}]
        context = render_rule([value], {'fs::read': {'name': 'read_api'}})
        self.assertIn('tool_call_templates', context)
        self.assertIn('read_api', context)
        self.assertIn('template_variables', context)
        self.assertNotIn('evidence_call_ids', context)
        with self.assertRaisesRegex(ValueError, 'Unresolved'):
            substitute({'path': '${UNKNOWN}'}, {'WORKSPACE': '/tmp'})
