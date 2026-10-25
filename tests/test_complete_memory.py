from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from custom.agents.tool_feedback import reported_error, validation_feedback
from custom.experiment import adapters
from custom.experiment.memory import load, render
from custom.experiment.selection import ROOT, load_config, tasks
from custom.experiment.runtime import ALIASES


class CompleteMemoryTests(unittest.TestCase):
    def test_every_selected_task_receives_identical_complete_library(self):
        cfg=load_config(ROOT/'config/recovery-ablation.json')
        cfg['memory']['profile']='complete'
        artifact=load(cfg)
        expected={e['id'] for e in artifact['memories']}
        selected=tasks(cfg)
        self.assertEqual([t['idx'] for t in selected],[9,24,117,416,267,271,273,274,278,386,389,390,394,403,410,411,425])
        for task in selected:
            servers={ALIASES.get(s,s) for s in task['servers']}
            tools,_=adapters.agent_tools(artifact['catalog'],artifact['catalog'],servers)
            aliases={t['meta']['benchmark_semantic_identity']:t['name'] for t in tools}
            context,exposure=render(cfg,artifact['catalog'],servers,ROOT,aliases)
            self.assertEqual(set(exposure['selected_ids']),expected)
            self.assertLessEqual(len(context),cfg['memory']['context_chars'])
            lines=context.splitlines()
            records=[json.loads(line) for line in lines if line.startswith('{')]
            self.assertEqual(len(records),len(expected))
            for record in records:
                self.assertTrue(set(record['tools']) <= set(aliases.values()))
                for binding in record['current_tool_bindings']:
                    self.assertEqual(binding['callable_name'],aliases.get(binding['knowledge_tool']))

    def test_complete_profile_fails_instead_of_silently_dropping_entries(self):
        cfg=load_config(ROOT/'config/recovery-ablation.json');cfg['memory'].update(profile='complete',context_chars=100)
        artifact=load(cfg)
        with self.assertRaisesRegex(ValueError,'silently dropped'):
            render(cfg,artifact['catalog'],set(),ROOT,{})

    def test_schema_feedback_explains_exact_constraint_without_rewriting_arguments(self):
        tool={'inputSchema':{'type':'object','properties':{'initialConcept':{'type':'string','minLength':50}},'required':['initialConcept']},
              'meta':{'benchmark_semantic_identity':'mcp-shrimp-task-manager::analyze_task'}}
        args={'initialConcept':'Brief'};before=deepcopy(args)
        response={'isError':True,'content':[{'type':'text','text':'schema_input_invalid'}]}
        issues=validation_feedback(tool,args,response)
        self.assertEqual(issues[0]['argument_path'],'/initialConcept')
        self.assertEqual(issues[0]['constraint'],'minLength')
        self.assertEqual(issues[0]['expected'],50)
        self.assertEqual(args,before)
        self.assertEqual(response['content'][0]['text'],'schema_input_invalid')

    def test_nested_json_error_is_detected_with_original_flag_preserved(self):
        tool={'inputSchema':{'type':'object','properties':{'tasksRaw':{'type':'string'}}},
              'meta':{'benchmark_semantic_identity':'mcp-shrimp-task-manager::split_tasks'}}
        response={'isError':False,'content':[{'type':'text','text':'tasksRaw 參數格式錯誤，invalid JSON'}]}
        self.assertTrue(reported_error(tool['meta']['benchmark_semantic_identity'],response))
        hints=validation_feedback(tool,{'tasksRaw':"[{name: 'x'}]"},response)
        self.assertEqual(hints[0]['constraint'],'valid_json_string')
        self.assertFalse(response['isError'])

    def test_pilot_report_inspects_every_task_and_recognizes_recovery(self):
        from custom.experiment.memory_ablation import report_pilot
        bad={'tool_call_id':'bad','semantic_identity':'mcp-shrimp-task-manager::split_tasks',
             'response':{'isError':False,'content':[{'type':'text','text':'tasksRaw 參數格式錯誤，invalid'}]}}
        good={'tool_call_id':'good','semantic_identity':bad['semantic_identity'],'response':{'isError':False,'content':[]}}
        row={'identity':{'task_id':386,'repeat':0},'raw_tool_trace':[bad,good],'agent_status':'completed','score':None,
             'judge_attempts':[],'memory_exposure':{'total_library_entries':3,'selected_ids':['a','b','c']}}
        report=report_pilot(SimpleNamespace(records={'status':'completed_with_failures','trajectories':{'one':row}}))
        self.assertEqual(report['planned'],1)
        self.assertTrue(report['tasks'][0]['complete_library_visible'])
        self.assertTrue(report['tasks'][0]['tool_errors'][0]['later_successful_same_tool_call'])
        self.assertEqual(report['tasks'][0]['unrecovered_tool_errors'],0)

    def test_retained_template_container_types_bind_to_native_schemas(self):
        from custom.experiment.skills import bind
        from jsonschema import validate
        artifact=load(load_config(ROOT/'config/recovery-ablation.json'))
        values={'WORKSPACE':ROOT.as_posix(),'SOURCE_PATH':(ROOT/'current.md').as_posix(),
            'SOURCE_ID':'observed-id','STATUS':'To Do','TASK_TEXT_1':'Current first item','TASK_TEXT_2':'Current second item',
            'REQUEST':'Current request','REQUEST_ID':'req-observed',
            'TASK_1_TITLE':'Current first title','TASK_1_DESCRIPTION':'Current first description',
            'TASK_2_TITLE':'Current second title','TASK_2_DESCRIPTION':'Current second description'}
        for entry in artifact['memories']:
            if entry['case_id'] not in ('verified-source-workflow','verified-request-workflow'):continue
            for template in entry['value']['tool_call_templates']:
                args=bind(template['arguments'],values)
                validate(args,artifact['catalog'][template['tool_id']]['inputSchema'])
                if 'texts' in args:self.assertTrue(all(isinstance(v,str) for v in args['texts']))
                if 'tasks' in args:self.assertTrue(all(isinstance(v,dict) for v in args['tasks']))

    def test_missing_field_feedback_includes_its_declared_type(self):
        tool={'inputSchema':{'type':'object','properties':{'thought_number':{'type':'integer','minimum':1}},'required':['thought_number']},
              'meta':{'benchmark_semantic_identity':'mcp-shrimp-task-manager::process_thought'}}
        response={'isError':True,'content':[{'type':'text','text':'schema_input_invalid'}]}
        issue=validation_feedback(tool,{},response)[0]
        self.assertEqual(issue['argument_path'],'/thought_number')
        self.assertEqual(issue['field_schema']['type'],'integer')

    def test_printed_tool_call_is_reviewed_even_with_a_high_rubric_score(self):
        from custom.experiment.memory_ablation import report_pilot
        row={'identity':{'task_id':425,'repeat':0},'raw_tool_trace':[],'agent_status':'completed',
             'answer':'search_files\n{"path":"current"}','score':{'task_fulfillment':10,'grounding':10,'planning_and_efficiency':10},'judge_attempts':[]}
        result=report_pilot(SimpleNamespace(records={'status':'completed','trajectories':{'one':row}}))
        self.assertTrue(result['tasks'][0]['textual_tool_call_without_execution'])
        self.assertTrue(result['tasks'][0]['review_required'])


if __name__=='__main__':unittest.main()
