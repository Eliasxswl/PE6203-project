"""Freeze verified independent recovery practice for the existing paired experiment."""
from copy import deepcopy
import json
from pathlib import Path

from . import adapters
from .causal import build_procedure, normalize, procedure_schema, text
from .core import initial_snapshot, make_client, runtime_for
from .results import atomic_json, safe_error
from .selection import ROOT, digest, file_hash, read_json

PROTOCOL = 'verified_tool_recovery_k0_v1'
TASKS = 'mcp-tasks'
FILE_PRACTICE = 'results/20261024T205056.788851Z_Kevin'


def validate_entry(entry, case, catalog):
    value = procedure_schema().model_validate(entry['value'], strict=True).model_dump(mode='json')
    calls = {c['tool_call_id']: c for c in case['trace']}
    if len(calls) != len(case['trace']):
        raise ValueError('Duplicate practice call identity')
    failed = {k for k, c in calls.items() if c['response'].get('isError')}
    for k, c in calls.items():
        proof = c.get('failure_evidence')
        if proof:
            if proof.get('kind') not in ('tool_reported_error', 'tool_reported_schema_error') or proof.get('response_sha256') != digest(c['response']):
                raise ValueError('Invalid observed tool-failure evidence')
            message = text(c['response'])
            if proof['kind'] == 'tool_reported_error':
                try:
                    observed = json.loads(message).get('status') == 'error'
                except (ValueError, AttributeError):
                    observed = False
            else:
                observed = message.startswith(('tasks 參數格式錯誤', 'tasksRaw 參數格式錯誤'))
            if not observed:
                raise ValueError('Failure classification contradicts the raw tool response')
            failed.add(k)
    verified = {k for k, c in calls.items() if c.get('verification') and k not in failed
                and c['semantic_identity'] == case['required_success_tool']}
    for k in verified:
        if calls[k]['verification']['response_sha256'] != digest(calls[k]['response']):
            raise ValueError('Practice verification response mismatch')
    cited = set(value['evidence_call_ids'])
    if not cited <= calls.keys() or not cited & failed or not cited & verified:
        raise ValueError('Knowledge requires actual error and verified correction evidence')
    if not set(value['tool_ids']) <= set(catalog) or not set(value['tool_ids']) <= {c['semantic_identity'] for c in calls.values()}:
        raise ValueError('Knowledge refers to an unobserved tool')
    for template in value.get('tool_call_templates', []):
        refs = set(template['evidence_call_ids'])
        if (not refs or not refs <= calls.keys() or refs & failed
                or template['tool_id'] not in value['tool_ids']
                or any(calls[k]['semantic_identity'] != template['tool_id'] for k in refs)):
            raise ValueError('Call template lacks successful matching tool evidence')
    rendered = json.dumps(value, ensure_ascii=False)
    for token in case['forbidden_constants']:
        if token and token in rendered:
            raise ValueError('Knowledge retained a practice constant')
    return value


def validate_artifact(artifact, source):
    if source.get('origin') != 'independent_verified_recovery_practice':
        raise ValueError('Recovery memory requires independent practice provenance')
    if source['catalog'] != artifact['catalog']:
        raise ValueError('Frozen recovery catalog mismatch')
    cases = {c['id']: c for c in source['cases']}
    for entry in artifact['memories']:
        if entry.get('case_id') not in cases:
            raise ValueError('Memory lacks its supporting practice case')
        validate_entry(entry, cases[entry['case_id']], artifact['catalog'])


def import_file_practice(catalog):
    """Reuse the already frozen generated rule, never tune it using official task outcomes."""
    base = ROOT / FILE_PRACTICE
    previous = read_json(base / 'experiment.json')
    if previous['knowledge_generation']['status'] != 'accepted':
        raise ValueError('Archived file recovery knowledge was not accepted')
    build = read_json(base / 'knowledge-build.json')
    for key, tool in build['evidence']['catalog'].items():
        if catalog.get(key) != tool:
            raise ValueError('File recovery practice catalog changed')
    calls = deepcopy(previous['practice_evidence']['observed_calls'])
    verified = previous['practice_evidence']['program_verified']
    if not verified['success']:
        raise ValueError('Archived file recovery did not verify success')
    for c in calls:
        if c['tool_call_id'] in verified['verified_read_call_ids']:
            target = json.loads(c['arguments'])['path']
            if not target.endswith(previous['cases'][0]['relative_path']) or text(c['response']) != previous['cases'][0]['content']:
                raise ValueError('Archived correct-file read evidence mismatch')
            c['verification'] = {'kind': 'exact_file_read', 'response_sha256': digest(c['response'])}
    case = {'id': 'recursive-file-recovery', 'trace': calls,
            'required_success_tool': '@modelcontextprotocol/server-filesystem::read_text_file',
            'forbidden_constants': [previous['cases'][0]['keyword'], previous['cases'][0]['content']],
            'origin_archive': FILE_PRACTICE,
            'origin_hashes': {n: file_hash(base / n) for n in ('experiment.json', 'knowledge-build.json', 'practice-probes.json')}}
    entry = deepcopy(previous['knowledge'][0])
    entry['case_id'] = case['id']
    validate_entry(entry, case, catalog)
    return case, entry


def collect_task_practice(config, directory, catalog):
    from custom.agents.LangChainAgent import ChatModel
    from custom.agents.tool_results import raw_result
    effective = deepcopy(config)
    fixtures = directory / 'practice-fixtures'
    fixtures.mkdir()
    effective['fixtures'] = fixtures.relative_to(ROOT).as_posix()
    journal = directory / 'task-practice.json'
    calls, client = [], None
    with runtime_for(effective, 'original', [TASKS], [], None) as runtime:
        tools, routing = adapters.agent_tools(adapters.semantic(runtime.catalog), runtime.catalog, {TASKS})
        for tool in adapters.semantic(runtime.catalog):
            if catalog.get(tool) != adapters.semantic(runtime.catalog)[tool]:
                raise ValueError('Task practice catalog differs from the frozen catalog')
        by_name = {t['name']: t for t in tools}
        for name, args in [('tasks_setup', {'source_path': runtime.workspace.as_posix()}),
                           ('tasks_add', {'texts': ['Assemble paper lanterns'], 'status': 'To Do'})]:
            response = raw_result(runtime.call(by_name[name]['meta']['benchmark_remote_name'], args))
            calls.append({'tool_call_id': 'seed-' + name, 'semantic_identity': TASKS + '::' + name,
                          'arguments': json.dumps(args), 'response': response})
            if not response.get('isError'):
                raise ValueError('Declared independent practice failure did not occur')
        atomic_json(journal, {'calls': calls, 'status': 'repairing'})
        target = runtime.workspace / 'practice-board.md'
        client = make_client(config, 'recovery_practice')
        try:
            agent = ChatModel(model_name=config['agent_model'], client=client, tools=tools,
                tool_server_map=routing, workspace_root=runtime.workspace, file_exists='Empty independent practice workspace.',
                max_round=8, tool_caller=runtime.call, temperature=config['agent_temperature'],
                max_new_tokens=config['agent_max_tokens'])
            agent.run_with_server('Recover from these actual failed tool calls and complete independent practice: '
                'create the task "Assemble paper lanterns" with status "To Do" in a new private Markdown '
                'source at ' + target.as_posix() + '. Use tools to do the work, not proposed calls. Observations:\n' +
                json.dumps(calls, ensure_ascii=False))
            calls.extend(deepcopy(agent.raw_tool_trace))
            proofs = {}
            for call in calls:
                if call['response'].get('isError'):
                    continue
                try:
                    payload = json.loads(text(call['response']))
                    args = json.loads(call['arguments'])
                except (ValueError, TypeError):
                    continue
                source = payload.get('source', {}) if isinstance(payload, dict) else {}
                if not source.get('path') or Path(source['path']).resolve() != target.resolve() or not target.is_file():
                    continue
                proof = None
                if call['semantic_identity'] == TASKS + '::tasks_setup':
                    registry = read_json(runtime.workspace / 'tasks-sources.json')
                    if source.get('id') and any(Path(r['path']).resolve() == target.resolve() for r in registry):
                        proof = {'kind': 'private_registry_readback', 'registry': registry}
                elif call['semantic_identity'] == TASKS + '::tasks_add':
                    content = target.read_text(encoding='utf-8')
                    if (args.get('texts') == ['Assemble paper lanterns'] and args.get('status') == 'To Do'
                            and any(t.get('text') == 'Assemble paper lanterns' and t.get('status') == 'To Do' for t in payload.get('added', []))
                            and 'Assemble paper lanterns' in content and 'To Do' in content):
                        proof = {'kind': 'private_added_items_readback', 'content': content}
                if proof:
                    proof['response_sha256'] = digest(call['response'])
                    call['verification'] = proof
                    proofs[call['semantic_identity']] = call
            atomic_json(journal, {'calls': calls, 'status': 'observed', 'execution_error': agent.execution_error,
                                 'messages': agent.messages, 'verified_tools': sorted(proofs)})
            normalized = normalize(calls, runtime.workspace)
            for c in normalized:
                if c.get('verification'):
                    c['verification']['response_sha256'] = digest(c['response'])
            cases = []
            for kind, success_tool in [('source-initialization', 'tasks_setup'), ('source-before-add', 'tasks_add')]:
                if TASKS + '::' + success_tool not in proofs:
                    continue
                keep = {'seed-tasks_setup'} if success_tool == 'tasks_setup' else {'seed-tasks_add'}
                trace = [c for c in normalized if c['tool_call_id'] in keep or c.get('verification')]
                constants = ['practice-board.md', 'Assemble paper lanterns']
                for c in trace:
                    try:
                        payload = json.loads(text(c['response']))
                        if payload.get('source', {}).get('id'):
                            constants.append(payload['source']['id'])
                        constants.extend(t['id'] for t in payload.get('added', []) if t.get('id'))
                    except (ValueError, AttributeError):
                        pass
                cases.append({'id': kind, 'trace': trace, 'forbidden_constants': constants,
                              'required_success_tool': TASKS + '::' + success_tool})
            return cases
        finally:
            client.close()


def prepare(config, task_list):
    options = config['memory']
    path, source_path = ROOT / options['artifact'], ROOT / options['source']
    if path.exists() or source_path.exists():
        raise ValueError('Frozen recovery inputs already exist; use a new artifact path')
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = initial_snapshot(config, task_list, lambda event: None)
    if snapshot['errors']:
        raise ValueError('Cannot freeze knowledge with unavailable Early servers')
    catalog = snapshot['knowledge']
    file_case, file_entry = import_file_practice(catalog)
    cases = [file_case] + collect_task_practice(config, path.parent, catalog)
    source = {'origin': 'independent_verified_recovery_practice', 'catalog': catalog, 'cases': cases,
              'scope': 'Synthetic failures and verified repairs only; no official task questions, answers or execution traces.'}
    source_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(source_path, source)
    entries, builds = [file_entry], []
    for case in cases[1:]:
        scoped = {k: catalog[k] for k in {c['semantic_identity'] for c in case['trace']}}
        evidence = {'observed_calls': case['trace'], 'scope': source['scope']}
        try:
            learned, journal = build_procedure(config, evidence, scoped, path.parent / (case['id'] + '.build.json'))
            entry = {**learned[0], 'case_id': case['id']}
            validate_entry(entry, case, catalog)
            entries.append(entry)
            builds.append({'case': case['id'], 'status': 'accepted', 'requests': len(journal['requests'])})
        except Exception as exc:
            builds.append({'case': case['id'], 'status': 'rejected', 'error': safe_error(exc)})
    artifact = {'protocol': PROTOCOL, 'source_sha256': file_hash(source_path), 'catalog': catalog,
                'memories': entries, 'memory_sha256': digest(entries), 'builds': builds,
                'builder_model': config['agent_model'], 'no_online_learning': True}
    validate_artifact(artifact, source)
    atomic_json(path, artifact)
    return artifact
