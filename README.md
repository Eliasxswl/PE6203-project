# PE6203 Project 4

Compare **No Update**, **Full Rewrite**, and **Selective Patch** under tool evolution.
Forked from [Octobrist/MCPEvol-Bench](https://github.com/Octobrist/MCPEvol-Bench) at `888c779a0fe735f612ca62bdd1fdd7c9e6bf8701`; see its [original README](https://github.com/Octobrist/MCPEvol-Bench/blob/888c779a0fe735f612ca62bdd1fdd7c9e6bf8701/README.md).

## Start

Use Python 3.11+ and Node.js 24. Create a virtual environment with your installed Python command (`python`, `python3`, or Windows `py`). Activate `.venv/Scripts/Activate.ps1` in PowerShell or `source .venv/bin/activate` on macOS/Linux. Then use `python` consistently.

For the current LangChain/knowledge experiment, install the standalone memory environment:

```text
python -m pip install -r requirements-memory.txt
npm install --prefix .runtime @1mcp/agent@0.39.1
```

Copy `.env.example` to `.env`, fill in the credentials referenced by the selected JSON profile, download/extract the three [tool bundles](https://huggingface.co/datasets/anonymous2233/evol-servers/tree/main), and generate local paths with `python scripts/prepare_local_config.py`. Full instructions: [docs/setup.md](docs/setup.md).

```text
python -m custom.experiment validate --config config/knowledge-evolution-formal.json
python -m custom.experiment check --config config/knowledge-evolution-formal.json
python -m custom.experiment run --config config/knowledge-evolution-formal.json --parallel --workers 10
```

The formal knowledge profile uses **17 tasks, three versions, three Agent repeats and five Judge attempts per trajectory**. Shared Early outcomes give 459 logical conditions, 357 actual trajectories and 1,785 planned Judge slots. The catalog-only profile is `config/experiment.json`, using a separate `requirements-api.txt` environment. The upstream full environment remains in `requirements.txt`.

### Reproducing the three strategies

All three strategies live in one frozen profile, `config/knowledge-evolution-formal.json`, whose `strategies` field lists `["no_update","full_rewrite","selective_patch"]`. The strategy is a configuration field, not a CLI flag, so a single command produces the whole comparison and every strategy sees the same tasks, stages, repeats and models:

```text
python -m custom.experiment run --config config/knowledge-evolution-formal.json --parallel --workers 10
```

Each run writes `results/<run-id>/` with its manifest and raw records. The retained formal comparison is `results/20261026T084527.010290Z_Kevin`. Running the strategies as three separate invocations is not needed and would break the matched comparison.

## Main Results

Formal run `20261026T084527.010290Z_Kevin`. Actor and Judge `glm-4-flash-250414`, knowledge updater `openai/gpt-6-luna`, Agent temperature 0.2, 3 repeats, 5 Judge attempts.

| Strategy | TF | PE | ECS | ΔTF vs No Update |
|---|---|---|---|---|
| No Update | 8.68 (n=102) | 9.62 | 8.371 | — |
| Full Rewrite | 8.65 (n=101) | 9.71 | 7.939 | −0.01 |
| Selective Patch | 8.99 (n=101) | 9.87 | 8.547 | +0.32 |

TF and PE are means over Middle and Late only; Early is executed once and shared by all strategies, so pooling it would make the No Update row incomparable. ECS is the paired Evolutionary Competency Score over 49 matched task/repeat triples, using the repository definition (population standard deviation across the three stages). ΔTF is paired against No Update on identical task/stage/repeat cells, not a difference of the column means. Two cells are absent because two trajectories failed to execute (`full_rewrite/iter5/9/0`, `selective_patch/iter5/278/0`).

The pooled means hide the mechanism. Split into the assignment's two questions — recovery on changed tasks, retention on tasks that should stay solvable — the trade-off becomes explicit.

## Recovery and Retention

Paired TF change against No Update at the same task and repeat, relative to the Early reference. These are the pipeline's own `aggregate.recovery_retention` values, computed per transition; No Update is the zero reference by definition.

| Transition | Cohort | Matched | Full Rewrite | Selective Patch |
|---|---|---|---|---|
| Early→Middle | Changed, 4 tasks (recovery) | 12 | +2.17 | +1.52 |
| Early→Middle | Retention, 13 tasks | 39 | +0.02 | +0.36 |
| Middle→Late | Changed, 4 tasks (recovery) | 11 | +1.62 | +0.96 |
| Middle→Late | Retention, 13 tasks | 38 | −1.21 | −0.27 |

Both strategies recover on changed tasks, and Full Rewrite recovers more. The difference is what they do to tasks that did not change. Full Rewrite is neutral at Middle (+0.02) and loses 1.21 TF at Late, where its unnecessary rewrites have accumulated; Selective Patch loses 0.27 in the same transition, roughly four times less. One matched cell is missing at Late for each strategy (`9/0` full rewrite, `278/0` selective patch) because those trajectories failed to execute, so the Late rows use 11 and 38 pairs.

This is the quantity the ECS ordering reflects: Full Rewrite buys a larger recovery and pays a larger retention loss, and the loss outweighs the gain by Late.

## Update Cost

Totals for the two transitions (Early→Middle, Middle→Late) per strategy — per episode, not per trajectory:

| Strategy | Updater calls | Tokens in / out | Wall-clock | Cost |
|---|---|---|---|---|
| No Update | 0 | 0 / 0 | 0.0 s | $0.00 |
| Full Rewrite | 42 | 132,853 / 14,955 | 229.4 s | $0.0182 |
| Selective Patch | 12 | 30,041 / 3,944 | 76.3 s | $0.0042 |

Selective Patch issues 29% of Full Rewrite's calls at 23% of its cost. Figures come from the `aggregate.update_costs` block of the run manifest and use the configured price ceiling in the profile; **no provider pricing date is recorded with the run**, so the dollar values should be read as order-of-magnitude, not as billable amounts.

## Method and subset

- Method: [docs/method.md](docs/method.md) — the two knowledge layers, why Full Rewrite and Selective Patch hold byte-identical catalog knowledge (`knowledge_sha256` equal in 153/153 pairs), and what the comparison therefore does and does not test.
- Subset coverage: [docs/subset-coverage.md](docs/subset-coverage.md) — three change levels, sample sizes, and the levels this subset cannot evaluate.
- Implementation: `src/custom/experiment/selective_patch.py`; detailed algorithm in [docs/selective_patch.md](docs/selective_patch.md).

## Representative failures

- **Under-update:** [docs/case-under-update.md](docs/case-under-update.md) — Task 416 at Late, required arguments absent from Agent knowledge, TF 1.0 against 10.0 after an update.
- **Over-update:** the Task 9 comparison below — unchanged-tool records rewritten, TF 3/10 against 10/10 after restoring them.

## Discussion

**When selective patching helps.** On the four changed tasks Selective Patch recovers +1.52 TF at Middle and +0.96 at Late against No Update, because the field-level diff is complete on catalog content and it leaves every unchanged record untouched. Full Rewrite recovers more there (+2.17 and +1.62) but only by rewriting records for tools the task never touches, and that is exactly the mechanism the over-update cases implicate.

**When it fails.** Not through under-update: the patch is exhaustive on catalog fields, so no changed argument can be missed. Its failures are residual rather than structural — the experience entries tied to changed tools are still rewritten, and those rewrites are the only place where Selective Patch can inherit the same contextual damage a full rewrite produces. That is why the Task 9 result matters, and it is the case where the two strategies differ least.

**Which change is hardest.** This subset cannot answer that. All four changed tasks change Description and Parameter jointly, and Tool-level change appears only as added tools, so a ranking of change levels has no support in the data and is reported as untested in [docs/subset-coverage.md](docs/subset-coverage.md).

**Cost–benefit.** Selective Patch reaches a higher ECS at 23% of Full Rewrite's update cost. Full Rewrite's larger recovery on changed tasks does not convert into ECS, because the 1.21 TF retention loss at Late cancels it while the paired ECS also penalises stage-to-stage volatility.

**Lessons.** Cohort-level and paired reporting were necessary to see any of this; the pooled TF means separate No Update and Full Rewrite by 0.03 and would have hidden the entire effect, while the retention table shows a 1.21 point loss for the same strategy.

## Provenance status

The retained formal run is `dirty_source: True` at revision `d7ddd29`, and the manifest records the three stage archives as `tool_bundles: missing`, so no archive checksum is bound to the run. Both are open items with owners in [docs/compliance_checklist.md](docs/compliance_checklist.md), together with the missing pricing date. They are disclosed here rather than left implicit.

## Member interfaces

- **Role 1:** catalog strategy plugin in `src/custom/experiment/selective_patch.py`; strategy-owned knowledge updates in `experience_state.py` use the same builder/validator for FR and SP.
- **Role 3:** select original IDs and maintain classifications in `config/subsets/selected_tasks.json`. Original tasks and 201 candidate IDs are in `src/custom/data/test_cases/`; fixture inputs are in `anotation_path/`. Do not rewrite task content.
- **Experiment settings:** edit the selected `config/*.json` profile. Models, repeats, provider pools and isolation policies are configuration fields. Formal profiles use `glm-4-flash-250414` for Actor/Judge and `openai/gpt-6-luna` for knowledge updates.
- **Tools:** `servers/{original,iter3,iter5}_servers/`; machine-specific routes are generated under `config/local/` and remain ignored.
- **Results:** start with [results/index.json](results/index.json). Each retained run contains its manifest, raw records and provenance. Historical committed archives remain available; formal scores are unchanged.

## Final case evidence

Original Task 9 is part of the frozen 17-task set. Its retained ten-group Late comparison uses temperature 0.2 and frozen FR snapshot repeat 2. Actual log reading and plan creation succeeded **3/10** with FR, **10/10** after restoring five unchanged-tool records, and **0/10** with an equal-length JSON key-order control. All 30 executions completed without infrastructure failures; no Judge or updater was called.

This is a local case under complete-library injection. It supports context-mediated regression from unnecessary rewriting, without identifying a unique sentence or establishing benchmark-wide superiority. Exact traces, input checks and limitations are in the [case review](results/20261029T113248.805747Z_Kevin/task-9-confirmation-review.json).

```text
python -m custom.experiment counterfactual-check --source-experiment results/20261026T084527.010290Z_Kevin --task-id 9 --snapshot-repeat 2 --repeats 10 --order-control
```

The case command uses the normal agent loop, fresh state per execution and matched paths within each group. It writes a separate result and leaves historical scores intact.

Tests: `python -m unittest discover -s tests -v`. Windows has been tested; real macOS/Linux tool-runtime validation remains pending. New maintained code and documentation are English; original benchmark data, frozen knowledge, tool-language matching and historical traces retain their original languages for reproducibility. Commit or push only when explicitly requested.
