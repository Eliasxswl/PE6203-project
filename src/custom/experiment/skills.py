"""Learn independently verified local-tool repairs; freeze before the original task evaluation."""
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import json
import multiprocessing as mp
from pathlib import Path
import random
import subprocess

from jsonschema import validate as validate_json

from . import adapters
from .causal import build_procedure, normalize, source_hash, text
from .core import make_client, runtime_for
from .errors import ToolMistake
from .memory import REFERENCE_PREFIX, guidance_line, load
from .recovery_memory import validate_artifact, validate_entry
from .results import atomic_json, safe_error
from .selection import ROOT, digest, file_hash, tree_hash

PROTOCOL = 'expanded_verified_skills_v1'
SHRIMP = 'mcp-shrimp-task-manager'
TASKS = 'mcp-tasks'
REQUEST = '@kazuph/mcp-taskmanager'
FAMILIES = {
    'analysis': (SHRIMP, ['analyze_task'], 'analyze_task'),
    'split': (SHRIMP, ['split_tasks'], 'split_tasks'),
    'source': (TASKS, ['tasks_setup', 'tasks_add'], 'tasks_add'),
    'request': (REQUEST, ['request_planning', 'get_next_task'], 'get_next_task'),
}


def definitions():
    subjects = ['museum telemetry', 'orchard irrigation', 'harbor scheduling', 'library preservation']
    output = []
    for family in FAMILIES:
        for index in range(4):
            subject = subjects[index]
            count = 3 if index == 3 else 2
            output.append({'id': f'{family}-{index}', 'family': family, 'split': 'practice' if index < 2 else 'validation',
                'recovery': index != 3, 'subject': subject, 'summary': 'Develop an independent ' + subject + ' prototype with clear validation and review stages.',
                'names': [f'{subject} component {i + 1}' for i in range(count)],
                'descriptions': [f'Implement and validate component {i + 1} for the independent {subject} prototype.' for i in range(count)],
                'source_file': f'practice-{family}-{index}.' + ['md', 'json', 'yml', 'md'][index],
                'status': 'To Do' if index % 2 == 0 else 'In Progress'})
    return output


def payload(call):
    try:
        value = json.loads(text(call.get('response')))
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def failure(call):
    response = call['response']
    if response.get('isError'):
        return True
    data = payload(call)
    message = text(response)
    kind = None
    if data.get('status') == 'error':
        kind = 'tool_reported_error'
    elif message.startswith(('tasks 參數格式錯誤', 'tasksRaw 參數格式錯誤')):
        kind = 'tool_reported_schema_error'
    if kind:
        call['failure_evidence'] = {'kind': kind, 'response_sha256': digest(response)}
        return True
    return False


def invoke(runtime, family, name, args, identity):
    from custom.agents.tool_results import raw_result
    server = FAMILIES[family][0]
    tool = runtime.catalog[server + '::' + name]
    try:
        response = raw_result(runtime.call(tool['remote_name'], args))
        protocol_error = None
    except ToolMistake as exc:
        response = {'isError': True, 'content': [{'type': 'text', 'text': str(exc)}]}
        protocol_error = exc.raw_response
    call = {'tool_call_id': identity, 'semantic_identity': server + '::' + name,
            'arguments': json.dumps(args, ensure_ascii=False), 'response': response, 'protocol_error': protocol_error}
    failure(call)
    return call


def seed(runtime, case):
    calls = []
    family = case['family']
    if family == 'request':
        # Vary counters so returned request IDs cannot be memorized as req-1.
        for i in range(int(case['id'].split('-')[-1])):
            calls.append(invoke(runtime, family, 'request_planning', {'originalRequest': f'Unrelated placeholder {i}',
                'tasks': [{'title': f'Placeholder {i}', 'description': 'Unrelated private setup state.'}]}, f'seed-dummy-{i}'))
        if case['recovery']:
            calls.append(invoke(runtime, family, 'request_planning', {'originalRequest': case['summary'],
                'tasks': [{'title': n, 'description': d} for n, d in zip(case['names'], case['descriptions'])]}, 'seed-register'))
            planned = payload(calls[-1])
            calls.append(invoke(runtime, family, 'get_next_task', {'requestId': planned['tasks'][0]['id']}, 'seed-wrong-id'))
    elif case['recovery'] and family == 'analysis':
        calls.append(invoke(runtime, family, 'analyze_task', {'summary': case['summary'], 'initialConcept': 'Build it.'}, 'seed-short-analysis'))
    elif case['recovery'] and family == 'split':
        tasks = [{'name': n, 'description': d, 'implementationGuide': 'Implement this component, then validate its interfaces.',
                  'dependencies': [] if i == 0 else [{'name': case['names'][0]}], 'relatedFiles': []}
                 for i, (n, d) in enumerate(zip(case['names'], case['descriptions']))]
        calls.append(invoke(runtime, family, 'split_tasks', {'updateMode': 'append', 'tasksRaw': json.dumps(tasks)}, 'seed-bad-dependency'))
    elif family == 'source':
        if case['recovery']:
            calls.append(invoke(runtime, family, 'tasks_setup', {'source_path': runtime.workspace.as_posix()}, 'seed-directory-source'))
            calls.append(invoke(runtime, family, 'tasks_add', {'texts': case['names'], 'status': case['status']}, 'seed-uninitialized-add'))
        else:
            calls.append(invoke(runtime, family, 'tasks_setup', {'source_path': (runtime.workspace / 'unrelated-source.md').as_posix()}, 'seed-unrelated-source'))
    if case['recovery'] and not any(failure(c) for c in calls):
        raise ValueError('Declared practice fault did not produce an actual tool error')
    return calls


def goal(runtime, case, calls, seed_calls):
    """Verify a tool operation and its state; never interpret final prose as success."""
    family = case['family']
    successful = [c for c in calls if not failure(c)]
    if family == 'analysis':
        for c in successful:
            if c['semantic_identity'] != SHRIMP + '::analyze_task':
                continue
            args = json.loads(c['arguments'])
            validate_json(args, runtime.catalog[c['semantic_identity']]['inputSchema'])
            if (args.get('summary') == case['summary'] and not args.get('previousAnalysis')
                    and ('Codebase Analysis' in text(c['response']) or '程式碼庫分析' in text(c['response']))):
                return True, [c], {'kind': 'validated_analysis_response', 'arguments': args}
    elif family == 'split':
        paths = list((runtime.workspace / 'shrimp-data').rglob('tasks.json'))
        if not paths:
            return False, [], {}
        state = json.loads(paths[0].read_text(encoding='utf-8'))
        stored = {t['name']: t for t in state['tasks']}
        if not set(case['names']) <= stored.keys():
            return False, [], {}
        for index, name in enumerate(case['names']):
            task = stored[name]
            if not task.get('implementationGuide') or task.get('relatedFiles'):
                return False, [], {}
            dependencies = {d['taskId'] for d in task.get('dependencies', [])}
            expected = set() if index == 0 else {stored[case['names'][index - 1]]['id']}
            if dependencies != expected:
                return False, [], {}
        for c in successful:
            if c['semantic_identity'] == SHRIMP + '::split_tasks':
                items = json.loads(json.loads(c['arguments'])['tasksRaw'])
                if [t['name'] for t in items] == case['names']:
                    return True, [c], {'kind': 'persisted_task_dependency_graph', 'state': state}
    elif family == 'source':
        target = runtime.workspace / case['source_file']
        if not target.is_file():
            return False, [], {}
        content = target.read_text(encoding='utf-8')
        for c in successful:
            if c['semantic_identity'] != TASKS + '::tasks_add':
                continue
            data, args = payload(c), json.loads(c['arguments'])
            source = data.get('source', {})
            if (source.get('path') and Path(source['path']).resolve() == target.resolve()
                    and args.get('source_id') == source.get('id') and args.get('texts') == case['names']
                    and args.get('status') == case['status'] and all(n in content for n in case['names'])
                    and [t.get('text') for t in data.get('added', [])] == case['names']
                    and all(t.get('status') == case['status'] for t in data['added'])):
                setup = next((p for p in successful if p['semantic_identity'] == TASKS + '::tasks_setup' and payload(p).get('source', {}).get('id') == source['id']), None)
                if setup:
                    return True, [setup, c], {'kind': 'persisted_source_and_added_items', 'content': content, 'source_id': source['id']}
    elif family == 'request':
        state_file = runtime.workspace / 'tasks.json'
        if not state_file.exists():
            return False, [], {}
        state = json.loads(state_file.read_text(encoding='utf-8'))
        targets = [r for r in state['requests'] if r['originalRequest'] == case['summary']]
        if (len(targets) != 1 or [t['title'] for t in targets[0]['tasks']] != case['names']
                or [t['description'] for t in targets[0]['tasks']] != case['descriptions']):
            return False, [], {}
        request = targets[0]
        for c in successful:
            if c['semantic_identity'] == REQUEST + '::get_next_task' and json.loads(c['arguments']).get('requestId') == request['requestId']:
                data = payload(c)
                if data.get('status') == 'next_task' and data.get('task', {}).get('id') == request['tasks'][0]['id']:
                    planned = next((p for p in seed_calls + successful if p['semantic_identity'] == REQUEST + '::request_planning' and payload(p).get('requestId') == request['requestId']), None)
                    if planned:
                        return True, [planned, c], {'kind': 'persisted_request_and_returned_task', 'state': state, 'request_id': request['requestId']}
    return False, [], {}


def query(case, workspace, seeds):
    family = case['family']
    if family == 'analysis':
        instruction = 'Submit an actual first analysis using analyze_task for this project; use a concrete technical strategy. Stop after that operation; no implementation or subsequent tools.'
    elif family == 'split':
        instruction = 'Register exactly the listed tasks in one append batch. Each task after the first depends on the previous task. Provide meaningful implementation guides and no related files. Stop after the tasks are stored.'
    elif family == 'source':
        instruction = f'Create a task source at {(workspace / case["source_file"]).as_posix()} and add exactly the listed task names with status {case["status"]}. Explicitly use the source ID returned for that source. Perform actual calls.'
    elif case['recovery']:
        instruction = 'The target request is already registered in the observations below. Retrieve its first pending task using the correct returned request ID. Preserve the existing request; stop after retrieval.'
    else:
        instruction = 'Register one new request for this project and its listed tasks, then retrieve its first pending task using the returned request ID. Stop after retrieval.'
    return instruction + '\nIndependent project input:\n' + json.dumps({'summary': case['summary'],
        'tasks': [{'name': n, 'description': d} for n, d in zip(case['names'], case['descriptions'])]}, ensure_ascii=False) + (
        '\nActual prior tool observations:\n' + json.dumps(seeds, ensure_ascii=False) if seeds else '')


def episode(spec):
    from custom.agents.LangChainAgent import ChatModel
    config, case = spec['config'], spec['case']
    server, names, success_name = FAMILIES[case['family']]
    path = Path(spec['journal'])
    row = {'protocol': PROTOCOL, 'case': case, 'condition': spec['condition'], 'repeat': spec['repeat'],
           'status': 'running', 'model_attempts': [], 'seed_calls': [], 'calls': [], 'success': False}
    atomic_json(path, row)
    client = None
    try:
        with runtime_for(config, 'original', [server], [], None) as runtime:
            current = adapters.semantic(runtime.catalog)
            if current != {k: v for k, v in spec['catalog'].items() if v['server'] == server}:
                raise ValueError('Practice tool catalog drifted')
            seeds = seed(runtime, case)
            row['seed_calls'] = deepcopy(seeds)
            tools, routing = adapters.agent_tools(current, runtime.catalog, {server})
            tools = [t for t in tools if t['name'] in names]
            client = make_client(config, 'skill_practice')
            def event(kind, data):
                if kind == 'model_start':row['model_attempts'].append({'status': 'started', 'messages': deepcopy(data['messages'])})
                elif kind == 'model_completed':row['model_attempts'][-1].update(status='completed', response=data)
                elif kind == 'model_failed':row['model_attempts'][-1].update(status='failed', error=data)
                elif kind == 'tool_completed':row['calls'] = deepcopy(data['raw_tool_trace'])
                atomic_json(path, row)
            agent = ChatModel(model_name=config['agent_model'], client=client, tools=tools, max_round=6,
                tool_server_map=routing, workspace_root=runtime.workspace, file_exists='Independent disposable practice workspace.',
                temperature=config['agent_temperature'], max_new_tokens=config['agent_max_tokens'], tool_caller=runtime.call,
                event_callback=event, prompt_time=spec['prompt_time'])
            if spec.get('entries'):
                aliases = {t['meta']['benchmark_semantic_identity']:t['name'] for t in tools}
                context = REFERENCE_PREFIX + ''.join(guidance_line(e, aliases, runtime.workspace) for e in spec['entries'])
                agent.messages[0]['content'] += context
            answer, _, _, _ = agent.run_with_server(query(case, runtime.workspace, seeds))
            calls = deepcopy(agent.raw_tool_trace)
            ok, verified_calls, proof = goal(runtime, case, calls, seeds)
            for c in verified_calls:
                c['verification'] = {'kind': proof['kind'], 'response_sha256': digest(c['response'])}
            all_calls = deepcopy(seeds) + calls
            proof_ids = {c['tool_call_id']:c['verification'] for c in verified_calls}
            for c in all_calls:
                failure(c)
                if c['tool_call_id'] in proof_ids:c['verification'] = proof_ids[c['tool_call_id']]
            normalized = normalize(all_calls, runtime.workspace)
            for c in normalized:
                for key in ('verification', 'failure_evidence'):
                    if c.get(key):c[key]['response_sha256'] = digest(c['response'])
            row.update(status='failed' if agent.execution_error else 'completed', execution_error=agent.execution_error,
                answer=answer, messages=agent.messages, calls=normalized, proof=normalize(proof, runtime.workspace),
                verified_call_ids=sorted(proof_ids), success=ok, request_count=agent.request_count)
    except Exception as exc:
        row.update(status='failed', error=safe_error(exc))
    finally:
        if client is not None:client.close()
        atomic_json(path, row)
    return row


def retain_template(row):
    """Preserve observed call structure; replace only input and returned-output values."""
    case, family = row['case'], row['case']['family']
    verified = [c for c in row['calls'] if c.get('verification')]
    variables, templates = {}, []
    def variable(name, meaning):
        variables[name] = meaning
        return '${' + name + '}'
    for c in verified:
        args = json.loads(c['arguments'])
        name = c['semantic_identity'].split('::')[-1]
        if family == 'analysis':
            args['summary'] = variable('SUMMARY', 'Current project summary, satisfying the tool schema minimum length.')
            args['initialConcept'] = variable('INITIAL_CONCEPT', 'Concrete current technical strategy; initialConcept requires at least 50 characters.')
            if args.get('previousAnalysis'):
                raise ValueError('First-analysis practice unexpectedly uses a prior analysis')
        elif family == 'split':
            tasks = json.loads(args['tasksRaw'])
            if [t['name'] for t in tasks] != case['names']:
                raise ValueError('Verified batch differs from the current practice inputs')
            for i, task in enumerate(tasks):
                for key in ('name', 'description', 'implementationGuide', 'notes', 'verificationCriteria'):
                    if task.get(key):
                        task[key] = variable(f'TASK_{i+1}_{key.upper()}', f'Current item {i+1} {key}; include every requested item, not a fixed two-item batch.')
                task['dependencies'] = [] if i == 0 else [variable(f'TASK_{i}_NAME', f'Exact name of current prerequisite item {i}; dependencies are strings, not objects.')]
            args['tasksRaw'] = json.dumps(tasks, ensure_ascii=False)
            if args.get('globalAnalysisResult'):
                args['globalAnalysisResult'] = variable('GLOBAL_ANALYSIS', 'Current shared technical analysis, if needed.')
        elif family == 'source':
            if name == 'tasks_setup':
                args['source_path'] = variable('SOURCE_PATH', 'Current full path to the requested supported task source file (.md, .json or .yml), not its directory.')
                if args.get('workspace'):
                    args['workspace'] = '${WORKSPACE}'
            else:
                args['texts'] = variable('TASK_TEXTS', 'JSON array of every task text requested in the current task; preserve item count.')
                args['status'] = variable('STATUS', 'Current requested task status, using the exact allowed enum.')
                args['source_id'] = variable('SOURCE_ID', 'Actual source.id returned by tasks_setup for the intended source; do not reuse a practice ID.')
        else:
            if name == 'request_planning':
                args['originalRequest'] = variable('REQUEST', 'Current original request.')
                args['tasks'] = variable('TASKS', 'JSON array of current items, each with title and description; preserve current item count.')
                if args.get('splitDetails'):
                    args['splitDetails'] = variable('SPLIT_DETAILS', 'Current breakdown explanation if needed.')
            else:
                args['requestId'] = variable('REQUEST_ID', 'Actual requestId returned by request_planning; task IDs are not request IDs. Reuse an existing request when already planned.')
        templates.append({'tool_id': c['semantic_identity'], 'arguments': args, 'evidence_call_ids': [c['tool_call_id']]})
    if not templates:
        raise ValueError('No objectively verified successful calls to retain')
    return templates, variables


def bind(value, values):
    """Typed placeholders and nested JSON strings must preserve valid escaping."""
    if isinstance(value, dict):
        return {k: bind(v, values) for k, v in value.items()}
    if isinstance(value, list):
        return [bind(v, values) for v in value]
    if not isinstance(value, str):
        return value
    if value.startswith('${') and value.endswith('}') and value.count('${') == 1:
        return deepcopy(values[value[2:-1]])
    if value.startswith(('[', '{')):
        try:
            return json.dumps(bind(json.loads(value), values), ensure_ascii=False)
        except json.JSONDecodeError:
            pass
    for key, replacement in values.items():
        if isinstance(replacement, str):
            value = value.replace('${' + key + '}', replacement)
    if '${' in value:
        raise ValueError('Unbound template variable')
    return value


def replay(config, row, templates, catalog, path):
    """Replay on private practice state only, with the original successful variable values."""
    case = row['case']
    family = case['family']
    verified = [c for c in row['calls'] if c.get('verification')]
    values = {}
    # Derive bindings from the observed successful arguments, not invented repaired calls.
    def collect(template, actual):
        if isinstance(template, str) and template.startswith('${') and template.endswith('}') and template.count('${') == 1:
            if template != '${WORKSPACE}':
                values[template[2:-1]] = actual
        elif isinstance(template, dict):
            for k, v in template.items():collect(v, actual[k])
        elif isinstance(template, list):
            for t, a in zip(template, actual):collect(t, a)
        elif isinstance(template, str) and template.startswith(('[', '{')):
            collect(json.loads(template), json.loads(actual))
    for t, c in zip(templates, verified):collect(t['arguments'], json.loads(c['arguments']))
    calls = []
    with runtime_for(config, 'original', [FAMILIES[family][0]], [], None) as runtime:
        if adapters.semantic(runtime.catalog) != {k: v for k, v in catalog.items() if v['server'] == FAMILIES[family][0]}:
            raise ValueError('Replay catalog drift')
        seeds = seed(runtime, case)
        values['WORKSPACE'] = runtime.workspace.as_posix()
        if 'SOURCE_PATH' in values:values['SOURCE_PATH'] = (runtime.workspace / case['source_file']).as_posix()
        if family == 'request':
            existing = next((c for c in seeds if c['tool_call_id'] == 'seed-register'), None)
            if existing:values['REQUEST_ID'] = payload(existing)['requestId']
        for i, template in enumerate(templates):
            if family == 'request' and case['recovery'] and template['tool_id'].endswith('::request_planning'):
                continue  # Preserve an already registered request instead of duplicating it.
            args = bind(template['arguments'], values)
            call = invoke(runtime, family, template['tool_id'].split('::')[-1], args, f'replay-{i}')
            calls.append(call)
            if failure(call):raise ValueError('Retained call failed physical practice replay')
            if call['semantic_identity'].endswith('::tasks_setup'):values['SOURCE_ID'] = payload(call)['source']['id']
            if call['semantic_identity'].endswith('::request_planning'):values['REQUEST_ID'] = payload(call)['requestId']
        ok, _, proof = goal(runtime, case, calls, seeds)
        atomic_json(path, {'success': ok, 'calls': normalize(calls, runtime.workspace), 'proof': normalize(proof, runtime.workspace)})
        if not ok:raise ValueError('Retained template did not reproduce the verified goal')


def summary(rows):
    output = {'protocol': PROTOCOL, 'judge_calls': 0, 'families': {}}
    for family in FAMILIES:
        selected = [r for r in rows if r['case']['family'] == family]
        item = {'conditions': {}, 'paired': {}}
        for condition in ('without_memory', 'with_memory'):
            arm = [r for r in selected if r['condition'] == condition]
            item['conditions'][condition] = {'planned': 6, 'observed': len(arm), 'completed': sum(r['status'] == 'completed' for r in arm),
                'successes': sum(r['status'] == 'completed' and r['success'] for r in arm)}
        pairs = []
        for a in [r for r in selected if r['condition'] == 'with_memory']:
            b = next((r for r in selected if r['condition'] == 'without_memory' and r['case']['id'] == a['case']['id'] and r['repeat'] == a['repeat']), None)
            if b and a['status'] == b['status'] == 'completed':
                pairs.append((a, b))
        for cohort in ('all', 'recovery', 'clean'):
            subset = [(a, b) for a, b in pairs if cohort == 'all' or a['case']['recovery'] == (cohort == 'recovery')]
            item['paired'][cohort] = {'pairs': len(subset), 'with_successes': sum(a['success'] for a, b in subset),
                'without_successes': sum(b['success'] for a, b in subset), 'wins': sum(a['success'] and not b['success'] for a, b in subset),
                'losses': sum(b['success'] and not a['success'] for a, b in subset)}
        output['families'][family] = item
    return output


def run(config, workers=10):
    """One entry: independent collection, frozen extraction, then untouched held-out checks."""
    from custom.utils.test_utils import offset_date
    if config.get('mode') == 'offline' or config.get('agent_backend') != 'langchain' or not 1 <= workers <= 10:
        raise ValueError('Expanded skills require the live official agent loop and 1 to 10 workers')
    old = load(config)
    old_source = json.loads((ROOT / config['memory']['source']).read_text(encoding='utf-8'))
    operator = subprocess.check_output(['git', 'config', 'user.name'], cwd=ROOT, text=True).strip()
    operator = ''.join(c if c.isalnum() or c in '-_' else '_' for c in operator)
    directory = ROOT / 'results' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ_') + operator)
    directory.mkdir()
    for part in ('practice', 'validation', 'fixtures', 'replay'):(directory / part).mkdir()
    manifest = {'protocol': PROTOCOL, 'status': 'collecting', 'settings': config, 'cases': definitions(),
        'workers': workers, 'practice_per_family': 2, 'heldout_per_family': 2, 'validation_repeats': 3,
        'conditions': ['without_memory', 'with_memory'], 'request_limit': 6, 'judge_calls': 0,
        'source_sha256': source_hash(), 'old_artifact_sha256': file_hash(ROOT / config['memory']['artifact']),
        'old_memory_sha256': old['memory_sha256'], 'prompt_time': str(offset_date(0)),
        'claim_limit': 'Independent synthetic operation checks, not official task performance. Official evaluation retains the frozen original 17 tasks.'}
    atomic_json(directory / 'experiment.json', manifest)
    print('Expanded skills: ' + str(directory), flush=True)
    pool = config['providers']['agent']
    def specification(case, repeat, condition, entries, part):
        fixture = directory / 'fixtures' / case['id']
        fixture.mkdir(exist_ok=True)
        effective = deepcopy(config)
        effective['fixtures'] = fixture.relative_to(ROOT).as_posix()
        position = list(FAMILIES).index(case['family']) * 4 + int(case['id'].split('-')[-1]) + repeat
        effective['providers']['agent'] = [pool[position % len(pool)]]
        return {'config': effective, 'case': case, 'condition': condition, 'repeat': repeat, 'entries': entries,
            'catalog': old['catalog'], 'prompt_time': manifest['prompt_time'],
            'journal': str(directory / part / f'{case["id"]}-{repeat}-{condition}.json')}
    def execute(specs):
        rows = []
        with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context('spawn')) as executor:
            futures = [executor.submit(episode, spec) for spec in specs]
            for future in as_completed(futures):
                row = future.result()
                rows.append(row)
                print(f'{row["case"]["id"]} {row["condition"]} {row["repeat"]}: {row["status"]}, verified={row["success"]}', flush=True)
        return rows
    try:
        training = execute([specification(c, 0, 'practice', [], 'practice') for c in definitions() if c['split'] == 'practice'])
        file_entries = [deepcopy(e) for e in old['memories'] if e['case_id'] == 'expanded-file-recovery']
        if len(file_entries) != 1:raise ValueError('Expected the single frozen verified file procedure')
        entries = file_entries
        cases = [deepcopy(c) for c in old_source['cases'] if c['id'] == file_entries[0]['case_id']]
        builds, family_entries = [], {}
        for family in FAMILIES:
            rows = sorted([r for r in training if r['case']['family'] == family], key=lambda r:r['case']['id'])
            try:
                if len(rows) != 2 or any(r['status'] != 'completed' or not r['success'] for r in rows):
                    raise ValueError('Both declared practice repairs must succeed; no retry or invented fallback')
                trace, constants, templates, variables = [], [], [], {}
                for row in rows:
                    row = deepcopy(row)
                    for c in row['calls']:c['tool_call_id'] = row['case']['id'] + ':' + c['tool_call_id']
                    retained, meanings = retain_template(row)
                    replay_config = specification(row['case'], 0, 'replay', [], 'replay')['config']
                    replay(replay_config, row, retained, old['catalog'], directory / 'replay' / (row['case']['id'] + '.json'))
                    trace.extend(row['calls'])
                    for t in retained:
                        previous = next((p for p in templates if p['tool_id'] == t['tool_id'] and p['arguments'] == t['arguments']), None)
                        if previous:previous['evidence_call_ids'].extend(t['evidence_call_ids'])
                        else:templates.append(t)
                    variables.update(meanings)
                    constants.extend([row['case']['subject'], row['case']['source_file']] + row['case']['names'])
                    for c in row['calls']:
                        data = payload(c)
                        if data.get('source', {}).get('id'):constants.append(data['source']['id'])
                        if data.get('requestId'):constants.append(data['requestId'])
                        constants.extend(t['id'] for t in data.get('tasks', []) if t.get('id'))
                        constants.extend(t['id'] for t in data.get('added', []) if t.get('id'))
                case = {'id': 'verified-' + family + '-workflow', 'trace': trace, 'forbidden_constants': sorted(set(constants)),
                    'required_success_tool': FAMILIES[family][0] + '::' + FAMILIES[family][2]}
                scoped = {k: v for k, v in old['catalog'].items() if k in {c['semantic_identity'] for c in trace}}
                required = [c['tool_call_id'] for c in trace if failure(c) or c.get('verification')]
                learned, journal = build_procedure(config, {'observed_calls': trace, 'required_evidence_call_ids': required,
                    'scope': 'Summarize both independent repairs concisely (at most 120 words total). Preserve all supporting IDs. No official task data. Do not generalize current item count or IDs into constants.'},
                    scoped, directory / (family + '-build.json'))
                entry = {**learned[0], 'case_id': case['id']}
                entry['value'].update(tool_ids=sorted({t['tool_id'] for t in templates}), tool_call_templates=templates, template_variables=variables)
                entry['id'] = digest(entry['value'])[:24]
                validate_entry(entry, case, old['catalog'])
                cases.append(case)
                entries.append(entry)
                family_entries[family] = entry
                builds.append({'family': family, 'status': 'accepted', 'summary_requests': 1, 'physical_replays': 2})
            except Exception as exc:
                builds.append({'family': family, 'status': 'rejected', 'error': safe_error(exc)})
                print(f'{family} knowledge rejected: {safe_error(exc)}', flush=True)
        source = {'origin': 'independent_verified_recovery_practice', 'catalog': old['catalog'], 'cases': cases,
            'scope': 'Original file rule unchanged; new rules learned only from independent tool errors and verified corrections. No official task trajectories.'}
        atomic_json(directory / 'candidate-evidence.json', source)
        artifact = {'protocol': old['protocol'], 'source_sha256': file_hash(directory / 'candidate-evidence.json'), 'catalog': old['catalog'],
            'memories': entries, 'memory_sha256': digest(entries), 'builds': builds, 'builder_model': config['agent_model'],
            'no_online_learning': True, 'status': 'frozen_before_independent_validation'}
        validate_artifact(artifact, source)
        atomic_json(directory / 'candidate-k0.json', artifact)
        manifest.update(status='validating', builds=builds, candidate_sha256=artifact['memory_sha256'])
        atomic_json(directory / 'experiment.json', manifest)
        specs = []
        for repeat in range(3):
            for c in definitions():
                if c['split'] != 'validation' or c['family'] not in family_entries:continue
                order = ['without_memory', 'with_memory']
                random.Random(25010 + repeat * 17 + int(c['id'].split('-')[-1]) + list(FAMILIES).index(c['family'])).shuffle(order)
                for condition in order:
                    specs.append(specification(c, repeat, condition, [family_entries[c['family']]] if condition == 'with_memory' else [], 'validation'))
        rows = execute(specs)
        result = summary(rows)
        result.update(status='completed_with_failures' if any(r['status'] != 'completed' for r in rows) else 'completed',
            builds=builds, candidate_sha256=artifact['memory_sha256'],
            coverage={'planned_validation': 48, 'attempted': len(rows), 'completed': sum(r['status'] == 'completed' for r in rows),
                      'not_attempted_rejected_knowledge': 48 - len(rows)},
            source_unchanged=source_hash() == manifest['source_sha256'], old_file_entry_unchanged=file_entries[0] == entries[0])
        if not result['source_unchanged']:result['status'] = 'invalidated'
        manifest['status'] = result['status']
        atomic_json(directory / 'experiment.json', manifest)
        atomic_json(directory / 'validation-summary.json', result)
        return directory, result
    except BaseException as exc:
        manifest.update(status='failed_or_interrupted', error=safe_error(exc))
        atomic_json(directory / 'experiment.json', manifest)
        raise
