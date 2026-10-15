# Experimental Protocol (Draft v0.1) — Group Project 4, Role 3

Status legend: **[FIXED]** already frozen in the repo; **[PROPOSED]** my recommendation, needs group sign-off; **[TBD]** needs verification.

## 1. Purpose
Test whether a *selective patch* of tool-related harness knowledge recovers performance on changed tools while preserving tasks that should stay solvable, versus *no update* and *full rewrite*. Only the harness update may vary between strategies.

## 2. Benchmark and versions
- Benchmark: MCPEvol-Bench, forked from Octobrist/MCPEvol-Bench at commit `888c779a0fe735f612ca62bdd1fdd7c9e6bf8701`. [FIXED]
- Pool: 201 candidate tasks (`chosen_idx.json`), drawn from `test_cases.json` (393 entries). Task content, fixtures, tools and rubric are unmodified. [FIXED]
- Stages: Early = `original`, Middle = `iter3`, Late = `iter5` (tool bundles from the upstream HuggingFace dataset). [FIXED]
- [TBD] The repo holds four mutation record files (`data/mutation/HYBRID/...`) but only three stages. The mapping from record file to stage is unverified (`metadata_verified: false`). The experiment uses native `tools/list` catalogs of the frozen bundles, not these records, so the records are used here only as a proxy to classify change types.

## 3. Strategies [FIXED, except selective_patch]
`no_update`, `full_rewrite`, `selective_patch`. All strategies start from independent copies of the same Early catalog; knowledge evolves Early → Middle → Late. `selective_patch` is not yet registered (Role 1); adding it requires a new, separately frozen experiment.

## 4. Controlled variables [FIXED]
Same model (`glm-4-flash-250414`) for Agent and judge; Agent temperature 0.2, judge temperature 0; 8192 max tokens; 5 judge attempts per trajectory; same task list for every strategy and version; request cap `max(10, 2 × Early tool count) + 1`; fresh fixtures, backend state and conversation per task; no retries, no judge top-up. No fine-tuning, no label changes.

## 5. Task selection criteria [PROPOSED]
1. Task is among the 201 candidates.
2. Task runs on frozen local tool bundles (dependency screened; no downloading launchers, no unreviewed external services).
3. Change-type coverage: the selected tasks must include Tool-, Parameter- and Description-level changes that **directly affect a required tool** of the task, with a stated quota per type.
4. Retention controls: include tasks whose required tools are not affected by any change, to measure damage from over-updating.
5. One frozen ID list (`config/subsets/selected_tasks.json`) used by all strategies; no replacement of failed tasks; selection seed 6203.

**Findings from the mutation records (proxy, to be re-verified against the real catalogs):**
- The current 5-task pilot (9, 24, 117, 273, 403) is dominated by task-manager servers and has no task whose required tool is removed or renamed, so it does not meet criterion 3. It is also missing explicit retention controls.
- Across the 201 candidates, 139 have a required tool with a Description-level change and 120 with a Parameter-level change (in at least one record file); 24 have no directly affected required tool.
- Tool-level changes are mostly *additions* that do not invalidate any required tool. Only 3 candidates (72, 90, 430) have a required tool deleted. They use external-service servers (swiftipedia, leetcode, wikipedia, ygocdb), so they may fail the local-dependency screen.
- **Consequence:** Tool-level coverage is scarce. If these 3 cannot run locally, report Tool-level as a documented limitation rather than substituting unrelated tasks.

## 6. Repeats [PROPOSED]
Target 3 runs per strategy; if compute-limited, use 1 and state it in the report. Current pilots use 1.

## 7. Metrics
TF, PE (1–10) and ECS from the benchmark; ECS uses matched valid task/repeat records across all stages. Recovery = change on changed-tool tasks; retention = change on unchanged-tool tasks. Update cost = tokens, time and API calls per update, recorded by the pipeline.

## 8. Failure handling [FIXED]
Execution/provider failures are excluded with cause and coverage counts; Agent operational mistakes stay scored; timeouts are never replayed. Failures are classified as under-update (patch misses a changed tool/parameter/description/rule) or over-update (patch alters knowledge that was working), each with an example trajectory.

## 9. Assumptions and limitations
- Pilot subset is dependency-screened, not a random sample; conclusions do not generalize to the full benchmark.
- Judge validity: an audit of task 117 found high TF scores on trajectories missing required steps. Repeated judge slots reduce variance but not systematic bias; the same model plays Agent and judge.
- The free-tier model and provider overload caused many `execution_failed` records in the first two archived runs; they are excluded from results.
- Only Windows has been tested; macOS/Linux are unverified.
- Mutation overlays are not applied; results reflect the supplied snapshots, not every paper overlay.

## 10. Reproducibility requirements
- Commit code and config before any reported run (`dirty_source` must be `False` in `experiment.json`); do not edit code, config, selection or inputs during a run.
- Publish `config/experiment.json`, `selected_tasks.json`, run commands, and raw `results/<id>/{experiment.json,records.json}` for every reported number.
- Record Python/Node versions, tool-bundle archives (original/iter3/iter5) and model version.
- Keep code and result commits separate; keep credentials and local configs out of Git.
