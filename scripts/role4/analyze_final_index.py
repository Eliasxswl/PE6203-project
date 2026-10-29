"""Recompute indexed formal runs and Task 9 behavioral ablation, offline only."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics as st

STAGES=('original','iter3','iter5')
METHODS=('no_update','full_rewrite','selective_patch')
ARMS=('fr_all','fr_changed_only','fr_order_only')
METRICS=('task_fulfillment','planning_and_efficiency')


def load(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def avg(v):return st.mean(v) if v else None
def ecs(v):return st.mean(v)-st.pstdev(v)
def valid(r):return all(type((r.get('score') or {}).get(k)) in (int,float) and math.isfinite(r['score'][k]) and 1<=r['score'][k]<=10 for k in METRICS)


def matched(rows,stages):
    units=sorted({(r['identity']['task_id'],r['identity']['repeat']) for r in rows.values()})
    return [(t,rep) for t,rep in units if all(valid(rows.get(f'{s}/{v}/{t}/{rep}',{})) for s in METHODS for v in stages)]


def physical_rows(rows):
    physical={}
    for key,row in rows.items():
        seen=set()
        while row.get('shared_from'):
            if key in seen:raise ValueError('Shared baseline cycle')
            seen.add(key);key=row['shared_from']
            if key not in rows:raise ValueError('Missing shared baseline')
            if row['score']!=rows[key]['score']:raise ValueError('Shared score mismatch')
            row=rows[key]
        physical[key]=row
    return physical


def formal(repo,folder):
    path=repo/folder;m=load(path/'experiment.json');d=load(path/'records.json');rows=d['trajectories']
    assert len(m['selected_ids'])==17 and m['settings']['agent_repeats']==3
    assert m['settings']['judge_attempts_per_trajectory']==5 and set(m['settings']['strategies'])==set(METHODS)
    unique=physical_rows(rows);common=matched(rows,STAGES);groups=[];cohorts=[];cost=[];rep_ecs=[];task_deltas=[];usage=[]
    audit=0
    for key,r in unique.items():
        for metric in METRICS:
            vals=[a['result'][metric] for a in r['judge_attempts'] if a.get('status')=='completed']
            if vals:assert valid(r) and math.isclose(avg(vals),r['score'][metric],abs_tol=1e-9),key;audit+=1
    for method in METHODS:
        xs=[ecs([rows[f'{method}/{v}/{t}/{rep}']['score']['task_fulfillment'] for v in STAGES]) for t,rep in common]
        assert math.isclose(avg(xs),d['aggregate']['paired_ecs']['values'][method],abs_tol=1e-10)
        for rep in range(3):
            units=[(t,r) for t,r in common if r==rep]
            rep_ecs.append({'strategy':method,'repeat':rep,'n':len(units),'ecs':avg([
                ecs([rows[f'{method}/{v}/{t}/{r}']['score']['task_fulfillment'] for v in STAGES]) for t,r in units])})
        for stage in STAGES:
            units=matched(rows,[stage]);result={'strategy':method,'stage':stage,'paired_n':len(units),'paired_ecs':avg(xs)}
            for metric in METRICS:
                result[metric]=avg([rows[f'{method}/{stage}/{t}/{rep}']['score'][metric] for t,rep in units])
                means=[avg([rows[f'{method}/{stage}/{t}/{r}']['score'][metric] for t,r in units if r==rep]) for rep in range(3)]
                result[metric+'_repeat_sd']=st.stdev(means)
            groups.append(result)
            if stage=='original':continue
            for cohort in ('changed','retention'):
                ids=[(t,r) for t,r in units if m['task_annotations'][str(t)]['transitions'][stage]['cohort']==cohort]
                # Older annotations use 'retention'; never infer controls from scores.
                if not ids and cohort=='retention':
                    ids=[(t,r) for t,r in units if m['task_annotations'][str(t)]['transitions'][stage]['cohort'] in ('control','unchanged')]
                delta=[rows[f'{method}/{stage}/{t}/{rep}']['score']['task_fulfillment']-
                    rows[f'no_update/{stage}/{t}/{rep}']['score']['task_fulfillment'] for t,rep in ids]
                task_deltas.extend({'strategy':method,'stage':stage,'cohort':cohort,'task':t,'repeat':rep,'delta_tf':value}
                    for (t,rep),value in zip(ids,delta))
                cohorts.append({'strategy':method,'stage':stage,'cohort':cohort,'n':len(ids),'mean_delta_tf':avg(delta)})
        snapshots=[e['stages'][v] for name,e in d['episodes'].items() if name.rsplit('/',1)[0]==method for v in STAGES[1:]]
        total={'strategy':method,'updates':len(snapshots)}
        for field in ('api_calls','input_tokens','output_tokens','api_cost','elapsed_seconds'):
            total[field]=sum(s[field] for s in snapshots) if all(s.get(field) is not None for s in snapshots) else None
        cost.append(total)
        for role in ('agent','judge'):
            records=[]
            for row in unique.values():
                if row['identity']['strategy']!=method:continue
                if role=='agent':records.extend(row.get('agent_usage') or [])
                else:records.extend(a['usage'] for a in row['judge_attempts'] if isinstance(a.get('usage'),dict))
            record={'strategy':method,'role':role,'reported_calls':len(records),'usd':None}
            for field in ('prompt_tokens','completion_tokens'):
                vals=[v[field] for v in records if type(v.get(field)) in (int,float)]
                record[field]=sum(vals) if vals else None
                record[field+'_missing_calls']=len(records)-len(vals)
            usage.append(record)
    result={'path':folder,'protocol':m['harness_protocol'],'dirty_source':m['dirty_source'],
        'revision':m['revision'],'agent_backend':m['settings'].get('agent_backend','legacy'),
        'source_records_sha256':hashlib.sha256((path/'records.json').read_bytes()).hexdigest(),
        'source_records_semantic_sha256':digest(d),'logical':len(rows),'physical':len(unique),
        'scored_physical':sum(valid(r) for r in unique.values()),'shared_aliases':len(rows)-len(unique),
        'status_counts':dict(Counter(r['status'] for r in unique.values())),
        'judge_statuses':dict(Counter(a['status'] for r in unique.values() for a in r['judge_attempts'])),
        'paired_ecs_n':len(common),'main':groups,'cohorts':cohorts,'update_costs':cost,'replicate_ecs':rep_ecs,
        'task_deltas':task_deltas,'physical_inference_usage':usage,
        'judge_means_verified':audit,'saved_ecs_verified':True,
        'exclusions':[{'identity':r['identity'],'reason':r.get('score_exclusion_reason')} for r in rows.values() if not valid(r)]}
    if (path/'update-budget.json').exists():
        ledger=load(path/'update-budget.json');assert math.isclose(sum(c['api_cost'] for c in cost),float(ledger['reported_usd']),abs_tol=1e-9)
        result['update_ledger_verified']=True
    if m.get('source_archive_sha256'):
        assert hashlib.sha256((path/'inputs/source.zip').read_bytes()).hexdigest()==m['source_archive_sha256']
        result['source_archive_verified']=True
    return result


def tool_text(response):
    return '\n'.join(item.get('text','') for item in response.get('content',[]) if item.get('type')=='text')


def log_read(row,expected):
    for call in row.get('raw_tool_trace',[]):
        if call.get('semantic_identity','').endswith('::read_text_file') and not call['response'].get('isError'):
            args=call.get('arguments',{})
            if isinstance(args,str):args=json.loads(args)
            path=str(args.get('path','')).replace('\\','/')
            text=tool_text(call['response']).replace('\r\n','\n').strip()
            if path.endswith('/log_yesterday.txt') and text==expected.replace('\r\n','\n').strip():return True
    return False


def plan_created(row):
    for call in row.get('raw_tool_trace',[]):
        if call.get('semantic_identity','').endswith('::request_planning') and not call['response'].get('isError'):
            try:v=json.loads(tool_text(call['response']))
            except (ValueError,TypeError):continue
            if v.get('status')=='planned' and v.get('requestId') and v.get('tasks'):return True
    return False


def wilson(k,n):
    z=1.959963984540054;p=k/n;den=1+z*z/n;center=(p+z*z/(2*n))/den
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [max(0,min(p,center-half)),min(1,max(p,center+half))]


def exact_p(b,c):
    n=b+c
    return min(1,2*sum(math.comb(n,k) for k in range(min(b,c)+1))/2**n) if n else 1.0


def case(repo,folder,knowledge):
    p=repo/folder;m=load(p/'experiment.json');d=load(p/'records.json');review=load(p/'task-9-confirmation-review.json')
    states=load(p/'inputs/counterfactual-snapshots.json');rows=d['trajectories'];trials=[]
    assert len(rows)==30 and set(m['diagnostic']['conditions'])==set(ARMS)
    assert hashlib.sha256((p/'inputs/source.zip').read_bytes()).hexdigest()==m['source_archive_sha256']
    assert knowledge['source_records_semantic_sha256']==review['portable_source_verification']['semantic_records_sha256']
    source_rows=load(repo/knowledge['path']/'records.json')
    initial={e['id']:e for e in source_rows['initial_snapshot']['experience_state']['memories']}
    full,restored,ordered=[{e['id']:e for e in states[a][0]['memories']} for a in ARMS]
    changed=set(review['affected_records_preserved']);unchanged=set(review['unaffected_records_restored'])
    assert set(full)==set(restored)==set(ordered)==changed|unchanged
    assert full==ordered
    assert all(full[e]==restored[e] for e in changed)
    assert all(restored[e]==initial[e] for e in unchanged)
    assert all(states[ARMS[0]][1]==states[a][1] for a in ARMS)
    # Check what the actor actually saw, not only producer annotations.
    for rep in range(10):
        group=[rows[f'{a}/iter5/9/{rep}'] for a in ARMS]
        requests=[r['agent_attempts'][0]['request'] for r in group]
        nonmemory=[]
        for row,req in zip(group,requests):
            base={k:v for k,v in req.items() if k!='messages'}
            assert base=={k:v for k,v in requests[0].items() if k!='messages'}
            assert req['messages'][1:]==requests[0]['messages'][1:]
            system=req['messages'][0]['content'];size=row['memory_exposure']['context_characters']
            nonmemory.append(system[:-size])
        assert len(set(nonmemory))==1
        assert len({r['counterfactual_callable_sha256'] for r in group})==1
        assert group[0]['workspace_observations'][0]==group[1]['workspace_observations'][0]==group[2]['workspace_observations'][0]
        callable_ids=set(group[0]['tool_identities'].values())
        assert all(t not in callable_ids for e in unchanged for t in full[e]['value']['tool_ids'])
        assert all(set(r['memory_exposure']['selected_ids'])==set(full) for r in group)
        # Order-only intervention reverses object keys but preserves all JSON values and list order.
        parsed=[]
        for req in (requests[0],requests[2]):
            lines=[]
            for line in req['messages'][0]['content'].splitlines():
                try:value=json.loads(line)
                except (ValueError,TypeError):continue
                if isinstance(value,dict) and 'guidance' in value:lines.append(value)
            parsed.append(lines)
        assert len(parsed[0])==len(parsed[1])==7 and parsed[0]==parsed[1]
        assert len(requests[0]['messages'][0]['content'])==len(requests[2]['messages'][0]['content'])
        assert requests[0]['messages'][0]['content']!=requests[2]['messages'][0]['content']
        for arm,row in zip(ARMS,group):
            key=f'{arm}/iter5/9/{rep}'
            success=log_read(row,review['fixture_log']['text']);planning=plan_created(row)
            assert success==review['trials'][key]['primary_log_read_success']
            assert planning==review['trials'][key]['secondary_plan_created']
            assert row.get('score') is None
            trials.append({'key':key,'arm':arm,'repeat':rep,'agent_status':row['agent_status'],
                'read_success':success,'plan_created':planning,
                'patterns':[json.loads(c['arguments']).get('pattern') for c in row['raw_tool_trace']
                    if c['semantic_identity'].endswith('::search_files')],
                'response_ids':[a['response']['id'] for a in row['agent_attempts'] if a.get('response',{}).get('id')]})
    summary=[]
    for a in ARMS:
        rs=[r for r in trials if r['arm']==a];count=sum(r['read_success'] for r in rs)
        assert count==review['summary'][a]['log_read_successes']
        summary.append({'arm':a,'n':len(rs),'read_successes':count,'rate':count/len(rs),
            'wilson95':wilson(count,len(rs)),'plan_created':sum(r['plan_created'] for r in rs)})
    pairs=[(next(r['read_success'] for r in trials if r['arm']==ARMS[0] and r['repeat']==rep),
        next(r['read_success'] for r in trials if r['arm']==ARMS[1] and r['repeat']==rep)) for rep in range(10)]
    b=sum(not x and y for x,y in pairs);c=sum(x and not y for x,y in pairs)
    assert exact_p(b,c)==review['paired_primary_comparison']['exact_two_sided_p']
    response_ids=[x for r in trials for x in r['response_ids']];assert len(response_ids)==len(set(response_ids))
    assert all(r['agent_status']=='completed' for r in trials)
    assert not any(a.get('response') for r in rows.values() for a in r['judge_attempts'])
    return {'path':folder,'summary':summary,'trials':trials,'restoration_only_success':b,'fr_only_success':c,
        'exact_p':exact_p(b,c),'source_semantic_hash_verified':True,'shared_input_checks':10,
        'initial_state_reset_verified':True,'unchanged_restored_from':'original K0, not Middle snapshot',
        'presentation_control_verified':True,'judge_calls':0,'new_update_calls':review['paid_update_calls'],
        'selection_disclosure':load(repo/'results/index.json')['cleanup']['selection_disclosure'],
        'limitations':review['limitations']}


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
        ['| '+' | '.join('—' if x is None else f'{x:.4f}' if isinstance(x,float) else str(x) for x in row)+' |' for row in rows])


def main(repo,out,plot=False):
    idx=load(repo/'results/index.json')['active_runs']
    runs={k:formal(repo,idx[k]) for k in ('catalog_baseline','knowledge_strategy_comparison')}
    cf=case(repo,idx['task9_over_update_case'],runs['knowledge_strategy_comparison'])
    out.mkdir(parents=True,exist_ok=True)
    result={'index':idx,'formal_runs':runs,'task9':cf,'validation':'All assertions passed; no model or MCP calls'}
    (out/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    text=['# Final indexed Role 4 analysis / 最终索引分析','',
        'Source of truth: `results/index.json`. Two formal rounds and one supplemental behavioral case are reported separately. / 两轮正式实验与补充行为案例独立报告，不合并均分。','']
    for label,r in runs.items():
        text += ['## '+label,'',f'Run: `{r["path"]}`; protocol `{r["protocol"]}`; backend `{r["agent_backend"]}`; dirty_source={r["dirty_source"]}.','',
            f'Logical trajectories {r["logical"]}; unique executions {r["physical"]}; scored executions {r["scored_physical"]}; shared Early aliases {r["shared_aliases"]}; matched all-stage ECS pairs {r["paired_ecs_n"]}.','',
            table(['Strategy','Stage','Matched N','TF','TF repeat SD','PE','PE repeat SD','Paired ECS'],[
                [v['strategy'],v['stage'],v['paired_n'],v[METRICS[0]],v[METRICS[0]+'_repeat_sd'],v[METRICS[1]],v[METRICS[1]+'_repeat_sd'],v['paired_ecs']] for v in r['main']]),'',
            'SD describes three repeat-level means, not five judge slots. ECS uses population SD across versions; the same task/repeat pairs are used for all strategies. / 标准差按执行重复；ECS版本间用总体标准差。','',
            table(['Strategy','Stage','Cohort','Matched N','ΔTF vs No Update'],[[v[k] for k in ('strategy','stage','cohort','n','mean_delta_tf')] for v in r['cohorts'] if v['strategy']!='no_update']),'',
            table(['Strategy','Updates','Calls','Input tokens','Output tokens','Update seconds','Reported USD'],[[v[k] for k in ('strategy','updates','api_calls','input_tokens','output_tokens','elapsed_seconds','api_cost')] for v in r['update_costs']]),'',
            'Costs are sums over six version transitions, not per-task costs or whole-experiment spending. / 费用为六次更新合计，不是单任务或全实验总费用。','',
            table(['Strategy','Role','Usage records','Input tokens','Output tokens'],[[v[k] for k in ('strategy','role','reported_calls','prompt_tokens','completion_tokens')] for v in r['physical_inference_usage']]),'',
            'Agent/Judge usage is counted physically, with shared Early charged once to its No Update owner. These asymmetric totals are accounting records, not normalized per-method runtime estimates. USD is unavailable rather than inferred as zero. / 共享Early只计一次；token记录不等于完整美元账单。','',
            'Coverage: `'+str(r['status_counts'])+'`; judge slots: `'+str(r['judge_statuses'])+'`. Exclusions and checksums are retained in analysis.json.','']
    text += ['## Why rounds are not pooled / 为什么不能合并','',
        'Both rounds use the original 17 tasks, three stages, three Agent repeats and five judge slots, with Agent temperature 0.2 and judge temperature 0. Round 1 is catalog-only/legacy Agent and deterministic updates; Round 2 uses LangChain and strategy-owned learned experience with a common paid updater. Therefore the rounds are different system conditions, not six repetitions of one condition. Cross-round differences cannot be attributed only to Selective Patch.','',
        '第一轮只更新工具目录，三策略均无更新模型费用；第二轮加入LangChain与自维护经验，两种更新策略使用同一更新模型与校验规则。以前“Full Rewrite零更新费用”的说法仅适用于第一轮。','',
        '## Task 9: separate behavioral endpoint / 独立的行为消融','',
        table(['Condition','Actual log reads','Rate','Wilson 95% interval','Plan created (secondary)'],[
            [s['arm'],str(s['read_successes'])+'/'+str(s['n']),s['rate'],str([round(x,4) for x in s['wilson95']]),s['plan_created']] for s in cf['summary']]),'',
        f'Paired primary comparison: {cf["restoration_only_success"]} restoration-only successes, {cf["fr_only_success"]} FR-only successes; descriptive exact two-sided paired p={cf["exact_p"]}. No multiplicity or exploratory-screening correction is implied.','',
        'No Judge calls were made: these numbers are not TF or full task-completion scores. Successful read means the actual requested log contents were returned by read_text_file. Request-planning creation is a separate secondary observable and does not by itself certify all user goals.','',
        'All callable tools, two affected experience records, user input, non-memory system input, model/decoding and initial workspace contents are fixed within groups. Five original-K0 records for unavailable, unchanged tools are restored in fr_changed_only. fr_order_only only changes JSON object-key presentation of all FR records, including affected ones; list order and semantic values are unchanged.','',
        '结论：固定任务9和这份Full Rewrite快照下，恢复五条未变化经验带来更高的实际读取成功率，支持全库注入时不必要重写可能通过上下文干扰损害行为。不能指认某句知识被删，也不能推广为所有任务都更好。','',
        '## Limitations and provenance / 限制与来源','',
        '- Task 9 and the FR repeat-2 snapshot were selected after exploratory screening. The ten-group confirmation was fixed before dispatch, but is not an independent random benchmark sample. Retain this disclosure in slides and reports.',
        '- Restoration changes wording, length and presentation together. Order-only outcomes demonstrate sensitivity; they do not isolate the harmful sentence or prove a single semantic mechanism.',
        '- Ten fresh private workspace groups reset state between conditions; do not describe this as thirty independent tasks. Three arms share each group’s initial inputs and provider account.',
        '- Round 2 and the supplemental case record dirty_source=true. The archived source hashes are verified; traceability is not equivalent to satisfying the older clean-source requirement.',
        '- Formal main scores are not rewritten by this supplemental case. Task-403 preparation is superseded for the final case, not represented as a successful experiment.',
        '- Source-record bytes differ only by Git newline normalization. The semantic source hash was independently matched to the published review; use recorded checksums rather than silently ignoring a byte mismatch.',
        '- Original formal results use a limited, gate-selected task set. No universal model/harness improvement or statistical significance of the main ranking is claimed.','']
    if plot:
        figures(runs,cf,out)
        text += ['## Figures','', '![Formal rounds](formal_rounds.png)','', '![Task 9](task9.png)','']
    (out/'RESULTS.md').write_text('\n'.join(text),encoding='utf-8')
    print(json.dumps({'rounds':{k:{'physical':r['physical'],'scored':r['scored_physical'],'ecs_pairs':r['paired_ecs_n']} for k,r in runs.items()},
        'task9':cf['summary'],'source_hash_verified':cf['source_semantic_hash_verified'],'input_groups_verified':cf['shared_input_checks']},indent=2))
    return result


def figures(runs,cf,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors=['#668099','#d79a52','#378c73'];fig,axs=plt.subplots(1,2,figsize=(12,4.6))
    for ax,(label,r) in zip(axs,runs.items()):
        vals=[next(v['paired_ecs'] for v in r['main'] if v['strategy']==s) for s in METHODS]
        ax.bar(range(3),vals,color=colors);ax.set(xticks=range(3),xticklabels=['No Update','Full Rewrite','Selective Patch'],ylim=(0,10),ylabel='Paired ECS',title=label+'\nN='+str(r['paired_ecs_n'])+' task/repeat pairs')
        for x,y in enumerate(vals):ax.text(x,y+.1,f'{y:.3f}',ha='center')
    fig.suptitle('Separate formal rounds: different protocols; do not pool');fig.tight_layout();fig.savefig(out/'formal_rounds.png',dpi=180);plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,4.8));rates=[s['rate'] for s in cf['summary']]
    ax.bar(range(3),rates,color=colors);ax.errorbar(range(3),rates,yerr=[
        [s['rate']-s['wilson95'][0] for s in cf['summary']],[s['wilson95'][1]-s['rate'] for s in cf['summary']]],fmt='none',color='#222',capsize=6)
    ax.set(xticks=range(3),xticklabels=['Full Rewrite','Restore 5 unchanged records','JSON key-order control'],ylim=(0,1.15),ylabel='Actual requested-log read rate',title='Task 9 · frozen FR repeat-2 snapshot · 10 groups\nBehavioral endpoint, not TF; error bars: Wilson 95% intervals')
    for i,s in enumerate(cf['summary']):ax.text(i,s['rate']+.025,f"{s['read_successes']}/{s['n']}",ha='center')
    fig.tight_layout();fig.savefig(out/'task9.png',dpi=180);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2]);p.add_argument('--output',type=Path);p.add_argument('--plot',action='store_true');a=p.parse_args()
    main(a.repo,a.output or a.repo/'.runtime/role4-final',a.plot)
