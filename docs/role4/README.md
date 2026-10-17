# Role 4 offline pilot analysis

This contribution analyzes archived experiments without model calls, tool-server execution, or changes to benchmark inputs. It does not constitute the final three-strategy evaluation.

Run from the repository root:

```text
python scripts/role4/analyze_pilots.py
```

The standard-library analysis writes to the ignored `.runtime/role4-analysis/` directory:

- `ROLE4_REVIEW.html`: Chinese review tables.
- `PILOT_REPORT.md`: bilingual coverage, TF/PE, paired ECS, update costs and cohort differences.
- `analysis.json`: per-trajectory scores, provenance, paired differences, token usage and coverage issues.
- `diagnostic_case_evidence.json`: actual evidence for candidate tasks 117 and 403.
- `source_index.json`: input SHA-256 checksums and checked-out source commit.
- `validation.json`: reconciliation and official ECS cross-check results.

Use `--output PATH` for another derived-output directory. Original results are never rewritten. `--plot` optionally generates a Matplotlib figure; Matplotlib must be installed in the user's existing analysis environment. No plotting dependency is needed for tables or JSON. Do not commit raw-result duplicates, local dependencies or generated caches.

Each archived run remains separate. Scores from different protocol revisions are not pooled as repeats. TF/PE means use valid score pairs and show denominators; missing values are not replaced with zero. Paired ECS uses task/repeat identities valid across all stages and all strategies present in that run, with population SD, independently checked against the frozen upstream implementation. Completed trajectories can still have incomplete judge slots. Saved judge means are checked where slot results expose numeric scores.

Recovery/retention outputs currently use absolute TF differences versus No Update at the same task, stage and repeat, using Role 3's provisional core labels. Normalized recovery and harm thresholds remain unimplemented until the group freezes them. Unknown extension labels remain unknown. Update costs are counted once per episode transition; historical missing usage is unavailable, not zero. The current Full Rewrite baseline rebuilds from the catalog without model requests, so an assumed LLM rewrite cost is inappropriate.

At base commit `291e1e998c7e81fa369cd195e3180cc9465764bd`, the seven archived runs contain 240 planned trajectories, 156 with valid TF/PE pairs, and 748 completed judge slots out of 1,200 planned. These are archive inventory totals, not a pooled performance estimate. See [diagnostic cases](DIAGNOSTIC_CASES.md) for evidence-review examples. Formal completion awaits a frozen task subset, Selective Patch integration, a clean-source formal run and causal under-update/over-update examples.

中文：本工具供 Role 4 离线整理试跑记录，不调用模型、不改原始数据。先在仓库根目录运行上面的命令，再打开 `.runtime/role4-analysis/ROLE4_REVIEW.html`。各运行独立分析；有效评分次数、缺失和配对样本数均明确记录。当前成果是试跑分析，不能替代正式三策略比较。
