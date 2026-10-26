"""Offline, run-specific analysis. No model calls and no edits to original records."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics as st
import sys

STAGES = ('original', 'iter3', 'iter5')
STRATEGIES = ('no_update', 'full_rewrite', 'selective_patch')
METRICS = ('task_fulfillment', 'planning_and_efficiency')
RUN = '20261026T084527.010290Z_Kevin'


def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def valid(r):
    s = r.get('score') or {}
    return all(type(s.get(k)) in (int, float) and math.isfinite(s[k]) and 1 <= s[k] <= 10 for k in METRICS)


def mean(v):
    return st.mean(v) if v else None


def ecs(v):
    return st.mean(v) - st.pstdev(v)


def resolve(rows, key):
    seen = set()
    while rows[key].get('shared_from'):
        if key in seen:
            raise ValueError('Shared-reference cycle')
        seen.add(key)
        target = rows[key]['shared_from']
        if target not in rows or rows[key].get('score') != rows[target].get('score'):
            raise ValueError('Missing or inconsistent shared score: ' + key)
        key = target
    return key


def paired_ids(rows, strategies, stages):
    ids = sorted({(r['identity']['task_id'], r['identity']['repeat']) for r in rows.values()})
    return [(t, rep) for t, rep in ids if all(valid(rows.get(f'{s}/{v}/{t}/{rep}', {}))
        for s in strategies for v in stages)]


def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |', '| '+' | '.join(['---']*len(headers))+' |'] +
        ['| '+' | '.join('—' if x is None else f'{x:.4f}' if isinstance(x,float) else str(x) for x in row)+' |' for row in rows])


def analyze(repo, output, run=RUN, plot=False):
    folder = repo / 'results' / run
    paths = [folder / n for n in ('experiment.json', 'records.json', 'update-budget.json', 'inputs/source.zip')]
    m, d, budget = [json.loads(p.read_text(encoding='utf-8')) for p in paths[:3]]
    hashes = {p.relative_to(repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    assert hashes[paths[3].relative_to(repo).as_posix()] == m['source_archive_sha256'], 'Source archive mismatch'
    rows = d['trajectories']
    ids = m['selected_ids']
    repeats = m['settings']['agent_repeats']
    assert set(m['settings']['strategies']) == set(STRATEGIES)
    assert len(rows) == len(ids)*repeats*len(STAGES)*len(STRATEGIES)
    physical = {resolve(rows,k): rows[resolve(rows,k)] for k in rows}
    judge_checked = 0
    for k, r in physical.items():
        for dim in METRICS:
            scores = [a['result'][dim] for a in r.get('judge_attempts',[]) if
                a.get('status') == 'completed' and isinstance(a.get('result',{}).get(dim), (int,float))]
            if scores:
                assert valid(r) and math.isclose(mean(scores),r['score'][dim],abs_tol=1e-9), k
                judge_checked += 1
    common = paired_ids(rows, STRATEGIES, STAGES)
    stage_common = {v:paired_ids(rows,STRATEGIES,[v]) for v in STAGES}
    summary, replicate, cohorts, comparisons = [], [], [], []
    core = {int(k): ('changed' if a['transitions']['iter3']['cohort']=='changed' else 'control')
        for k,a in m['task_annotations'].items()}
    for s in STRATEGIES:
        vals = [ecs([rows[f'{s}/{v}/{t}/{rep}']['score']['task_fulfillment'] for v in STAGES]) for t,rep in common]
        assert math.isclose(mean(vals),d['aggregate']['paired_ecs']['values'][s], abs_tol=1e-10)
        for rep in range(repeats):
            subset = [(t,r) for t,r in common if r==rep]
            replicate.append({'strategy':s,'repeat':rep,'n':len(subset),'ecs':mean([
                ecs([rows[f'{s}/{v}/{t}/{r}']['score']['task_fulfillment'] for v in STAGES]) for t,r in subset])})
        for v in STAGES:
            matched=stage_common[v]
            available=[r for r in rows.values() if r['identity']['strategy']==s and r['identity']['stage']==v and valid(r)]
            entry={'strategy':s,'stage':v,'available':len(available),'planned':len(ids)*repeats,'matched':len(matched),
                'paired_ecs':mean(vals)}
            for metric in METRICS:
                entry[metric]=mean([rows[f'{s}/{v}/{t}/{rep}']['score'][metric] for t,rep in matched])
                # Repeat-level variation: not five judge slots as independent repeats.
                rms=[mean([rows[f'{s}/{v}/{t}/{r}']['score'][metric] for t,r in matched if r==rep]) for rep in range(repeats)]
                entry[metric+'_repeat_means']=rms
                entry[metric+'_repeat_sd']=st.stdev(rms) if all(x is not None for x in rms) and len(rms)>1 else None
            summary.append(entry)
            if v=='original':continue
            for cohort in ('changed','control'):
                subset=[(t,rep) for t,rep in matched if core.get(t)==cohort]
                deltas=[]
                for t,rep in subset:
                    tf=rows[f'{s}/{v}/{t}/{rep}']['score']['task_fulfillment']
                    base=rows[f'no_update/{v}/{t}/{rep}']['score']['task_fulfillment']
                    deltas.append(tf-base)
                    comparisons.append({'strategy':s,'stage':v,'task':t,'repeat':rep,'cohort':cohort,'tf':tf,
                        'no_update_tf':base,'delta':tf-base})
                cohorts.append({'strategy':s,'stage':v,'cohort':cohort,'n':len(subset),'mean_delta':mean(deltas),
                    'negative_pairs':sum(x<0 for x in deltas),'drops_ge_2_diagnostic':sum(x<=-2 for x in deltas)})
    # Audit every memory-selection decision against actual previous/current contracts.
    memory_audit=[]
    costs=[]
    for eid, episode in d['episodes'].items():
        s,rep=eid.rsplit('/',1)
        for j,v in enumerate(STAGES[1:],1):
            snap=episode['stages'][v]; prev=episode['stages'][STAGES[j-1]]
            entries={e['id']:e for e in prev['experience_state']['memories']}
            after={e['id']:e for e in snap['experience_state']['memories']}
            old,new=prev['catalog'],snap['catalog']
            decisions={e['id']:e for e in snap['experience_update']['entries']}
            for name,e in entries.items():
                tools=e['value']['tool_ids']
                if e.get('adaptation',{}).get('status')=='unavailable':
                    servers={t.split('::')[0] for t in tools}
                    affected={k:x for k,x in old.items() if x['server'] in servers}!={k:x for k,x in new.items() if x['server'] in servers}
                else:affected=any(old.get(t)!=new.get(t) for t in tools)
                memory_audit.append({'strategy':s,'repeat':int(rep),'stage':v,'entry_id':name,
                    'affected':affected,'rebuilt':decisions[name]['rebuilt'],
                    'unchanged':e==after[name], 'tool_ids':tools})
            costs.append({'strategy':s,'repeat':int(rep),'stage':v,**{k:snap.get(k) for k in
                ('elapsed_seconds','api_calls','input_tokens','output_tokens','api_cost','cost_currency')}})
    cost_summary=[]
    for s in STRATEGIES:
        items=[c for c in costs if c['strategy']==s]
        entry={'strategy':s,'transitions':len(items)}
        for k in ('elapsed_seconds','api_calls','input_tokens','output_tokens','api_cost'):
            entry[k]=sum(c[k] for c in items) if all(c[k] is not None for c in items) else None
        entry['currency']='USD' if entry['api_cost'] else None
        cost_summary.append(entry)
    assert math.isclose(sum(c['api_cost'] for c in cost_summary),float(budget['reported_usd']),abs_tol=1e-10)
    # Separate physical agent and judge usage; copied Early rows contribute no extra calls.
    inference=[]
    for s in STRATEGIES:
        for role in ('agent','judge'):
            usages=[]
            eligible=[r for r in physical.values() if r['identity']['strategy']==s]
            for r in eligible:
                if role=='agent':usages.extend(r.get('agent_usage') or [])
                else:usages.extend(a['usage'] for a in r.get('judge_attempts',[]) if isinstance(a.get('usage'),dict))
            inference.append({'strategy':s,'role':role,'usage_records':len(usages),
                **{k:sum(u[k] for u in usages if type(u.get(k)) in (int,float)) for k in ('prompt_tokens','completion_tokens')},
                'cost_usd':None,'cost_note':'GLM inference: no dollar cost inferred; shared Early charged once to no_update owner'})
    coverage={'logical_trajectories':len(rows),'logical_scored':sum(valid(r) for r in rows.values()),
        'physical_trajectories':len(physical),'physical_scored':sum(valid(r) for r in physical.values()),
        'shared_aliases':len(rows)-len(physical),'physical_statuses':dict(Counter(r['status'] for r in physical.values())),
        'judge_statuses':dict(Counter(a['status'] for r in physical.values() for a in r.get('judge_attempts',[]))),
        'paired_ecs_n':len(common),'stage_matched_n':{k:len(v) for k,v in stage_common.items()},
        'excluded':[{'key':k,'reason':r.get('score_exclusion_reason'),'errors':r.get('errors')} for k,r in rows.items() if not valid(r)]}
    selective=[a for a in memory_audit if a['strategy']=='selective_patch']
    assert all(a['rebuilt']==a['affected'] and (a['affected'] or a['unchanged']) for a in selective)
    # Independent official ECS calculation, without importing the experiment runtime.
    spec=importlib.util.spec_from_file_location('role4_upstream_ecs', repo/'src/custom/analysis/answer/evolutionary_volatility.py')
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
    for s in STRATEGIES:
        check=[]
        for t,rep in common:
            xs=[rows[f'{s}/{v}/{t}/{rep}']['score']['task_fulfillment'] for v in STAGES]
            ref=mod._compute_row(str(t),*xs);check.append(ref.mean-ref.stdev)
        assert math.isclose(mean(check),d['aggregate']['paired_ecs']['values'][s],abs_tol=1e-10)
    output.mkdir(parents=True,exist_ok=True)
    result={'run':run,'hashes':hashes,'dirty_source':m['dirty_source'],'revision':m['revision'],
        'protocol':m['harness_protocol'],'purpose':m['purpose'],'coverage':coverage,
        'main_results':summary,'replicate_ecs':replicate,'cohorts':cohorts,'paired_task_deltas':comparisons,
        'cost_summary':cost_summary,'update_records':costs,'inference_usage':inference,'memory_audit':memory_audit,
        'validation':{'judge_metric_means_checked':judge_checked,'official_and_saved_ecs_match':True,
            'budget_matches_updates':True,'source_archive_verified':True,'selective_decision_audit_passed':True}}
    (output/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    case_keys=['no_update/iter5/416/0','full_rewrite/iter5/403/0','selective_patch/iter5/117/1',
        'selective_patch/iter5/389/0','no_update/iter5/389/0']
    case_data={k:{field:rows[k].get(field) for field in ('identity','score','messages','trajectory_messages',
        'raw_tool_trace','judge_attempts','answer','stop_reason')} for k in case_keys}
    (output/'case_evidence.json').write_text(json.dumps(case_data,ensure_ascii=False,indent=2),encoding='utf-8')
    text=['# Three-strategy evaluation / 三策略评估','',f'Run: `{run}`; protocol: `{m["harness_protocol"]}`.','',
        'This report analyzes only the specified run, not earlier pilots. The older protocol document is not a reliable description of the evolved experience-memory implementation. / 仅分析指定运行，不混入旧试跑；实际清单及源码快照优先于旧协议描述。','',
        '## Coverage / 数据覆盖','',table(['Measure','Value'],[[k,str(v)] for k,v in coverage.items() if k!='excluded']),'',
        'Shared Early is executed/scored once per task/repeat and reused across strategies. Logical rows are not independent observations. Judge slots are scoring attempts, not experiment repeats. / Early共享，不能重复计算调用成本或样本数。','',
        '## Main results / 主结果','',
        'Within each stage use exactly the same valid task/repeat identities across all strategies. SD is across three repeat-level means (sample SD); denominators vary where execution failed. Paired ECS uses all-stage common identities and population SD within each triple. / 各版本三策略共同样本；均分波动按三次实验均分算，不把judge当重复。','',
        table(['Strategy','Stage','Matched N','TF','TF repeat SD','PE','PE repeat SD','Paired ECS'],[
            [r['strategy'],r['stage'],r['matched'],r[METRICS[0]],r[METRICS[0]+'_repeat_sd'],r[METRICS[1]],r[METRICS[1]+'_repeat_sd'],r['paired_ecs']] for r in summary]),'',
        '## Repeat-level ECS / 各重复的ECS','',table(['Strategy','Repeat','Matched N','ECS'],[[r['strategy'],r['repeat'],r['n'],r['ecs']] for r in replicate]),'',
        table(['Strategy','Mean of 3 repeat ECS','Sample SD'],[[s,
            mean([r['ecs'] for r in replicate if r['strategy']==s]),
            st.stdev([r['ecs'] for r in replicate if r['strategy']==s])] for s in STRATEGIES]),'',
        'The mean of three repeat ECS values weights repeats equally; the primary pooled paired ECS weights the 49 valid task/repeat identities equally. They differ slightly because repeat 0 has 15 matched tasks and the others 17. / 重复均值与49配对样本均值权重不同，二者均明确报告。','',
        '## Recovery and retention / 恢复与保留','',
        'Absolute TF difference versus No Update on the same task/stage/repeat. These are descriptive paired effects, not proof of causation. The normalized recovery ratio is omitted because some Early baselines do not degrade and its cutoff was not established by this analysis. / 采用同任务同版本绝对差，不事后挑归一化公式。','',
        table(['Strategy','Stage','Cohort','Matched N','Mean ΔTF','Negative pairs','Drops ≥2 (diagnostic)'],[
            [r[k] for k in ('strategy','stage','cohort','n','mean_delta','negative_pairs','drops_ge_2_diagnostic')] for r in cohorts]),'',
        '## Update cost / 更新成本','',
        'Totals across six version transitions per strategy (two transitions × three repeats), not per task. Unlike the old catalog-only baseline, this run rewrites learned experience using a paid updater for Full Rewrite and Selective Patch. / 本次经验知识重写调用付费更新器，与旧版不同。','',
        table(['Strategy','Updates','Calls','Input tokens','Output tokens','Seconds','Reported USD'],[
            [r[k] for k in ('strategy','transitions','api_calls','input_tokens','output_tokens','elapsed_seconds','api_cost')] for r in cost_summary]),'',
        'Provider-reported update costs are used; reservation ceilings are not actual spend. Agent/judge tokens are recorded separately below; their USD is unavailable, not silently inferred as zero. Shared Early usage is charged once to its owner No Update; these totals are physical accounting rather than symmetric per-strategy runtime-cost estimates.','',
        table(['Strategy','Role','Usage records','Input tokens','Output tokens'],[[r[k] for k in ('strategy','role','usage_records','prompt_tokens','completion_tokens')] for r in inference]),'',
        '## Memory selection audit / 补丁范围审计','',
        table(['Strategy','Entry transitions','Rebuilt','Unaffected entries rebuilt','Affected entries not rebuilt'],[[s,
            sum(a['strategy']==s for a in memory_audit),sum(a['strategy']==s and a['rebuilt'] for a in memory_audit),
            sum(a['strategy']==s and a['rebuilt'] and not a['affected'] for a in memory_audit),
            sum(a['strategy']==s and not a['rebuilt'] and a['affected'] for a in memory_audit)] for s in STRATEGIES]),'',
        'This audits dependency selection and retention of untouched records, not semantic or behavioral correctness of rebuilt text. No observed selection omission does not prove no possible under-update. / 选择范围正确不等于重写内容或实际行为必然正确。','',
        '## Limitations / 限制','',
        '- Only 17 gate-limited tasks (four changed, thirteen controls); not a representative estimate of all MCPEvol-Bench tasks. Change type and server family are confounded; pure Tool deletion cases are absent.',
        '- Three repeats provide limited uncertainty evidence; no significance claim or post-hoc confidence threshold is made. Logical shared baselines are not treated as independent runs.',
        '- Two execution failures are excluded under the recorded protocol. The valid-only estimates can be optimistic; report coverage and complete-case ECS together. Excluded records remain in analysis.json.',
        '- dirty_source=true violates the older clean-commit protocol condition. The run contains a SHA-256-verified source.zip, frozen inputs and revision, so it is traceable; this is not equivalent to clean-source compliance.',
        '- Judge validity is limited by the same Agent/judge model and partial judge slots; inspect trajectories instead of equating a high TF with independently verified task success.',
        '- This experience-memory protocol must be explained to the report author. Do not reuse the old claim that Full Rewrite has zero update API cost.',
        '- Causal under-update and over-update case evidence is reported separately in CASES.md; suspected cases must remain labeled suspected.', '']
    if plot:
        text += ['## Figures / 图表','', '![TF PE and ECS](metrics.png)','', '![Recovery retention and update cost](tradeoffs.png)','']
    (output/'RESULTS.md').write_text('\n'.join(text),encoding='utf-8')
    if plot:figures(result,output)
    print(json.dumps({'coverage':coverage,'costs':cost_summary,'validation':result['validation']},ensure_ascii=False,indent=2))
    return result


def figures(r,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(1,3,figsize=(15,4.7))
    for s in STRATEGIES:
        rs=[x for x in r['main_results'] if x['strategy']==s]
        for j,k in enumerate(METRICS):
            axs[j].errorbar(range(3),[x[k] for x in rs],yerr=[x[k+'_repeat_sd'] for x in rs],marker='o',capsize=3,label=s)
            axs[j].set(xticks=range(3),xticklabels=['Early','Middle','Late'],ylim=(0,10.5),title='TF' if j==0 else 'PE',ylabel='Mean ± repeat SD')
    axs[2].bar(range(3),[next(x['paired_ecs'] for x in r['main_results'] if x['strategy']==s) for s in STRATEGIES],color=['#668099','#d79a52','#378c73'])
    axs[2].set(xticks=range(3),xticklabels=['No update','Full rewrite','Selective patch'],title=f'Paired ECS ({r["coverage"]["paired_ecs_n"]} task/repeat pairs)',ylim=(0,10))
    for ax in axs:ax.grid(axis='y',alpha=.2)
    axs[0].legend(fontsize=8); fig.suptitle('Three strategies · 17 tasks · 3 repeats · shared Early; coverage in report')
    fig.tight_layout();fig.savefig(out/'metrics.png',dpi=180);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(12,4.5))
    for i,s in enumerate(STRATEGIES[1:]):
        rs=[x for x in r['cohorts'] if x['strategy']==s]
        axs[0].bar([j+(i-.5)*.35 for j in range(4)],[x['mean_delta'] for x in rs],width=.35,label=s,color=['#d79a52','#378c73'][i])
    axs[0].axhline(0,color='#555',lw=1);axs[0].set(xticks=range(4),xticklabels=['Middle\nChanged n=12','Middle\nControl n=39','Late\nChanged n=11','Late\nControl n=38'],ylabel='Paired mean TF difference vs No Update',title='Recovery / retention (descriptive)')
    axs[0].legend(fontsize=8)
    axs[1].bar(range(3),[x['api_cost'] for x in r['cost_summary']],color=['#668099','#d79a52','#378c73'])
    axs[1].set(xticks=range(3),xticklabels=['No update','Full rewrite','Selective patch'],ylabel='Provider-reported USD',title='Update cost: 2 transitions × 3 repeats')
    for ax in axs:ax.grid(axis='y',alpha=.2)
    fig.tight_layout();fig.savefig(out/'tradeoffs.png',dpi=180);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2])
    p.add_argument('--output',type=Path);p.add_argument('--run',default=RUN);p.add_argument('--plot',action='store_true');a=p.parse_args()
    analyze(a.repo,a.output or a.repo/'.runtime/role4-three-strategy',a.run,a.plot)
