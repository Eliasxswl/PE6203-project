"""Optional paid updater with a persistent per-experiment reservation budget.

Preparation has one writer under the experiment lock. Reservations survive failed
or unknown requests and resume; this is not a platform-wide API key credit limit.
"""
from copy import deepcopy
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import re
from types import SimpleNamespace
from urllib.parse import urlsplit

from .results import atomic_json, safe_error, utc_now
from .selection import read_json


def validate_options(options):
    required = {'api_key_env', 'base_url_env', 'budget_usd', 'prompt_usd_per_million',
                'completion_usd_per_million', 'reasoning_effort'}
    if not isinstance(options, dict) or set(options) != required:
        raise ValueError('update_provider requires explicit credentials, price limits, reasoning and budget')
    for name in ('api_key_env', 'base_url_env'):
        if not isinstance(options[name], str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', options[name]):
            raise ValueError('Updater credentials must be environment variable names')
    for name in ('budget_usd', 'prompt_usd_per_million', 'completion_usd_per_million'):
        value = options[name]
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError('Updater budget and price limits must be finite positive numbers')
    if options['reasoning_effort'] not in ('none', 'low', 'medium', 'high'):
        raise ValueError('Unsupported updater reasoning effort')


def credentials(options):
    endpoint = os.environ.get(options['base_url_env'], '').rstrip('/')
    parsed = urlsplit(endpoint)
    if (parsed.scheme != 'https' or parsed.netloc != 'openrouter.ai' or parsed.path != '/api/v1'
            or parsed.query or parsed.fragment):
        raise ValueError('Paid updater budget routing requires https://openrouter.ai/api/v1')
    secret = os.environ.get(options['api_key_env'])
    if not secret:
        raise ValueError('Set the configured updater API key in the local .env')
    return endpoint, secret


class OpenRouterUpdater:
    def __init__(self, config, path, emit=None, raw=None):
        options = config['memory']['update_provider']
        validate_options(options)
        endpoint, secret = credentials(options)
        self.path, self.options = Path(path), options
        self.emit = emit or (lambda event: None)
        self.model = config['memory']['model']
        self.policy = {'model': self.model, 'endpoint': endpoint, **options}
        self.last_request = None
        if self.path.exists():
            ledger = read_json(self.path)
            if ledger['policy'] != self.policy:
                raise ValueError('Updater budget policy changed; create a fresh experiment')
        else:
            ledger = {'protocol': 'updater_reservation_budget_v1', 'policy': self.policy,
                'scope': 'This experiment; platform API key credit limit unchanged',
                'reserved_usd': '0', 'reported_usd': '0', 'all_costs_reported': True, 'requests': []}
            atomic_json(self.path, ledger)
        self.raw = raw
        if raw is None:
            import httpx
            from openai import OpenAI
            self.raw = OpenAI(api_key=secret, base_url=endpoint, max_retries=0,
                http_client=httpx.Client(follow_redirects=False,
                    timeout=httpx.Timeout(config['runtime']['model_timeout'], connect=config['runtime']['connect_timeout'])))
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        allowed = {'model', 'messages', 'temperature', 'max_tokens', 'response_format'}
        if set(kwargs) - allowed or kwargs.get('model') != self.model:
            raise ValueError('Updater budget permits only the fixed text-generation request')
        request = deepcopy(kwargs)
        request.pop('temperature', None)
        request['reasoning_effort'] = self.options['reasoning_effort']
        request['extra_body'] = {'provider': {'allow_fallbacks': False, 'require_parameters': True,
            'max_price': {'prompt': self.options['prompt_usd_per_million'],
                          'completion': self.options['completion_usd_per_million'], 'request': 0}},
            'usage': {'include': True}}
        cap = request.get('max_tokens')
        if type(cap) is not int or not 0 < cap <= 8192:
            raise ValueError('Paid updater requires an output limit of at most 8192 tokens')
        if any(not isinstance(m.get('content'), str) for m in request.get('messages', [])):
            raise ValueError('Updater budget accepts plain text only')
        size = len(json.dumps(request, ensure_ascii=False).encode('utf-8'))
        if size > 100000:
            raise ValueError('Updater input exceeds the bounded short-context request size')
        # UTF-8 bytes bound BPE tokens; reserve generous framing and a 20% margin.
        upper = ((Decimal(size + 10000) * Decimal(str(self.options['prompt_usd_per_million'])) +
                  Decimal(cap) * Decimal(str(self.options['completion_usd_per_million']))) /
                 Decimal(1000000)) * Decimal('1.2')
        ledger = read_json(self.path)
        if ledger.get('blocked') or Decimal(ledger['reserved_usd']) + upper > Decimal(str(self.options['budget_usd'])):
            raise ValueError('Updater budget exhausted or blocked; no request dispatched')
        item = {'sequence': len(ledger['requests']), 'status': 'dispatched', 'started_at': utc_now(),
                'reserved_upper_bound_usd': str(upper), 'request': request}
        ledger['reserved_usd'] = str(Decimal(ledger['reserved_usd']) + upper)
        ledger['requests'].append(item)
        atomic_json(self.path, ledger)  # Persist before a potentially billable call.
        self.last_request = item
        try:
            response = self.raw.chat.completions.create(**request)
            data = response.model_dump(mode='json')
            item.update(status='completed', response=data)
            cost = (data.get('usage') or {}).get('cost')
            if cost is None:
                ledger['all_costs_reported'] = False
            else:
                amount = Decimal(str(cost))
                if not amount.is_finite() or amount < 0:
                    ledger['blocked'] = True
                    raise ValueError('Invalid updater billing response')
                item['reported_cost_usd'] = str(amount)
                ledger['reported_usd'] = str(Decimal(ledger['reported_usd']) + amount)
                if amount > upper:
                    ledger['blocked'] = True
                    raise ValueError('Updater cost exceeded its reservation; further calls blocked')
            return response
        except Exception as exc:
            item.update(status='failed', error=safe_error(exc))
            if 'reported_cost_usd' not in item:
                ledger['all_costs_reported'] = False
            raise
        finally:
            atomic_json(self.path, ledger)
            self.emit({'kind': 'experience_update_budget', 'reserved_usd': ledger['reserved_usd'],
                'reported_usd': ledger['reported_usd'], 'all_costs_reported': ledger['all_costs_reported'],
                'requests': len(ledger['requests'])})

    def close(self):
        self.raw.close()
