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


if __name__=='__main__':unittest.main()
