"""Recovery provenance, complete structured exposure and paired coverage."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest.mock import patch

from custom.experiment import memory
from custom.experiment.memory_ablation import report
from custom.experiment.recovery_memory import PROTOCOL, validate_artifact, validate_entry
from custom.experiment.selection import ROOT, digest, file_hash


def example():
    failure = {'tool_call_id': 'failure', 'semantic_identity': 'fs::read', 'response': {'isError': True}}
    success = {'tool_call_id': 'read', 'semantic_identity': 'fs::read', 'response': {'isError': False}}
    success['verification'] = {'kind': 'exact_file_read', 'response_sha256': digest(success['response'])}
    case = {'id': 'practice', 'trace': [failure, success], 'forbidden_constants': ['practice-secret'], 'required_success_tool': 'fs::read'}
    entry = {'id': 'rule', 'case_id': 'practice', 'value': {'tool_ids': ['fs::read'],
        'content': 'Use discovered paths with fs::read.', 'applicability': 'After a failed lookup',
        'failed_assumption': 'A guessed path exists', 'corrective_actions': ['Discover a path', 'Read the returned path'],
        'verification': 'Observe a correct read', 'evidence_call_ids': ['failure', 'read']}}
    catalog = {'fs::read': {'server': 'fs'}}
    return case, entry, catalog


class RecoveryTests(unittest.TestCase):
    def test_evidence_must_include_a_real_error(self):
        case, entry, catalog = example()
        validate_entry(entry, case, catalog)
        case['trace'][0]['response']['isError'] = False
        with self.assertRaisesRegex(ValueError, 'actual error'):
            validate_entry(entry, case, catalog)

    def test_success_response_cannot_change_after_verification(self):
        case, entry, catalog = example()
        case['trace'][1]['response']['content'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'response mismatch'):
            validate_entry(entry, case, catalog)

    def test_unrelated_success_does_not_certify_required_operation(self):
        case, entry, catalog = example()
        case['trace'][1]['semantic_identity'] = 'fs::search'
        with self.assertRaisesRegex(ValueError, 'verified correction'):
            validate_entry(entry, case, catalog)

    def test_practice_constants_and_unobserved_tools_are_rejected(self):
        case, entry, catalog = example()
        entry['value']['content'] = 'Use practice-secret'
        with self.assertRaisesRegex(ValueError, 'practice constant'):
            validate_entry(entry, case, catalog)
        entry['value']['content'] = 'Read current paths'
        entry['value']['tool_ids'] = ['fs::invented']
        with self.assertRaisesRegex(ValueError, 'unobserved tool'):
            validate_entry(entry, case, catalog)

    def test_current_procedure_fields_are_visible_with_real_aliases(self):
        case, entry, catalog = example()
        with tempfile.TemporaryDirectory(dir=ROOT / '.runtime') as tmp:
            root = Path(tmp)
            source = {'origin': 'independent_verified_recovery_practice', 'catalog': catalog, 'cases': [case]}
            (root / 'source.json').write_text(json.dumps(source), encoding='utf-8')
            artifact = {'protocol': PROTOCOL, 'catalog': catalog, 'memories': [entry],
                        'memory_sha256': digest([entry]), 'source_sha256': file_hash(root / 'source.json')}
            (root / 'artifact.json').write_text(json.dumps(artifact), encoding='utf-8')
            config = {'memory': {'source': 'source.json', 'artifact': 'artifact.json', 'inject': True, 'context_chars': 8000}}
            with patch.object(memory, 'ROOT', root):
                context, exposure = memory.render(config, catalog, {'fs'}, root, {'fs::read': 'read_api'})
                for field in ('content', 'applicability', 'failed_assumption', 'corrective_actions', 'verification'):
                    self.assertIn(field, context)
                self.assertNotIn('fs::read', context)
                self.assertIn('read_api', context)
                self.assertEqual(exposure['presentation'], 'verified_procedure_v1')
                config['memory']['inject'] = False
                self.assertEqual(memory.render(config, catalog, {'fs'}, root)[0], '')

    def test_artifact_requires_independent_practice(self):
        case, entry, catalog = example()
        source = {'origin': 'official_task_trajectory', 'catalog': catalog, 'cases': [case]}
        with self.assertRaisesRegex(ValueError, 'independent practice'):
            validate_artifact({'catalog': catalog, 'memories': [entry]}, source)

    def test_paired_analysis_does_not_compare_unmatched_scores(self):
        rows = {}
        for idx, repeat, before, after in [(1, 0, 3, 5), (2, 0, 9, None)]:
            for c, score in [('without_memory', before), ('with_memory', after)]:
                rows[f'{c}/original/{idx}/{repeat}'] = {'identity': {'strategy': c, 'stage': 'original', 'task_id': idx, 'repeat': repeat},
                    'agent_status': 'completed' if score is not None else 'failed', 'score': None if score is None else {
                        'task_fulfillment': score, 'grounding': score, 'planning_and_efficiency': score},
                    'judge_attempts': [], 'agent_attempts': [], 'memory_exposure': {'selected_ids': ['rule'] if c == 'with_memory' else []}}
        result = report(SimpleNamespace(records={'status': 'completed_with_failures', 'trajectories': rows}, manifest={'harness_protocol': 'verified'}))
        self.assertEqual(result['paired']['all_tasks']['pairs'], 1)
        self.assertEqual(result['paired']['all_tasks']['mean_score_deltas_with_minus_without']['task_fulfillment'], 2)
        self.assertIsNone(result['tasks'][1]['mean_tf_delta_with_minus_without'])

    def test_frozen_recovery_runs_both_conditions_through_existing_pipeline(self):
        from custom.experiment.core import initial_snapshot
        from custom.experiment.memory_ablation import run
        from custom.experiment.selection import load_config, read_json
        config = load_config(ROOT / 'config/langchain-minimal.json')
        idx = read_json(ROOT / config['selection_file'])['samples'][0]['idx']
        task = {'idx': idx, 'question': 'Read the frozen file.',
                'servers': {'@modelcontextprotocol/server-filesystem': ['read_file']}}
        with tempfile.TemporaryDirectory(dir=ROOT / '.runtime') as tmp:
            root = Path(tmp)
            fixtures = root / 'fixtures'
            fixtures.mkdir()
            (fixtures / 'notes.txt').write_text('Frozen data', encoding='utf-8')
            config.update(mode='offline', fixtures=str(fixtures), agent_repeats=1)
            catalog = initial_snapshot(config, [task], lambda event: None)['knowledge']
            tool = next(iter(catalog))
            case, entry, _ = example()
            for call in case['trace']:
                call['semantic_identity'] = tool
            case['required_success_tool'] = tool
            entry['value']['tool_ids'] = [tool]
            source = {'origin': 'independent_verified_recovery_practice', 'catalog': catalog, 'cases': [case]}
            (root / 'source.json').write_text(json.dumps(source), encoding='utf-8')
            artifact = {'protocol': PROTOCOL, 'catalog': catalog, 'memories': [entry],
                        'memory_sha256': digest([entry]), 'source_sha256': file_hash(root / 'source.json')}
            (root / 'artifact.json').write_text(json.dumps(artifact), encoding='utf-8')
            config['memory'] = {'artifact': str(root / 'artifact.json'), 'source': str(root / 'source.json'),
                                'inject': True, 'context_chars': 8000}
            path, output = run(config, [task], [idx])
            self.assertEqual(output['status'], 'completed')
            self.assertEqual(output['paired']['all_tasks']['pairs'], 1)
            self.assertEqual(output['conditions']['with_memory']['exposed_trajectories'], 1)
            self.assertEqual(output['conditions']['without_memory']['exposed_trajectories'], 0)
            self.assertEqual(output['conditions']['with_memory']['valid_judge_slots'], 5)
            self.assertEqual(output['conditions']['without_memory']['valid_judge_slots'], 5)
            self.assertTrue((path / 'inputs/frozen-k0.json').exists())
