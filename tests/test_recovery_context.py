from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest

from custom.experiment.memory import load, render
from custom.experiment.recovery_context import RecoveryContext, PREFIX, trigger
from custom.experiment.selection import ROOT, load_config, digest, file_hash
from custom.experiment.testing import Message, Response


class RecoveryContextTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT/'config/recovery-ablation.json')
        self.artifact = load(self.config)
        self.aliases = {k:v['name'] for k,v in self.artifact['catalog'].items()}

    def gate(self, aliases=None, limit=8000):
        return RecoveryContext(self.artifact['memories'], aliases or self.aliases, ROOT, limit)

    def call(self, name='mcp-tasks::tasks_add', error=True, message='You must request a file path and call tasks_setup.'):
        return {'tool_call_id':'observed-1','semantic_identity':name,'response':{'isError':error,'content':[{'type':'text','text':message}]}}

    def test_no_reference_without_real_matching_error(self):
        gate=self.gate()
        self.assertEqual(gate.take(),'')
        for call in [self.call(error=False), self.call(name='other::tasks_add'),self.call(message='Permission denied')]:
            gate.observe(call)
            self.assertEqual(gate.take(),'')
        self.assertFalse(gate.activations)

    def test_actual_repair_reference_lasts_one_decision_and_preserves_raw_response(self):
        gate=self.gate();call=self.call();before=deepcopy(call)
        gate.observe(call)
        context=gate.take()
        self.assertIn('tasks_setup',context)
        self.assertIn('SOURCE_ID',context)
        self.assertEqual(gate.take(),'')
        self.assertEqual(call,before)
        self.assertEqual(gate.activations[0]['response_sha256'],digest(call['response']))

    def test_status_error_without_mcp_error_flag_is_recognized(self):
        call=self.call('@kazuph/mcp-taskmanager::get_next_task',False,json.dumps({'status':'error','message':'Request not found'}))
        gate=self.gate();gate.observe(call)
        self.assertIn('REQUEST_ID',gate.take())
        self.assertEqual(trigger(call),('request','request_id_not_found'))
        self.assertFalse(call['response']['isError'])

    def test_unavailable_dependencies_and_context_budget_do_not_activate(self):
        for gate in [self.gate({'mcp-tasks::tasks_add':'tasks_add'}),self.gate(limit=10)]:
            gate.observe(self.call())
            self.assertEqual(gate.take(),'')
            self.assertEqual(gate.activations,[])

    def test_file_only_and_triggered_initial_prompts_are_identical(self):
        catalog=self.artifact['catalog'];required={t['server'] for t in catalog.values()}
        outputs=[]
        for profile in ['file_only','error_triggered']:
            cfg=deepcopy(self.config);cfg['memory']['profile']=profile
            context,exposure=render(cfg,catalog,required,ROOT,self.aliases)
            outputs.append(context)
            expected=[m['id'] for m in self.artifact['memories'] if m['case_id']=='expanded-file-recovery']
            self.assertEqual(exposure['selected_ids'],expected)
        self.assertEqual(outputs[0],outputs[1])

    def test_official_loop_adds_no_hidden_request_and_retires_reference_after_repair(self):
        from custom.agents.LangChainAgent import ChatModel
        requests=[];events=[]
        def create(**kwargs):
            requests.append(deepcopy(kwargs))
            if len(requests)<=2:
                name='tasks_add' if len(requests)==1 else 'tasks_setup'
                args={'texts':['current item'],'status':'To Do'} if name=='tasks_add' else {'source_path':'current.md'}
                return Response(Message(tool_calls=[SimpleNamespace(id='call-'+str(len(requests)),function=SimpleNamespace(name=name,arguments=json.dumps(args)))]))
            return Response(Message('Observed completion'))
        client=SimpleNamespace(api_key='test-only',base_url='http://unused.invalid/v1',chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        tools=[]
        for name in ['tasks_setup','tasks_add']:
            tool=deepcopy(self.artifact['catalog']['mcp-tasks::'+name])
            tool['meta']={'benchmark_semantic_identity':'mcp-tasks::'+name,'benchmark_remote_name':name}
            tools.append(tool)
        def caller(name,args):
            return self.call(error=name=='tasks_add',message='call tasks_setup.' if name=='tasks_add' else 'Source initialized')['response']
        agent=ChatModel('unused',client,tools,max_round=3,tool_caller=caller,workspace_root=ROOT,event_callback=lambda k,p:events.append((k,deepcopy(p))))
        agent.recovery=self.gate({t['meta']['benchmark_semantic_identity']:t['name'] for t in tools})
        answer,transcript,_,_=agent.run_with_server('Initialize the requested task source.')
        self.assertIsNone(agent.execution_error)
        self.assertEqual(len(requests),3)
        self.assertEqual(len(agent.raw_tool_trace),2)
        self.assertNotIn(PREFIX,requests[0]['messages'][0]['content'])
        self.assertIn(PREFIX,requests[1]['messages'][0]['content'])
        self.assertNotIn(PREFIX,requests[2]['messages'][0]['content'])
        self.assertNotIn(PREFIX,transcript[0]['content'])
        self.assertNotIn('Recovery reference',agent.raw_tool_trace[0]['response']['content'][0]['text'])
        self.assertEqual(answer,'Observed completion')

    def test_three_arm_pipeline_uses_original_scheduler_and_common_samples(self):
        from custom.experiment.core import initial_snapshot
        from custom.experiment.memory_ablation import run
        from test_recovery_memory import example
        cfg=load_config(ROOT/'config/langchain-minimal.json')
        idx=json.loads((ROOT/cfg['selection_file']).read_text(encoding='utf8'))['samples'][0]['idx']
        task={'idx':idx,'question':'Read the frozen file.','servers':{'@modelcontextprotocol/server-filesystem':['read_file']}}
        with tempfile.TemporaryDirectory(dir=ROOT/'.runtime') as tmp:
            root=Path(tmp);fixtures=root/'fixtures';fixtures.mkdir();(fixtures/'notes.txt').write_text('Frozen data',encoding='utf8')
            cfg.update(mode='offline',agent_repeats=1,fixtures=str(fixtures))
            catalog=initial_snapshot(cfg,[task],lambda e:None)['knowledge'];tool=next(iter(catalog))
            case,entry,_=example();case['id']=entry['case_id']='expanded-file-recovery'
            for call in case['trace']:call['semantic_identity']=tool
            case['required_success_tool']=tool;entry['value']['tool_ids']=[tool]
            source={'origin':'independent_verified_recovery_practice','catalog':catalog,'cases':[case]}
            (root/'source.json').write_text(json.dumps(source),encoding='utf8')
            artifact={'protocol':'verified_tool_recovery_k0_v1','catalog':catalog,'memories':[entry],
                      'memory_sha256':digest([entry]),'source_sha256':file_hash(root/'source.json')}
            (root/'artifact.json').write_text(json.dumps(artifact),encoding='utf8')
            cfg['memory']={'artifact':str(root/'artifact.json'),'source':str(root/'source.json'),'inject':True,'context_chars':8000,'comparison':'three_arm'}
            path,result=run(cfg,[task],[idx])
            self.assertEqual(result['common_sample']['triples'],1)
            self.assertEqual(result['complete_five_judge_sensitivity']['triples'],1)
            self.assertEqual(set(result['conditions']),{'without_memory','file_only','error_triggered'})
            self.assertTrue(all(c['valid_judge_slots']==5 for c in result['conditions'].values()))
            self.assertTrue(all(c['activation_count']==0 for c in result['conditions'].values()))
            from custom.experiment.results import Store
            from custom.experiment.memory_ablation import report
            store=Store(path)
            store.records['trajectories'][f'error_triggered/original/{idx}/0']['score']=None
            missing=report(store)
            self.assertEqual(missing['common_sample']['triples'],0)
            self.assertEqual(missing['comparisons']['file_only_vs_without_memory']['pairs'],1)
            self.assertEqual(missing['comparisons']['error_triggered_vs_file_only']['pairs'],0)


if __name__=='__main__':unittest.main()
