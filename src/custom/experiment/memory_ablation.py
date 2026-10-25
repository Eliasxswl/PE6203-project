"""Paired Early-only diagnostic using the existing isolated trajectory scheduler."""
from copy import deepcopy

from . import adapters
from .core import initial_snapshot, run_trajectory
from .memory import load
from .results import Store, atomic_json, create, identity, safe_error, writer_lock
from .selection import ROOT, fingerprints

PROTOCOL = 'langmem_usefulness_ablation_v1'
CONDITIONS = ('without_memory', 'with_memory')
RECOVERY_CONDITIONS = ('without_memory', 'file_only', 'error_triggered')
PILOT_CONDITIONS = ('full_memory',)


def report_pilot(store):
    from custom.agents.tool_feedback import reported_error
    rows = list(store.records['trajectories'].values())
    metrics = ('task_fulfillment', 'grounding', 'planning_and_efficiency')
    scored = [r for r in rows if r.get('score') is not None]
    output = {'protocol': 'complete_memory_task_pilot_v1', 'status': store.records['status'],
        'purpose': 'Development inspection on the unchanged selected tasks, not a memory-benefit or strategy comparison.',
        'planned': len(rows), 'completed_agents': sum(r['agent_status'] == 'completed' for r in rows),
        'scored': len(scored), 'valid_judge_slots': sum(a['status'] == 'completed' for r in rows for a in r['judge_attempts']),
        'means': {m: sum(r['score'][m] for r in scored) / len(scored) if scored else None for m in metrics}, 'tasks': []}
    for row in sorted(rows, key=lambda r: (r['identity']['task_id'], r['identity']['repeat'])):
        calls = row['raw_tool_trace']
        errors = []
        for index, call in enumerate(calls):
            if reported_error(call.get('semantic_identity'), call['response']):
                errors.append({'tool_call_id': call['tool_call_id'], 'tool': call['semantic_identity'],
                    'later_successful_same_tool_call': any(c['semantic_identity'] == call['semantic_identity'] and
                        not reported_error(c.get('semantic_identity'), c['response']) for c in calls[index+1:])})
        exposure = row.get('memory_exposure', {})
        output['tasks'].append({'task_id': row['identity']['task_id'], 'repeat': row['identity']['repeat'],
            'agent_status': row['agent_status'], 'score': row.get('score'), 'stop_reason': row.get('stop_reason'),
            'requests': row.get('request_count'), 'request_limit': row.get('request_limit'),
            'selected_memory_ids': exposure.get('selected_ids', []),
            'complete_library_visible': bool(exposure.get('total_library_entries')) and
                len(exposure.get('selected_ids', [])) == exposure['total_library_entries'],
            'tool_errors': errors, 'unrecovered_tool_errors': sum(not e['later_successful_same_tool_call'] for e in errors),
            'schema_feedback_calls': sum(bool(c.get('harness_schema_feedback')) for c in calls),
            'review_required': bool(errors) or row['agent_status'] != 'completed'})
    return output


def report_three(store):
    rows = store.records['trajectories']
    metrics = ('task_fulfillment', 'grounding', 'planning_and_efficiency')
    output = {'protocol': 'triggered_recovery_three_arm_v1', 'status': store.records['status'], 'conditions': {},
        'interpretation': 'Frozen Early-only knowledge ablation; primary means use identical task/repeat triples. Missing slots are not zeros. No evolution-method claim.'}
    for condition in RECOVERY_CONDITIONS:
        group = [r for r in rows.values() if r['identity']['strategy'] == condition]
        output['conditions'][condition] = {'planned': len(group), 'completed_agents': sum(r['agent_status'] == 'completed' for r in group),
            'scored': sum(r.get('score') is not None for r in group), 'execution_failures': sum(r['agent_status'] == 'failed' for r in group),
            'valid_judge_slots': sum(a['status'] == 'completed' for r in group for a in r['judge_attempts']),
            'not_attempted_judge_slots': sum(a['status'] == 'not_attempted' for r in group for a in r['judge_attempts']),
            'activation_count': sum(len(r.get('memory_activations', [])) for r in group),
            'activated_trajectories': sum(bool(r.get('memory_activations')) for r in group)}
    units = sorted({(r['identity']['task_id'], r['identity']['repeat']) for r in rows.values()})
    triples = []
    for task_id, repeat in units:
        triple = {c: rows[identity(c, 'original', task_id, repeat)] for c in RECOVERY_CONDITIONS}
        if all(r.get('score') is not None for r in triple.values()):
            triples.append((task_id, repeat, triple))
    def means(items):
        return {c: {m: sum(t[c]['score'][m] for _, _, t in items) / len(items) if items else None for m in metrics} for c in RECOVERY_CONDITIONS}
    output['common_sample'] = {'triples': len(triples), 'tasks': len({i for i, _, _ in triples}), 'means': means(triples),
        'same_catalog': all(len({r.get('knowledge_sha256') for r in t.values()}) == 1 for _, _, t in triples),
        'included': [{'task_id': i, 'repeat': j} for i, j, _ in triples]}
    complete = [(i, j, t) for i, j, t in triples if all(sum(a['status'] == 'completed' for a in r['judge_attempts']) == 5 for r in t.values())]
    output['complete_five_judge_sensitivity'] = {'triples': len(complete), 'means': means(complete)}
    output['comparisons'] = {}
    for baseline, treatment in [('without_memory', 'file_only'), ('without_memory', 'error_triggered'), ('file_only', 'error_triggered')]:
        pairs = []
        for task_id, repeat in units:
            before, after = (rows[identity(c, 'original', task_id, repeat)] for c in (baseline, treatment))
            if before.get('score') is not None and after.get('score') is not None:
                pairs.append({'task_id': task_id, 'repeat': repeat, 'deltas': {m: after['score'][m] - before['score'][m] for m in metrics}})
        output['comparisons'][treatment + '_vs_' + baseline] = {'baseline': baseline, 'treatment': treatment,
            'pairs': len(pairs), 'mean_deltas': {m: sum(p['deltas'][m] for p in pairs) / len(pairs) if pairs else None for m in metrics}, 'details': pairs}
    output['tasks'] = [{'task_id': i, 'triples': len(group), 'means': means(group)} for i in sorted({x[0] for x in triples})
                       for group in [[x for x in triples if x[0] == i]]]
    return output


def check_frozen_scopes(snapshot, artifact, required_servers):
    """Check relevant frozen domains; unseen public catalogs are shared by both arms."""
    known = {tool['server'] for tool in artifact['catalog'].values()}
    available = set(required_servers) - set(snapshot['errors'])
    expected = {k: v for k, v in artifact['catalog'].items() if v['server'] in available}
    current = {k: v for k, v in adapters.semantic(snapshot['catalog']).items()
               if v['server'] in known & available}
    if current != expected:
        raise ValueError('Early tool catalog differs from frozen evidence in a required knowledge domain')


def report(store):
    if store.manifest.get('diagnostic', {}).get('conditions') == list(PILOT_CONDITIONS):
        return report_pilot(store)
    if store.manifest.get('diagnostic', {}).get('conditions') == list(RECOVERY_CONDITIONS):
        return report_three(store)
    rows = list(store.records['trajectories'].values())
    output = {'protocol': store.manifest.get('harness_protocol', PROTOCOL), 'status': store.records['status'], 'conditions': {}, 'pairs': [],
              'interpretation': 'Frozen-knowledge Early-only comparison; model rubric scores do not certify task completion or evolution-method superiority.'}
    for condition in CONDITIONS:
        group = [r for r in rows if r['identity']['strategy'] == condition]
        valid = [r for r in group if r.get('score') is not None]
        output['conditions'][condition] = {'planned': len(group), 'scored': len(valid),
            'exposed_trajectories': sum(bool(r.get('memory_exposure', {}).get('selected_ids')) for r in group),
            'selected_memory_ids': {str(r['identity']['task_id']) + '/' + str(r['identity']['repeat']):
                                    r.get('memory_exposure', {}).get('selected_ids', []) for r in group},
            'means': {key: sum(r['score'][key] for r in valid) / len(valid) if valid else None
                      for key in ('task_fulfillment', 'grounding', 'planning_and_efficiency')},
            'judge_slots': sum(len(r['judge_attempts']) for r in group),
            'valid_judge_slots': sum(a['status'] == 'completed' for r in group for a in r['judge_attempts']),
            'agent_requests': sum(len(r['agent_attempts']) for r in group),
            'execution_failures': sum(r['agent_status'] == 'failed' for r in group),
            'tool_calls': sum(len(r.get('raw_tool_trace', [])) for r in group),
            'tool_error_responses': sum(bool(c.get('response', {}).get('isError')) for r in group for c in r.get('raw_tool_trace', []))}
    for task_id, repeat in sorted({(r['identity']['task_id'], r['identity']['repeat']) for r in rows}):
        pair = {c: store.records['trajectories'][identity(c, 'original', task_id, repeat)] for c in CONDITIONS}
        valid_pair = all(r.get('score') is not None for r in pair.values())
        output['pairs'].append({'task_id': task_id, 'repeat': repeat,
            'same_catalog': all(r.get('knowledge_sha256') for r in pair.values()) and
                len({r.get('knowledge_sha256') for r in pair.values()}) == 1,
            'tf_delta_with_minus_without': pair['with_memory']['score']['task_fulfillment'] -
                pair['without_memory']['score']['task_fulfillment']
                if valid_pair else None,
            'score_deltas_with_minus_without': {s: pair['with_memory']['score'][s] - pair['without_memory']['score'][s]
                for s in ('task_fulfillment', 'grounding', 'planning_and_efficiency')} if valid_pair else None,
            'memory_exposed': bool(pair['with_memory'].get('memory_exposure', {}).get('selected_ids')),
            'tool_error_responses': {c: sum(bool(t.get('response', {}).get('isError')) for t in r.get('raw_tool_trace', [])) for c, r in pair.items()}})
    pairs = output['pairs']
    for label, matched in [('all_tasks', [p for p in pairs if p['score_deltas_with_minus_without'] is not None]),
                           ('memory_exposed', [p for p in pairs if p['memory_exposed'] and p['score_deltas_with_minus_without'] is not None])]:
        output.setdefault('paired', {})[label] = {'pairs': len(matched),
            'mean_score_deltas_with_minus_without': {s: sum(p['score_deltas_with_minus_without'][s] for p in matched) / len(matched)
                if matched else None for s in ('task_fulfillment', 'grounding', 'planning_and_efficiency')}}
    output['tasks'] = []
    for idx in sorted({p['task_id'] for p in pairs}):
        matched = [p for p in pairs if p['task_id'] == idx and p['tf_delta_with_minus_without'] is not None]
        output['tasks'].append({'task_id': idx, 'paired_repeats': len(matched),
            'mean_tf_delta_with_minus_without': sum(p['tf_delta_with_minus_without'] for p in matched) / len(matched) if matched else None,
            'memory_exposed_repeats': sum(p['memory_exposed'] for p in pairs if p['task_id'] == idx)})
    return output


def run(config, task_list, task_ids, parallel=False, workers=1):
    from .runtime import ALIASES, policy_for, reap_orphans
    from custom.utils.test_utils import offset_date
    if not task_ids or len(task_ids) != len(set(task_ids)) or not set(task_ids) <= {t['idx'] for t in task_list}:
        raise ValueError('Diagnostic IDs must be distinct members of the frozen selection')
    if type(workers) is not int or not 1 <= workers <= 10 or (not parallel and workers != 1):
        raise ValueError('Use 1 to 10 workers; serial mode uses one')
    artifact = load(config)
    comparison = config['memory'].get('comparison')
    conditions = PILOT_CONDITIONS if comparison == 'full_pilot' else RECOVERY_CONDITIONS if comparison == 'three_arm' else CONDITIONS
    if conditions == PILOT_CONDITIONS and (config['agent_repeats'] != 1 or config['memory'].get('profile') != 'complete'):
        raise ValueError('Full-library task pilot requires one repeat and the complete memory profile')
    if conditions == RECOVERY_CONDITIONS and artifact['protocol'] != 'verified_tool_recovery_k0_v1':
        raise ValueError('Three-arm recovery comparison requires verified frozen knowledge')
    selected = [next(t for t in task_list if t['idx'] == idx) for idx in task_ids]
    for server in {ALIASES.get(s, s) for t in selected for s in t['servers']}:
        if parallel and policy_for(server, config).get('concurrency') not in ('private', 'readonly'):
            raise ValueError('Memory diagnostic requires isolated or readonly tools: ' + server)
    config = deepcopy(config)
    config['strategies'] = ['no_update']  # Native store templates only; no adaptation is performed.
    expected = fingerprints(config)
    path = create(config, selected, expected, parallel, workers)
    with writer_lock(path):
        store = Store(path)
        rows = {}
        for template in store.records['trajectories'].values():
            if template['identity']['stage'] != 'original':
                continue
            for condition in conditions:
                row = deepcopy(template)
                row['identity']['strategy'] = condition
                row.pop('shared_from', None)
                rows[identity(condition, 'original', row['identity']['task_id'], row['identity']['repeat'])] = row
        store.records.update(trajectories=rows, episodes={}, status='running')
        recovery = artifact['protocol'] == 'verified_tool_recovery_k0_v1'
        store.manifest.update(harness_protocol='verified_recovery_usefulness_ablation_v1' if recovery else PROTOCOL,
            purpose='frozen_recovery_knowledge_usefulness' if recovery else 'official_langmem_usefulness_diagnostic',
            diagnostic={'task_ids': task_ids, 'memory_sha256': artifact['memory_sha256'],
                'conditions': list(conditions), 'stage': 'original', 'no_online_learning': True,
                'order': 'Rotate leading condition by task position/repeat; parallel completion unrestricted'},
            shared_early=None, task_annotations={}, prompt_time=str(offset_date(0)),
            analysis={'comparison': 'with versus without frozen LangMem knowledge; no ECS'},
            logical_conditions=[r['identity'] for r in rows.values()], planned_jobs=[r['identity'] for r in rows.values()])
        atomic_json(path / 'experiment.json', store.manifest)
        if conditions == PILOT_CONDITIONS:
            store.manifest.update(harness_protocol='complete_memory_task_pilot_v1', purpose='fixed_task_experience_adaptation_development')
            store.manifest['analysis'] = {'comparison': 'Single full-library development pass on the unchanged selection; no memory ablation or ECS',
                'evaluation': 'Existing five-slot rubric and unchanged request caps; inspect every task trace and all missing results'}
            store.manifest['diagnostic']['condition_settings'] = {'full_memory': {'inject': True, 'profile': 'complete'}}
            atomic_json(path / 'experiment.json', store.manifest)
        if conditions == RECOVERY_CONDITIONS:
            store.manifest['harness_protocol'] = 'triggered_recovery_three_arm_v1'
            store.manifest['analysis'] = {'comparison': 'without memory / file only / file plus error-triggered recovery; no ECS',
                'primary': 'All scored task/repeat triples, same samples across three conditions',
                'sensitivity': 'Triples with all five Judge slots valid in every condition',
                'missing_data': 'No retry or slot top-up; show all coverage and pairwise results'}
            store.manifest['diagnostic']['condition_settings'] = {
                'without_memory': {'inject': False, 'profile': 'file_only'},
                'file_only': {'inject': True, 'profile': 'file_only'},
                'error_triggered': {'inject': True, 'profile': 'error_triggered'}}
            atomic_json(path / 'experiment.json', store.manifest)
        inputs = path / 'inputs'
        inputs.mkdir()
        atomic_json(inputs / 'frozen-k0.json', artifact)
        from .selection import read_json
        atomic_json(inputs / 'practice-evidence.json', read_json(ROOT / config['memory']['source']))
        store.save()
        print('LangMem diagnostic: ' + str(path), flush=True)
        try:
            snapshot = initial_snapshot(config, task_list, store.apply)
            required_servers = {ALIASES.get(s, s) for task in task_list for s in task['servers']}
            check_frozen_scopes(snapshot, artifact, required_servers)
            store.records['initial_snapshot'] = snapshot
            jobs = []
            for repeat in range(config['agent_repeats']):
                for position, task in enumerate(selected):
                    offset = (position + repeat) % len(conditions)
                    for condition in conditions[offset:] + conditions[:offset]:
                        effective = deepcopy(config)
                        effective['memory']['inject'] = condition == 'with_memory'
                        if conditions == PILOT_CONDITIONS:
                            effective['memory'].update(inject=True, profile='complete')
                        if conditions == RECOVERY_CONDITIONS:
                            effective['memory']['inject'] = condition != 'without_memory'
                            effective['memory']['profile'] = 'error_triggered' if condition == 'error_triggered' else 'file_only'
                        jobs.append({'config': effective, 'tasks': task_list, 'task': task,
                            'stage': 'original', 'strategy': condition, 'repeat': repeat,
                            'snapshot': deepcopy(snapshot), 'knowledge': deepcopy(snapshot['knowledge']),
                            'records': rows, 'initial_snapshot': snapshot, 'prompt_time': store.manifest['prompt_time']})
            if parallel:
                from .parallel import supervise_stage
                supervise_stage(jobs, store, workers, config['runtime']['shutdown_timeout'])
            else:
                for job in jobs:
                    run_trajectory(job, store.apply)
            if fingerprints(config) != expected:
                store.records['status'] = 'invalidated'
                for row in store.records['trajectories'].values():
                    row.update(score=None, score_exclusion_reason='experimental_inputs_changed')
            else:
                complete = all(r['status'] == 'completed' and r.get('score') is not None for r in store.records['trajectories'].values())
                store.records['status'] = 'completed' if complete else 'completed_with_failures'
        except BaseException as exc:
            store.records['status'] = 'failed_or_interrupted'
            store.event('memory_diagnostic_failed', error=safe_error(exc))
            store.recover(reason='memory_diagnostic_interrupted')
            raise
        finally:
            reap_orphans(store.records['events'])
            store.save()
            output = report(store)
            atomic_json(path / ('task-review.json' if conditions == PILOT_CONDITIONS else 'memory-ablation.json'), output)
    return path, output
