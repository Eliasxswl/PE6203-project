"""New task subsets retain frozen compatibility checks and per-server failure isolation."""
from copy import deepcopy
import unittest

from custom.experiment.memory_ablation import check_frozen_scopes


def tool(server, name):
    return {'server': server, 'name': name, 'description': 'Frozen public description', 'inputSchema': {'type': 'object'}}


class MemoryScopeTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {'a::read': tool('a', 'read'), 'b::add': tool('b', 'add')}
        self.artifact = {'catalog': self.catalog}

    def test_subset_need_not_start_unrelated_frozen_servers(self):
        check_frozen_scopes({'catalog': {'a::read': self.catalog['a::read']}, 'errors': {}}, self.artifact, {'a'})

    def test_new_public_domain_is_allowed_without_rewriting_old_knowledge(self):
        before = deepcopy(self.artifact)
        current = {'a::read': self.catalog['a::read'], 'c::clock': tool('c', 'clock')}
        check_frozen_scopes({'catalog': current, 'errors': {}}, self.artifact, {'a', 'c'})
        self.assertEqual(self.artifact, before)

    def test_changed_or_missing_known_tool_is_rejected(self):
        changed = deepcopy(self.catalog)
        changed['a::read']['description'] = 'Changed'
        for current in (changed, {'b::add': self.catalog['b::add']}):
            with self.assertRaisesRegex(ValueError, 'required knowledge domain'):
                check_frozen_scopes({'catalog': current, 'errors': {}}, self.artifact, {'a', 'b'})

    def test_failed_backend_is_left_for_task_level_failure_handling(self):
        check_frozen_scopes({'catalog': {'b::add': self.catalog['b::add']}, 'errors': {'a': {'message': 'startup failed'}}},
                            self.artifact, {'a', 'b'})
