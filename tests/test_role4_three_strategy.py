"""Regression checks for shared baselines, paired samples, and invalid scores."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('role4_three',Path(__file__).resolve().parents[1]/'scripts/role4/analyze_three_strategy.py')
analysis=importlib.util.module_from_spec(spec);spec.loader.exec_module(analysis)


def row(s='no_update',stage='original',task=1,rep=0,tf=8):
    return {'identity':{'strategy':s,'stage':stage,'task_id':task,'repeat':rep},
        'score':{'task_fulfillment':tf,'planning_and_efficiency':9}}


class ThreeStrategyTests(unittest.TestCase):
    def test_shared_baseline_is_one_physical_record(self):
        rows={'base':row(),'copy':{**row('full_rewrite'),'shared_from':'base'}}
        self.assertEqual({analysis.resolve(rows,k) for k in rows},{'base'})

    def test_invalid_shared_score_fails(self):
        with self.assertRaises(ValueError):
            analysis.resolve({'base':row(),'copy':{**row(tf=7),'shared_from':'base'}},'copy')

    def test_shared_cycle_fails(self):
        with self.assertRaises(ValueError):
            analysis.resolve({'a':{**row(),'shared_from':'b'},'b':{**row(),'shared_from':'a'}},'a')

    def test_missing_score_excludes_pair_not_zero(self):
        rows={f'{s}/{v}/1/0':row(s,v) for s in analysis.STRATEGIES for v in analysis.STAGES}
        self.assertEqual(analysis.paired_ids(rows,analysis.STRATEGIES,analysis.STAGES),[(1,0)])
        rows['selective_patch/iter5/1/0']['score']=None
        self.assertEqual(analysis.paired_ids(rows,analysis.STRATEGIES,analysis.STAGES),[])
        self.assertEqual(analysis.paired_ids(rows,analysis.STRATEGIES,['original']),[(1,0)])

    def test_population_ecs_and_score_validity(self):
        self.assertEqual(analysis.ecs([9,9,9]),9)
        self.assertAlmostEqual(analysis.ecs([9,5,9]),5.78104858350254)
        self.assertFalse(analysis.valid(row(tf=float('nan'))))
        self.assertFalse(analysis.valid(row(tf=True)))


if __name__=='__main__':unittest.main()
