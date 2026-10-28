"""Prepare/replay an archived Late unchanged-memory intervention; offline by default."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

RUN = '20261026T084527.010290Z_Kevin'
ARMS = ('rewrite_unchanged', 'preserve_unchanged')
PROTOCOL = 'role4_archived_late_unchanged_memory_ablation_v1'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Values contain env-variable names, never loaded credentials.
    fd, name = tempfile.mkstemp(prefix=path.name, suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(name, path)
    finally:
        if Path(name).exists():Path(name).unlink()


def affected(entry, before, after):
    if entry.get('adaptation', {}).get('status') == 'unavailable':
        servers = {t.split('::')[0] for t in entry['value']['tool_ids']}
        return {k:v for k,v in before.items() if v['server'] in servers} != {k:v for k,v in after.items() if v['server'] in servers}
    return any(before.get(t) != after.get(t) for t in entry['value']['tool_ids'])


def arm_states(previous, current):
    """Hold changed-tool experience fixed; restore only unaffected previous records."""
    before = {e['id']:e for e in previous['experience_state']['memories']}
    after = {e['id']:e for e in current['experience_state']['memories']}
    if len(before)!=len(previous['experience_state']['memories']) or len(after)!=len(current['experience_state']['memories']):
        raise ValueError('Duplicate memory identities')
    if set(before) != set(after):raise ValueError('Memory identities changed')
    if previous['experience_state']['origins'] != current['experience_state']['origins']:
        raise ValueError('Practice provenance changed')
    control = deepcopy(current['experience_state'])
    replaced = []
    for i, entry in enumerate(control['memories']):
        eid = entry['id']
        if not affected(before[eid], previous['catalog'], current['catalog']):
            control['memories'][i] = deepcopy(before[eid])
            replaced.append(eid)
    control['memory_sha256'] = digest(control['memories'])
    control['dependency_hashes'] = {e['id']:{t:digest(current['knowledge'][t]) if t in current['knowledge'] else None
        for t in e['value']['tool_ids']} for e in control['memories']}
    states = {ARMS[0]:deepcopy(current['experience_state']), ARMS[1]:control}
    changed = {eid for eid in before if affected(before[eid],previous['catalog'],current['catalog'])}
    left,right = [{e['id']:e for e in states[a]['memories']} for a in ARMS]
    assert all(left[eid] == right[eid] for eid in changed)
    assert all(right[eid] == before[eid] for eid in replaced)
    assert all(states[a]['memory_sha256']==digest(states[a]['memories']) for a in ARMS)
    return states, replaced, sorted(changed)


def prepare(repo, directory):
    run = repo/'results'/RUN
    m = json.loads((run/'experiment.json').read_text(encoding='utf-8'))
    d = json.loads((run/'records.json').read_text(encoding='utf-8'))
    if hashlib.sha256((run/'inputs/source.zip').read_bytes()).hexdigest()!=m['source_archive_sha256']:
        raise ValueError('Archived source checksum mismatch')
    ep = d['episodes']['full_rewrite/0']['stages']
    states, untouched, changed = arm_states(ep['iter3'],ep['iter5'])
    cfg = deepcopy(m['settings'])
    # Freeze the same provider account as source task/repeat for both arms.
    for role in ('agent','judge'):
        options=cfg['providers'][role]
        if isinstance(options,list):cfg['providers'][role]=[options[m['selected_ids'].index(403)%len(options)]]
    plan={'protocol':PROTOCOL,'source_run':RUN,'source_repeat':0,'task_id':403,'stage':'iter5',
        'purpose':'Fixed archived snapshots; effect of rewriting unchanged experience at the Middle-to-Late transition',
        'not_tested':'Fresh update-generation variability or whole-benchmark performance',
        'task':next(t for t in m['task_definitions'] if t['idx']==403),
        'tasks':m['task_definitions'],'settings':cfg,'prompt_time':m['prompt_time'],
        'initial_snapshot':d['initial_snapshot'],'snapshot':ep['iter5'],
        'arms':states,'unaffected_entry_ids':untouched,'affected_entry_ids':changed,
        'catalog_sha256':digest(ep['iter5']['knowledge']),
        'source_hashes':{n:hashlib.sha256((run/n).read_bytes()).hexdigest() for n in ['experiment.json','records.json','inputs/source.zip']},
        'invariants':{'same_task':True,'same_tool_knowledge':True,'same_affected_memories':True,
            'same_models_and_provider':True,'no_updater_calls':True,'fresh_runtime_per_trial':True},
        'caveat':'This tests archived full-library context, not the isolated effect of one sentence. No live outcome exists until run completes.'}
    # Store only needed snapshots, not requests/responses from archive updates.
    for key in ('initial_snapshot','snapshot'):
        plan[key]={k:deepcopy(plan[key][k]) for k in ('catalog','knowledge','errors','experience_state')}
    plan['plan_sha256']=digest(plan)
    path=directory/'plan.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=plan:
        raise ValueError('Different immutable plan exists; use a new --directory')
    save(path,plan)
    return plan


def verify(plan):
    v=deepcopy(plan);expected=v.pop('plan_sha256')
    if digest(v)!=expected:raise ValueError('Plan was modified after preparation')


def preflight(repo, plan):
    verify(plan)
    missing=[]
    for name in ('mcp','openai','httpx','langchain','langchain_openai','jsonschema','psutil','dotenv'):
        if importlib.util.find_spec(name) is None:missing.append('Python dependency: '+name)
    if importlib.util.find_spec('dotenv') is not None:
        from dotenv import load_dotenv
        load_dotenv(repo/'.env',override=False)
    for role in ('agent','judge'):
        for provider in plan['settings']['providers'][role]:
            for field in ('api_key_env','base_url_env'):
                env=provider.get(field)
                if env and not os.environ.get(env):missing.append('Missing environment variable: '+env)
    if not shutil.which('node'):missing.append('Node.js executable on PATH')
    if not shutil.which('git'):missing.append('Git executable on PATH')
    if not (repo/'.runtime/node_modules/@1mcp/agent/build/index.js').is_file():missing.append('Prepared local 1mcp installation')
    config_path=repo/plan['settings']['runtime']['configs']['iter5']
    if not config_path.is_file():missing.append('Local Late server config: '+str(config_path.relative_to(repo)))
    else:
        conf=json.loads(config_path.read_text(encoding='utf-8'))['mcpServers']
        for name in plan['task']['servers']:
            entry=conf.get(name)
            policy=plan['settings']['runtime']['policies'].get(name,{})
            if policy.get('concurrency') not in ('private','readonly'):missing.append('Unreviewed isolation policy: '+name)
            if not entry:
                missing.append('Missing configured server: '+name);continue
            command=Path(entry.get('command','')).name.lower()
            if command in ('npx','npx.cmd','npm','npm.cmd','uvx','uvx.exe'):
                missing.append('Unfrozen downloading launcher: '+name)
            if command in ('node','node.exe') and (not entry.get('args') or not Path(entry['args'][0]).is_file()):
                missing.append('Missing frozen server executable: '+name)
    return {'protocol':PROTOCOL,'status':'ready_for_live_start' if not missing else 'blocked_before_live',
        'plan_sha256':plan['plan_sha256'],'missing':sorted(set(missing)),
        'network_calls':0,'live_model_calls':0,'note':'Static preflight only; runtime still checks exact catalogs and isolated fixture copies.'}


def summarize(records):
    groups={};paired=[]
    for arm in ARMS:
        rs=[r for r in records['trajectories'].values() if r['identity']['strategy']==arm]
        good=[r for r in rs if r.get('score')]
        groups[arm]={'planned':len(rs),'scored':len(good),'valid_judge_slots':sum(a['status']=='completed' for r in rs for a in r['judge_attempts']),
            'schema_error_calls':sum(bool(c.get('harness_schema_feedback')) or 'schema_input_invalid' in json.dumps(c.get('response',{}))
                for r in rs for c in r.get('raw_tool_trace',[])),
            'tool_error_calls':sum(bool(c.get('response',{}).get('isError')) for r in rs for c in r.get('raw_tool_trace',[])),
            'stop_reasons':[r.get('stop_reason') for r in rs]}
    for rep in sorted({r['identity']['repeat'] for r in records['trajectories'].values()}):
        pair={a:records['trajectories'][f'{a}/iter5/403/{rep}'] for a in ARMS}
        if all(r.get('score') for r in pair.values()):
            paired.append({'repeat':rep,'tf_rewrite_minus_preserve':pair[ARMS[0]]['score']['task_fulfillment']-pair[ARMS[1]]['score']['task_fulfillment'],
                'scores':{a:r['score'] for a,r in pair.items()}})
    return {'status':records['status'],'conditions':groups,'paired':paired,
        'mean_tf_rewrite_minus_preserve':sum(p['tf_rewrite_minus_preserve'] for p in paired)/len(paired) if paired else None,
        'interpretation':'Negative values support a detrimental context effect for these fixed snapshots; inspect actual calls and repetitions. No pre-assumed positive result.'}


def execution_fingerprint(repo, plan, directory):
    paths=[directory/'plan.json',repo/plan['settings']['runtime']['configs']['iter5']]
    paths+=sorted(p for p in (repo/plan['settings']['fixtures']).rglob('*') if p.is_file())
    paths+=sorted((repo/'src/custom').rglob('*.py'))
    return digest({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


def execute(repo, directory, plan, repeats):
    status=preflight(repo,plan)
    if status['missing']:raise ValueError('Live prerequisites missing; run preflight for details')
    if not 1<=repeats<=10:raise ValueError('Use 1–10 paired repeats')
    sys.path.insert(0,str(repo))
    from custom.experiment.core import run_trajectory
    from custom.experiment.experience_state import as_artifact
    from custom.experiment.results import atomic_json, identity
    # Validate both memory libraries against exactly the same Late catalog.
    for state in plan['arms'].values():as_artifact(state,plan['snapshot']['knowledge'])
    config=deepcopy(plan['settings']);config['mode']='live'
    frozen_inputs=execution_fingerprint(repo,plan,directory)
    run_dir=directory/('live-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'))
    run_dir.mkdir(parents=True,exist_ok=False)
    records={'status':'running','trajectories':{},'events':[]}
    for rep in range(repeats):
        for arm in ARMS:
            key=identity(arm,'iter5',403,rep)
            records['trajectories'][key]={'identity':{'strategy':arm,'stage':'iter5','task_id':403,'repeat':rep},
                'status':'pending','agent_status':'pending','agent_attempts':[],'tool_attempts':[],
                'judge_attempts':[{'slot':i,'status':'pending'} for i in range(5)],
                'errors':[],'raw_tool_trace':[],'trajectory_messages':[],'score':None}
    code_state={'revision':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
        'dirty_source':bool(subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True).strip())}
    atomic_json(run_dir/'experiment.json',{'protocol':PROTOCOL,'plan':plan,'repeats':repeats,
        **code_state,'execution_input_sha256':frozen_inputs,
        'order':'AB then BA, alternating; serial execution with a fresh LiveRuntime per trial',
        'planned_agent_trajectories':2*repeats,'planned_judge_slots':10*repeats,
        'updater_calls':0,'mode':'live'})
    def emit(event):
        if event['kind']=='trajectory':records['trajectories'][event['key']]=deepcopy(event['record'])
        else:records['events'].append(event)
        atomic_json(run_dir/'records.json',records)
    atomic_json(run_dir/'records.json',records)
    try:
        for rep in range(repeats):
            for arm in (ARMS if rep%2==0 else ARMS[::-1]):
                if execution_fingerprint(repo,plan,directory)!=frozen_inputs:
                    raise ValueError('Experimental inputs changed before trial')
                spec={'config':deepcopy(config),'tasks':deepcopy(plan['tasks']),'task':deepcopy(plan['task']),
                    'stage':'iter5','strategy':arm,'repeat':rep,'snapshot':deepcopy(plan['snapshot']),
                    'knowledge':deepcopy(plan['snapshot']['knowledge']),'experience_state':deepcopy(plan['arms'][arm]),
                    'initial_snapshot':deepcopy(plan['initial_snapshot']),'records':records['trajectories'],
                    'prompt_time':plan['prompt_time']}
                run_trajectory(spec,emit)
        complete=all(r.get('score') for r in records['trajectories'].values())
        records['status']='completed' if complete else 'completed_with_failures'
    finally:
        if records['status']=='running':records['status']='interrupted'
        if execution_fingerprint(repo,plan,directory)!=frozen_inputs:
            records['status']='invalidated_inputs_changed'
            for row in records['trajectories'].values():
                row['score']=None;row['score_exclusion_reason']='experimental_inputs_changed'
        atomic_json(run_dir/'records.json',records)
        atomic_json(run_dir/'summary.json',summarize(records))
    return run_dir


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','preflight','run'])
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--directory',type=Path)
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--execute-live',action='store_true',help='Explicitly allow actual Agent/Judge requests')
    a=parser.parse_args();repo=a.repo.resolve();directory=a.directory or repo/'.runtime/role4-task403-ablation'
    if a.action=='prepare':
        p=prepare(repo,directory);print(json.dumps({'status':'prepared_not_executed','unaffected_entries':len(p['unaffected_entry_ids']),
            'affected_entries':len(p['affected_entry_ids']),'plan_sha256':p['plan_sha256']},indent=2))
    else:
        p=json.loads((directory/'plan.json').read_text(encoding='utf-8'));verify(p)
        if a.action=='preflight':
            report=preflight(repo,p);save(directory/'preflight.json',report);print(json.dumps(report,indent=2))
        elif not a.execute_live:parser.error('run requires --execute-live; default preparation never calls models')
        else:print(execute(repo,directory,p,a.repeats))
