"""Case-level frozen-memory controls; no knowledge generation or replacement scores."""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import uuid

from . import adapters
from .core import run_trajectory, runtime_for
from .experience_state import affected, dependencies, validate_state
from .results import Store, atomic_json, create, identity, safe_error, writer_lock
from .runtime import ALIASES, policy_for
from .selection import ROOT, digest, file_hash, fingerprints, read_json

PROTOCOL = 'frozen_memory_counterfactual_v1'
CONDITIONS = ('fr_all', 'fr_changed_only', 'frozen_k0')
STAGE = 'iter5'
FIXED = ('agent_model', 'judge_model', 'agent_temperature', 'judge_temperature', 'agent_max_tokens',
         'judge_max_tokens', 'agent_thinking', 'judge_thinking', 'judge_output_mode', 'round_policy',
         'judge_attempts_per_trajectory', 'automatic_api_retries', 'judge_failure_top_up', 'agent_backend',
         'max_requests', 'selection_seed', 'memory', 'runtime')


def scope(catalog, task):
    servers = {ALIASES.get(s, s) for s in task['servers']}
    return adapters.semantic({k: v for k, v in catalog.items() if v['server'] in servers})


def conditions(records, repeat, restore_entries=None):
    if f'full_rewrite/{repeat}' not in records['episodes']:
        raise ValueError('Snapshot repeat is not present in the archived Full Rewrite run')
    stages = records['episodes'][f'full_rewrite/{repeat}']['stages']
    if any(stages[s]['status'] != 'ready' for s in ('original', STAGE)):
        raise ValueError('Counterfactual requires committed source checkpoints')
    initial, late = stages['original'], stages[STAGE]
    old, target = initial['knowledge'], late['knowledge']
    k0, full = initial['experience_state'], late['experience_state']
    validate_state(k0, old);validate_state(full, target)
    old_entries = {e['id']:e for e in k0['memories']}
    selected = {e['id'] for e in k0['memories'] if affected(e, old, target)}
    restored = set(old_entries) - selected if restore_entries is None else set(restore_entries)
    if not restored <= set(old_entries) - selected:
        raise ValueError('Restore only existing entries whose tool contracts are unchanged')
    hybrid = deepcopy(full)
    hybrid['memories'] = [deepcopy(old_entries[e['id']] if e['id'] in restored else e) for e in full['memories']]
    hybrid['memory_sha256'] = digest(hybrid['memories'])
    hybrid['dependency_hashes'] = {e['id']:dependencies(e, target) for e in hybrid['memories']}
    validate_state(hybrid, target)
    return {'fr_all':(deepcopy(full),deepcopy(target)),
            'fr_changed_only':(hybrid,deepcopy(target)),
            'frozen_k0':(deepcopy(k0),deepcopy(old))}, deepcopy(late), sorted(selected)


def order_control(variant):
    """Change JSON object-key presentation only; every value and list order stays fixed."""
    def reverse_keys(value):
        if isinstance(value, dict):
            return {key:reverse_keys(value[key]) for key in reversed(value)}
        if isinstance(value, list):
            return [reverse_keys(item) for item in value]
        return value
    state, knowledge = deepcopy(variant)
    for entry in state['memories']:
        entry['value'] = reverse_keys(entry['value'])
    if (state, knowledge) != variant:
        raise ValueError('Order control changed knowledge semantics')
    validate_state(state, knowledge)
    return state, knowledge


def isolation_probe(config, selected, snapshot, emit):
    """Two simultaneously live private servers; a real write in one must not reach the other."""
    servers={ALIASES.get(s,s) for t in selected for s in t['servers']}
    for server in servers:
        policy=policy_for(server,config)
        if policy['concurrency']!='private' or policy.get('external_mutation'):
            raise ValueError('Counterfactual permits only reviewed private local backends')
    from custom.agents.tool_results import raw_result
    with ExitStack() as stack:
        runtimes=[stack.enter_context(runtime_for(config,STAGE,servers,selected,None,emit)) for _ in range(2)]
        if len({str(r.workspace) for r in runtimes})!=2 or len({r.url for r in runtimes})!=2:
            raise ValueError('Isolation probe reused a workspace or endpoint')
        for runtime in runtimes:
            if adapters.semantic(runtime.catalog)!={k:v for k,v in adapters.semantic(snapshot['catalog']).items() if v['server'] in servers}:
                raise ValueError('Late backend differs from the frozen source catalog')
        marker='independent-counterfactual-isolation-probe'
        if 'mcp-shrimp-task-manager' not in servers:
            tool = 'mcp-tasks::tasks_setup'
            if tool not in runtimes[0].catalog:
                tool = '@modelcontextprotocol/server-filesystem::write_file'
            if tool not in runtimes[0].catalog:
                raise ValueError('No reviewed writable backend for the isolation probe')
            targets = [r.workspace / '.counterfactual-isolation.md' for r in runtimes]
            if any(p.exists() for p in targets):
                raise ValueError('Probe marker already exists')
            arguments = ({'source_path':targets[0].as_posix()} if tool.startswith('mcp-tasks::') else
                         {'path':targets[0].as_posix(),'content':marker})
            response = raw_result(runtimes[0].call(runtimes[0].catalog[tool]['remote_name'],arguments))
            if response.get('isError') or not targets[0].is_file() or targets[1].exists():
                raise ValueError('A private task-source write did not remain isolated')
            return {'status':'passed','workspace_paths':[str(r.workspace) for r in runtimes],
                'endpoints':[r.url for r in runtimes],'distinct_workspaces':True,'distinct_endpoints':True,
                'write_visible_only_to_owner':True,'probe_response':response,
                'scope':'Private task-source workspace/process/port isolation; not an OS security sandbox.'}
        def tasks(runtime):
            return [t for p in (runtime.workspace/'shrimp-data').rglob('tasks.json') for t in read_json(p).get('tasks',[])]
        if any(tasks(r) for r in runtimes):raise ValueError('Probe task state was not initially empty')
        tool='mcp-shrimp-task-manager::split_tasks'
        args={'updateMode':'append','tasksRaw':json.dumps([{'name':marker,
            'description':'Create a temporary task used only to verify private backend state isolation.',
            'implementationGuide':'This temporary task is not part of the benchmark. Verify the stored marker only in its owning private runtime.',
            'verificationCriteria':'The marker is present in the first runtime and absent in the second runtime.',
            'dependencies':[],'relatedFiles':[]}])}
        response=raw_result(runtimes[0].call(runtimes[0].catalog[tool]['remote_name'],args))
        if response.get('isError') or marker not in {t['name'] for t in tasks(runtimes[0])} or tasks(runtimes[1]):
            raise ValueError('A private backend write did not remain isolated')
        return {'status':'passed','workspace_paths':[str(r.workspace) for r in runtimes],
                'endpoints':[r.url for r in runtimes],'distinct_workspaces':True,'distinct_endpoints':True,
                'write_visible_only_to_owner':True,'probe_response':response,
                'scope':'Private workspace/process/port isolation; not an OS security sandbox for arbitrary tools.'}


def case_outcome(row):
    """Task 9 observations supplement the original rubric; they are not new TF labels."""
    if row['identity']['task_id'] != 9:
        return None
    observations = row.get('workspace_observations', [])
    expected = observations[0].get('txt/log_yesterday.txt', {}).get('text') if observations else None
    if not expected or not expected.strip():
        return None
    read, planned = False, False
    for call in row['raw_tool_trace']:
        response = call.get('response', {})
        if response.get('isError'):
            continue
        text = '\n'.join(b.get('text', '') for b in response.get('content', []) if b.get('type') == 'text')
        tool = call.get('semantic_identity', '')
        if tool in {f'@modelcontextprotocol/server-filesystem::{name}' for name in
                    ('read_text_file', 'read_file', 'read_multiple_files')}:
            try:
                arguments = call.get('arguments', {})
                arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
                paths = arguments.get('paths', [arguments.get('path')])
                target = any(isinstance(p, str) and
                             p.replace('\\', '/').endswith('/txt/log_yesterday.txt') for p in paths)
            except (ValueError, TypeError, AttributeError):
                target = False
            read |= target and expected.replace('\r\n', '\n').strip() in text.replace('\r\n', '\n')
        if tool == '@kazuph/mcp-taskmanager::request_planning':
            try:
                data = json.loads(text)
                planned |= bool(data.get('status') == 'planned' and data.get('requestId') and
                                isinstance(data.get('tasks'), list) and data['tasks'])
            except (ValueError, AttributeError):
                pass
    return {'log_read': read, 'plan_created': planned, 'workflow_complete': read and planned}


def report(store):
    rows = list(store.records['trajectories'].values())
    result = {'protocol': PROTOCOL, 'status': store.records['status'], 'conditions': {},
              'evaluation': 'Actual tool-return observations only; no Judge or replacement TF/ECS.',
              'same_callable_tools': len({r['counterfactual_callable_sha256'] for r in rows}) == 1}
    for condition in store.manifest['diagnostic']['conditions']:
        group = [r for r in rows if r['identity']['strategy'] == condition]
        observed = [case_outcome(r) for r in group if r['agent_status'] == 'completed']
        observed = [o for o in observed if o is not None]
        result['conditions'][condition] = {'planned': len(group),
            'completed_agents': sum(r['agent_status'] == 'completed' for r in group),
            'observed_task9_trajectories': len(observed),
            **{name: sum(o[name] for o in observed) for name in ('log_read', 'plan_created', 'workflow_complete')}}
    return result


def run(config, task_list, source, task_id, snapshot_repeat=2, repeats=10, include_order_control=False):
    if type(repeats) is not int or repeats not in (1, 3, 10):
        raise ValueError('Use one pilot, three quick repeats, or ten confirmation repeats')
    source = (ROOT / Path(source)).resolve()
    manifest, historical = read_json(source/'experiment.json'), read_json(source/'records.json')
    if manifest.get('source_archive_sha256') and file_hash(source/'inputs/source.zip') != manifest['source_archive_sha256']:
        raise ValueError('Archived source checksum mismatch')
    if any(config.get(k) != manifest['settings'].get(k) for k in FIXED):
        raise ValueError('Keep the archived model, decoding, memory, runtime and request budgets')
    selected = [t for t in task_list if t['idx'] == task_id]
    archived = {t['idx']:t for t in manifest['task_definitions']}
    if len(selected) != 1 or selected[0] != archived.get(task_id):
        raise ValueError('Use an unchanged task from the original frozen selection')
    variants, snapshot, changed = conditions(historical, snapshot_repeat)
    from .memory import load, render
    from .experience_state import as_artifact
    if load(config)['memory_sha256'] != variants['frozen_k0'][0]['memory_sha256']:
        raise ValueError('Configured initial knowledge differs from the frozen K0')
    variants = {name:variants[name] for name in CONDITIONS[:2]}
    if include_order_control:
        variants['fr_order_only'] = order_control(variants['fr_all'])
    required = {ALIASES.get(s, s) for s in selected[0]['servers']}
    callable_hashes = {digest(scope(k, selected[0])) for _, k in variants.values()}
    if len(callable_hashes) != 1:
        raise ValueError('Every condition must expose identical callable tools')
    callable_hash = next(iter(callable_hashes))
    effective = deepcopy(config)
    effective.update(strategies=['no_update'], agent_repeats=repeats)
    visible = {}
    for name, (state, knowledge) in variants.items():
        tools, _ = adapters.agent_tools(knowledge, snapshot['catalog'], required)
        context, exposure = render(effective, knowledge, required, Path('DIAGNOSTIC_WORKSPACE'),
            api_names={t['meta']['benchmark_semantic_identity']:t['name'] for t in tools},
            artifact=as_artifact(state, knowledge))
        visible[name] = {'context_sha256':digest(context), 'selected_ids':exposure['selected_ids']}
        if name == 'fr_all':
            full_context = context
        if name == 'fr_order_only':
            def decoded(text):
                return [json.loads(line) if line.startswith('{') else line for line in text.splitlines()]
            if context == full_context or len(context) != len(full_context) or decoded(context) != decoded(full_context):
                raise ValueError('Order control must change presentation with identical content and length')
    expected = fingerprints(effective)
    path = create(effective, selected, expected, False, 1)
    from custom.utils.test_utils import offset_date
    prompt_time = str(offset_date(0))
    directories = {f'{task_id}/{repeat}':str(ROOT/'.runtime/r'/uuid.uuid4().hex[:16]) for repeat in range(repeats)}
    with writer_lock(path):
        store = Store(path)
        rows = {}
        for row in store.records['trajectories'].values():
            if row['identity']['stage'] != STAGE:
                continue
            for name in variants:
                clone = deepcopy(row)
                clone['identity']['strategy'] = name
                clone.pop('shared_from', None)
                clone['counterfactual_callable_sha256'] = callable_hash
                rows[identity(name, STAGE, task_id, clone['identity']['repeat'])] = clone
        store.records.update(status='running', trajectories=rows, episodes={},
                             initial_snapshot=deepcopy(historical['initial_snapshot']))
        store.manifest.update(harness_protocol=PROTOCOL, purpose='frozen_late_memory_counterfactual',
            shared_early=None, prompt_time=prompt_time, task_annotations={},
            logical_conditions=[r['identity'] for r in rows.values()],
            planned_jobs=[r['identity'] for r in rows.values()],
            diagnostic={'source_experiment':str(source), 'source_records_sha256':file_hash(source/'records.json'),
                'snapshot_repeat':snapshot_repeat, 'stage':STAGE, 'conditions':list(variants), 'task_ids':[task_id],
                'trajectory_repeats':repeats, 'visible_memory_inputs':{str(task_id):visible},
                'actor_only':True, 'observe_workspace':True, 'paired_runtime_directories':directories,
                'clock':'current batch start', 'fixed_original_selection':manifest['selected_ids'],
                'affected_entry_ids':changed, 'paid_update_calls':0,
                'condition_hashes':{n:{'memory_sha256':s['memory_sha256'], 'reference_catalog_sha256':digest(k)}
                                   for n,(s,k) in variants.items()},
                'order':'Rotate leading condition per group; fresh paths between groups; no outcome-based stopping.'},
            analysis={'comparison':'Frozen FR versus retained unaffected knowledge; optional JSON key-order control.'})
        atomic_json(path/'experiment.json', store.manifest)
        atomic_json(path/'inputs/counterfactual-snapshots.json', variants)
        store.save()
        print('Counterfactual:', path, flush=True)
        try:
            if effective['mode'] == 'live':
                store.manifest['isolation'] = isolation_probe(effective, selected, snapshot, store.apply)
                atomic_json(path/'experiment.json', store.manifest)
            names = tuple(variants)
            for repeat in range(repeats):
                offset = repeat % len(names)
                for name in names[offset:] + names[:offset]:
                    state, knowledge = variants[name]
                    key = identity(name, STAGE, task_id, repeat)
                    run_trajectory({'config':effective, 'tasks':selected, 'task':selected[0], 'stage':STAGE,
                        'strategy':name, 'repeat':repeat, 'snapshot':deepcopy(snapshot),
                        'knowledge':deepcopy(knowledge), 'experience_state':deepcopy(state),
                        'records':{key:store.records['trajectories'][key]},
                        'initial_snapshot':deepcopy(historical['initial_snapshot']), 'prompt_time':prompt_time,
                        'phase':'agent', 'actor_only':True, 'observe_workspace':True,
                        'controlled_runtime_directory':directories[f'{task_id}/{repeat}']}, store.apply)
            if fingerprints(effective) != expected or file_hash(source/'records.json') != store.manifest['diagnostic']['source_records_sha256']:
                raise ValueError('Diagnostic inputs or historical source changed')
            store.manifest['fixture_unchanged'] = True
            atomic_json(path/'experiment.json', store.manifest)
            failed = any(r['agent_status'] != 'completed' for r in store.records['trajectories'].values())
            store.records['status'] = 'completed_with_failures' if failed else 'completed'
        except BaseException as exc:
            store.records['status'] = 'failed'
            store.event('counterfactual_failure', error=safe_error(exc))
            raise
        finally:
            store.save()
            result = report(store)
            atomic_json(path/'counterfactual.json', result)
    return path, result
