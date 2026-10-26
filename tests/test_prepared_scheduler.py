from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from custom.experiment.parallel import supervise
from custom.experiment.results import identity
from custom.experiment.selection import STAGES


class PreparedSchedulerTests(unittest.TestCase):
    def test_frozen_jobs_use_two_pools_with_shared_early_executed_first(self):
        store=SimpleNamespace(records={'trajectories':{}},apply=Mock(),event=Mock(),save=Mock())
        tasks=[{'idx':n,'servers':{}} for n in [9,24]]
        specs=[]
        for strategy in ['no_update','full_rewrite','selective_patch']:
            for repeat in range(3):
                stages={s:{'status':'ready','knowledge':{'stage':s},'experience_state':{'stage':s}}
                        for s in STAGES}
                spec={'strategy':strategy,'repeat':repeat,'tasks':tasks,'episode':{'stages':stages}}
                specs.append(spec)
                for stage in STAGES:
                    for task in tasks:
                        row={'status':'pending'}
                        if stage=='original' and strategy!='no_update':
                            row['shared_from']=identity('no_update',stage,task['idx'],repeat)
                        store.records['trajectories'][identity(strategy,stage,task['idx'],repeat)]=row
        original=deepcopy(specs)
        with patch('custom.experiment.parallel.supervise_stage') as pool:
            supervise(specs,store,10,5)
        self.assertEqual(pool.call_count,2)
        first=pool.call_args_list[0].args[0];second=pool.call_args_list[1].args[0]
        self.assertEqual(len(first),6)
        self.assertTrue(all(j['stage']=='original' and j['strategy']=='no_update' for j in first))
        self.assertEqual(len(second),36)
        self.assertEqual({j['stage'] for j in second},{'iter3','iter5'})
        self.assertEqual({j['strategy'] for j in second},{'no_update','full_rewrite','selective_patch'})
        self.assertEqual(specs,original)
        for job in first+second:
            self.assertEqual(job['knowledge']['stage'],job['stage'])
            self.assertEqual(job['experience_state']['stage'],job['stage'])
        store.save.assert_called_once()

    def test_unprepared_states_keep_ordered_catalog_update_dependencies(self):
        spec={'episode':{'stages':{}}};store=Mock()
        with patch('custom.experiment.parallel.run_episode') as run,patch('custom.experiment.parallel.supervise_stage') as pool:
            supervise([spec],store,3,5)
        run.assert_called_once();pool.assert_not_called()


if __name__=='__main__':unittest.main()
