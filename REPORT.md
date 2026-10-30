# Report: Tool Harness Adaptation under Environment Change

Assignment report for Group Project 4. Repository entry point: [README.md](README.md). Evidence paths point into `results/20261026T084527.010290Z_Kevin`. Every figure below is recomputed from that run's `records.json` and `experiment.json`; if this document and the manifest ever disagree, the manifest wins.

## 1. Setup

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

**On the updater model.** The assignment fixes the base model, decoding and the Judge across strategies, and those are fixed: one Actor model and one Judge model for all three strategies, identical prompts and temperatures. The knowledge updater is a separate component of the adaptation method, not of the Agent — it plays the role of an external service that maintains tool knowledge, which is what the benchmark is about. It is the same model with the same settings for both updating strategies, and `no_update` calls it zero times, so it cannot confound the comparison. It does mean the experience layer is model-generated and not deterministic given the same catalog, so reproducibility relies on the recorded update outputs rather than on re-deriving them.

## 2. Main results

Means over Middle and Late only; Early is executed once and shared, so pooling it would make the No Update row incomparable.

| Strategy | TF | PE | ECS (paired, 49 triples) | ΔTF vs No Update |
|---|---|---|---|---|
| No Update | 8.68 (n=102) | 9.62 | 8.371 | — |
| Full Rewrite | 8.65 (n=101) | 9.71 | 7.939 | −0.01 |
| Selective Patch | 8.99 (n=101) | 9.87 | 8.547 | +0.32 |

Two cells are missing because two trajectories failed to execute (`full_rewrite/iter5/9/0`, `selective_patch/iter5/278/0`).

**What the comparison actually tests.** Full Rewrite and Selective Patch hold byte-identical catalog knowledge: `knowledge_sha256` is equal in all 153 strategy pairs. Both derive it from the same stage catalog, so the catalog layer cannot explain any difference. The experience layer does differ — `experience_state_sha256` differs in 102 of 153 pairs, because Full Rewrite rewrites every entry and Selective Patch rewrites only entries tied to changed tools. **The experiment therefore compares two experience-layer update policies, not two catalog-knowledge policies.**

## 3. Recovery and retention

Paired TF change against No Update at the same task and repeat, computed by the pipeline per transition. No Update is the zero reference.

| Transition | Cohort | Matched | Full Rewrite | Selective Patch |
|---|---|---|---|---|
| Early→Middle | Changed, 4 tasks (recovery) | 12 | +2.17 | +1.52 |
| Early→Middle | Retention, 13 tasks | 39 | +0.02 | +0.36 |
| Middle→Late | Changed, 4 tasks (recovery) | 11 | +1.62 | +0.96 |
| Middle→Late | Retention, 13 tasks | 38 | −1.21 | −0.27 |

Both strategies recover on changed tasks and Full Rewrite recovers more. The difference is cost to untouched tasks: Full Rewrite is neutral at Middle and loses 1.21 TF at Late; Selective Patch loses 0.27. **Selective Patch's claim is therefore "recovers less but damages less", not "recovers more without damage"** — the retention column is where the trade-off shows, and Selective Patch is not without loss.

## 4. Update cost

Totals over the two transitions per strategy — per episode, not per trajectory.

| Strategy | Updater calls | Tokens in / out | Wall-clock | Cost |
|---|---|---|---|---|
| No Update | 0 | 0 / 0 | 0.0 s | $0.00 |
| Full Rewrite | 42 | 132,853 / 14,955 | 229.4 s | $0.0182 |
| Selective Patch | 12 | 30,041 / 3,944 | 76.3 s | $0.0042 |

Selective Patch issues 29% of Full Rewrite's calls at 23% of its cost. Dollar amounts are what the provider reported per update request (manifest basis: "Provider-reported update request costs"), not estimates from a price table. No pricing date is recorded with the run, so the figures cannot be re-priced against a later tariff; token and call counts are exact.

## 5. Failure analysis

Definitions are fixed before the run: **F1 under-update** — a changed required tool's knowledge is not updated and the task fails; **F2 over-update** — an unchanged tool's knowledge is modified and the paired No Update trajectory drops by at least 2.0 TF.

### F1: under-update, Task 416 (No Update, Late)

Task 416's required tool gains `splitDetails`, `priority` and `tags` at the stage. No Update's Agent-visible prompt contains those names 0 times; Full Rewrite's contains 3 / 4 / 4. Scores: No Update 1.0 / 1.0 / 1.0 at Middle and Late; Full Rewrite 7.6 / 8.8 / 1.6 then 10.0 / 10.0 / 1.0; Selective Patch 2.0 / 4.6 / 3.6 then 5.8 / 4.6 / 5.8. The Judge records 0 of 6 requirements met and a 100% defect rate.

Two points must be stated plainly. First, **this trajectory belongs to No Update, not to Selective Patch** — the patch writes every differing catalog value, so an omitted argument cannot arise from it by construction, and the case is presented as the baseline failure F1 targets. Second, with catalog knowledge fully updated, both updating strategies still recover only partially and with high variance on this task, so updated knowledge is necessary but not sufficient. Selective Patch's failure mode here is *partial recovery*, not under-update. See [docs/case-under-update.md](docs/case-under-update.md).

### F2: over-update

**Full Rewrite — seven literal F2 trajectories**, four of them 10.0 → 1.0: `iter5/389/0`, `iter5/403/0`, `iter5/410/1`, `iter5/278/2`, plus `iter5/274/2` (6.4 → 1.5), `iter3/394/2` (10.0 → 7.0), `iter5/394/2` (10.0 → 7.6). The controlled confirmation is the Task 9 comparison: restoring five records that were rewritten although their tools did not change moves the score from 3/10 to 10/10 (exact paired p = 0.0156), while an equal-length key-order control scores 0/10.

**Selective Patch — three literal F2 trajectories**, same screen: `iter5/389/0` (10.0 → 1.0), `iter5/274/0` (10.0 → 7.0), `iter3/274/2` (10.0 → 7.6). The catastrophic case is traced end to end: Selective Patch's guidance for unchanged tools differs from No Update's ("use 'get_next_task' with the correct 'requestId'" became "register a request with … required tags"), and the run ends in a `minLength` schema rejection on `initialConcept` with 0 of 4 requirements met. The reason such damage is possible at all is that selection is **per experience entry, not per tool**: an entry references several tools and is rewritten if any of them changed, so unchanged siblings are rewritten with it. See [docs/case-sp-over-update.md](docs/case-sp-over-update.md).

All of these are mechanism-identified from run records and code, not counterfactually confirmed except the Task 9 test.

## 6. Discussion

**When selective patching helps.** Both updating strategies recover on changed tasks because both hold current catalog knowledge — a gain No Update does not have. Selective Patch does not recover more than Full Rewrite; its advantage is similar recovery at a quarter of the update cost while leaving most untouched-tool experience entries alone.

**When it fails.** Not by omitting catalog changes — its diff is exhaustive — but by entry-level over-update, as in Task 389. Selective Patch's over-update surface is smaller than Full Rewrite's (3 versus 7 literal F2 trajectories) and is not zero.

**Which change type is hardest.** Not answerable with this subset. All four changed tasks change Description and Parameter jointly; Tool-level change appears only as added tools. **Tool rename, tool removal, Parameter-only and Description-only changes were not tested**, because no selected task contains them, and the candidates that would (72, 90, 430) launch external services that the reviewed isolation gate rejects. This is a scope limit, not a result.

**Statistical strength.** Paired bootstrap, 20,000 resamples:

| Comparison | Δ | 95% CI | Separable from zero |
|---|---|---|---|
| Selective Patch − No Update, TF | +0.32 | [−0.09, +0.74] | No |
| Full Rewrite − No Update, TF | −0.01 | [−0.53, +0.51] | No |
| Selective Patch − No Update, ECS | +0.18 | [−0.29, +0.67] | No |
| Full Rewrite − No Update, ECS | −0.43 | [−1.07, +0.17] | No |
| Selective Patch − Full Rewrite, ECS | +0.61 | [+0.00, +1.27] | Marginal |

**Neither strategy is demonstrably better than No Update.** With task 416 excluded, SP − NU falls to +0.03 [−0.42, +0.52] and FR − NU becomes −0.65 [−1.27, −0.12], separable on the wrong side. Only the Selective Patch − Full Rewrite ordering survives every exclusion (+0.61, +0.68, +0.61). "Selective Patch beats No Update" must therefore not be claimed; "Selective Patch beats Full Rewrite" is descriptive and survives, though it is close to its lower bound.

## 7. Limitations

- **Ceiling effect.** No Update already scores 8.68 TF and 9.62 PE, so mean-level headroom is about one point; a real effect on a handful of tasks is invisible in pooled means. That is why all comparisons here are paired per cell, and why the cohort split carries the argument.
- **Same model as Actor and Judge.** `judge_model` is empty in the profile and resolves to the Actor model. Five Judge attempts reduce sampling noise, not a bias shared between generator and scorer, so scores are an internally consistent ranking rather than an absolute capability measure.
- **Sample size.** 4 changed tasks, 11–12 paired cells per transition, 3 repeats. Recovery figures describe this frozen subset and do not estimate a benchmark-level rate. The over-update evidence is largely single trajectories, with one controlled test (Task 9).
- **Untested change levels.** Tool rename/removal and single-level Parameter or Description changes, as above.
- **Provenance.** The retained run is `dirty_source: True` at revision `d7ddd29` and cannot be rebuilt exactly from a commit; archive SHA-256 values were computed after the run and are therefore not bound to it ([docs/bundle-checksums.md](docs/bundle-checksums.md)); costs have no pricing date. All three are disclosed rather than repaired.
- **Platform.** All strategies ran on Windows 11; upstream ran Linux, and macOS/Linux tool-runtime validation is pending, so cross-platform equivalence is assumed.
- **One unexplained observation.** On the two tool-addition tasks at Late, Selective Patch averages 8.50 against No Update's 9.93 (n=6). Recorded as an observation, not a finding.
