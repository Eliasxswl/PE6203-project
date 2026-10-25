"""Independent file-recovery transfer check: new practice, frozen rules, untouched held-outs."""
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
from .causal import SERVER, build_procedure, call_template_schema, execute_trial, normalize, outcome, source_hash, text
from .core import runtime_for
from .memory import REFERENCE_PREFIX, guidance_line
from .results import atomic_json, safe_error
from .selection import ROOT, digest, file_hash, tree_hash

PROTOCOL = 'file_recovery_transfer_v1'
CONDITIONS = ('no_rule', 'old_rule', 'new_rule', 'irrelevant_rule')
OLD_ARTIFACT = 'results/20261024T211931.519298Z_Kevin/inputs/frozen-k0.json'
SUMMARY_ARTIFACT = 'results/20261024T220523.893038Z_Kevin/frozen-rule.json'


def cases(template_mode=False):
    """Fixed before generation; the builder sees only the practice split."""
    definitions = [
        ('practice-middle', 'practice', 'cobalt', 'draft-{key}-v2.txt', 1, 'discovery'),
        ('practice-extension', 'practice', 'marigold', 'archive-{key}.md', 3, 'discovery'),
        ('practice-known', 'practice', 'quartz', '{key}-memo.txt', 0, 'known_path'),
        ('test-suffix', 'heldout', 'harbor', 'archive-{key}.txt', 2, 'discovery'),
        ('test-middle-root', 'heldout', 'falcon', 'check-{key}-final.md', 0, 'discovery'),
        ('test-prefix', 'heldout', 'cedar', '{key}-note.log', 4, 'discovery'),
        ('test-csv', 'heldout', 'meadow', 'notes-report-{key}.csv', 1, 'discovery'),
        ('test-json', 'heldout', 'opal', 'v1-{key}-backup.json', 3, 'discovery'),
        ('test-exact-name', 'heldout', 'breeze', '{key}.txt', 2, 'discovery'),
        ('test-known', 'heldout', 'willow', 'saved-{key}.txt', 3, 'known_path'),
        ('test-visible-tree', 'heldout', 'saffron', 'packet-{key}-memo.md', 2, 'visible_tree')]
    if template_mode:
        words = iter(('anchorage', 'chestnut', 'seashell', 'riverbed', 'onyx', 'zephyr', 'maple', 'safflower'))
        definitions = [(name, split, next(words) if split == 'heldout' else key,
                        template.replace('.log', '.ini').replace('.csv', '.yaml') if split == 'heldout' else template,
                        depth, mode) for name, split, key, template, depth, mode in definitions]
    version = 'file-transfer-v2-' if template_mode else 'file-transfer-v1-'
    return [{'id': name, 'split': split, 'keyword': key, 'cohort': mode,
             'relative_path': '/'.join([f'level-{i}' for i in range(depth)] + [template.format(key=key)]),
             'content': 'Payload: ' + hashlib.sha256((version + name).encode()).hexdigest()}
            for name, split, key, template, depth, mode in definitions]


def render_rule(entries, catalog):
    aliases = {k: v['name'] for k, v in catalog.items()}
    return REFERENCE_PREFIX + ''.join(guidance_line(e, aliases, Path('${WORKSPACE}')) for e in sorted(entries, key=lambda e: e['id']))


def irrelevant_reference(length, catalog):
    filler = 'Display colors and archive theme labels are cosmetic. '
    value = {'tool_ids': list(catalog), 'content': '', 'applicability': 'Display theme preferences.',
             'failed_assumption': 'Cosmetic colors alter labels.', 'corrective_actions': ['Keep current display colors.'],
             'verification': 'Display labels retain their colors.'}
    entry = {'id': 'neutral-control', 'value': value}
    base = render_rule([entry], catalog)
    if len(base) > length:
        raise ValueError('Knowledge context too short for the matched irrelevant control')
    padding = length - len(base)
    value['content'] = (filler * (padding // len(filler) + 1))[:padding]
    return render_rule([entry], catalog)


def practice(config, case, directory):
    from custom.agents.tool_results import raw_result
    calls = []
    with runtime_for(config, 'original', [SERVER], [], None) as runtime:
        catalog = {k: v for k, v in adapters.semantic(runtime.catalog).items()
                   if k.endswith(('::search_files', '::read_text_file'))}
        tools = {t['meta']['benchmark_semantic_identity']: t for t in adapters.agent_tools(catalog, runtime.catalog, {SERVER})[0]}

        def call(name, args):
            response = raw_result(runtime.call(tools[SERVER + '::' + name]['meta']['benchmark_remote_name'], args))
            calls.append({'tool_call_id': case['id'] + '-' + str(len(calls)),
                'semantic_identity': SERVER + '::' + name, 'arguments': json.dumps(args), 'response': response})
            atomic_json(directory / (case['id'] + '.json'), {'calls': calls})
            return response

        root = runtime.workspace.as_posix()
        target = runtime.workspace / case['relative_path']
        if case['cohort'] == 'known_path':
            call('read_text_file', {'path': target.as_posix()})
        else:
            call('read_text_file', {'path': root + '/' + case['keyword'] + '.txt'})
            pattern = '**/' + case['keyword'] + '*.txt' if case['id'] == 'practice-middle' else '**/*' + case['keyword'] + '*.txt'
            wrong = call('search_files', {'path': root, 'pattern': pattern})
            if text(wrong) != 'No matches found':
                raise ValueError('Declared failed search unexpectedly matched a file')
            found = call('search_files', {'path': root, 'pattern': '**/*' + case['keyword'] + '*'})
            if target.as_posix() not in text(found).replace('\\', '/'):
                raise ValueError('Practice correction did not discover the target')
            call('read_text_file', {'path': target.as_posix()})
        verified = outcome(calls, target, case['content'])
        if not verified['success'] or (case['cohort'] == 'discovery' and not calls[0]['response'].get('isError')):
            raise ValueError('Practice error/correction evidence was not verified')
        for c in calls:
            if c['tool_call_id'] in verified['verified_read_call_ids']:
                c['verification'] = {'kind': 'exact_file_read', 'response_sha256': digest(c['response'])}
        evidence = {'case': case['id'], 'scenario': 'Locate by a filename keyword; extension is not supplied.'
                    if case['cohort'] == 'discovery' else 'The exact existing file path is already known; read directly.',
                    'observed_calls': normalize(calls, runtime.workspace), 'verified_read_call_ids': verified['verified_read_call_ids']}
        atomic_json(directory / (case['id'] + '.json'), evidence)
        return evidence, catalog


def validate_rule(entries, evidence, catalog, training):
    if not entries:
        raise ValueError('No new knowledge was produced')
    value = entries[0]['value']
    if not set(value['tool_ids']) <= set(catalog):
        raise ValueError('New rule refers to an unobserved tool')
    ids = set(value['evidence_call_ids'])
    known = {c['tool_call_id'] for e in evidence for c in e['observed_calls']}
    if not ids <= known:
        raise ValueError('New rule cited an unobserved call')
    for e in evidence:
        if not set(e['verified_read_call_ids']) <= ids:
            raise ValueError('New rule omitted a verified practice boundary')
        if e['case'] != 'practice-known' and not ids & {c['tool_call_id'] for c in e['observed_calls'] if c['response'].get('isError')}:
            raise ValueError('New rule omitted actual failure evidence')
    rendered = json.dumps(value, ensure_ascii=False)
    for c in training:
        if c['keyword'].casefold() in rendered.casefold() or c['content'].split(': ', 1)[-1] in rendered:
            raise ValueError('New rule memorized a practice constant')


def substitute(arguments, values):
    rendered = deepcopy(arguments)
    for key, value in rendered.items():
        if not isinstance(value, str):
            raise ValueError('File call templates require string argument values')
        for variable, replacement in values.items():
            value = value.replace('${' + variable + '}', replacement)
        if '${' in value:
            raise ValueError('Unresolved call-template placeholder')
        rendered[key] = value
    return rendered


def retain_templates(evidence, catalog, training, path):
    """Retain literal successful syntax; parameterize observed input and output bindings only."""
    templates = None
    for observation, case in zip(evidence, training):
        if case['cohort'] != 'discovery':
            continue
        calls = observation['observed_calls']
        read_index = next(i for i, c in enumerate(calls) if c['tool_call_id'] in observation['verified_read_call_ids'])
        read = calls[read_index]
        proof = read.get('verification') or {}
        if read['response'].get('isError') or proof.get('response_sha256') != digest(read['response']):
            raise ValueError('Cannot retain an unverified read')
        target = json.loads(read['arguments'])['path']
        searches = [c for c in calls[:read_index] if c['semantic_identity'] == SERVER + '::search_files'
                    and not c['response'].get('isError') and target.replace('\\', '/') in text(c['response']).replace('\\', '/')]
        if not searches:
            raise ValueError('No observed successful search led to the verified read')
        pair = [searches[-1], read]
        current = []
        for position, call in enumerate(pair):
            if call['semantic_identity'] not in catalog:
                raise ValueError('Successful trace refers to an unobserved tool')
            arguments = json.loads(call['arguments'])
            for key, value in arguments.items():
                if not isinstance(value, str):
                    raise ValueError('Retained file-call arguments must be strings')
                arguments[key] = '${DISCOVERED_PATH}' if position == 1 and value == target else value.replace(case['keyword'], '${KEYWORD}')
            current.append({'tool_id': call['semantic_identity'], 'arguments': arguments, 'evidence_call_ids': [call['tool_call_id']]})
        if templates is None:
            templates = current
        else:
            for previous, item in zip(templates, current):
                if previous['tool_id'] != item['tool_id'] or previous['arguments'] != item['arguments']:
                    raise ValueError('Successful examples do not share a common input-bound template')
                previous['evidence_call_ids'].extend(item['evidence_call_ids'])
    if not templates:
        raise ValueError('No verified recovery templates could be retained')
    for template in templates:
        call_template_schema().model_validate(template, strict=True)
    atomic_json(path, {'status': 'accepted', 'method': 'verified_trace_parameterization',
                      'templates': templates, 'requests': [], 'summary_source': SUMMARY_ARTIFACT})
    return templates


def replay_templates(config, templates, training, directory):
    """Admission checks only training cases; test Agents remain free to choose their own calls."""
    from custom.agents.tool_results import raw_result
    for case in training:
        if case['cohort'] != 'discovery':
            continue
        effective = deepcopy(config)
        effective['fixtures'] = (directory / 'fixtures' / case['id']).relative_to(ROOT).as_posix()
        calls = []
        with runtime_for(effective, 'original', [SERVER], [], None) as runtime:
            values = {'WORKSPACE': runtime.workspace.as_posix(), 'KEYWORD': case['keyword']}
            for index, template in enumerate(templates):
                tool = runtime.catalog[template['tool_id']]
                arguments = substitute(template['arguments'], values)
                response = raw_result(runtime.call(tool['remote_name'], arguments))
                calls.append({'tool_call_id': 'replay-' + str(index), 'semantic_identity': template['tool_id'],
                              'arguments': json.dumps(arguments), 'response': response})
                atomic_json(directory / 'practice' / (case['id'] + '-template-replay.json'), {'calls': normalize(calls, runtime.workspace), 'status': 'replaying'})
                if index == 0:
                    values['DISCOVERED_PATH'] = text(response).splitlines()[0]
            verified = outcome(calls, runtime.workspace / case['relative_path'], case['content'])
            atomic_json(directory / 'practice' / (case['id'] + '-template-replay.json'), {'calls': normalize(calls, runtime.workspace), 'verified': verified})
            if not verified['success']:
                raise ValueError('Call templates failed physical practice replay')


def summarize(rows, planned, rejection):
    result = {'protocol': PROTOCOL, 'status': 'completed_with_rejected_knowledge' if rejection else 'completed',
              'judge_calls': 0, 'conditions': {}, 'paired': {}, 'knowledge_rejection': rejection}
    for condition in CONDITIONS:
        selected = [r for r in rows if r['condition'] == condition]
        result['conditions'][condition] = {'planned': planned, 'executed': len(selected),
            'execution_failures': sum(r['status'] != 'completed' for r in selected),
            'correct_reads': sum(bool((r.get('outcome') or {}).get('success')) for r in selected),
            'completed_task_successes': sum(r['status'] == 'completed' and bool((r.get('outcome') or {}).get('task_success')) for r in selected)}
    for other in ('no_rule', 'old_rule', 'irrelevant_rule'):
        pairs = []
        for row in [r for r in rows if r['condition'] == 'new_rule']:
            baseline = next(r for r in rows if r['case'] == row['case'] and r['repeat'] == row['repeat'] and r['condition'] == other)
            if row['status'] == baseline['status'] == 'completed':
                pairs.append({'case': row['case'], 'repeat': row['repeat'], 'cohort': row['cohort'],
                    'new': bool(row['outcome']['task_success']), 'other': bool(baseline['outcome']['task_success'])})
        result['paired'][other] = {label: {'pairs': len(group), 'new_successes': sum(p['new'] for p in group),
            'other_successes': sum(p['other'] for p in group),
            'wins': sum(p['new'] and not p['other'] for p in group), 'losses': sum(p['other'] and not p['new'] for p in group)}
            for label, group in [('all', pairs), ('discovery', [p for p in pairs if p['cohort'] == 'discovery']),
                                 ('easy_controls', [p for p in pairs if p['cohort'] != 'discovery'])]}
    if any(r['status'] != 'completed' for r in rows):
        result['status'] = 'completed_with_failures'
    return result


def export_candidate(directory, learned, evidence, training, catalog, model, build_requests=1):
    """Prepare a loadable candidate K0 before testing; preserve unrelated knowledge verbatim."""
    from .recovery_memory import validate_artifact
    old = read_json(ROOT / OLD_ARTIFACT)
    old_source_path = (ROOT / OLD_ARTIFACT).with_name('practice-evidence.json')
    old_source = read_json(old_source_path)
    if (digest(old['memories']) != old['memory_sha256'] or digest(old_source['catalog']) != digest(old['catalog'])
            or file_hash(old_source_path) != old['source_sha256']):
        raise ValueError('Old knowledge provenance mismatch')
    for key, tool in catalog.items():
        if old['catalog'].get(key) != tool:
            raise ValueError('File tool catalog changed since the old knowledge snapshot')
    previous = next(e for e in old['memories'] if e['case_id'] == 'recursive-file-recovery')
    case = {'id': 'expanded-file-recovery', 'trace': [c for e in evidence for c in e['observed_calls']],
            'required_success_tool': SERVER + '::read_text_file',
            'forbidden_constants': [v for c in training for v in (c['keyword'], c['content'])]}
    entry = {**deepcopy(learned[0]), 'id': previous['id'], 'case_id': case['id']}
    others = [e for e in old['memories'] if e['id'] != previous['id']]
    source = {'origin': 'independent_verified_recovery_practice', 'catalog': old['catalog'],
        'cases': [case] + [c for c in old_source['cases'] if c['id'] in {e['case_id'] for e in others}],
        'scope': 'Expanded independent synthetic file practice; other frozen knowledge retained verbatim.',
        'old_artifact_sha256': file_hash(ROOT / OLD_ARTIFACT)}
    atomic_json(directory / 'candidate-evidence.json', source)
    entries = [entry if e['id'] == previous['id'] else deepcopy(e) for e in old['memories']]
    candidate = {'protocol': old['protocol'], 'source_sha256': file_hash(directory / 'candidate-evidence.json'),
        'catalog': old['catalog'], 'memories': entries, 'memory_sha256': digest(entries),
        'builder_model': model, 'no_online_learning': True,
        'status': 'candidate_frozen_before_validation', 'builds': [{'case': case['id'], 'requests': build_requests, 'journal': 'knowledge-build.json'}]}
    validate_artifact(candidate, source)
    atomic_json(directory / 'candidate-k0.json', candidate)
    return candidate['memory_sha256']


def run(config, workers=1, template_mode=False):
    from custom.utils.test_utils import offset_date
    if config.get('mode') == 'offline' or config.get('agent_backend') != 'langchain' or not 1 <= workers <= 10:
        raise ValueError('Transfer validation requires the live official loop and 1 to 10 workers')
    operator = subprocess.check_output(['git', 'config', 'user.name'], cwd=ROOT, text=True).strip()
    operator = ''.join(c if c.isalnum() or c in '-_' else '_' for c in operator)
    directory = ROOT / 'results' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ_') + operator)
    directory.mkdir()
    for name in ('practice', 'trials', 'fixtures'):
        (directory / name).mkdir()
    protocol = 'file_recovery_transfer_retained_calls_v1' if template_mode else PROTOCOL
    definitions = cases(template_mode)
    for case in definitions:
        fixture = directory / 'fixtures' / case['id']
        target = fixture / case['relative_path']
        target.parent.mkdir(parents=True)
        target.write_text(case['content'], encoding='utf-8')
        (fixture / 'unrelated-note.txt').write_text('Unrelated disposable practice data.', encoding='utf-8')
    manifest = {'protocol': protocol, 'status': 'preparing', 'cases': definitions, 'settings': config,
                'workers': workers, 'repeats': config['agent_repeats'], 'conditions': list(CONDITIONS),
                'request_limit': 4, 'judge_calls': 0, 'source_sha256': source_hash(),
                'fixtures_sha256': tree_hash(directory / 'fixtures'), 'old_artifact_sha256': file_hash(ROOT / OLD_ARTIFACT),
                'success_criterion': 'Correct target read with exact bytes AND payload returned in final answer; provider failures excluded from paired comparisons.',
                'claim_limit': 'Independent synthetic transfer check developed after observing a benchmark weakness; not a fresh estimate of full benchmark performance.'}
    atomic_json(directory / 'experiment.json', manifest)
    print('Transfer validation: ' + str(directory), flush=True)
    try:
        evidence, catalog = [], None
        training = [c for c in definitions if c['split'] == 'practice']
        for case in training:
            effective = deepcopy(config)
            effective['fixtures'] = (directory / 'fixtures' / case['id']).relative_to(ROOT).as_posix()
            observed, current = practice(effective, case, directory / 'practice')
            if catalog is not None and catalog != current:
                raise ValueError('Practice catalog changed between cases')
            evidence.append(observed)
            catalog = current
        old = [e for e in read_json(ROOT / OLD_ARTIFACT)['memories'] if e['case_id'] == 'recursive-file-recovery']
        if template_mode:
            prior_summary = read_json(ROOT / SUMMARY_ARTIFACT)
            if prior_summary['rejection']:
                raise ValueError('No accepted frozen summary to enrich')
            old = deepcopy(prior_summary['knowledge'])
            manifest.update(summary_artifact_sha256=file_hash(ROOT / SUMMARY_ARTIFACT),
                condition_meanings={'no_rule': 'No knowledge', 'old_rule': 'Frozen summary only',
                                    'new_rule': 'Identical summary plus retained and physically verified successful call templates',
                                    'irrelevant_rule': 'Matched irrelevant reference'})
        rejection, learned, new_rule = None, [], None
        try:
            if template_mode:
                templates = retain_templates(evidence, catalog, training, directory / 'knowledge-build.json')
                replay_templates(config, templates, training, directory)
                learned = deepcopy(old)
                learned[0]['value']['tool_call_templates'] = templates
                learned[0]['id'] = digest(learned[0]['value'])[:24]
            else:
                required = [c['tool_call_id'] for e in evidence for c in e['observed_calls']
                            if c['response'].get('isError') or c['tool_call_id'] in e['verified_read_call_ids']]
                learned, build = build_procedure(config, {'independent_practice': evidence, 'required_evidence_call_ids': required,
                    'scope': 'Explain all verified contrasts, including the direct-read boundary. Preserve each failure and verified-read ID. Infer a reusable procedure; do not copy practice constants.'},
                    catalog, directory / 'knowledge-build.json')
            validate_rule(learned, evidence, catalog, training)
            new_rule = render_rule(learned, catalog)
        except Exception as exc:
            rejection = safe_error(exc)
        if rejection:
            summary = summarize([], 8 * config['agent_repeats'], rejection)
            summary['protocol'] = protocol
            summary.update(status='rejected_before_validation', fixtures_unchanged=tree_hash(directory / 'fixtures') == manifest['fixtures_sha256'],
                           source_unchanged=source_hash() == manifest['source_sha256'])
            manifest.update(status=summary['status'], knowledge_rejection=rejection)
            atomic_json(directory / 'frozen-rule.json', {'knowledge': learned, 'sha256': digest(learned), 'rejection': rejection})
            atomic_json(directory / 'experiment.json', manifest)
            atomic_json(directory / 'transfer-summary.json', summary)
            return directory, summary
        candidate_sha = export_candidate(directory, learned, evidence, training, catalog, config['agent_model'], build_requests=0 if template_mode else 1) if not rejection else None
        length = len(new_rule or render_rule(old, catalog))
        rules = {'no_rule': '', 'old_rule': render_rule(old, catalog), 'new_rule': new_rule,
                 'irrelevant_rule': irrelevant_reference(length, catalog)}
        manifest.update(status='running', knowledge=learned, knowledge_sha256=digest(learned), rules=rules,
                        candidate_k0_sha256=candidate_sha, presentation='Same renderer and reference prefix as the official-task memory comparison.',
                        knowledge_rejection=rejection, control_length='Irrelevant reference character-matches new rule, or old rule if new generation rejected; not token matched.')
        atomic_json(directory / 'frozen-rule.json', {'knowledge': learned, 'sha256': digest(learned), 'rejection': rejection})
        atomic_json(directory / 'experiment.json', manifest)
        specs = []
        pool = config['providers']['agent']
        heldout = [c for c in definitions if c['split'] == 'heldout']
        for repeat in range(config['agent_repeats']):
            for position, case in enumerate(heldout):
                order = list(CONDITIONS)
                random.Random(7301 + repeat * 10 + position).shuffle(order)
                for condition in order:
                    if rules[condition] is None:
                        continue
                    effective = deepcopy(config)
                    effective['fixtures'] = (directory / 'fixtures' / case['id']).relative_to(ROOT).as_posix()
                    effective['providers']['agent'] = [pool[(position + repeat) % len(pool)]]
                    query = 'Locate the UTF-8 file whose filename contains the keyword ' + case['keyword'] + '. Read it using the tool, then return its contents. Do not guess its path or contents.'
                    if case['cohort'] == 'known_path':
                        query = 'Read the existing UTF-8 file at ${WORKSPACE}/' + case['relative_path'] + ' using the tool, then return its contents. The exact path is supplied.'
                    specs.append({'protocol': protocol, 'config': effective, 'case': case, 'condition': condition,
                        'repeat': repeat, 'rule': rules[condition], 'prompt_time': str(offset_date(0)),
                        'query': query, 'verify_answer': True, 'rule_is_context': True,
                        'file_tree': '\n'.join([case['relative_path'], 'unrelated-note.txt']) if case['cohort'] == 'visible_tree' else 'Discover files with tools; no file tree supplied.',
                        'journal': str(directory / 'trials' / f'{condition}-{case["id"]}-{repeat}.json')})
        rows = []
        with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context('spawn')) as executor:
            futures = {executor.submit(execute_trial, spec): spec for spec in specs}
            for future in as_completed(futures):
                row = future.result()
                row['cohort'] = futures[future]['case']['cohort']
                atomic_json(Path(futures[future]['journal']), row)
                rows.append(row)
        summary = summarize(rows, len(heldout) * config['agent_repeats'], rejection)
        summary['protocol'] = protocol
        summary.update(fixtures_unchanged=tree_hash(directory / 'fixtures') == manifest['fixtures_sha256'],
                       source_unchanged=source_hash() == manifest['source_sha256'])
        if not summary['fixtures_unchanged'] or not summary['source_unchanged']:
            summary['status'] = 'invalidated'
        manifest['status'] = summary['status']
        atomic_json(directory / 'experiment.json', manifest)
        atomic_json(directory / 'transfer-summary.json', summary)
        return directory, summary
    except BaseException as exc:
        manifest.update(status='failed_or_interrupted', error=safe_error(exc))
        atomic_json(directory / 'experiment.json', manifest)
        raise


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))
