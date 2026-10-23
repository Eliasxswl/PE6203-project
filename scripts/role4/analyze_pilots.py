"""Read-only GitHub snapshot + offline Role 4 analysis. No model or tool execution.

Run from the repository: python scripts/role4/analyze_pilots.py
Outputs are derived JSON, Markdown, HTML and scientific PNG figures, not formal results.
"""
import argparse
import collections
import csv
import hashlib
import html
import io
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REPO = 'Eliasxswl/PE6203-project'
STAGES = ('original', 'iter3', 'iter5')
DIMENSIONS = ('task_fulfillment', 'planning_and_efficiency')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def finite_score(score, name):
    v = score.get(name) if isinstance(score, dict) else None
    return v if type(v) in (int, float) and math.isfinite(v) and 1 <= v <= 10 else None


def mean(values):
    return statistics.mean(values) if values else None


def token_totals(usages):
    if isinstance(usages, dict):
        usages = [usages]
    if not isinstance(usages, list):
        usages = []
    result = {'reported_calls': len(usages)}
    for field in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
        known = [u[field] for u in usages if isinstance(u, dict) and type(u.get(field)) in (int, float)]
        result[field] = sum(known) if known else None
        result[field + '_missing_calls'] = len(usages) - len(known)
    return result


def ecs(values):
    return statistics.mean(values) - statistics.pstdev(values)


def fmt(value):
    return '—' if value is None else f'{value:.3f}'


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |']
        + ['| ' + ' | '.join(str(v).replace('|', '/') for v in row) + ' |' for row in rows])


def analyze(index, out, plot=False):
    source = Path(index['snapshot'])
    # Verify every cached byte before deriving any results.
    for name, expected in index['sha256'].items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected, name
    annotations_text = (source / 'docs/task_subset_annotation.csv').read_text(encoding='utf-8-sig')
    delimiter = '\t' if '\t' in annotations_text.splitlines()[0] else ','
    labels = {int(r['idx']): r for r in csv.DictReader(io.StringIO(annotations_text), delimiter=delimiter)}
    out.mkdir(parents=True, exist_ok=True)
    details, run_summaries, groups, paired, ecs_rows, costs, issues, case_evidence = [], [], [], [], [], [], [], []
    usage_summary = []
    for record_path in sorted((source / 'results').glob('*/records.json')):
        run = record_path.parent.name
        records = json.loads(record_path.read_text(encoding='utf-8'))
        manifest = json.loads((record_path.parent / 'experiment.json').read_text(encoding='utf-8'))
        trajectories = records.get('trajectories', {})
        if not isinstance(trajectories, dict):
            raise ValueError('Unsupported trajectory schema: ' + run)
        local, original_rows = [], {}
        for key, row in trajectories.items():
            ident = row['identity']
            tup = (ident['strategy'], ident['stage'], ident['task_id'], ident['repeat'])
            if tup in original_rows:
                raise ValueError('Duplicate identity: ' + run + str(tup))
            original_rows[tup] = row
            scores = {name: finite_score(row.get('score'), name) for name in DIMENSIONS}
            slots = row.get('judge_attempts', [])
            valid_slots = sum(a.get('status') == 'completed' for a in slots)
            attempts = collections.Counter(a.get('status', 'unknown') for a in slots)
            label = labels.get(int(ident['task_id']), {})
            cohort = {'changed-core': 'changed', 'control-core': 'control'}.get(label.get('group'), 'unknown')
            entry = dict(run=run, key=key, **ident, cohort=cohort,
                status=row.get('status'), agent_status=row.get('agent_status'), **scores,
                valid_score=all(v is not None for v in scores.values()),
                judge_slots=len(slots), valid_judge_slots=valid_slots, judge_statuses=dict(attempts),
                exclusion_reason=row.get('score_exclusion_reason'), agent_usage=row.get('agent_usage'),
                agent_elapsed_seconds=row.get('agent_elapsed_seconds'),
                agent_tokens=token_totals(row.get('agent_usage')),
                judge_tokens=token_totals([a['usage'] for a in slots if isinstance(a.get('usage'), dict)]),
                source=f'results/{run}/records.json#trajectories/{key}')
            # Audit means from saved judge attempts when numeric slot scores are available.
            for dim in DIMENSIONS:
                vals = []
                for a in slots:
                    if a.get('status') != 'completed':
                        continue
                    for container in ('result', 'score', 'scores', 'parsed'):
                        v = finite_score(a.get(container), dim)
                        if v is not None:
                            vals.append(v)
                            break
                if vals:
                    entry[dim + '_judge_recomputed'] = mean(vals)
                    if scores[dim] is not None and not math.isclose(mean(vals), scores[dim], abs_tol=1e-8):
                        issues.append({'run': run, 'key': key, 'issue': 'judge_mean_mismatch', 'metric': dim})
            local.append(entry)
            if valid_slots < len(slots):
                issues.append({'run': run, 'key': key, 'issue': 'incomplete_judge_slots',
                    'valid': valid_slots, 'planned': len(slots), 'statuses': dict(attempts)})
            # Preserve actual tool call/result evidence for diagnostic review, not causal claims.
            if int(ident['task_id']) in (117, 403):
                messages = row.get('trajectory_messages') or row.get('messages') or []
                calls = []
                for j, message in enumerate(messages):
                    for tc in message.get('tool_calls', []) if isinstance(message, dict) else []:
                        calls.append({'message_index': j, 'function': tc.get('function'), 'id': tc.get('id')})
                case_evidence.append({'run': run, 'key': key, 'identity': ident, 'score': row.get('score'),
                    'status': row.get('status'), 'stop_reason': row.get('stop_reason'),
                    'answer': row.get('answer'), 'tool_calls': calls,
                    'raw_tool_trace': row.get('raw_tool_trace'), 'judge_attempts': slots,
                    'classification': 'diagnostic_candidate_only; no selective_patch causal attribution'})
        details.extend(local)
        strategies = sorted({r['strategy'] for r in local})
        task_repeats = sorted({(r['task_id'], r['repeat']) for r in local})
        run_summaries.append({'run': run, 'status': records.get('status'),
            'dirty_source': manifest.get('dirty_source'), 'harness_protocol': manifest.get('harness_protocol', 'legacy_unspecified'),
            'selected_ids': manifest.get('selected_ids'), 'strategies': strategies,
            'planned': len(local), 'scored': sum(r['valid_score'] for r in local),
            'statuses': dict(collections.Counter(r['status'] for r in local)),
            'judge_completed': sum(r['valid_judge_slots'] for r in local),
            'judge_planned': sum(r['judge_slots'] for r in local),
            'manifest_source': f'results/{run}/experiment.json'})
        lookup = {(r['strategy'], r['stage'], r['task_id'], r['repeat']): r for r in local}
        for strategy in strategies:
            for stage in STAGES:
                rs = [r for r in local if r['strategy'] == strategy and r['stage'] == stage]
                valid = [r for r in rs if r['valid_score']]
                groups.append({'run': run, 'strategy': strategy, 'stage': stage, 'planned': len(rs),
                    'valid': len(valid), 'excluded': len(rs)-len(valid),
                    **{d: mean([r[d] for r in valid]) for d in DIMENSIONS}})
        # All-strategy paired comparisons within a run and stage; never pool runs.
        for stage in STAGES:
            for task_id, repeat in task_repeats:
                matched = [lookup.get((s, stage, task_id, repeat)) for s in strategies]
                if not all(r is not None and r['valid_score'] for r in matched):
                    continue
                baseline = lookup.get(('no_update', stage, task_id, repeat))
                if baseline is None:
                    continue
                for r in matched:
                    paired.append({'run': run, 'stage': stage, 'task_id': task_id, 'repeat': repeat,
                        'strategy': r['strategy'], 'cohort': r['cohort'],
                        'tf': r['task_fulfillment'], 'baseline_tf': baseline['task_fulfillment'],
                        'delta_tf_vs_no_update': r['task_fulfillment'] - baseline['task_fulfillment'],
                        'pe': r['planning_and_efficiency'],
                        'delta_pe_vs_no_update': r['planning_and_efficiency'] - baseline['planning_and_efficiency']})
        for strategy in strategies:
            for stage in STAGES:
                rs = [r for r in local if r['strategy'] == strategy and r['stage'] == stage]
                usage_summary.append({'run': run, 'strategy': strategy, 'stage': stage,
                    'planned': len(rs), **{role: {
                        field: sum(r[role][field] for r in rs if r[role][field] is not None)
                        if any(r[role][field] is not None for r in rs) else None
                        for field in ('reported_calls','prompt_tokens','completion_tokens','total_tokens')}
                        for role in ('agent_tokens','judge_tokens')}})
        matched_ecs = [(t, rep) for t, rep in task_repeats if all(
            lookup.get((s, stage, t, rep), {}).get('valid_score', False)
            for s in strategies for stage in STAGES)]
        for strategy in strategies:
            values = [ecs([lookup[(strategy, stage, t, rep)]['task_fulfillment'] for stage in STAGES])
                for t, rep in matched_ecs]
            ecs_rows.append({'run': run, 'strategy': strategy, 'matched_tasks': len(values),
                'identities': matched_ecs, 'paired_ecs': mean(values), 'population_sd': True})
        for eid, episode in records.get('episodes', {}).items():
            for stage, snapshot in episode.get('stages', {}).items():
                if stage == 'original':
                    continue
                costs.append({'run': run, 'episode': eid, 'stage': stage,
                    **{k: snapshot.get(k) for k in ('status', 'elapsed_seconds', 'api_calls',
                        'input_tokens', 'output_tokens', 'api_cost', 'cost_currency', 'cost_basis')},
                    'source': f'results/{run}/records.json#episodes/{eid}/stages/{stage}'})
    write_json(out / 'analysis.json', {'repository': REPO, 'commit': index['commit'], 'scope': 'PILOT ONLY',
        'runs': run_summaries, 'groups': groups, 'paired': paired, 'paired_ecs': ecs_rows,
        'update_costs': costs, 'inference_token_usage': usage_summary,
        'trajectories': details, 'issues': issues})
    write_json(out / 'diagnostic_case_evidence.json', case_evidence)
    # Core numerical invariants are checked before reports are emitted.
    assert math.isclose(ecs([9, 9, 9]), 9)
    assert ecs([9, 5, 9]) < ecs([8, 8, 8])
    assert sum(g['planned'] for g in groups) == len(details)
    assert len({(r['run'], r['key']) for r in details}) == len(details)
    assert not [i for i in issues if i['issue'] == 'judge_mean_mismatch'], 'Judge means differ from saved scores'
    # Independently compare the formula to the frozen upstream implementation.
    import importlib.util
    official_path = source / 'src/custom/analysis/answer/evolutionary_volatility.py'
    spec = importlib.util.spec_from_file_location('role4_official_ecs', official_path)
    official = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = official
    spec.loader.exec_module(official)
    for result in ecs_rows:
        values = []
        for task_id, repeat in result['identities']:
            tf = [next(r['task_fulfillment'] for r in details if r['run'] == result['run']
                and r['strategy'] == result['strategy'] and r['stage'] == stage
                and r['task_id'] == task_id and r['repeat'] == repeat) for stage in STAGES]
            reference = official._compute_row(str(task_id), *tf)
            values.append(reference.mean - reference.stdev)
        expected = mean(values)
        assert expected is None and result['paired_ecs'] is None or math.isclose(expected, result['paired_ecs'], abs_tol=1e-10)
    write_json(out / 'validation.json', {'source_checksums_verified': len(index['sha256']),
        'unique_trajectories': len(details), 'planned_counts_reconciled': True,
        'judge_mean_mismatches': 0, 'official_ecs_comparisons': len(ecs_rows), 'passed': True})
    report = [
        '# Role 4 pilot analysis / 试跑分析', '',
        '**PILOT ONLY — not a formal comparison of three strategies. / 仅为试跑，不是三策略正式结论。**', '',
        f'Source: https://github.com/{REPO}/tree/{index["commit"]}', '',
        '## What is available / 已完成的整理', '',
        f'Analyzed {len(run_summaries)} archived runs and {len(details)} planned trajectories. Each run is kept separate; missing scores are not replaced with zero. / 已独立整理各次运行，不混合，不将缺失填零。', '',
        table(['Run', 'Planned', 'Scored', 'Judge valid/planned', 'Dirty source', 'Protocol'],
            [[r['run'], r['planned'], r['scored'], f"{r['judge_completed']}/{r['judge_planned']}",
                r['dirty_source'], r['harness_protocol']] for r in run_summaries]), '',
        '## TF and PE by run / 各次运行的分数', '',
        'Means below use available valid TF/PE pairs; coverage is shown. These unpaired group means are diagnostic; use matched comparisons for strategy differences. / 下表为有效记录均分，策略比较另按相同任务配对。', '',
        table(['Run', 'Strategy', 'Stage', 'Valid/planned', 'TF', 'PE'],
            [[g['run'], g['strategy'], g['stage'], f"{g['valid']}/{g['planned']}",
                fmt(g[DIMENSIONS[0]]), fmt(g[DIMENSIONS[1]])] for g in groups]), '',
        '## Matched ECS / 配对 ECS', '',
        'For each run, use only task/repeat identities scored at all three stages under every strategy present. ECS = mean_task(mean_stage(TF) − population_SD_stage(TF)). Missing identities remain excluded and the denominator is reported. / 仅在同一运行内，对所有已有策略和三个版本均有分数的任务计算。', '',
        table(['Run', 'Strategy', 'Matched task/repeats', 'ECS'],
            [[r['run'], r['strategy'], r['matched_tasks'], fmt(r['paired_ecs'])] for r in ecs_rows]), '',
        '## Update cost / 更新成本', '',
        'Each transition is counted once per strategy/repeat, not once per task. Missing values remain unavailable. Dollar prices are not inferred. / 每次更新只计一次，不按任务重复累加；未报告费用不视为零。', '',
        table(['Run', 'Episode', 'Stage', 'Status', 'Seconds', 'Input tokens', 'Output tokens', 'API cost'],
            [[c['run'], c['episode'], c['stage'], c['status'], fmt(c['elapsed_seconds']),
                c['input_tokens'], c['output_tokens'], c['api_cost']] for c in costs]), '',
        'Current adapters.py rebuilds full_rewrite directly from the live catalog and explicitly declares no model requests. It is therefore not valid to assume an LLM full-rewrite token cost or claim that patching saves API cost against it. Confirm historical record values per run. / 当前全部重建不调用模型，不能预设选择性补丁会比它省 API 费用。', '',
        '## Recovery and retention / 恢复与保留', '',
        'Task labels are from Role 3 at this pinned commit; they are provisional and drawn from pilot catalog evidence. Changed-core and control-core are kept separate. Unknown extensions are not assigned labels by guessing. / 使用 Role 3 当前标注，未确认扩展任务保持未知。', '',
        'Paired absolute ΔTF = strategy TF − no_update TF at the same task/stage/repeat. The proposed normalized recovery ratio is not reported until its baseline and cutoff are frozen. Original-stage comparisons are calibration only. / 先报告同任务同版本绝对差；归一化恢复比例待协议冻结。', '',
    ]
    cohorts = []
    for run in run_summaries:
        for stage in STAGES[1:]:
            for strategy in run['strategies']:
                if strategy == 'no_update':
                    continue
                for cohort in ('changed', 'control'):
                    rs = [r for r in paired if r['run'] == run['run'] and r['stage'] == stage
                        and r['strategy'] == strategy and r['cohort'] == cohort]
                    cohorts.append([run['run'], strategy, stage, cohort, len(rs),
                        fmt(mean([r['delta_tf_vs_no_update'] for r in rs]))])
    report += [table(['Run', 'Strategy', 'Stage', 'Cohort', 'Matched N', 'Mean ΔTF'], cohorts), '',
        '## Interpretation and unfinished formal work / 解读与待完成部分', '',
        '- Scores from different code/protocol runs are never treated as independent repeats of one frozen experiment. / 不同代码版本的试跑不合并成重复实验。',
        '- A completed trajectory can have fewer than five valid judge slots. Saved score means are checked against judge-slot scores when the schema exposes them. / completed 不代表评分完整。',
        '- Early-stage strategy differences indicate execution/judging variability; version differences alone do not establish effects of an update. / 原始版本已有波动，不能把所有分差归因于更新。',
        '- Task 117 and control 403 are diagnostic review candidates, not established under-update/over-update cases. No selective_patch trajectory is invented. / 候选案例须核对调用、补丁和返回证据。',
        '- The current task list and recovery/retention definitions need group freeze; selective_patch, clean source, full coverage and the official run remain prerequisites for final claims. / 正式结论待任务与公式冻结、第三策略接入和干净版本正式运行。', '',
        '## Reproduce / 复现', '',
        'Run python scripts/role4/analyze_pilots.py from the repository. Outputs default to .runtime/role4-analysis. Optional --plot requires Matplotlib. Input SHA-256 values and source commit are saved in source_index.json. No LLM calls or changes to experiment records. / 本地离线运行，保存输入校验值，不调用模型，不修改原始结果。', '',
        'Detailed machine-readable records: analysis.json; raw case evidence: diagnostic_case_evidence.json. / 详细数值与证据见同目录 JSON。',
    ]
    (out / 'PILOT_REPORT.md').write_text('\n'.join(report), encoding='utf-8')
    make_html(out, index, run_summaries, groups, ecs_rows, cohorts, costs, plot)
    if plot:
        make_plot(out, groups)
    print('Analysis complete:', len(run_summaries), 'runs;', len(details), 'trajectories;', len(issues), 'coverage issues', flush=True)


def make_html(out, index, runs, groups, ecs_rows, cohorts, costs, plot):
    def ht(headers, rows):
        return '<div class="scroll"><table><thead><tr>' + ''.join('<th>'+html.escape(str(v))+'</th>' for v in headers) + '</tr></thead><tbody>' + ''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in row)+'</tr>' for row in rows) + '</tbody></table></div>'
    content = '<h1>Role 4 · 试跑分析</h1><p class="note">仅供试跑核验 · 正式任务集及第三策略未就绪 · 各运行独立呈现</p>'
    content += '<p>来源提交：<code>'+index['commit']+'</code>。本报告没有合并不同运行，也没有将缺失成绩填零。</p>'
    content += '<h2>运行覆盖率</h2>' + ht(['运行', '计划轨迹', '有效分数', '有效/计划评分', 'Dirty source'], [[r['run'],r['planned'],r['scored'],f"{r['judge_completed']}/{r['judge_planned']}",r['dirty_source']] for r in runs])
    if plot:
        content += '<h2>版本比较</h2><p>每个面板为独立运行。分数缺失处不连线；无置信区间，不解释为多次独立重复。</p><img src="pilot_tf.png" alt="各次试跑按版本的 TF 均值">'
    content += '<h2>TF / PE 明细</h2>' + ht(['运行','策略','版本','有效/计划','TF','PE'], [[g['run'],g['strategy'],g['stage'],f"{g['valid']}/{g['planned']}",fmt(g[DIMENSIONS[0]]),fmt(g[DIMENSIONS[1]])] for g in groups])
    content += '<h2>同任务配对 ECS</h2><p>三个版本 TF 均值减总体标准差，再对所有策略共同有效的任务取平均。</p>' + ht(['运行','策略','共同任务/重复数','ECS'], [[r['run'],r['strategy'],r['matched_tasks'],fmt(r['paired_ecs'])] for r in ecs_rows])
    content += '<h2>恢复与保留：相对 No Update 的绝对差</h2><p>按 Role 3 当前标注。归一化恢复公式尚未冻结，不报告该比值。</p>'+ht(['运行','策略','版本','分组','配对N','平均 ΔTF'],cohorts)
    content += '<h2>结论边界与待办</h2><p>当前仅有两基线。分差是描述性结果；未证实 Selective Patch 的优劣，也未证实 under-update / over-update 根因。正式分析需冻结任务与公式、接入第三策略并从干净版本运行。Full Rewrite 当前直接重建目录，不调用模型，不能预设其高 token 成本。</p><p>完整成本记录、异常列表和逐任务分差见 analysis.json；中英文分析见 PILOT_REPORT.md。</p>'
    (out / 'ROLE4_REVIEW.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Role 4 试跑分析</title><style>body{font:16px/1.65 "Segoe UI","Microsoft YaHei",sans-serif;background:#f5f7fa;color:#203047;max-width:1400px;margin:40px auto;padding:0 24px}h1{font-size:32px}h2{margin-top:40px}.note{color:#955300}table{border-collapse:collapse;background:white;width:100%;font-size:14px}th,td{border:1px solid #dce2e8;padding:9px 12px;text-align:left;white-space:nowrap}th{background:#e8eef5}tbody tr:nth-child(even){background:#f7f9fc}.scroll{overflow-x:auto}img{width:100%;height:auto}code{overflow-wrap:anywhere}</style>'+content+'</html>', encoding='utf-8')


def make_plot(out, groups):
    import os
    os.environ['MPLCONFIGDIR'] = str(ROOT / '.plot_cache')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    runs = sorted({r['run'] for r in groups})
    fig, axes = plt.subplots(math.ceil(len(runs)/2), 2, figsize=(13, 3.2*math.ceil(len(runs)/2)), squeeze=False)
    for ax, run in zip(axes.flat, runs):
        for strategy in sorted({r['strategy'] for r in groups if r['run']==run}):
            rs = {r['stage']:r for r in groups if r['run']==run and r['strategy']==strategy}
            ys = [rs.get(s,{}).get('task_fulfillment') for s in STAGES]
            ax.plot(range(3), [v if v is not None else float('nan') for v in ys], marker='o', label=strategy)
            for j, value in enumerate(ys):
                if value is not None:
                    ax.annotate('n='+str(rs[STAGES[j]]['valid']), (j, value),
                        textcoords='offset points', xytext=(3, 8 if strategy == 'full_rewrite' else -14), fontsize=7)
        ax.set(title=run.split('_')[0], xticks=range(3), xticklabels=['Early','Middle','Late'], ylim=(0,10.6), ylabel='Available-score mean TF')
        ax.grid(alpha=.2); ax.legend(fontsize=8)
    for ax in list(axes.flat)[len(runs):]:
        ax.set_visible(False)
    fig.suptitle('PILOT ONLY: independent runs; coverage in report; no pooling', fontsize=14)
    fig.tight_layout(rect=(0,0,1,.97))
    fig.savefig(out / 'pilot_tf.png', dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--plot', action='store_true', help='Optional Matplotlib figures')
    args = parser.parse_args()
    source = args.repo_root.resolve()
    out = (args.output or source / '.runtime/role4-analysis').resolve()
    if out == source or source / 'results' == out or source / 'results' in out.parents:
        parser.error('Output must not overwrite the repository or original results')
    commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    paths = [p for p in (source / 'results').glob('*/*.json') if p.name in ('records.json', 'experiment.json')]
    paths += [source / p for p in ('docs/task_subset_annotation.csv',
        'src/custom/analysis/answer/evolutionary_volatility.py')]
    index = {'repository': REPO, 'commit': commit, 'snapshot': str(source),
        'sha256': {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    write_json(out / 'source_index.json', index)
    analyze(index, out, args.plot)
