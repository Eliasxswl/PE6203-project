from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import Mock
from types import SimpleNamespace

from custom.experiment import adapters, memory
from custom.experiment.experience_state import initialize, evolve, validate_state, as_artifact, witness, submission, restore_submission
from custom.experiment.selection import ROOT, load_config, digest, file_hash


class ExperienceStateTests(unittest.TestCase):
    def setUp(self):
        self.config=load_config(ROOT/'config/recovery-ablation.json')
        self.artifact=memory.load(self.config)
        self.catalog=deepcopy(self.artifact['catalog'])
        self.state=initialize(self.config,self.catalog)
        self.target=deepcopy(self.catalog)
        schema=self.target['@kazuph/mcp-taskmanager::request_planning']['inputSchema']
        schema['properties']['splitDetails']={'type':'string','minLength':10}
        schema['required']=sorted(set(schema['required'])|{'splitDetails'})
        self.calls=[]

    def builder(self,config,entry,origin,old,new,context,index,emit):
        self.calls.append(entry['id'])
        for template in entry['value']['tool_call_templates']:
            if template['tool_id']=='@kazuph/mcp-taskmanager::request_planning':
                template['arguments']['splitDetails']='${SPLIT_DETAILS}'
                entry['value'].setdefault('template_variables',{})['SPLIT_DETAILS']='Current breakdown, at least ten characters.'
        entry['adaptation']={'status':'active','stage':context['stage'],'reason':'Test contract rebuild'}
        return entry,{'status':'completed','api_calls':1,'input_tokens':3,'output_tokens':4}

    def update(self,strategy,target=None,builder=None):
        return evolve(self.config,strategy,self.state,self.catalog,target or self.target,
                      {'stage':'iter3','repeat':0},rebuilder=builder or self.builder)

    def test_no_update_keeps_entire_initial_state(self):
        state,audit=self.update('no_update')
        self.assertEqual(state,self.state)
        self.assertEqual(self.calls,[])
        self.assertEqual(audit['api_calls'],0)

    def test_selective_update_uses_dependencies_and_preserves_unrelated_records(self):
        before=deepcopy(self.state)
        state,audit=self.update('selective_patch')
        selected=next(e['id'] for e in before['memories'] if e['case_id']=='verified-request-workflow')
        self.assertEqual(self.calls,[selected])
        self.assertEqual(audit['selected_ids'],[selected])
        for old,new in zip(before['memories'],state['memories']):
            if old['id']!=selected:self.assertEqual(old,new)
        self.assertEqual(self.state,before)
        validate_state(state,self.target)

    def test_full_and_selective_use_the_same_rebuilder_with_different_scope(self):
        full,full_audit=self.update('full_rewrite')
        full_calls=self.calls[:];self.calls.clear()
        selective,selective_audit=self.update('selective_patch')
        self.assertEqual(len(full_calls),3)
        self.assertEqual(len(self.calls),1)
        changed=next(e['id'] for e in self.state['memories'] if e['case_id']=='verified-request-workflow')
        self.assertEqual(next(e for e in full['memories'] if e['id']==changed),next(e for e in selective['memories'] if e['id']==changed))
        self.assertEqual(full_audit['api_calls'],3)
        self.assertEqual(selective_audit['api_calls'],1)

    def test_unrelated_tool_addition_does_not_rebuild_active_experience(self):
        target=deepcopy(self.catalog)
        target['demo::new']={'server':'demo','name':'new','description':'Unrelated','inputSchema':{'type':'object'}}
        state,audit=self.update('selective_patch',target)
        self.assertEqual(self.calls,[])
        self.assertEqual(state['memories'],self.state['memories'])

    def test_description_change_is_a_dependency_change(self):
        target=deepcopy(self.catalog);key='mcp-tasks::tasks_add'
        target[key]['description']+=' A changed semantic instruction.'
        state,audit=self.update('selective_patch',target)
        expected=next(e['id'] for e in self.state['memories'] if key in e['value']['tool_ids'])
        self.assertEqual(self.calls,[expected])

    def test_invalid_rebuild_fails_without_committing_partial_state(self):
        original=deepcopy(self.state)
        def invalid(*args):
            entry,journal=self.builder(*args)
            if entry['case_id']=='verified-request-workflow':
                entry['value']['tool_call_templates'][0]['arguments'].pop('splitDetails')
            return entry,journal
        state,audit=self.update('full_rewrite',builder=invalid)
        self.assertIsNone(state)
        self.assertEqual(audit['status'],'failed')
        self.assertEqual(self.state,original)
        self.assertGreater(audit['api_calls'],0)

    def test_provider_failure_preserves_dispatch_and_unknown_usage(self):
        def failing(*args):
            exc=RuntimeError('Simulated provider interruption')
            exc.experience_journal={'status':'failed','api_calls':1,'input_tokens':None,'output_tokens':None}
            raise exc
        state,audit=self.update('selective_patch',builder=failing)
        self.assertIsNone(state)
        self.assertEqual(audit['api_calls'],1)
        self.assertIsNone(audit['input_tokens'])

    def test_render_reads_the_supplied_snapshot_instead_of_reloading_k0(self):
        state,_=self.update('selective_patch')
        cfg=deepcopy(self.config);cfg['memory'].update(profile='complete',context_chars=12000)
        tools,_=adapters.agent_tools(self.target,self.target,{t['server'] for t in self.target.values()})
        aliases={t['meta']['benchmark_semantic_identity']:t['name'] for t in tools}
        with patch.object(memory,'load',side_effect=AssertionError('Fixed K0 must not be reloaded')):
            context,exposure=memory.render(cfg,self.target,set(),ROOT,aliases,artifact=as_artifact(state,self.target))
        self.assertEqual(exposure['artifact_sha256'],state['memory_sha256'])
        self.assertIn('splitDetails',context)

    def test_template_container_types_are_not_replaced_by_string_placeholders(self):
        with self.assertRaisesRegex(ValueError,'container types'):
            witness('${TASKS}',{'type':'array'},{'TASKS':'Current tasks'})

    def test_independent_updates_do_not_mutate_each_others_snapshots(self):
        left,_=self.update('full_rewrite');right,_=self.update('selective_patch')
        old=deepcopy(right)
        left['memories'][0]['value']['content']='Changed only in the first strategy'
        self.assertEqual(right,old)
        self.assertNotEqual(left['memories'],self.state['memories'])

    def test_live_builder_protocol_uses_one_named_call_data_record(self):
        from custom.experiment.experience_state import rewrite
        from custom.experiment.testing import Message,Response
        entry=next(e for e in self.state['memories'] if e['case_id']=='verified-source-workflow')
        from test_update_contract import wire_record
        response=Response(Message(json.dumps(wire_record(entry,self.catalog))))
        response.usage=SimpleNamespace(prompt_tokens=11,completion_tokens=12,model_dump=lambda:{'prompt_tokens':11,'completion_tokens':12})
        client=Mock();client.chat.completions.create.return_value=response
        with patch('custom.experiment.core.make_client',return_value=client):
            updated,journal=rewrite(self.config,entry,self.state['origins'][entry['id']],self.catalog,self.catalog,
                {'strategy':'full_rewrite','stage':'iter3','repeat':0},0,lambda e:None)
        self.assertEqual(updated['value']['content'],entry['value']['content'])
        self.assertEqual(journal['api_calls'],1)
        self.assertEqual(journal['input_tokens'],11)
        self.assertEqual(client.chat.completions.create.call_count,1)
        kwargs=client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs['response_format']['type'],'json_schema')
        self.assertTrue(kwargs['response_format']['json_schema']['strict'])
        self.assertEqual([m['role'] for m in kwargs['messages']],['system','user'])
        data=json.loads(kwargs['messages'][1]['content'])
        self.assertEqual(set(data),{'previous_record','variable_meanings','previous_contracts','target_contracts'})
        self.assertNotIn('tools',kwargs)
        self.assertEqual(updated['value']['tool_call_templates'],entry['value']['tool_call_templates'])

    def test_malformed_builder_json_is_not_repaired_or_retried(self):
        from custom.experiment.experience_state import rewrite
        from custom.experiment.testing import Message,Response
        entry=next(e for e in self.state['memories'] if e['case_id']=='verified-source-workflow')
        response=Response(Message('{"content":"missing closing brace"'))
        response.usage=None
        response.model_dump=lambda **kwargs:{'choices':[{'message':{'content':'{"content":"missing closing brace"'}}],'usage':None}
        client=Mock();client.chat.completions.create.return_value=response
        with patch('custom.experiment.core.make_client',return_value=client):
            with self.assertRaises(json.JSONDecodeError) as failed:
                rewrite(self.config,entry,self.state['origins'][entry['id']],self.catalog,self.catalog,
                    {'strategy':'full_rewrite','stage':'iter3','repeat':0},0,lambda e:None)
        self.assertEqual(client.chat.completions.create.call_count,1)
        self.assertEqual(failed.exception.experience_journal['status'],'failed')

    def test_submission_preserves_evidence_without_asking_model_to_copy_it(self):
        for entry in self.state['memories']:
            data=submission(entry)
            self.assertNotIn('evidence_call_ids',json.dumps(data))
            restored=restore_submission(data,entry,self.catalog)
            self.assertEqual(restored['evidence_call_ids'],entry['value']['evidence_call_ids'])
            self.assertEqual(restored['tool_call_templates'],entry['value']['tool_call_templates'])
            data['evidence_call_ids']=['invented']
            with self.assertRaisesRegex(ValueError,'submission fields'):restore_submission(data,entry,self.catalog)

    def test_submission_rejects_missing_calls_instead_of_filling_them(self):
        entry=self.state['memories'][0];data=submission(entry)
        data['calls'].pop('call_0')
        with self.assertRaisesRegex(ValueError,'every named call slot'):restore_submission(data,entry,self.catalog)

    def test_new_variable_is_bound_to_its_real_target_argument(self):
        entry=next(e for e in self.state['memories'] if e['case_id']=='verified-request-workflow')
        data=submission(entry)
        data['calls']['call_0']['arguments']['splitDetails']='${SPLIT_DETAILS}'
        value=restore_submission(data,entry,self.target)
        self.assertIn('request_planning.splitDetails',value['template_variables']['SPLIT_DETAILS'])
        for key,meaning in entry['value']['template_variables'].items():
            self.assertEqual(value['template_variables'][key],meaning)
        data['calls']['call_0']['arguments']['invented']='${UNKNOWN}'
        with self.assertRaisesRegex(ValueError,'target-contract binding'):restore_submission(data,entry,self.target)


class ExperiencePipelineTests(unittest.TestCase):
    def fixture(self,directory):
        from custom.experiment.testing import catalog_for
        config=load_config(ROOT/'config/langchain-minimal.json')
        config.update(mode='offline',agent_repeats=1,fixtures=str(directory/'fixtures'),mock={'rename_tools':True})
        (directory/'fixtures').mkdir();(directory/'fixtures/notes.txt').write_text('Frozen unit fixture',encoding='utf8')
        idx=json.loads((ROOT/config['selection_file']).read_text(encoding='utf8'))['samples'][0]['idx']
        tasks=[{'idx':idx,'question':'Read the frozen file.','servers':{'@modelcontextprotocol/server-filesystem':['read_file']}}]
        catalog=adapters.semantic(catalog_for(config,tasks,'original'));key=next(iter(catalog))
        failure={'tool_call_id':'failure','semantic_identity':key,'response':{'isError':True}}
        success={'tool_call_id':'read','semantic_identity':key,'response':{'isError':False}}
        success['verification']={'kind':'unit_fixture_success','response_sha256':digest(success['response'])}
        case={'id':'unit','trace':[failure,success],'forbidden_constants':['private-unit-name'],'required_success_tool':key}
        entry={'id':'stable-rule','case_id':'unit','value':{'tool_ids':[key],'content':'Read the requested document.',
            'applicability':'When a read is required','failed_assumption':'A guessed path exists','corrective_actions':['Use observed paths'],
            'verification':'Observe the actual read','evidence_call_ids':['failure','read'],
            'tool_call_templates':[{'tool_id':key,'arguments':{},'evidence_call_ids':['read']}]}}
        source={'origin':'independent_verified_recovery_practice','catalog':catalog,'cases':[case]}
        (directory/'source.json').write_text(json.dumps(source),encoding='utf8')
        artifact={'protocol':'verified_tool_recovery_k0_v1','source_sha256':file_hash(directory/'source.json'),'catalog':catalog,
                  'memories':[entry],'memory_sha256':digest([entry])}
        (directory/'artifact.json').write_text(json.dumps(artifact),encoding='utf8')
        config['memory']={'artifact':str(directory/'artifact.json'),'source':str(directory/'source.json'),
                          'inject':True,'profile':'complete','evolution':True,'context_chars':8000}
        return config,tasks,artifact

    def test_serial_and_spawn_follow_the_same_versioned_state_and_shared_early(self):
        from custom.experiment.__main__ import execute
        from custom.experiment.results import Store
        for parallel in (False,True):
            with self.subTest(parallel=parallel),tempfile.TemporaryDirectory(dir=ROOT/'.runtime') as tmp:
                config,tasks,artifact=self.fixture(Path(tmp))
                path,aggregate=execute(config,tasks,parallel=parallel,workers=2 if parallel else 1)
                store=Store(path);idx=tasks[0]['idx']
                self.assertEqual(aggregate['completion']['planned_trajectories'],7)
                self.assertEqual(aggregate['completion']['judge_slots'],35)
                self.assertTrue((path/'inputs/source.zip').exists())
                for strategy in config['strategies']:
                    stages=store.records['episodes'][strategy+'/0']['stages']
                    for stage in ('original','iter3','iter5'):
                        row=store.records['trajectories'][f'{strategy}/{stage}/{idx}/0']
                        self.assertEqual(row['experience_memory_sha256'],stages[stage]['experience_state']['memory_sha256'])
                    if strategy=='no_update':
                        self.assertEqual(stages['iter5']['experience_state']['memory_sha256'],artifact['memory_sha256'])
                    else:self.assertNotEqual(stages['iter3']['experience_state']['memory_sha256'],artifact['memory_sha256'])
                values=aggregate['paired']['iter3']['means']
                self.assertLess(values['no_update']['task_fulfillment'],values['full_rewrite']['task_fulfillment'])

    def test_failed_preparation_dispatches_no_benchmark_requests(self):
        from custom.experiment.__main__ import execute
        from custom.experiment.results import Store,create
        paths=[]
        def capture(*args,**kwargs):
            path=create(*args,**kwargs);paths.append(path);return path
        with tempfile.TemporaryDirectory(dir=ROOT/'.runtime') as tmp:
            config,tasks,artifact=self.fixture(Path(tmp))
            with patch('custom.experiment.__main__.create',side_effect=capture),patch(
                    'custom.experiment.testing.rewrite_experience',side_effect=ValueError('Invalid unit rebuild')):
                with self.assertRaisesRegex(RuntimeError,'preparation failed'):
                    execute(config,tasks)
            store=Store(paths[0])
            self.assertTrue(all(not r['agent_attempts'] for r in store.records['trajectories'].values()))

    def test_frozen_early_pilot_accepts_an_evolution_profile_without_updating_it(self):
        from custom.experiment.memory_ablation import run
        from custom.experiment.results import Store
        with tempfile.TemporaryDirectory(dir=ROOT/'.runtime') as tmp:
            config,tasks,artifact=self.fixture(Path(tmp))
            config['memory'].update(comparison='full_pilot',profile='complete')
            path,report=run(config,tasks,[tasks[0]['idx']])
            self.assertEqual(report['planned'],1)
            self.assertEqual(report['scored'],1)
            row=next(iter(Store(path).records['trajectories'].values()))
            self.assertEqual(row['experience_memory_sha256'],artifact['memory_sha256'])
            self.assertTrue((path/'inputs/source.zip').exists())
            self.assertFalse((path/'update-budget.json').exists())


if __name__=='__main__':unittest.main()
