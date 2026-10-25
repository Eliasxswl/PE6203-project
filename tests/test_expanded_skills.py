import json
from pathlib import Path
import unittest
import tempfile
from types import SimpleNamespace
from copy import deepcopy

from custom.experiment.skills import bind, definitions, failure, goal, retain_template, summary, SHRIMP, REQUEST
from custom.experiment.memory import guidance_line
from custom.experiment.recovery_memory import validate_entry
from custom.experiment.selection import digest


class SkillTests(unittest.TestCase):
    def test_typed_and_nested_json_bindings(self):
        value = {'tasksRaw': json.dumps([{'name': '${NAME}', 'dependencies': [], 'relatedFiles': []}]), 'texts': '${TEXTS}'}
        result = bind(value, {'NAME': 'quoted "name" \\ test', 'TEXTS': ['one', 'two']})
        self.assertEqual(result['texts'], ['one', 'two'])
        self.assertEqual(json.loads(result['tasksRaw'])[0]['name'], 'quoted "name" \\ test')
        with self.assertRaises(KeyError):bind('${MISSING}', {})

    def test_inner_schema_and_status_errors_remain_raw(self):
        for message in ('tasks 參數格式錯誤，test', '{"status":"error","message":"Request not found"}'):
            call = {'response': {'isError': False, 'content': [{'type': 'text', 'text': message}]}}
            before = deepcopy(call['response'])
            self.assertTrue(failure(call))
            self.assertEqual(call['response'], before)
            self.assertEqual(call['failure_evidence']['response_sha256'], digest(before))
        self.assertFalse(failure({'response': {'isError': False, 'content': [{'type': 'text', 'text': 'No matches found'}]}}))

    def test_practice_split_is_disjoint_and_clean_case_changes_count(self):
        cases = definitions()
        self.assertEqual(len(cases), 16)
        for family in {c['family'] for c in cases}:
            train = [c for c in cases if c['family'] == family and c['split'] == 'practice']
            heldout = [c for c in cases if c['family'] == family and c['split'] == 'validation']
            self.assertEqual(len(train), 2)
            self.assertEqual(len(heldout), 2)
            self.assertTrue(all(c['recovery'] for c in train))
            self.assertTrue(set(c['subject'] for c in train).isdisjoint(c['subject'] for c in heldout))
            self.assertEqual(len(next(c for c in heldout if not c['recovery'])['names']), 3)

    def test_actual_nested_call_structure_is_retained(self):
        case = next(c for c in definitions() if c['id'] == 'split-0')
        tasks = [{'name': n, 'description': d, 'implementationGuide': 'Implement and check this piece.',
                  'dependencies': [] if i == 0 else [case['names'][0]], 'relatedFiles': []}
                 for i, (n, d) in enumerate(zip(case['names'], case['descriptions']))]
        row = {'case': case, 'calls': [{'semantic_identity': SHRIMP + '::split_tasks', 'tool_call_id': 'ok', 'verification': {'kind': 'persisted'},
            'arguments': json.dumps({'updateMode': 'append', 'tasksRaw': json.dumps(tasks)})}]}
        templates, variables = retain_template(row)
        args = templates[0]['arguments']
        items = json.loads(args['tasksRaw'])
        self.assertEqual(items[1]['dependencies'], ['${TASK_1_NAME}'])
        self.assertEqual(items[0]['relatedFiles'], [])
        self.assertNotIn(case['subject'], json.dumps(templates))
        self.assertEqual(args['updateMode'], 'append')
        self.assertIn('TASK_1_NAME', variables)

    def test_old_file_renderer_is_byte_compatible(self):
        root = Path(__file__).resolve().parents[1]
        old = json.loads((root / 'results/20261024T222342.186571Z_Kevin/candidate-k0.json').read_text(encoding='utf-8'))
        entry = next(e for e in old['memories'] if e['case_id'] == 'expanded-file-recovery')
        aliases = {k:v['name'] for k,v in old['catalog'].items()}
        output = json.loads(guidance_line(entry, aliases, Path('/practice')))
        self.assertEqual(output['guidance']['template_usage'], 'Substitute current inputs and observed output paths; never pass placeholder strings literally. Known exact paths can be read directly.')
        self.assertEqual(set(output['guidance']['template_variables']), {'KEYWORD', 'DISCOVERED_PATH'})

    def test_fake_semantic_error_proof_is_rejected(self):
        from test_recovery_memory import example
        case, entry, catalog = example()
        c = case['trace'][0]
        c['response'] = {'isError': False, 'content': [{'type': 'text', 'text': '{"status":"error"}'}]}
        failure(c)
        validate_entry(entry, case, catalog)
        c['response']['content'][0]['text'] = '{"status":"ok"}'
        c['failure_evidence']['response_sha256'] = digest(c['response'])
        with self.assertRaisesRegex(ValueError, 'contradicts'):validate_entry(entry, case, catalog)

    def test_request_goal_requires_correct_persisted_request_and_returned_task(self):
        case = next(c for c in definitions() if c['id'] == 'request-2')
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / '.runtime') as tmp:
            runtime = SimpleNamespace(workspace=Path(tmp))
            state = {'requests': [{'requestId': 'req-8', 'originalRequest': case['summary'], 'tasks': [
                {'id': 'task-'+str(i), 'title': n, 'description': d} for i,(n,d) in enumerate(zip(case['names'],case['descriptions']))]}]}
            (runtime.workspace/'tasks.json').write_text(json.dumps(state),encoding='utf8')
            def call(name,args,data):
                return {'semantic_identity': REQUEST+'::'+name,'arguments':json.dumps(args),
                        'response':{'isError':False,'content':[{'type':'text','text':json.dumps(data)}]}}
            planned = call('request_planning',{}, {'requestId':'req-8'})
            got = call('get_next_task',{'requestId':'req-8'},{'status':'next_task','task':{'id':'task-0'}})
            self.assertTrue(goal(runtime,case,[got],[planned])[0])
            got['arguments'] = json.dumps({'requestId':'task-0'})
            self.assertFalse(goal(runtime,case,[got],[planned])[0])
            got['arguments'] = json.dumps({'requestId':'req-8'})
            got['response']['content'][0]['text'] = json.dumps({'status':'next_task','task':{'id':'task-1'}})
            self.assertFalse(goal(runtime,case,[got],[planned])[0])

    def test_execution_failure_is_excluded_even_when_tool_goal_completed(self):
        case = next(c for c in definitions() if c['id']=='request-2')
        rows = [{'case':case,'condition':c,'repeat':0,'status':s,'success':True}
                for c,s in [('without_memory','completed'),('with_memory','failed')]]
        result = summary(rows)['families']['request']
        self.assertEqual(result['paired']['all']['pairs'],0)
        self.assertEqual(result['conditions']['with_memory']['successes'],0)


if __name__ == '__main__':
    unittest.main()
