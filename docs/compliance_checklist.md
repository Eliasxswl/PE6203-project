# Assignment Compliance Checklist (v0.5, 2026-10-29)

Status: **Met** / **Partial** / **Not met** / **Pending** (owned by another role). Evidence paths refer to the team fork `Eliasxswl/PE6203-project`.

Referenced runs: `results/20261026T084527.010290Z_Kevin` (formal three-strategy comparison, 17 tasks, 3 repeats), `results/20261019T234451.269257Z_Kevin` (catalog baseline), `results/20261029T113248.805747Z_Kevin` (Task 9 confirmation case).

v0.5 changes: statuses re-verified against the formal run and the Task 9 case. Eight rows move from Partial/Pending to Met (#1, #5, #7, #8, #10, #11, #13, #18). New rows #24 (stratified metrics), #25 (failure-case resolve), #26 (pricing basis). Three residual gaps are now isolated and named: clean-source rerun (#14), bundle checksums (#22), pricing date (#26).

## Requirement status

| # | Requirement (assignment) | Status | Evidence / action |
|---|---|---|---|
| 1 | Three strategies compared: no update, full rewrite, selective patch | **Met** | `settings.strategies` lists all three; `strategy_plugins: ["custom.experiment.selective_patch"]`; all three executed on all three stages in `20261026T084527`. |
| 2 | Base model, decoding and judge fixed across strategies | **Met** | One model `glm-4-flash-250414` for Agent and judge (`judge_model: ""` resolves to Agent model); temperatures 0.2/0, 8192 tokens, 5 judge attempts; identical in every strategy row of the run. |
| 3 | No fine-tuning; no benchmark label changes | **Met** | No training code or weights in the repo; `src/custom/data/test_cases/test_cases.json` hash `1370d7f9...` recorded in `fingerprints.sources`; reference answers excluded from Agent input. |
| 4 | MCPEvol-Bench; fixed documented subset, same for all strategies | **Met** | `config/subsets/selected_tasks.json`, SHA-256 `fb5887bc21829ab3a8c7b4da553cde1d75a2b79b016a23278106051b23368a07`, recorded in `fingerprints.sources` and identical across all strategies; `task_count: 17`. |
| 5 | Early, Middle, Late evaluated | **Met** | `stages: ["original","iter3","iter5"]`; 357 actual executions plus 102 shared Early references; 459 logical conditions. |
| 6 | Tool-, Parameter-, Description-level changes in selected tasks | **Partial** | Live catalogs: Description+Parameter on required tools in 9/24/117/416 (117 Description-only at Middle); Tool-level appears only as added tools (24, 117). **Not assessed:** tool rename, tool removal, Parameter-only and Description-only. Detail and reasons in `docs/subset-coverage.md`; removal candidates 72/90/430 are rejected by the reviewed gate, so the gap is not closable by relabelling. |
| 7 | Three runs preferred; single run must be stated | **Met** | `settings.agent_repeats: 3`; three independent Agent repeats per strategy/stage/task. The report may therefore state mean/interval rather than "single run". |
| 8 | Report TF, PE, ECS for method and both baselines | **Met** | `aggregate.paired_ecs` over 49 matched task/repeat triples: Selective Patch 8.547, No Update 8.371, Full Rewrite 7.939. Per-stage TF/PE in #24. |
| 9 | Recovery and retention analysis | **Met** | `aggregate.recovery_retention` uses confirmed labels relative to Early and same-version paired TF against No Update; per-transition and per-cohort values recorded. Imbalance 4 changed vs 13 controls reported. |
| 10 | Update cost per strategy | **Met** | `aggregate.update_costs`: No Update 0 calls / $0.00; Selective Patch 12 calls / $0.0042; Full Rewrite 42 calls / $0.0182 (USD). Counted once per episode transition, separated from evaluation cost. |
| 11 | Failure analysis: ≥2 types, ≥1 trajectory each | **Met** | F1 (under-update) documented in `docs/case-under-update.md` (Task 416, TF 1.0 against 10.0 after update). F2 (over-update) populated by seven Full Rewrite retention trajectories meeting the literal criterion, four of them 10.0 → 1.0, plus the Task 9 controlled test (3/10 → 10/10 after restoring five rewritten-but-unchanged records; exact paired p = 0.0156). See #25. |
| 12 | Discussion: when patching helps/fails, hardest change type | **Partial** | Inputs now complete (#24, #25). Narrative ownership is Role 5. Hardest-type statement must be phrased as "no Tool-only case exists in the frozen subset", not as a measured ranking. |
| 13 | Codebase: pipeline, own selective method, two baselines | **Met** | `custom.experiment` pipeline; baselines `no_update` and `full_rewrite`; own method `custom.experiment.selective_patch` plus the strategy-owned experience layer in `experience_state.py`; offline suite in `tests/`. |
| 14 | Reproduction material: configs, commands, raw logs | **Partial** | Manifests, raw records, source ZIP and prompt hashes are retained per run. **Residual gap:** the formal run is `dirty_source: True` at revision `d7ddd29`. A clean-commit rerun, or an explicit disclosure in the report, remains required. |
| 15 | 10-min presentation + 5-min Q&A | **Pending** | Whole group. |
| 16 | Judge validity concern documented | **Partial** | Same model acts as Actor and Judge; five Judge attempts reduce sampling noise but not shared-model bias. Disclosed in README "Provenance status" and protocol §10; the Task-117 audit (high TF with missing steps) stands as the concrete symptom. |
| 17 | Preflight before subset freeze | **Met (as run)** | 17 selected tasks passed the applicable preflight checks; steps 1–3 of protocol §8 executed before freeze; non-runnable candidates recorded with causes and never replaced. |
| 18 | Same OS/environment type for all strategies | **Met** | All strategies ran inside one manifest: Windows 11, Python 3.12.14, Node v24.21.0 (`experiment.json` → `environment`). Upstream ran Linux; state this difference in the report. |
| 19 | Compute plan and key usage | **Met** | Per-account concurrency 1 in the formal profile; providers declared by environment-variable name and quota group; keys never written into records or documents. |
| 20 | Change types verified against real catalogs | **Met** | All 17 core-task labels re-derived from live `tools/list` diffs on 2026-10-17; upstream mutation records explicitly rejected as a labelling source. |
| 21 | Early/Middle/Late mapping verified against primary sources | **Met** | Paper arXiv:2607.14642v1 §5.2 and Table 3 caption; upstream README at `888c779`; protocol §2.1–§2.2. |
| 22 | Stage bundles available and pinned | **Partial** | Archives present locally (3,395,494,138 B total) and their SHA-256 values are now recorded in `docs/bundle-checksums.md`. **Residual gap:** the formal manifest still records `tool_bundles: missing`, so the hashes are not bound to the run; capture them at run time in the next run. |
| 23 | Extension tasks (8 runnable but catalog-uncaptured) | **Not met (by scope)** | Deliberately excluded from the frozen 17-task core; documented as a coverage gap (#6). No post-freeze replacement. |
| 24 | (new) Metrics reported separately by change type | **Met** | Stratified TF/PE table below, computed from the formal run. |
| 25 | (new) Over-update criterion put under a controlled test | **Met** | `results/20261029T113248.805747Z_Kevin/task-9-confirmation-review.json`: 10 groups × 3 conditions, 30 executions, no Judge or updater calls, 0 infrastructure failures. |
| 26 | (new) Update cost carries a pricing basis and date | **Not met** | Price ceilings (`prompt_usd_per_million: 0.1`) are configured but neither a pricing date nor a provider price-version is recorded with the run. Token and call counts are exact; dollar values are estimates. |
| 27 | (new) Statistical inference reported alongside point estimates | **Met** | Paired bootstrap, 20,000 resamples, seed 20261029, in README "Statistical evidence". Only Selective Patch − Full Rewrite on ECS separates from zero (+0.61, CI [+0.00, +1.27]); Selective Patch − No Update (+0.18, CI [−0.29, +0.67]) and Full Rewrite − No Update (−0.43, CI [−1.07, +0.17]) do not. The report must not claim either strategy beats No Update. |

## Stratified metrics by change type (#24)

Computed from `results/20261026T084527.010290Z_Kevin/records.json`; cells are `TF / PE` with `n` in parentheses. Early is executed once and shared by all three strategies, so it has a single column.

| Change group | Stage | No Update | Full Rewrite | Selective Patch |
|---|---|---|---|---|
| Description+Parameter, 4 tasks (9, 24, 117, 416) | Early | 8.67 / 10.00 (12) | shared | shared |
| | Middle | 6.83 / 8.68 (12) | 9.00 / 9.98 (12) | 8.35 / 10.00 (12) |
| | Late | 7.22 / 9.21 (12) | 8.58 / 9.33 (11) | 8.10 / 9.60 (12) |
| Tool addition only, 2 tasks (24, 117) | Early | 9.80 / 10.00 (6) | shared | shared |
| | Middle | 10.00 / 10.00 (6) | 10.00 / 10.00 (6) | 10.00 / 10.00 (6) |
| | Late | 9.93 / 10.00 (6) | 9.80 / 10.00 (6) | 8.50 / 9.19 (6) |
| Retention control, 13 tasks | Early | 9.90 / 9.98 (39) | shared | shared |
| | Middle | 9.05 / 9.68 (39) | 9.07 / 9.88 (39) | 9.41 / 10.00 (39) |
| | Late | 9.32 / 9.99 (39) | 8.14 / 9.57 (39) | 9.03 / 9.79 (38) |

Reading notes: the changed cohort is Description+Parameter jointly, so no Parameter-only, Description-only or Tool-only row can be reported (#6). Missing cells are execution failures, not zero scores: `full_rewrite/iter5/9/0` and `selective_patch/iter5/278/0`.

## Three residual gaps

| Gap | Why it blocks a "Met" | Cheapest honest fix |
|---|---|---|
| #14 `dirty_source: True` | Assignment asks for reproducible material; a dirty-source run cannot be rebuilt from a commit | Clean-commit rerun with identical settings, or a first-page disclosure naming revision `d7ddd29` and the uncommitted delta |
| #22 bundle checksums missing | Archive identity is unbound to the run, so extraction equivalence cannot be audited | Record SHA-256 of the three zips plus an extracted-tree manifest into the run manifest |
| #26 no pricing date | Cost figures cannot be re-priced or checked against the provider's price history | Record pricing date and model/price-version alongside `update_costs` |

Non-closable within this project: #6 Tool-level coverage and #23 extension tasks. Both require catalog capture for servers outside the reviewed gate, or benchmark content the gate rejects. They must be reported as scope limits, not as results.

## Open items for Role 3

1. Keep this table current through the report freeze; re-verify after any rerun.
2. Hand #24 and #25 to Role 5 as the quantitative base for discussion sections D1–D3.
3. Obtain Role 2 evidence for #22 and the pricing date for #26 before submission.
