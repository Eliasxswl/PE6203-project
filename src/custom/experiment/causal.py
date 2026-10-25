"""Controlled synthetic file-recovery diagnostic; real MCP calls, program outcomes."""
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing as mp
from pathlib import Path
import random
import subprocess

from . import adapters
from .core import make_client, runtime_for
from .results import atomic_json, redact, safe_error
from .selection import ROOT, digest, tree_hash

PROTOCOL = 'verified_file_recovery_causal_v2'
SERVER = '@modelcontextprotocol/server-filesystem'
CONDITIONS = ('no_rule', 'verified_rule', 'generated_rule', 'irrelevant_rule')
GOLD = ('When a file must be located below a directory, search_files matches paths relative to that directory. '
        'A pattern without **/ need not match nested files. For a filename keyword use **/*KEYWORD*, '
        'substituting the current keyword. Read the exact absolute path returned by the search. '
        'ENOENT only means the attempted path failed: discover the actual path rather than guessing filenames '
        'or declaring that no matching file exists. Completion requires a successful read of the located file.')


def call_template_schema():
    from pydantic import BaseModel, Field

    class ObservedCallTemplate(BaseModel):
        model_config = {'extra': 'forbid'}
        tool_id: str
        arguments: dict[str, object]
        evidence_call_ids: list[str] = Field(min_length=1)

    return ObservedCallTemplate


def procedure_schema():
    from pydantic import BaseModel, Field
    ObservedCallTemplate = call_template_schema()

    class ToolRecovery(BaseModel):
        """Transferable recovery procedure grounded in observed failure and correction."""
        model_config = {'extra': 'forbid'}
        tool_ids: list[str] = Field(min_length=1)
        content: str = Field(min_length=1, description='Concise general procedure; never copy practice filenames, keyword or file contents')
        applicability: str = Field(min_length=1, description='Observable situation in which the procedure applies')
        failed_assumption: str = Field(min_length=1, description='What failed and what assumption the observation contradicts')
        corrective_actions: list[str] = Field(min_length=1, description='Ordered general actions using current inputs and returned paths, not practice constants')
        verification: str = Field(min_length=1, description='Observable successful correction criterion, not merely a final claim')
        evidence_call_ids: list[str] = Field(min_length=2, description='IDs of the supplied real calls supporting both failure and verified correction')
        tool_call_templates: list[ObservedCallTemplate] = Field(default_factory=list)
        template_variables: dict[str, str] = Field(default_factory=dict)

    return ToolRecovery


def build_procedure(config, evidence, catalog, path):
    """One JSON-object request plus strict local validation; no tool-choice fallback or repair."""
    from importlib.metadata import version
    schema = procedure_schema()
    schema_json = schema.model_json_schema()
    journal = {'protocol': PROTOCOL, 'status': 'started', 'output_mode': 'json_object',
        'model': config['agent_model'], 'schema': schema_json,
        'evidence': {**deepcopy(evidence), 'catalog': deepcopy(catalog)},
        'versions': {'openai': version('openai')}, 'requests': []}
    shape = {'tool_ids': ['<exact ID from catalog>'], 'content': '<general procedure>',
        'applicability': '<observable situation>', 'failed_assumption': '<why the old attempt failed>',
        'corrective_actions': ['<general action using current inputs>'],
        'verification': '<observable successful correction criterion>',
        'evidence_call_ids': evidence.get('required_evidence_call_ids') or ['<observed failure ID>', '<observed verified-success ID>']}
    messages = [{'role': 'user', 'content':
        'Derive one reusable tool-recovery procedure from the observed failure and verified correction below. '
        'Explain the actual change that enabled success, rather than listing tool descriptions. '
        'Preserve failure and verified-success evidence IDs. Do not copy practice filenames, keyword, '
        'task text, record IDs, payload or private paths. Use current task inputs and tool-returned identifiers in the procedure.\n'
        'Observed practice evidence:\n' + json.dumps(journal['evidence'], ensure_ascii=False) +
        '\nReturn one JSON DATA RECORD with these seven direct keys. Replace every placeholder using '
        'the observations. Do not return a JSON Schema; do not wrap values in properties, title, type or required. '
        'No Markdown or extra text. Record shape:\n' + json.dumps(shape)}]
    journal['requests'].append({'status': 'started', 'messages': messages})
    atomic_json(path, journal)
    client = make_client(config, 'causal_build')
    try:
        response = client.chat.completions.create(model=config['agent_model'], messages=messages,
            temperature=0, max_tokens=8192, response_format={'type': 'json_object'})
        journal['requests'][0].update(status='completed', response=response.model_dump(mode='json'))
        if response.choices[0].finish_reason != 'stop' or getattr(response.choices[0].message, 'refusal', None):
            raise ValueError('Causal knowledge response was incomplete or refused')
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('Duplicate causal knowledge field: ' + key)
                result[key] = value
            return result
        value = json.loads(response.choices[0].message.content or '', object_pairs_hook=unique)
        value = schema.model_validate(value, strict=True).model_dump(mode='json', exclude_defaults=True)
        if not set(value['tool_ids']) <= set(catalog):
            raise ValueError('Causal knowledge refers to an unobserved tool')
        learned = [{'id': digest(value)[:24], 'value': value}]
        journal.update(status='completed', memories=learned)
        return learned, journal
    except Exception as exc:
        journal.update(status='rejected', error=safe_error(exc))
        if journal['requests'][0]['status'] == 'started':
            journal['requests'][0].update(status='failed', error=safe_error(exc))
        raise
    finally:
        atomic_json(path, journal)
        client.close()


def text(response):
    return '\n'.join(c.get('text', '') for c in (response or {}).get('content', []) if c.get('type') == 'text')


def source_hash():
    return digest({p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted((ROOT / 'src/custom').rglob('*.py'))})


def normalize(value, workspace):
    if isinstance(value, str):
        return value.replace(workspace.as_posix(), '${WORKSPACE}').replace(str(workspace), '${WORKSPACE}')
    if isinstance(value, dict):
        return {k: normalize(v, workspace) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v, workspace) for v in value]
    return value


def outcome(trace, target, expected):
    """Only an observed read of the correct file and exact bytes counts as success."""
    reads, errors = [], 0
    for call in trace:
        response = call.get('response') or {}
        errors += bool(response.get('isError'))
        if call.get('semantic_identity') != SERVER + '::read_text_file' or response.get('isError'):
            continue
        try:
            args = call['arguments']
            args = json.loads(args) if isinstance(args, str) else args
            correct = Path(args.get('path', '')).resolve() == target.resolve()
        except (ValueError, TypeError, AttributeError):
            correct = False
        if correct and text(response) == expected:
            reads.append(call['tool_call_id'])
    return {'success': bool(reads), 'verified_read_call_ids': reads, 'tool_errors': errors}


def generated_reference(learned, calls, verified, case, catalog):
    if not learned:
        raise ValueError('No structured causal knowledge produced; empty library is not an evaluated condition')
    known_ids = {c['tool_call_id'] for c in calls}
    failed_ids = {calls[0]['tool_call_id'], calls[1]['tool_call_id']}
    for entry in learned:
        ids = set(entry['value']['evidence_call_ids'])
        if not ids <= known_ids:
            raise ValueError('Generated knowledge cited unobserved practice calls')
        if not set(verified['verified_read_call_ids']) <= ids or not failed_ids & ids:
            raise ValueError('Generated knowledge did not preserve both failure and verified recovery evidence')
    rendered = json.dumps([e['value'] for e in learned], ensure_ascii=False)
    for token in (case['keyword'], case['content']):
        if token in rendered:
            raise ValueError('Generated rule memorized a practice constant instead of a transferable procedure')
    for identity in sorted(catalog, key=len, reverse=True):
        rendered = rendered.replace(identity, catalog[identity]['name'])
    return rendered


def probe(runtime, tools, case, journal=None):
    """Real failed lookup/read followed by discovery and a byte-verified read."""
    by_id = {t['meta']['benchmark_semantic_identity']: t for t in tools}
    calls = []

    def invoke(name, args):
        tool = by_id[SERVER + '::' + name]
        from custom.agents.tool_results import raw_result
        response = raw_result(runtime.call(tool['meta']['benchmark_remote_name'], args))
        calls.append({'tool_call_id': 'probe-' + str(len(calls)), 'semantic_identity': SERVER + '::' + name,
                      'arguments': json.dumps(args), 'response': response})
        if journal is not None:
            atomic_json(journal, {'observed_calls': calls})
        return response

    root = runtime.workspace.as_posix()
    invoke('read_text_file', {'path': root + '/missing.txt'})
    invoke('search_files', {'path': root, 'pattern': '*' + case['keyword'] + '*'})
    found = invoke('search_files', {'path': root, 'pattern': '**/*' + case['keyword'] + '*'})
    target = runtime.workspace / case['relative_path']
    if found.get('isError') or target.as_posix() not in text(found).replace('\\', '/'):
        raise ValueError('Practice recursive discovery did not return the target')
    invoke('read_text_file', {'path': target.as_posix()})
    verified = outcome(calls, target, case['content'])
    if not verified['success'] or not calls[0]['response'].get('isError'):
        raise ValueError('Practice error/correction evidence was not verified')
    return calls, verified


def execute_trial(spec):
    """One independent private runtime; its journal is never shared with another trial."""
    config, case, condition = spec['config'], spec['case'], spec['condition']
    if config.get('agent_backend') == 'langchain':
        from custom.agents.LangChainAgent import ChatModel
    else:
        from custom.agents.SimpleOpenAIAgent import ChatModel
    row = {'protocol': spec.get('protocol', PROTOCOL), 'case': case['id'], 'repeat': spec['repeat'], 'condition': condition,
           'status': 'running', 'model_attempts': [], 'rule_sha256': digest(spec['rule']),
           'rule_characters': len(spec['rule']), 'outcome': None}
    path = Path(spec['journal'])
    atomic_json(path, row)
    client = None
    try:
        with runtime_for(config, 'original', [SERVER], [], None) as runtime:
            tools, routing = adapters.agent_tools(adapters.semantic(runtime.catalog), runtime.catalog, {SERVER})
            tools = [t for t in tools if t['name'] in ('search_files', 'read_text_file')]
            client = make_client(config, 'causal_trial')

            def event(kind, payload):
                if kind == 'model_start':
                    row['model_attempts'].append({'status': 'started', 'messages': deepcopy(payload['messages'])})
                elif kind == 'model_completed':
                    row['model_attempts'][-1].update(status='completed', response=payload)
                elif kind == 'model_failed':
                    row['model_attempts'][-1].update(status='failed', error=payload)
                atomic_json(path, row)

            agent = ChatModel(model_name=config['agent_model'], client=client, tools=tools,
                max_round=4, tool_server_map=routing, workspace_root=runtime.workspace,
                file_exists=spec.get('file_tree', 'Discover the files with the available tools; no complete file tree is supplied in this diagnostic.'),
                temperature=config['agent_temperature'], max_new_tokens=config['agent_max_tokens'],
                tool_caller=runtime.call, event_callback=event, prompt_time=spec['prompt_time'])
            if spec['rule']:
                prefix = '' if spec.get('rule_is_context') else '\n\nReference from separate practice, not current observations:\n'
                agent.messages[0]['content'] += prefix + spec['rule'].replace('${WORKSPACE}', runtime.workspace.as_posix())
            query = spec.get('query') or ('Locate the text file whose filename contains the keyword ' + case['keyword'] +
                     ' somewhere below the workspace. Read that file with the available tool, then return its contents. '
                     'Do not guess its path or contents.')
            query = query.replace('${WORKSPACE}', runtime.workspace.as_posix())
            answer, _, _, _ = agent.run_with_server(query)
            row.update(answer=answer, trajectory_messages=agent.messages, raw_tool_trace=agent.raw_tool_trace,
                request_count=agent.request_count, stop_reason=agent.stop_reason,
                outcome=outcome(agent.raw_tool_trace, runtime.workspace / case['relative_path'], case['content']),
                target_relative_path=case['relative_path'], expected_content_sha256=digest(case['content']),
                status='failed' if agent.execution_error else 'completed', execution_error=agent.execution_error)
            if spec.get('verify_answer'):
                row['outcome']['task_success'] = row['outcome']['success'] and case['content'] in answer
    except Exception as exc:
        row.update(status='failed', error=safe_error(exc))
    finally:
        if client is not None:
            client.close()
        atomic_json(path, row)
    return row


def run(config, workers=1):
    from custom.utils.test_utils import offset_date
    if config.get('mode') == 'offline' or not 1 <= workers <= 10:
        raise ValueError('Use live mode and 1 to 10 workers')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    operator = subprocess.check_output(['git', 'config', 'user.name'], cwd=ROOT, text=True).strip()
    operator = ''.join(c if c.isalnum() or c in '-_' else '_' for c in operator)
    directory = ROOT / 'results' / (stamp + '_' + operator)
    directory.mkdir(parents=True)
    (directory / 'trials').mkdir()
    fixtures = directory / 'fixtures'
    fixtures.mkdir()
    cases = []
    for index in range(4):
        key = hashlib.sha256(('causal-v1-' + str(index)).encode()).hexdigest()[:10]
        case = {'id': 'practice' if index == 0 else 'heldout-' + str(index), 'keyword': 'item_' + key,
                'relative_path': '/'.join(['shelf_' + key] * (index + 1)) + '/item_' + key + '.txt',
                'content': 'Observed file payload: ' + hashlib.sha256(('payload-' + key).encode()).hexdigest()}
        target = fixtures / case['relative_path']
        target.parent.mkdir(parents=True)
        target.write_text(case['content'], encoding='utf-8')
        cases.append(case)
    effective = deepcopy(config)
    effective['fixtures'] = fixtures.relative_to(ROOT).as_posix()
    manifest = {'protocol': PROTOCOL, 'status': 'preparing', 'cases': cases,
        'repeats': config['agent_repeats'], 'workers': workers, 'conditions': list(CONDITIONS),
        'settings': effective, 'fixture_sha256': tree_hash(fixtures),
        'judge_calls': 0, 'request_limit': 4, 'task_source': 'Independent synthetic diagnostic; official tasks unchanged',
        'knowledge_output_mode': 'json_object_plus_local_schema; one request; no repair',
        'source_sha256': source_hash(),
        'claim_limit': 'Tests transfer of one file-recovery skill, not general memory benefit or server evolution.'}
    atomic_json(directory / 'experiment.json', manifest)
    print('Causal diagnostic: ' + str(directory), flush=True)
    try:
        with runtime_for(effective, 'original', [SERVER], [], None) as runtime:
            catalog = adapters.semantic(runtime.catalog)
            tools, _ = adapters.agent_tools(catalog, runtime.catalog, {SERVER})
            calls, verified = probe(runtime, tools, cases[0], directory / 'practice-probes.json')
            evidence = {'observed_calls': calls, 'program_verified': verified,
                        'required_success_evidence_ids': verified['verified_read_call_ids'],
                        'failed_observation_ids': [calls[0]['tool_call_id'], calls[1]['tool_call_id']],
                        'scope': 'Derive a reusable lookup/recovery rule. Do not retain practice paths, keyword or payload.'}
            normalized = normalize(evidence, runtime.workspace)
        short_catalog = {k: v for k, v in catalog.items() if k.endswith(('::search_files', '::read_text_file'))}
        learned, build, generated, rejection = [], {}, None, None
        try:
            learned, build = build_procedure(effective, normalized, short_catalog, directory / 'knowledge-build.json')
            generated = generated_reference(learned, calls, verified, cases[0], short_catalog)
        except Exception as exc:
            rejection = safe_error(exc)
            learned = []
        reference_length = len(generated) if generated is not None else len(GOLD)
        filler = 'Reference: archive labels use lowercase letters; document colors and display themes are cosmetic. '
        irrelevant = (filler * (reference_length // len(filler) + 1))[:reference_length]
        rules = {'no_rule': '', 'verified_rule': GOLD, 'generated_rule': generated, 'irrelevant_rule': irrelevant}
        manifest.update(status='running', knowledge=learned, knowledge_sha256=digest(learned),
            practice_evidence=normalized, builder_versions=build.get('versions'), rules=rules,
            knowledge_generation={'status': 'rejected' if rejection else 'accepted', 'rejection': rejection},
            control_length='Irrelevant reference character-matches generated reference, or verified rule if generation was rejected; not token matched')
        atomic_json(directory / 'experiment.json', manifest)
        specs = []
        pool = config['providers']['agent']
        for repeat in range(config['agent_repeats']):
            for position, case in enumerate(cases[1:]):
                order = list(CONDITIONS)
                random.Random(6203 + repeat * 10 + position).shuffle(order)
                for condition in order:
                    if rules[condition] is None:
                        continue  # Unavailable knowledge is never scored as an empty-memory tie.
                    trial_config = deepcopy(effective)
                    trial_config['providers']['agent'] = [pool[(position + repeat) % len(pool)]]
                    specs.append({'config': trial_config, 'case': case, 'condition': condition, 'repeat': repeat,
                        'rule': rules[condition], 'prompt_time': str(offset_date(0)),
                        'journal': str(directory / 'trials' / f'{condition}-{case["id"]}-{repeat}.json')})
        results = []
        if workers == 1:
            for spec in specs:
                results.append(execute_trial(spec))
        else:
            with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context('spawn')) as executor:
                futures = [executor.submit(execute_trial, spec) for spec in specs]
                for future in as_completed(futures):
                    results.append(future.result())
        summary = {'protocol': PROTOCOL, 'status': 'completed_with_rejected_knowledge' if rejection else 'completed',
                   'conditions': {}, 'judge_calls': 0, 'knowledge_generation': manifest['knowledge_generation'],
                   'fixture_unchanged': tree_hash(fixtures) == manifest['fixture_sha256'],
                   'source_unchanged': source_hash() == manifest['source_sha256']}
        for condition in CONDITIONS:
            rows = [r for r in results if r['condition'] == condition]
            planned = len(cases[1:]) * config['agent_repeats']
            summary['conditions'][condition] = {'planned': planned, 'executed': len(rows), 'not_attempted': planned - len(rows),
                'unavailable_reason': rejection if condition == 'generated_rule' else None,
                'execution_failures': sum(r['status'] != 'completed' for r in rows),
                'verified_successes': sum(bool((r.get('outcome') or {}).get('success')) for r in rows),
                'model_requests': sum(len(r['model_attempts']) for r in rows)}
        if any(r['status'] != 'completed' for r in results) or not summary['fixture_unchanged'] or not summary['source_unchanged']:
            summary['status'] = 'completed_with_failures'
        manifest['status'] = summary['status']
        atomic_json(directory / 'experiment.json', manifest)
        atomic_json(directory / 'causal-summary.json', summary)
        return directory, summary
    except BaseException as exc:
        manifest.update(status='failed_or_interrupted', error=safe_error(exc))
        atomic_json(directory / 'experiment.json', manifest)
        raise
