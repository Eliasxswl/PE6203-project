from copy import deepcopy
import json
import unittest

from jsonschema import validate as validate_json

from custom.experiment import adapters, memory
from custom.experiment.experience_state import initialize, evolve, as_artifact, witness
from custom.experiment.runtime import ALIASES
from custom.experiment.selection import ROOT, load_config, read_json
from custom.experiment.tool_knowledge import validate_artifact, validate_value, verify_inner_json


class ToolKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.config=load_config(ROOT/'config/knowledge-evolution.json')
        self.artifact=memory.load(self.config)
        self.source=read_json(ROOT/self.config['memory']['source'])
        self.catalog=self.artifact['catalog']

    def test_normal_success_knowledge_does_not_require_a_fabricated_failure(self):
        values=[e['value'] for e in self.artifact['memories'] if 'kind' in e['value']]
        self.assertEqual(sorted(v['kind'] for v in values),['constraint','effect_boundary','procedure','procedure'])
        for value in values:
            self.assertNotIn('failed_assumption',value)
            self.assertNotIn('corrective_actions',value)
            validate_value(value)

    def test_legacy_recovery_is_retained_alongside_new_kinds(self):
        self.assertEqual(sum('kind' not in e['value'] for e in self.artifact['memories']),3)
        validate_artifact(self.artifact,self.source)

    def test_readback_dependency_corruption_is_rejected(self):
        source=deepcopy(self.source)
        case=next(c for c in source['cases'] if c.get('family')=='lifecycle')
        case['observation']['created']['tasks'][1]['dependencies']=[]
        with self.assertRaisesRegex(ValueError,'dependency graph'):validate_artifact(self.artifact,source)

    def test_modified_raw_response_is_not_accepted_as_verified(self):
        source=deepcopy(self.source)
        case=next(c for c in source['cases'] if c.get('family')=='analysis')
        case['trace'][0]['response']['content'][0]['text']='A different observation'
        with self.assertRaisesRegex(ValueError,'verification mismatch'):validate_artifact(self.artifact,source)

    def test_effect_rule_cannot_treat_guidance_as_created_output(self):
        source=deepcopy(self.source)
        case=next(c for c in source['cases'] if c.get('family')=='effect')
        case['observation']['artifact_exists_after']=True
        with self.assertRaisesRegex(ValueError,'implementation output'):validate_artifact(self.artifact,source)

    def test_private_practice_values_cannot_be_retained(self):
        artifact=deepcopy(self.artifact)
        entry=next(e for e in artifact['memories'] if e['value'].get('kind')=='procedure')
        case=next(c for c in self.source['cases'] if c['id']==entry['case_id'])
        entry['value']['content']+=' '+case['forbidden_constants'][0]
        with self.assertRaisesRegex(ValueError,'private practice'):validate_artifact(artifact,self.source)

    def test_string_encoded_task_arrays_are_checked_without_coercion(self):
        for bad in ('not json','{}','[]','[{"dependencies":[{"name":"a"}]}]'):
            with self.subTest(bad=bad),self.assertRaises((ValueError,TypeError)):
                verify_inner_json({'tasksRaw':bad})
        with self.assertRaisesRegex(ValueError,'encoded string'):verify_inner_json({'tasksRaw':[{'name':'a'}]})
        verify_inner_json({'tasksRaw':'[{"name":"${NAME}","description":"${DESCRIPTION}","dependencies":[]}]'})

    def test_uuid_placeholder_witness_follows_the_real_tool_pattern(self):
        schema=self.catalog['mcp-shrimp-task-manager::get_task_detail']['inputSchema']
        value=witness({'taskId':'${ID}'},schema,{'ID':'Actual returned task ID'})
        validate_json(value,schema)

    def test_selective_change_rebuilds_only_the_relevant_success_rule(self):
        state=initialize(self.config,self.catalog);target=deepcopy(self.catalog)
        target['mcp-shrimp-task-manager::analyze_task']['description']+=' Updated review instruction.'
        selected=[]
        def builder(config,entry,*args):
            selected.append(entry['id'])
            entry['adaptation']={'status':'active','reason':'Unit contract change'}
            return entry,{'api_calls':1,'input_tokens':0,'output_tokens':0}
        updated,audit=evolve(self.config,'selective_patch',state,self.catalog,target,{'stage':'iter3','repeat':0},rebuilder=builder)
        self.assertEqual(audit['status'],'completed')
        self.assertEqual(len(selected),1)
        for before,after in zip(state['memories'],updated['memories']):
            if before['id'] not in selected:self.assertEqual(before,after)

    def test_all_original_tasks_receive_the_complete_mixed_library(self):
        from custom.experiment.selection import tasks
        state=initialize(self.config,self.catalog)
        self.assertEqual(as_artifact(state,self.catalog)['protocol'],'verified_tool_knowledge_k0_v2')
        for task in tasks(self.config):
            required={ALIASES.get(s,s) for s in task['servers']}
            tools,_=adapters.agent_tools(self.catalog,self.catalog,required)
            context,exposure=memory.render(self.config,self.catalog,required,ROOT/'.runtime/r/0000000000000000/workspace',
                api_names={t['meta']['benchmark_semantic_identity']:t['name'] for t in tools},artifact=as_artifact(state,self.catalog))
            self.assertEqual(len(exposure['selected_ids']),7)
            self.assertIn('effect_boundary',context)


if __name__=='__main__':unittest.main()
