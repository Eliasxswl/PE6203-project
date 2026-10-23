# Role 4 pilot analysis / 试跑分析

**PILOT ONLY — not a formal comparison of three strategies. / 仅为试跑，不是三策略正式结论。**

Source: https://github.com/Eliasxswl/PE6203-project/tree/291e1e998c7e81fa369cd195e3180cc9465764bd

## What is available / 已完成的整理

Analyzed 7 archived runs and 240 planned trajectories. Each run is kept separate; missing scores are not replaced with zero. / 已独立整理各次运行，不混合，不将缺失填零。

| Run | Planned | Scored | Judge valid/planned | Dirty source | Protocol |
| --- | --- | --- | --- | --- | --- |
| 20261014T210414.755267Z_Kevin | 30 | 4 | 17/150 | True | legacy_unspecified |
| 20261014T214507.134301Z_Kevin | 30 | 1 | 3/150 | True | legacy_unspecified |
| 20261015T045814.065101Z_Kevin | 30 | 30 | 149/150 | True | legacy_unspecified |
| 20261015T094217.941435Z_Kevin | 30 | 2 | 10/150 | False | legacy_unspecified |
| 20261015T094611.592744Z_Kevin | 30 | 30 | 146/150 | True | legacy_unspecified |
| 20261015T160434.320145Z_Kevin | 30 | 30 | 150/150 | True | minimal_repair_v1 |
| 20261015T200405.239100Z_Kevin | 60 | 59 | 273/300 | True | minimal_repair_v2 |

## TF and PE by run / 各次运行的分数

Means below use available valid TF/PE pairs; coverage is shown. These unpaired group means are diagnostic; use matched comparisons for strategy differences. / 下表为有效记录均分，策略比较另按相同任务配对。

| Run | Strategy | Stage | Valid/planned | TF | PE |
| --- | --- | --- | --- | --- | --- |
| 20261014T210414.755267Z_Kevin | full_rewrite | original | 0/5 | — | — |
| 20261014T210414.755267Z_Kevin | full_rewrite | iter3 | 0/5 | — | — |
| 20261014T210414.755267Z_Kevin | full_rewrite | iter5 | 0/5 | — | — |
| 20261014T210414.755267Z_Kevin | no_update | original | 3/5 | 5.300 | 6.833 |
| 20261014T210414.755267Z_Kevin | no_update | iter3 | 1/5 | 3.800 | 1.800 |
| 20261014T210414.755267Z_Kevin | no_update | iter5 | 0/5 | — | — |
| 20261014T214507.134301Z_Kevin | full_rewrite | original | 0/5 | — | — |
| 20261014T214507.134301Z_Kevin | full_rewrite | iter3 | 0/5 | — | — |
| 20261014T214507.134301Z_Kevin | full_rewrite | iter5 | 0/5 | — | — |
| 20261014T214507.134301Z_Kevin | no_update | original | 1/5 | 8.000 | 9.667 |
| 20261014T214507.134301Z_Kevin | no_update | iter3 | 0/5 | — | — |
| 20261014T214507.134301Z_Kevin | no_update | iter5 | 0/5 | — | — |
| 20261015T045814.065101Z_Kevin | full_rewrite | original | 5/5 | 6.400 | 8.200 |
| 20261015T045814.065101Z_Kevin | full_rewrite | iter3 | 5/5 | 6.400 | 8.600 |
| 20261015T045814.065101Z_Kevin | full_rewrite | iter5 | 5/5 | 6.790 | 7.010 |
| 20261015T045814.065101Z_Kevin | no_update | original | 5/5 | 6.760 | 6.080 |
| 20261015T045814.065101Z_Kevin | no_update | iter3 | 5/5 | 5.320 | 7.400 |
| 20261015T045814.065101Z_Kevin | no_update | iter5 | 5/5 | 6.040 | 7.000 |
| 20261015T094217.941435Z_Kevin | full_rewrite | original | 0/5 | — | — |
| 20261015T094217.941435Z_Kevin | full_rewrite | iter3 | 0/5 | — | — |
| 20261015T094217.941435Z_Kevin | full_rewrite | iter5 | 0/5 | — | — |
| 20261015T094217.941435Z_Kevin | no_update | original | 2/5 | 5.500 | 5.800 |
| 20261015T094217.941435Z_Kevin | no_update | iter3 | 0/5 | — | — |
| 20261015T094217.941435Z_Kevin | no_update | iter5 | 0/5 | — | — |
| 20261015T094611.592744Z_Kevin | full_rewrite | original | 5/5 | 6.040 | 6.027 |
| 20261015T094611.592744Z_Kevin | full_rewrite | iter3 | 5/5 | 5.400 | 7.120 |
| 20261015T094611.592744Z_Kevin | full_rewrite | iter5 | 5/5 | 7.050 | 7.660 |
| 20261015T094611.592744Z_Kevin | no_update | original | 5/5 | 9.520 | 7.880 |
| 20261015T094611.592744Z_Kevin | no_update | iter3 | 5/5 | 6.720 | 7.680 |
| 20261015T094611.592744Z_Kevin | no_update | iter5 | 5/5 | 6.400 | 7.800 |
| 20261015T160434.320145Z_Kevin | full_rewrite | original | 5/5 | 9.400 | 10.000 |
| 20261015T160434.320145Z_Kevin | full_rewrite | iter3 | 5/5 | 5.720 | 9.520 |
| 20261015T160434.320145Z_Kevin | full_rewrite | iter5 | 5/5 | 8.160 | 10.000 |
| 20261015T160434.320145Z_Kevin | no_update | original | 5/5 | 8.000 | 10.000 |
| 20261015T160434.320145Z_Kevin | no_update | iter3 | 5/5 | 7.800 | 9.760 |
| 20261015T160434.320145Z_Kevin | no_update | iter5 | 5/5 | 8.560 | 9.800 |
| 20261015T200405.239100Z_Kevin | full_rewrite | original | 10/10 | 4.560 | 8.490 |
| 20261015T200405.239100Z_Kevin | full_rewrite | iter3 | 9/10 | 6.533 | 9.600 |
| 20261015T200405.239100Z_Kevin | full_rewrite | iter5 | 10/10 | 7.460 | 9.600 |
| 20261015T200405.239100Z_Kevin | no_update | original | 10/10 | 5.365 | 8.915 |
| 20261015T200405.239100Z_Kevin | no_update | iter3 | 10/10 | 7.540 | 9.120 |
| 20261015T200405.239100Z_Kevin | no_update | iter5 | 10/10 | 7.120 | 9.020 |

## Matched ECS / 配对 ECS

For each run, use only task/repeat identities scored at all three stages under every strategy present. ECS = mean_task(mean_stage(TF) − population_SD_stage(TF)). Missing identities remain excluded and the denominator is reported. / 仅在同一运行内，对所有已有策略和三个版本均有分数的任务计算。

| Run | Strategy | Matched task/repeats | ECS |
| --- | --- | --- | --- |
| 20261014T210414.755267Z_Kevin | full_rewrite | 0 | — |
| 20261014T210414.755267Z_Kevin | no_update | 0 | — |
| 20261014T214507.134301Z_Kevin | full_rewrite | 0 | — |
| 20261014T214507.134301Z_Kevin | no_update | 0 | — |
| 20261015T045814.065101Z_Kevin | full_rewrite | 5 | 4.791 |
| 20261015T045814.065101Z_Kevin | no_update | 5 | 4.403 |
| 20261015T094217.941435Z_Kevin | full_rewrite | 0 | — |
| 20261015T094217.941435Z_Kevin | no_update | 0 | — |
| 20261015T094611.592744Z_Kevin | full_rewrite | 5 | 4.593 |
| 20261015T094611.592744Z_Kevin | no_update | 5 | 6.044 |
| 20261015T160434.320145Z_Kevin | full_rewrite | 5 | 6.081 |
| 20261015T160434.320145Z_Kevin | no_update | 5 | 7.524 |
| 20261015T200405.239100Z_Kevin | full_rewrite | 9 | 4.797 |
| 20261015T200405.239100Z_Kevin | no_update | 9 | 4.387 |

## Update cost / 更新成本

Each transition is counted once per strategy/repeat, not once per task. Missing values remain unavailable. Dollar prices are not inferred. / 每次更新只计一次，不按任务重复累加；未报告费用不视为零。

| Run | Episode | Stage | Status | Seconds | Input tokens | Output tokens | API cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 20261014T210414.755267Z_Kevin | no_update/0 | iter3 | ready | 0.001 | None | None | None |
| 20261014T210414.755267Z_Kevin | no_update/0 | iter5 | ready | 0.001 | None | None | None |
| 20261014T210414.755267Z_Kevin | full_rewrite/0 | iter3 | ready | 0.001 | None | None | None |
| 20261014T210414.755267Z_Kevin | full_rewrite/0 | iter5 | ready | 0.001 | None | None | None |
| 20261014T214507.134301Z_Kevin | no_update/0 | iter3 | ready | 0.001 | None | None | None |
| 20261014T214507.134301Z_Kevin | no_update/0 | iter5 | ready | 0.001 | None | None | None |
| 20261014T214507.134301Z_Kevin | full_rewrite/0 | iter3 | ready | 0.001 | None | None | None |
| 20261014T214507.134301Z_Kevin | full_rewrite/0 | iter5 | ready | 0.001 | None | None | None |
| 20261015T045814.065101Z_Kevin | no_update/0 | iter3 | ready | 0.024 | None | None | None |
| 20261015T045814.065101Z_Kevin | no_update/0 | iter5 | ready | 0.001 | None | None | None |
| 20261015T045814.065101Z_Kevin | full_rewrite/0 | iter3 | ready | 0.001 | None | None | None |
| 20261015T045814.065101Z_Kevin | full_rewrite/0 | iter5 | ready | 0.001 | None | None | None |
| 20261015T094611.592744Z_Kevin | no_update/0 | iter3 | ready | 0.001 | None | None | None |
| 20261015T094611.592744Z_Kevin | no_update/0 | iter5 | ready | 0.001 | None | None | None |
| 20261015T094611.592744Z_Kevin | full_rewrite/0 | iter3 | ready | 0.001 | None | None | None |
| 20261015T094611.592744Z_Kevin | full_rewrite/0 | iter5 | ready | 0.001 | None | None | None |
| 20261015T160434.320145Z_Kevin | no_update/0 | iter3 | ready | 0.001 | None | None | None |
| 20261015T160434.320145Z_Kevin | no_update/0 | iter5 | ready | 0.001 | None | None | None |
| 20261015T160434.320145Z_Kevin | full_rewrite/0 | iter3 | ready | 0.001 | None | None | None |
| 20261015T160434.320145Z_Kevin | full_rewrite/0 | iter5 | ready | 0.001 | None | None | None |
| 20261015T200405.239100Z_Kevin | no_update/0 | iter3 | ready | 0.001 | None | None | None |
| 20261015T200405.239100Z_Kevin | no_update/0 | iter5 | ready | 0.001 | None | None | None |
| 20261015T200405.239100Z_Kevin | full_rewrite/0 | iter3 | ready | 0.001 | None | None | None |
| 20261015T200405.239100Z_Kevin | full_rewrite/0 | iter5 | ready | 0.001 | None | None | None |

Current adapters.py rebuilds full_rewrite directly from the live catalog and explicitly declares no model requests. It is therefore not valid to assume an LLM full-rewrite token cost or claim that patching saves API cost against it. Confirm historical record values per run. / 当前全部重建不调用模型，不能预设选择性补丁会比它省 API 费用。

## Recovery and retention / 恢复与保留

Task labels are from Role 3 at this pinned commit; they are provisional and drawn from pilot catalog evidence. Changed-core and control-core are kept separate. Unknown extensions are not assigned labels by guessing. / 使用 Role 3 当前标注，未确认扩展任务保持未知。

Paired absolute ΔTF = strategy TF − no_update TF at the same task/stage/repeat. The proposed normalized recovery ratio is not reported until its baseline and cutoff are frozen. Original-stage comparisons are calibration only. / 先报告同任务同版本绝对差；归一化恢复比例待协议冻结。

| Run | Strategy | Stage | Cohort | Matched N | Mean ΔTF |
| --- | --- | --- | --- | --- | --- |
| 20261014T210414.755267Z_Kevin | full_rewrite | iter3 | changed | 0 | — |
| 20261014T210414.755267Z_Kevin | full_rewrite | iter3 | control | 0 | — |
| 20261014T210414.755267Z_Kevin | full_rewrite | iter5 | changed | 0 | — |
| 20261014T210414.755267Z_Kevin | full_rewrite | iter5 | control | 0 | — |
| 20261014T214507.134301Z_Kevin | full_rewrite | iter3 | changed | 0 | — |
| 20261014T214507.134301Z_Kevin | full_rewrite | iter3 | control | 0 | — |
| 20261014T214507.134301Z_Kevin | full_rewrite | iter5 | changed | 0 | — |
| 20261014T214507.134301Z_Kevin | full_rewrite | iter5 | control | 0 | — |
| 20261015T045814.065101Z_Kevin | full_rewrite | iter3 | changed | 3 | -0.600 |
| 20261015T045814.065101Z_Kevin | full_rewrite | iter3 | control | 2 | 3.600 |
| 20261015T045814.065101Z_Kevin | full_rewrite | iter5 | changed | 3 | -2.350 |
| 20261015T045814.065101Z_Kevin | full_rewrite | iter5 | control | 2 | 5.400 |
| 20261015T094217.941435Z_Kevin | full_rewrite | iter3 | changed | 0 | — |
| 20261015T094217.941435Z_Kevin | full_rewrite | iter3 | control | 0 | — |
| 20261015T094217.941435Z_Kevin | full_rewrite | iter5 | changed | 0 | — |
| 20261015T094217.941435Z_Kevin | full_rewrite | iter5 | control | 0 | — |
| 20261015T094611.592744Z_Kevin | full_rewrite | iter3 | changed | 3 | -0.533 |
| 20261015T094611.592744Z_Kevin | full_rewrite | iter3 | control | 2 | -2.500 |
| 20261015T094611.592744Z_Kevin | full_rewrite | iter5 | changed | 3 | 1.083 |
| 20261015T094611.592744Z_Kevin | full_rewrite | iter5 | control | 2 | 0.000 |
| 20261015T160434.320145Z_Kevin | full_rewrite | iter3 | changed | 3 | 0.133 |
| 20261015T160434.320145Z_Kevin | full_rewrite | iter3 | control | 2 | -5.400 |
| 20261015T160434.320145Z_Kevin | full_rewrite | iter5 | changed | 3 | -0.667 |
| 20261015T160434.320145Z_Kevin | full_rewrite | iter5 | control | 2 | 0.000 |
| 20261015T200405.239100Z_Kevin | full_rewrite | iter3 | changed | 2 | 3.600 |
| 20261015T200405.239100Z_Kevin | full_rewrite | iter3 | control | 6 | -2.200 |
| 20261015T200405.239100Z_Kevin | full_rewrite | iter5 | changed | 3 | -1.000 |
| 20261015T200405.239100Z_Kevin | full_rewrite | iter5 | control | 6 | 1.867 |

## Interpretation and unfinished formal work / 解读与待完成部分

- Scores from different code/protocol runs are never treated as independent repeats of one frozen experiment. / 不同代码版本的试跑不合并成重复实验。
- A completed trajectory can have fewer than five valid judge slots. Saved score means are checked against judge-slot scores when the schema exposes them. / completed 不代表评分完整。
- Early-stage strategy differences indicate execution/judging variability; version differences alone do not establish effects of an update. / 原始版本已有波动，不能把所有分差归因于更新。
- Task 117 and control 403 are diagnostic review candidates, not established under-update/over-update cases. No selective_patch trajectory is invented. / 候选案例须核对调用、补丁和返回证据。
- The current task list and recovery/retention definitions need group freeze; selective_patch, clean source, full coverage and the official run remain prerequisites for final claims. / 正式结论待任务与公式冻结、第三策略接入和干净版本正式运行。

## Reproduce / 复现

Run python scripts/role4/analyze_pilots.py from the repository. Outputs default to .runtime/role4-analysis. Optional --plot requires Matplotlib. Input SHA-256 values and source commit are saved in source_index.json. No LLM calls or changes to experiment records. / 本地离线运行，保存输入校验值，不调用模型，不修改原始结果。

Detailed machine-readable records: analysis.json; raw case evidence: diagnostic_case_evidence.json. / 详细数值与证据见同目录 JSON。