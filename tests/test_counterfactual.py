from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from custom.experiment import adapters
from custom.experiment.counterfactual import conditions, scope, order_control, case_outcome, run
from custom.experiment.results import Store, atomic_json, create
from custom.experiment.selection import ROOT, digest, file_hash, fingerprints, read_json

SOURCE = ROOT/'results/20261026T084527.010290Z_Kevin'


class FrozenCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = read_json(SOURCE/'records.json')
        cls.manifest = read_json(SOURCE/'experiment.json')

    def test_restoration_preserves_exact_affected_updates_and_only_restores_unchanged_records(self):
        before = digest(self.records)
        variants, _, affected = conditions(self.records, 2)
        old = {e['id']:e for e in variants['frozen_k0'][0]['memories']}
        full = {e['id']:e for e in variants['fr_all'][0]['memories']}
        self.assertEqual(len(affected), 2)
        for entry in variants['fr_changed_only'][0]['memories']:
            self.assertEqual(entry, full[entry['id']] if entry['id'] in affected else old[entry['id']])
        self.assertEqual(digest(self.records), before)
        task = next(t for t in self.manifest['task_definitions'] if t['idx'] == 9)
        self.assertEqual(scope(variants['fr_all'][1], task), scope(variants['fr_changed_only'][1], task))

    def test_key_order_control_changes_presentation_without_changing_values_or_length(self):
        original = conditions(self.records, 2)[0]['fr_all']
        control = order_control(original)
        self.assertEqual(original, control)
        self.assertEqual(digest(original), digest(control))
        a, b = json.dumps(original, ensure_ascii=False), json.dumps(control, ensure_ascii=False)
        self.assertNotEqual(a, b)
        self.assertEqual(len(a), len(b))

    def test_bad_repetitions_and_model_changes_fail_before_dispatch(self):
        cfg = deepcopy(self.manifest['settings'])
        with self.assertRaisesRegex(ValueError, 'confirmation'):
            run(cfg, self.manifest['task_definitions'], SOURCE, 9, repeats=True)
        cfg['agent_temperature'] = 0
        with patch('custom.experiment.counterfactual.create', side_effect=AssertionError('No run should start')):
            with self.assertRaisesRegex(ValueError, 'archived model'):
                run(cfg, self.manifest['task_definitions'], SOURCE, 9)

    def test_observations_require_actual_read_content_and_successful_plan_return(self):
        row = {'identity':{'task_id':9}, 'workspace_observations':[{'txt/log_yesterday.txt':{'text':'line one\nline two\n'}}],
               'raw_tool_trace':[]}
        self.assertEqual(case_outcome(row), {'log_read':False,'plan_created':False,'workflow_complete':False})
        row['raw_tool_trace'] = [
            {'semantic_identity':'@modelcontextprotocol/server-filesystem::read_text_file',
             'arguments':{'path':'/private/workspace/txt/log_yesterday.txt'},
             'response':{'content':[{'type':'text','text':'line one\r\nline two\r\n'}], 'isError':False}},
            {'semantic_identity':'@kazuph/mcp-taskmanager::request_planning',
             'response':{'content':[{'type':'text','text':'schema_input_invalid'}], 'isError':True}}]
        self.assertTrue(case_outcome(row)['log_read'])
        self.assertFalse(case_outcome(row)['plan_created'])
        row['raw_tool_trace'][-1]['response'] = {'content':[{'type':'text','text':json.dumps(
            {'status':'planned','requestId':'actual-id','tasks':[{'title':'Analyze'}]})}], 'isError':False}
        self.assertTrue(case_outcome(row)['workflow_complete'])
        row['raw_tool_trace'][0]['arguments']['path'] = '/private/workspace/txt/another_log.txt'
        self.assertFalse(case_outcome(row)['log_read'])
        row['identity']['task_id'] = 24
        self.assertIsNone(case_outcome(row))


class CasePipelineTests(unittest.TestCase):
    def test_thirty_fresh_executions_use_frozen_inputs_and_never_dispatch_judge_or_updater(self):
        from test_experience_state import ExperiencePipelineTests
        from custom.experiment.experience_state import initialize
        from custom.experiment.testing import OfflineRuntime
        with tempfile.TemporaryDirectory(dir=ROOT/'.runtime') as tmp:
            cfg, tasks, artifact = ExperiencePipelineTests().fixture(Path(tmp))
            cfg['strategies'] = ['full_rewrite']
            cfg['mock'] = {}
            catalog = artifact['catalog']
            early_state = initialize(cfg, catalog)
            full = deepcopy(early_state)
            full['memories'][0]['value']['content'] = 'Rebuilt independent read procedure.'
            full['memory_sha256'] = digest(full['memories'])
            full['knowledge_stage'] = 'iter5'
            early = {'status':'ready','catalog':catalog,'knowledge':catalog,'errors':{},'experience_state':early_state}
            late = {**deepcopy(early),'experience_state':full}
            source = create(cfg, tasks, fingerprints(cfg))
            store = Store(source)
            store.records['initial_snapshot'] = early
            store.records['episodes']['full_rewrite/0']['stages'] = {'original':early,'iter5':late}
            store.save()
            original_hash = file_hash(source/'records.json')

            class MetadataRuntime(OfflineRuntime):
                def __exit__(self, *args):
                    super().__exit__(*args)
                    self.directory.mkdir()
                    (self.directory/'service.log').write_text('Stopped service', encoding='utf-8')

            def runtime(config, stage, servers, task_list, cancel, owner_callback=None):
                return MetadataRuntime(config, 'original', servers, cancel, task_list)

            with patch('custom.experiment.core.runtime_for', side_effect=runtime), patch(
                    'custom.experiment.core.request_judge', side_effect=AssertionError('No Judge calls')), patch(
                    'custom.experiment.update_provider.OpenRouterUpdater', side_effect=AssertionError('No update calls')):
                output, result = run(cfg, tasks, source, tasks[0]['idx'], snapshot_repeat=0,
                                     repeats=10, include_order_control=True)
            actual = Store(output)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(len(actual.records['trajectories']), 30)
            self.assertTrue(all(v['completed_agents'] == 10 for v in result['conditions'].values()))
            self.assertTrue(all(not any(a['status'] == 'completed' for a in r['judge_attempts'])
                                for r in actual.records['trajectories'].values()))
            directories = actual.manifest['diagnostic']['paired_runtime_directories']
            self.assertEqual(len(set(directories.values())), 10)
            self.assertTrue(all(not Path(p).exists() for p in directories.values()))
            self.assertEqual(file_hash(source/'records.json'), original_hash)
            self.assertFalse((output/'update-budget.json').exists())


if __name__ == '__main__':
    unittest.main()
