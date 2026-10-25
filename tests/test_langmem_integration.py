"""Integration boundaries: provenance, dependency scope, dispatch and isolation."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import tempfile
import unittest
from unittest.mock import patch
from custom.experiment.selection import ROOT

from custom.experiment import memory
from custom.experiment.selection import digest, file_hash


def fixture(tmp_path):
    source = tmp_path / 'source.json'
    source.write_text('{}', encoding='utf-8')
    catalog = {'a::read': {'server': 'a'}, 'b::add': {'server': 'b'}}
    records = [
        {'id': 'single', 'value': {'tool_ids': ['a::read'], 'content': 'Read ${WORKSPACE}/notes.'}},
        {'id': 'workflow', 'value': {'tool_ids': ['a::read', 'b::add'], 'content': 'Pass observed read data to add.'}}]
    artifact = {'protocol': memory.PROTOCOL, 'source_sha256': file_hash(source),
                'catalog': catalog, 'memories': records, 'memory_sha256': digest(records)}
    (tmp_path / 'artifact.json').write_text(json.dumps(artifact), encoding='utf-8')
    return {'memory': {'artifact': 'artifact.json', 'source': 'source.json', 'inject': True, 'context_chars': 2000}}, catalog, tmp_path


class LangMemTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / '.runtime')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.addCleanup(patch.stopall)
        patch.object(memory, 'ROOT', self.directory).start()
        self.frozen = fixture(self.directory)

    def test_does_not_expose_partial_cross_server_workflow(self):
        frozen = self.frozen
        config, catalog, path = frozen
        context, exposure = memory.render(config, catalog, {'a'}, path)
        assert exposure['selected_ids'] == ['single']
        assert 'Pass observed read data' not in context
        assert path.as_posix() in context


    def test_off_condition_keeps_artifact_without_exposing_it(self):
        frozen = self.frozen
        config, catalog, path = frozen
        original = (path / 'artifact.json').read_bytes()
        enabled, exposed = memory.render(config, catalog, {'a', 'b'}, path)
        config['memory']['inject'] = False
        disabled, hidden = memory.render(config, catalog, {'a', 'b'}, path)
        assert enabled and disabled == ''
        assert hidden['selected_ids'] == []
        assert exposed['artifact_sha256'] == hidden['artifact_sha256']
        assert (path / 'artifact.json').read_bytes() == original


    def test_no_truncated_memory_is_injected(self):
        frozen = self.frozen
        config, catalog, path = frozen
        config['memory']['context_chars'] = 10
        context, exposed = memory.render(config, catalog, {'a', 'b'}, path)
        assert context == '' and exposed['context_characters'] == 0


    def test_source_drift_prevents_loading(self):
        frozen = self.frozen
        config, _, path = frozen
        (path / 'source.json').write_text('{"changed":true}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'fingerprint'):
            memory.load(config)

    def test_only_actual_api_aliases_are_shown_to_the_model(self):
        config, catalog, path = self.frozen
        artifact = json.loads((path / 'artifact.json').read_text(encoding='utf-8'))
        artifact['memories'][0]['value']['content'] = 'Call a::read on ${WORKSPACE}/notes.'
        artifact['memory_sha256'] = digest(artifact['memories'])
        (path / 'artifact.json').write_text(json.dumps(artifact), encoding='utf-8')
        context, exposed = memory.render(config, catalog, {'a', 'b'}, path,
            api_names={'a::read': 'read_api', 'b::add': 'add_api'})
        assert 'read_api' in context and 'add_api' in context
        assert 'a::read' not in context and 'b::add' not in context
        assert exposed['presentation'] == 'visible_api_names_v1'

    def test_missing_real_alias_is_rejected(self):
        config, catalog, path = self.frozen
        with self.assertRaisesRegex(ValueError, 'actual API alias'):
            memory.render(config, catalog, {'a', 'b'}, path, api_names={'a::read': 'read_api'})


    def test_sdk_wrapper_dispatches_once_and_preserves_failure(self):
        tmp_path = self.directory
        calls = []
        response = SimpleNamespace(model_dump=lambda **kwargs: {'id': 'real-response'})
        def send(**kwargs):
            calls.append(kwargs)
            return response
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=send)))
        journal = {'requests': []}
        wrapper = memory.RecordedCompletions(client, journal, tmp_path / 'journal.json', limit=1)
        raw = wrapper.with_raw_response.create(model='test', messages=[])
        assert len(calls) == 1
        assert raw.parse() is response and raw.parse() is response
        assert len(calls) == 1
        with self.assertRaisesRegex(RuntimeError, 'budget'):
            wrapper.create(model='test', messages=[])
        assert len(calls) == 1


    def test_practice_namespaces_cannot_modify_unrelated_memory(self):
        frozen = self.frozen
        config, catalog, path = frozen
        config['memory']['artifact'] = 'new.json'
        source = {'origin': 'independent_synthetic_practice', 'catalog': catalog, 'cases': [
            {'id': 'first', 'tool_ids': ['a::read'], 'scenario': 'practice a', 'trace': []},
            {'id': 'second', 'tool_ids': ['b::add'], 'scenario': 'practice b', 'trace': []}]}
        (path / 'source.json').write_text(json.dumps(source), encoding='utf-8')
        existing_inputs = []
        def extract(config, evidence, existing, observed, journal):
            existing_inputs.append(deepcopy(existing))
            key = next(iter(observed))
            return [{'id': key, 'value': {'tool_ids': [key], 'content': key}}], {'requests': [], 'versions': {}, 'model': 'test'}
        with patch.object(memory, 'extract', extract):
            result = memory.prepare(config)
        assert existing_inputs == [[], []]
        assert {m['id'] for m in result['memories']} == set(catalog)
