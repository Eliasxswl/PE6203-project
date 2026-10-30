# Report: Tool Harness Adaptation under Environment Change

Assignment report for Group Project 4. Repository entry point: [README.md](README.md). Evidence paths point into `results/20261026T084527.010290Z_Kevin`. Every figure below is recomputed from that run's `records.json` and `experiment.json`; if this document and the manifest ever disagree, the manifest wins.

## 1. Problem

An agent that schedules MCP tools carries knowledge about those tools — names, descriptions, argument schemas, and practical notes on how to use them. The MCPEvol-Bench environment evolves the servers through successive mutation rounds, so that knowledge goes stale. The benchmark's question is whether an agent can keep itself functional across such changes.

Three responses are compared. **No Update** keeps the original knowledge and absorbs the drift. **Full Rewrite** regenerates everything from the current catalog. **Selective Patch** updates only what the change detector says changed. The research question is whether selective updating preserves performance on changed tasks without damaging tasks that did not change, and at what update cost.

The two questions are separable and are reported separately throughout: **recovery** on tasks whose required tools changed, and **retention** on tasks that should remain solvable.

## 2. Setup and method

| Item | Value |
|---|---|
| Benchmark | MCPEvol-Bench, fork pinned at `888c779` |
| Frozen subset | 17 tasks, SHA-256 `fb5887bc…`, from 201 candidates |
| Stages | Early `original`, Middle `iter3`, Late `iter5` |
| Strategies | `no_update`, `full_rewrite`, `selective_patch` |
| Actor model | `glm-4-flash-250414`, temperature 0.2, 8192 max tokens |
| Judge model | unset in the profile, so it resolves to the Actor model; temperature 0, 5 attempts per trajectory |
| Knowledge updater | `openai/gpt-6-luna`, used only by Full Rewrite and Selective Patch |
| Repeats | 3 Agent repeats per task/stage |
| Scale | 459 logical conditions = 357 actual executions + 102 shared Early references; 1,785 planned Judge slots; 457 scored, 2 `execution_failed` |
| Environment | Windows 11, Python 3.12.14, Node v24.21.0 |

### 2.1 How the subset was chosen

> From the 201 candidate tasks, a task enters the frozen subset only if it completes on all three stages in live mode without environment or network failure, and its required tools show a verifiable `tools/list` difference at at least one stage or, for controls, no difference at any stage. Labels come from those diffs alone. No task is replaced after the freeze.

25 of 201 candidates were runnable under this gate. All 4 runnable tasks with a changed required tool were taken (9, 24, 117, 416), and 13 runnable tasks with no change at any stage were taken as retention controls, giving 17. Upstream mutation records were deliberately not used as a labelling source, because they do not match the snapshots.

### 2.2 What the three strategies actually differ in

Knowledge has two layers: **catalog knowledge** (`server::tool` → name, description, `inputSchema`, derived deterministically from `tools/list`) and an **experience layer** (operational notes written by the updater model).

Full Rewrite and Selective Patch hold **byte-identical catalog knowledge** — `knowledge_sha256` is equal in all 153 strategy pairs of the run, because both derive it from the same stage catalog. The experience layer differs: `experience_state_sha256` differs in 102 of 153 pairs, because Full Rewrite rewrites every entry and Selective Patch rewrites only entries tied to changed tools. **The experiment therefore compares two experience-layer update policies, not two catalog-knowledge policies.**

### 2.3 The Selective Patch algorithm

1. Diff `previous_catalog` against `current_catalog` at the tool level, then field by field (recursive equality on nested schema values, no embedding threshold). Each affected tool gets a type: added, removed, description change, parameter change, or mixed.
2. Patch every differing field into the catalog record. Unchanged fields are not touched. Because the patch is exhaustive over catalog fields, **it cannot omit a change by construction**.
3. Select experience entries whose referenced tools (`tool_ids`) intersect the affected set, and rewrite only those.

Step 3 is where selectivity is real, and where its weakness is: an entry references several tools and is rewritten if **any** of them changed, so an unchanged tool that shares an entry with a changed tool is rewritten anyway. Selective updating is therefore at entry granularity, not tool granularity.

**On the updater model.** The assignment fixes the base model, decoding and the Judge across strategies, and those are fixed: one Actor model and one Judge model for all three strategies, identical prompts and temperatures. The knowledge updater is a separate component of the adaptation method, not of the Agent — it stands in for an external service that maintains tool knowledge, which is what the benchmark is about. It is the same model with the same settings for both updating strategies, and `no_update` calls it zero times, so it cannot confound the comparison. It does mean the experience layer is model-generated and not deterministic given the same catalog, so reproducibility relies on the recorded update outputs rather than on re-deriving them.

## 3. Main results

Means over Middle and Late only; Early is executed once and shared, so pooling it would make the No Update row incomparable.

| Strategy | TF | PE | ECS (paired, 49 triples) | ΔTF vs No Update |
|---|---|---|---|---|
| No Update | 8.68 (n=102) | 9.62 | 8.371 | — |
| Full Rewrite | 8.65 (n=101) | 9.71 | 7.939 | −0.01 |
| Selective Patch | 8.99 (n=101) | 9.87 | 8.547 | +0.32 |

Two cells are missing because two trajectories failed to execute (`full_rewrite/iter5/9/0`, `selective_patch/iter5/278/0`).

## 4. Recovery and retention

Paired TF change against No Update at the same task and repeat, computed by the pipeline per transition. No Update is the zero reference.

| Transition | Cohort | Matched | Full Rewrite | Selective Patch |
|---|---|---|---|---|
| Early→Middle | Changed, 4 tasks (recovery) | 12 | +2.17 | +1.52 |
| Early→Middle | Retention, 13 tasks | 39 | +0.02 | +0.36 |
| Middle→Late | Changed, 4 tasks (recovery) | 11 | +1.62 | +0.96 |
| Middle→Late | Retention, 13 tasks | 38 | −1.21 | −0.27 |

Both strategies recover on changed tasks and Full Rewrite recovers more — roughly a third more at each transition. The difference is cost to untouched tasks: Full Rewrite is neutral at Middle and loses 1.21 TF at Late; Selective Patch loses 0.27. **Selective Patch's claim is therefore "recovers less but damages less", not "recovers more without damage"** — the retention column is where the trade-off shows, and Selective Patch is not without loss.

## 5. Update cost

Totals over the two transitions per strategy — per episode, not per trajectory.

| Strategy | Updater calls | Tokens in / out | Wall-clock | Cost |
|---|---|---|---|---|
| No Update | 0 | 0 / 0 | 0.0 s | $0.00 |
| Full Rewrite | 42 | 132,853 / 14,955 | 229.4 s | $0.0182 |
| Selective Patch | 12 | 30,041 / 3,944 | 76.3 s | $0.0042 |

Selective Patch issues 29% of Full Rewrite's calls at 23% of its cost. Dollar amounts are what the provider reported per update request (manifest basis: "Provider-reported update request costs"), not estimates from a price table. No pricing date is recorded with the run, so the figures cannot be re-priced against a later tariff; token and call counts are exact.

## 6. Failure analysis

Definitions are fixed before the run: **F1 under-update** — a changed required tool's knowledge is not updated and the task fails; **F2 over-update** — an unchanged tool's knowledge is modified and the paired No Update trajectory drops by at least 2.0 TF.

### 6.1 F1: under-update, and why it is a No Update failure

Task 416's required tool gains `splitDetails`, `priority` and `tags` at the stage. No Update's Agent-visible prompt contains those names 0 times; Full Rewrite's contains 3 / 4 / 4. Scores: No Update 1.0 / 1.0 / 1.0 at Middle and Late; Full Rewrite 7.6 / 8.8 / 1.6 then 10.0 / 10.0 / 1.0; Selective Patch 2.0 / 4.6 / 3.6 then 5.8 / 4.6 / 5.8. The Judge records 0 of 6 requirements met and a 100% defect rate.

**This trajectory is No Update's, and that is deliberate.** Selective Patch cannot under-update by construction (§2.3, step 2): it writes every differing catalog field, so an omitted argument cannot arise from it. The F1 category is therefore represented by the baseline, which is the only strategy that can exhibit it. Presenting a Selective Patch trajectory as an under-update would misdescribe the implementation.

What Selective Patch does instead is fail to *recover fully*. On the task where No Update stays at 1.0, Selective Patch reaches 5.8 / 4.6 / 5.8 at Late and Full Rewrite 10.0 / 10.0 / 1.0, despite both holding the identical updated catalog — so the residual gap lives in the experience layer, and per-repeat variance is large for both. **Partial recovery is Selective Patch's counterpart failure mode**, and it is reported as such rather than dressed up as under-update. See [docs/case-under-update.md](docs/case-under-update.md).

| Failure class | No Update | Full Rewrite | Selective Patch |
|---|---|---|---|
| F1 under-update | inherent (Task 416) | none observed | structurally impossible |
| F2 over-update | n/a (nothing rewritten) | 7 literal trajectories + Task 9 controlled test | 3 literal trajectories |
| Partial recovery | n/a | present, high variance | present (Task 416) |

### 6.2 F2: over-update

**Full Rewrite — seven literal F2 trajectories**, four of them 10.0 → 1.0: `iter5/389/0`, `iter5/403/0`, `iter5/410/1`, `iter5/278/2`, plus `iter5/274/2` (6.4 → 1.5), `iter3/394/2` (10.0 → 7.0), `iter5/394/2` (10.0 → 7.6). The controlled confirmation is the Task 9 comparison: restoring five records that were rewritten although their tools did not change moves the score from 3/10 to 10/10 (exact paired p = 0.0156), while an equal-length key-order control scores 0/10.

**Selective Patch — three literal F2 trajectories**, same screen: `iter5/389/0` (10.0 → 1.0), `iter5/274/0` (10.0 → 7.0), `iter3/274/2` (10.0 → 7.6). The catastrophic case is traced end to end: Selective Patch's guidance for unchanged tools differs from No Update's ("use 'get_next_task' with the correct 'requestId'" became "register a request with … required tags"), and the run ends in a `minLength` schema rejection on `initialConcept` with 0 of 4 requirements met. Entry bundling (§2.3, step 3) is why a selective policy still damages unchanged tools. See [docs/case-sp-over-update.md](docs/case-sp-over-update.md).

A fourth Selective Patch case on a changed tool, task 117 at Late repeat 1, scores 2.0 where its siblings score 10.0 and 9.0; the Judge attributes it directly: "the agent attempted to plan the tasks but encountered a schema error due to the inclusion of 'tags' in the input." Updated knowledge supplying an argument the schema rejects is the same damage direction.

All of these are mechanism-identified from run records and code; only the Task 9 test is counterfactually confirmed.

## 7. Discussion

**When selective patching helps.** Both updating strategies recover on changed tasks because both hold current catalog knowledge — a gain No Update does not have. Selective Patch does not recover more than Full Rewrite; it recovers about two thirds as much (+1.52 against +2.17 at Middle, +0.96 against +1.62 at Late) while leaving most untouched-tool experience entries alone and spending a quarter of the update cost. Its advantage is therefore in what it does *not* touch, not in what it repairs.

**When it fails.** Three ways, none of them omission: entry-level over-update (Task 389), partial recovery despite an updated catalog (Task 416), and, on a changed tool, updated knowledge that pushes the Agent into an invalid call (Task 117). Over-update is real but rarer than Full Rewrite's — 3 literal F2 trajectories against 7.

**Which change type is hardest.** Not answerable with this subset. All four changed tasks change Description and Parameter jointly; Tool-level change appears only as added tools. **Tool rename, tool removal, Parameter-only and Description-only changes were not tested**, because no selected task contains them, and the candidates that would (72, 90, 430) launch external services that the reviewed isolation gate rejects. This is a scope limit, not a result.

**Statistical strength.** Paired bootstrap, 20,000 resamples:

| Comparison | Δ | 95% CI | Separable from zero |
|---|---|---|---|
| Selective Patch − No Update, TF | +0.32 | [−0.09, +0.74] | No |
| Full Rewrite − No Update, TF | −0.01 | [−0.53, +0.51] | No |
| Selective Patch − No Update, ECS | +0.18 | [−0.29, +0.67] | No |
| Full Rewrite − No Update, ECS | −0.43 | [−1.07, +0.17] | No |
| Selective Patch − Full Rewrite, ECS | +0.61 | [+0.00, +1.27] | Marginal |

**Neither strategy is demonstrably better than No Update.** With task 416 excluded, SP − NU falls to +0.03 [−0.42, +0.52] and FR − NU becomes −0.65 [−1.27, −0.12], separable on the wrong side. Only the Selective Patch − Full Rewrite ordering survives every exclusion (+0.61, +0.68, +0.61). "Selective Patch beats No Update" must therefore not be claimed; "Selective Patch beats Full Rewrite" is descriptive and survives, though close to its lower bound.

**One earlier anomaly, now resolved.** On the two tool-addition tasks at Late, a preliminary average had Selective Patch at 8.50 against No Update's 9.93 (n=6). Inspecting the six trajectories per strategy: task 24 is 10.0 / 10.0 / 10.0 for all three strategies, and task 117 is 9.8 / 9.8 / 10.0 for No Update, 10.0 / 9.4 / 9.4 for Full Rewrite, and 10.0 / 2.0 / 9.0 for Selective Patch. The whole gap is one trajectory — the task 117 over-update case in §6.2. Dropping it, Selective Patch averages 9.8. There is no systematic weakness on tool-addition tasks; the number was an artifact of a single damaged run.

## 8. Limitations

- **Ceiling effect.** No Update already scores 8.68 TF and 9.62 PE, so mean-level headroom is about one point; a real effect on a handful of tasks is invisible in pooled means. All comparisons here are paired per cell for that reason.
- **Same model as Actor and Judge.** `judge_model` is empty in the profile and resolves to the Actor model. Five Judge attempts reduce sampling noise, not a bias shared between generator and scorer, so scores are an internally consistent ranking rather than an absolute capability measure.
- **Sample size.** 4 changed tasks, 11–12 paired cells per transition, 3 repeats. Recovery figures describe this frozen subset and do not estimate a benchmark-level rate. The over-update evidence is largely single trajectories, with one controlled test (Task 9).
- **Untested change levels.** Tool rename/removal and single-level Parameter or Description changes, as in §7.
- **Provenance.** The retained run is `dirty_source: True` at revision `d7ddd29` and cannot be rebuilt exactly from a commit; archive SHA-256 values were computed after the run and are therefore not bound to it ([docs/bundle-checksums.md](docs/bundle-checksums.md)); costs carry no pricing date. All three are disclosed rather than repaired.
- **Platform.** All strategies ran on Windows 11; upstream ran Linux, and macOS/Linux tool-runtime validation is pending, so cross-platform equivalence is assumed.

## 9. Conclusion

The comparison supports three claims and refuses two.

Supported: (1) **stale knowledge is genuinely costly** — No Update scores 1.0 on every repeat of task 416 while both updating strategies recover partially or fully; (2) **Full Rewrite damages retention** — it loses 1.21 TF on unchanged tasks at Late and is the only strategy whose ECS is separable from No Update in the wrong direction once task 416 is excluded; (3) **selective updating reaches comparable recovery at a fraction of the cost** — 29% of the calls and 23% of the spend, with a retention loss roughly four times smaller than Full Rewrite's at Late.

Refused: (4) selective patching is not shown to beat No Update (Δ ECS +0.18, CI [−0.29, +0.67], and most of that edge disappears without task 416); (5) no ranking of change types is possible, because the subset contains no single-level or tool-removal change.

What the project contributes is therefore a fair, fully paired three-strategy harness with the two knowledge layers separated and measured independently, a negative but robust result about Full Rewrite, a cost accounting, and a failure taxonomy that distinguishes under-update, over-update and partial recovery — with the first of those shown to belong exclusively to the baseline by construction.

## Appendix: anticipated questions

**Doesn't the knowledge updater change the "fixed base model" requirement?** No. The fixed pair is Actor and Judge, and those are identical across all three strategies. The updater is part of the adaptation method being compared, is the same model for both updating strategies, and is never called by No Update, so it cannot differ across strategies. The cost is that the experience layer is model-generated, which is why update outputs are recorded rather than re-derived.

**If Selective Patch is not significantly better than No Update, what is the contribution?** The robust result is the ordering against Full Rewrite, which survives every exclusion. The contribution is the design that makes the comparison fair (identical catalog knowledge, paired cells, separated cohorts), the negative finding that Full Rewrite costs retention, and the cost accounting. Claiming superiority over No Update would be overstating a result that one task carries.

**Why only four changed tasks?** 201 candidates reduce to 25 runnable under the reviewed isolation gate, and all four with a changed required tool were taken. The rest either fail the gate or need catalogs that were never captured. Adding tasks by relabelling would have manufactured labels that the underlying diffs do not support.

**Why is the Judge the same model as the Actor?** `judge_model` is empty in the profile and resolves to the Actor model, which is disclosed as a bias risk in §8. Five attempts per trajectory reduce sampling noise only. The scores are used for within-run comparisons, which is what the paired design requires, not as absolute capability measures.

**Can Selective Patch under-update?** Not by construction — it writes every differing catalog field. Its counterpart failure is partial recovery, shown in §6.1.
