"""No model/runtime imports: verify the intervention and negative-result handling."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('task403_ablation',Path(__file__).resolve().parents[1]/'scripts/role4/task403_ablation.py')
ab=importlib.util.module_from_spec(spec);spec.loader.exec_module(ab)


def snapshot(changed=False):
    catalog={k:{'server':'mock','name':k,'description':('new' if changed and k=='mock::a' else 'old'),
        'inputSchema':{'type':'object'}} for k in ('mock::a','mock::b')}
    memories=[{'id':k,'value':{'tool_ids':['mock::'+k],'content':'rebuilt' if changed else 'previous'}} for k in ('a','b')]
    state={'memories':memories,'origins':{'a':{},'b':{}},'memory_sha256':ab.digest(memories),
        'dependency_hashes':{e['id']:{t:ab.digest(catalog[t]) for t in e['value']['tool_ids']} for e in memories}}
    return {'catalog':catalog,'knowledge':deepcopy(catalog),'experience_state':state}


class Task403AblationTests(unittest.TestCase):
    def test_only_unaffected_memory_is_restored(self):
        before,after=snapshot(),snapshot(True);states,untouched,affected=ab.arm_states(before,after)
        self.assertEqual(untouched,['b']);self.assertEqual(affected,['a'])
        self.assertEqual(states[ab.ARMS[0]]['memories'][0],states[ab.ARMS[1]]['memories'][0])
        self.assertEqual(states[ab.ARMS[1]]['memories'][1],before['experience_state']['memories'][1])
        self.assertNotEqual(states[ab.ARMS[0]]['memories'][1],states[ab.ARMS[1]]['memories'][1])

    def test_source_snapshots_are_not_mutated(self):
        before,after=snapshot(),snapshot(True);expected=deepcopy((before,after))
        states,_,_=ab.arm_states(before,after)
        states[ab.ARMS[0]]['memories'][0]['value']['content']='mutated'
        self.assertEqual((before,after),expected)
        self.assertNotEqual(states[ab.ARMS[0]]['memories'][0],states[ab.ARMS[1]]['memories'][0])

    def test_changed_provenance_is_rejected(self):
        before,after=snapshot(),snapshot(True);after['experience_state']['origins']['a']={'different':True}
        with self.assertRaises(ValueError):ab.arm_states(before,after)

    def test_checksum_and_identity_guards(self):
        plan={'protocol':'test'};plan['plan_sha256']=ab.digest(plan);ab.verify(plan)
        plan['protocol']='edited'
        with self.assertRaises(ValueError):ab.verify(plan)
        before,after=snapshot(),snapshot(True);after['experience_state']['memories'].pop()
        with self.assertRaises(ValueError):ab.arm_states(before,after)

    def test_missing_pairs_not_zero_and_unfavorable_results_retained(self):
        rows={}
        for arm,tf in zip(ab.ARMS,(9,4)):
            rows[f'{arm}/iter5/403/0']={'identity':{'strategy':arm,'repeat':0},
                'score':{'task_fulfillment':tf},'judge_attempts':[]}
        result=ab.summarize({'status':'completed','trajectories':rows})
        self.assertEqual(result['mean_tf_rewrite_minus_preserve'],5)
        rows[f'{ab.ARMS[1]}/iter5/403/0']['score']=None
        result=ab.summarize({'status':'partial','trajectories':rows})
        self.assertIsNone(result['mean_tf_rewrite_minus_preserve'])
        self.assertEqual(result['paired'],[])


if __name__=='__main__':unittest.main()
