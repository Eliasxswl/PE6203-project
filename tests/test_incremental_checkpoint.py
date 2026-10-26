from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from custom.experiment import checkpoint
from custom.experiment.results import Store, atomic_json
from custom.experiment.selection import ROOT


class IncrementalCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT/'.runtime')
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        atomic_json(self.path/'experiment.json', {'schema_version':1})
        atomic_json(self.path/'records.json', {'schema_version':1, 'status':'prepared',
            'events':[], 'episodes':{}, 'trajectories':{}, 'aggregate':{}, 'initial_snapshot':None})
        self.store = Store(self.path)
        self.store.SNAPSHOT_SECONDS = float('inf')

    def test_each_event_is_durable_without_rewriting_the_snapshot(self):
        original = (self.path/'records.json').read_bytes()
        self.store.records['status']='running'
        with patch('custom.experiment.results.atomic_json', side_effect=AssertionError('No full rewrite')):
            for i in range(20):self.store.event('unit_event', number=i)
        self.assertEqual((self.path/'records.json').read_bytes(),original)
        reloaded=Store(self.path)
        self.assertEqual(reloaded.records['status'],'running')
        self.assertEqual(reloaded.records['events'],self.store.records['events'])
        self.assertEqual(reloaded.sequence,20)

    def test_snapshot_and_pruning_do_not_duplicate_events(self):
        self.store.event('first');self.store.save()
        self.assertEqual(checkpoint.replay(self.store.journal_path,self.store.sequence),[])
        self.store.event('second')
        reloaded=Store(self.path)
        self.assertEqual([e['kind'] for e in reloaded.records['events']],['first','second'])
        self.assertEqual(reloaded.sequence,2)

    def test_failed_snapshot_remains_recoverable_from_the_journal(self):
        self.store.event('committed')
        with patch('custom.experiment.results.atomic_json',side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):self.store.save()
        self.assertEqual(Store(self.path).records['events'],self.store.records['events'])

    def test_crash_after_snapshot_before_pruning_does_not_replay_twice(self):
        self.store.event('committed')
        with patch('custom.experiment.checkpoint.prune',side_effect=OSError('crash after publish')):
            with self.assertRaises(OSError):self.store.save()
        reloaded=Store(self.path)
        self.assertEqual(len(reloaded.records['events']),1)
        reloaded.event('next')
        self.assertEqual(len(Store(self.path).records['events']),2)

    def test_failed_append_does_not_advance_memory_or_acknowledgement(self):
        before=deepcopy(self.store.records)
        with patch('custom.experiment.checkpoint.append',side_effect=OSError('commit failed')):
            with self.assertRaises(OSError):self.store.event('uncommitted')
        self.assertEqual(self.store.records,before)
        self.assertEqual(self.store.sequence,0)

    def test_stale_writer_is_rejected(self):
        stale=Store(self.path)
        self.store.event('first writer')
        with self.assertRaisesRegex(ValueError,'Another writer'):stale.event('stale writer')
        self.assertEqual(len(Store(self.path).records['events']),1)

    def test_interrupted_transaction_is_rolled_back(self):
        self.store.event('committed')
        with checkpoint.connection(self.store.journal_path) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO events VALUES (2, ?)', ('not a committed JSON event',))
            db.execute('UPDATE progress SET sequence=2')
        self.assertEqual(len(Store(self.path).records['events']),1)

    def test_missing_committed_prefix_is_rejected(self):
        self.store.event('first');self.store.event('second')
        with checkpoint.connection(self.store.journal_path) as db:
            with db:db.execute('DELETE FROM events WHERE sequence=1')
        with self.assertRaisesRegex(ValueError,'missing event'):Store(self.path)

    def test_snapshot_reader_retries_a_publish_prune_race(self):
        self.store.event('first')
        replay=checkpoint.replay
        calls=[]
        def race(path,sequence):
            calls.append(sequence)
            if len(calls)==1:
                self.store.save()
                raise ValueError('Reader saw the older snapshot')
            return replay(path,sequence)
        with patch('custom.experiment.checkpoint.replay',side_effect=race):loaded=Store(self.path)
        self.assertEqual(calls,[0,1])
        self.assertEqual(len(loaded.records['events']),1)

    def test_sensitive_values_are_redacted_before_incremental_persistence(self):
        self.store.event('secret_test', api_key='private-unit-test-key', text='Authorization: Bearer private-unit-test-key')
        payload=checkpoint.replay(self.store.journal_path,0)
        self.assertNotIn('private-unit-test-key',json.dumps(payload))


if __name__=='__main__':unittest.main()
