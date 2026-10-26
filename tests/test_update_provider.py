from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from custom.experiment.selection import ROOT, load_config, read_json
from custom.experiment.update_provider import OpenRouterUpdater, validate_options


class UpdateProviderTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT/'config/experience-evolution.json')
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'.runtime')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'budget.json'
        opts = self.config['memory']['update_provider']
        self.env = patch.dict('os.environ', {opts['api_key_env']: 'unit-test-secret',
            opts['base_url_env']: 'https://openrouter.ai/api/v1'})
        self.env.start();self.addCleanup(self.env.stop)
        self.raw = Mock()
        self.raw.chat.completions.create.return_value = SimpleNamespace(
            model_dump=lambda **kw: {'usage': {'cost': 0.00001}})
        self.request = {'model': self.config['memory']['model'], 'messages': [{'role':'user','content':'Test JSON'}],
            'temperature':0, 'max_tokens':8192, 'response_format': {'type':'json_object'}}

    def client(self):
        return OpenRouterUpdater(self.config, self.path, raw=self.raw)

    def test_request_price_and_model_routing_are_fixed_and_reserved_before_dispatch(self):
        def respond(**kwargs):
            ledger = read_json(self.path)
            self.assertGreater(Decimal(ledger['reserved_usd']), 0)
            self.assertEqual(len(ledger['requests']), 1)
            return SimpleNamespace(model_dump=lambda **kw: {'usage': {'cost':0.00001}})
        self.raw.chat.completions.create.side_effect = respond
        client = self.client();client.create(**self.request)
        args = self.raw.chat.completions.create.call_args.kwargs
        self.assertNotIn('temperature', args)
        self.assertEqual(args['reasoning_effort'], 'none')
        self.assertFalse(args['extra_body']['provider']['allow_fallbacks'])
        self.assertEqual(args['extra_body']['provider']['max_price']['request'], 0)
        self.assertEqual(read_json(self.path)['reported_usd'], '0.00001')

    def test_budget_reservations_survive_new_clients_and_block_before_call(self):
        self.config['memory']['update_provider']['budget_usd'] = 0.008
        self.client().create(**self.request)
        with self.assertRaisesRegex(ValueError, 'budget exhausted'):
            self.client().create(**self.request)
        self.assertEqual(self.raw.chat.completions.create.call_count, 1)
        self.assertEqual(len(read_json(self.path)['requests']), 1)

    def test_unknown_outcome_is_not_retried_or_refunded(self):
        self.config['memory']['update_provider']['budget_usd'] = 0.008
        self.raw.chat.completions.create.side_effect = TimeoutError('Unknown provider outcome')
        with self.assertRaises(TimeoutError):self.client().create(**self.request)
        ledger = read_json(self.path)
        self.assertGreater(Decimal(ledger['reserved_usd']), 0)
        self.assertFalse(ledger['all_costs_reported'])
        with self.assertRaisesRegex(ValueError,'budget exhausted'):self.client().create(**self.request)
        self.assertEqual(self.raw.chat.completions.create.call_count, 1)

    def test_missing_reported_cost_is_distinct_from_zero(self):
        self.raw.chat.completions.create.return_value = SimpleNamespace(model_dump=lambda **kw:{'usage':{}})
        self.client().create(**self.request)
        self.assertFalse(read_json(self.path)['all_costs_reported'])
        self.assertNotIn('reported_cost_usd', read_json(self.path)['requests'][0])

    def test_policy_change_cannot_reset_a_resume_budget(self):
        self.client().create(**self.request)
        self.config['memory']['update_provider']['budget_usd'] = 2
        with self.assertRaisesRegex(ValueError, 'policy changed'):self.client()

    def test_nontext_or_unbounded_requests_are_rejected_without_dispatch(self):
        client = self.client()
        for changes in ({'max_tokens':9000}, {'model':'other-model'}, {'tools':[]},
                        {'messages':[{'role':'user','content':[{'type':'image_url'}]}]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                client.create(**{**self.request, **changes})
        self.raw.chat.completions.create.assert_not_called()

    def test_billing_violation_blocks_further_dispatch(self):
        self.raw.chat.completions.create.return_value = SimpleNamespace(model_dump=lambda **kw:{'usage':{'cost':0.1}})
        client = self.client()
        with self.assertRaisesRegex(ValueError,'cost exceeded'):client.create(**self.request)
        with self.assertRaisesRegex(ValueError,'budget exhausted'):client.create(**self.request)
        self.assertTrue(read_json(self.path)['blocked'])
        self.assertEqual(self.raw.chat.completions.create.call_count, 1)

    def test_invalid_budget_and_non_openrouter_endpoint_are_rejected(self):
        options = self.config['memory']['update_provider']
        for number in (0, -1, True, float('nan')):
            with self.subTest(number=number), self.assertRaises(ValueError):
                validate_options({**options,'budget_usd':number})
        with patch.dict('os.environ',{options['base_url_env']:'https://example.com/api/v1'}):
            with self.assertRaisesRegex(ValueError,'routing requires'):self.client()

    def test_paid_provider_requires_explicit_update_model(self):
        from custom.experiment.memory import validate_options as validate_memory
        options = deepcopy(self.config['memory'])
        options.pop('model')
        with self.assertRaisesRegex(ValueError,'explicit model'):validate_memory(options)

    def test_real_rebuilder_uses_dedicated_client_and_reports_actual_cost(self):
        from custom.experiment import memory
        from custom.experiment.experience_state import initialize, rewrite, submission, evolve
        from custom.experiment.testing import Message, Response
        config = self.config
        catalog = memory.load(config)['catalog'];state = initialize(config, catalog)
        entry = state['memories'][1]
        from test_update_contract import wire_record
        response = Response(Message(json.dumps(wire_record(entry,catalog))))
        response.usage = SimpleNamespace(prompt_tokens=8,completion_tokens=9,
            model_dump=lambda:{'prompt_tokens':8,'completion_tokens':9,'cost':0.00001})
        self.raw.chat.completions.create.return_value = response
        def factory(cfg,path,emit=None):return OpenRouterUpdater(cfg,path,emit=emit,raw=self.raw)
        with patch('custom.experiment.update_provider.OpenRouterUpdater',side_effect=factory), patch(
                'custom.experiment.core.make_client',side_effect=AssertionError('Do not use the Agent provider')):
            _,journal = rewrite(config,entry,state['origins'][entry['id']],catalog,catalog,
                {'stage':'iter3','repeat':0,'strategy':'full_rewrite','budget_path':str(self.path)},1,lambda e:None)
        self.assertEqual(journal['api_calls'], 1)
        self.assertEqual(journal['api_cost'], 0.00001)
        self.assertEqual(journal['provider']['api_key_env'],'OPENROUTE_API_KEY')
        def builder(*args):return deepcopy(args[1]), deepcopy(journal)
        _,audit = evolve(config,'full_rewrite',state,catalog,catalog,{'stage':'iter3','repeat':0},rebuilder=builder)
        self.assertAlmostEqual(audit['api_cost'], 0.00003)
        self.assertEqual(audit['cost_currency'],'USD')


if __name__ == '__main__':unittest.main()
