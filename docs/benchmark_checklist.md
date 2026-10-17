# Group Project 4 — Benchmark Requirements Checklist (benchmark_checklist_en.md)

> Purpose: turn each requirement in the assignment document into a checkable item. Every item states **how to verify** it and **what counts as passing**.
> Status marks: `[ ]` not done / `[~]` in progress / `[x]` accepted.

## 0. Basic information

| Item | Content |
|---|---|
| Course project | Group Project 4: Tool Harness Adaptation under Environment Change |
| Benchmark | MCPEvol-Bench |
| Paper | arXiv:2607.14642 (NeurIPS 2026) |
| Given repository | https://github.com/Octobrist/MCPEvol-Bench |
| Pinned version (commit / tag) | Group fork starts at `888c779a0fe735f612ca62bdd1fdd7c9e6bf8701` (see `docs/fixed-plan.md`). A separate upstream snapshot zip (no `.git`, commit unknown) was compared: its `test_cases.json` and the four `evolution.json` files are byte-identical to the fork. No upgrade after freezing. |
| Local data checksums (first 16 hex of SHA-256) | `test_cases.json` b51d09d93afa94b0; `chosen_idx.json` 55df803b7cf40fe1; `mutation/HYBRID/evolution.json` 26d3e98c1464ab8b; `…/HYBRID/evolution.json` 9186e5959df32b93; `…/HYBRID/HYBRID/evolution.json` d78c551f0136a7b0; `…/HYBRID/HYBRID/HYBRID/evolution.json` 43d7deba235cb601 |
| Note | When the first draft was written the upstream repository could not be opened, so data-structure items were marked [TBD]; they have since been checked against the upstream snapshot and the results are filled in Appendix B. Items still unchecked remain marked. |

---

## 1. Three strategies

| ID | Requirement | Source | How to verify | Pass criterion | Status |
|---|---|---|---|---|---|
| S1 | **No Update**: after an environment change, keep the original tool knowledge unchanged | Assignment §2, §4.1 | Select `no_update` in the `strategies` list of `config/experiment.json` (the pipeline has no `--strategy` flag); hash the knowledge before and after a run | Knowledge hash identical before/after; update-step token count in the log is 0 | [x] (verified in code: `adapters.update` retains Early knowledge, `no_model_usage()`) |
| S2 | **Full Rewrite**: regenerate the **complete** set of tool knowledge for the tool-scheduling framework | Assignment §2, §4.1 | Select `full_rewrite`; check that the output covers every tool entry | Number of rewritten entries = total tool count; every entry has a generation log | [x] (verified in code: rebuild = `semantic(new_tools)` over the full current catalog; update-step tokens = 0, no model call) |
| S3 | **Selective Patch (own method)**: update only the knowledge related to changed tools | Assignment §2, §4.1 | Select `selective_patch` in `strategies` (requires Role 1); output a patch manifest (which entries changed and why) | The set of modified entries is a subset of the "affected entries" identified by the change detector; hashes of all other entries are unchanged; README explains the algorithm | [ ] (not registered; `strategy_plugins` empty — Role 1) |
| S4 | All three strategies share one pipeline; only strategy parameters differ | Assignment §3.2 fair comparison | `diff` the config files of the three runs | The diff shows only the `strategy` item (and its sub-parameters) | [ ] |

## 2. Three server-version stages

> **Mapping verified (2026-10-17, Role 3).** Paper §5.2 states verbatim: *"Early Stage (original, non-evolved server), Middle Stage (evolved for 3 rounds), and Late Stage (evolved for 5 rounds)"*; the Table 3 caption says the same. One mutation operator is applied per round. The upstream README (at fork base commit `888c779`) ships only three 1mcp configs, `original/iter3/iter5` (167 servers each), and the ECS script takes exactly three evaluation directories (baseline + two evolution stages). Therefore **Early = `original`, Middle = `iter3`, Late = `iter5`**; `iter5` is the **server-code snapshot after five evolution rounds** (HF dataset `iter5_servers.zip`; 87 config entries launch local node bundles) and **does not require a fifth mutation-record layer**.
>
> The four nested `mutation/HYBRID.../evolution.json` files in the repo (89/86/85/87 servers; 270/332/295/284 tool records) are only the overlay source for the upstream `--step 4` path; `get_all_evolution_status()` reads however many nested levels the operator points to, while `--step 3` connects to the live server. Our experiment runs `mode: live` with all `evolution_files` empty, so records are not applied — and they do not match the snapshots anyway (shrimp-task-manager and mcp-tasks are recorded as Description-changed but show zero live change; `parallel-thinking` exists in iter3 without a tracked addition). Conclusion: **records must not be used to label change types; only real `tools/list` diffs are valid**; the report must state this is "a comparison on the three supplied snapshots", not an operator-by-operator replay of the paper overlays.
>
> Reproduction material: the HF dataset `anonymous2233/evol-servers` (2026-05-10) contains exactly `original_servers.zip` / `iter3_servers.zip` / `iter5_servers.zip` (3,395,494,138 bytes ≈ 3.16 GiB total); all three stages are publicly reproducible. `prepare_local_config.py` also freezes npx packages into each stage archive, so **all three zips are required**. No official checksums are published — Role 2 to record the three zip SHA-256 values and an extracted-tree manifest. Live-catalog evidence currently covers only the five pilot servers; on 2026-10-17 an independent server-level diff was reproduced from `judge_catalog` in `results/20261015T045814.../records.json`, reproducing all 17 core-task labels (see `benchmark_task_list.md` v0.3 and `experimental_protocol.md` §2).

| ID | Requirement | How to verify | Pass criterion | Status |
|---|---|---|---|---|
| V1 | Evaluate the **Early** stage | Group result files by `stage=original` | All three strategies have Early TF and PE | [ ] |
| V2 | Evaluate the **Middle** stage | Same, `stage=iter3` | All three strategies have Middle results | [ ] |
| V3 | Evaluate the **Late** stage | Same, `stage=iter5` | All three strategies have Late results | [ ] |
| V4 | Complete result matrix | Build a 3 strategies × 3 stages × {TF, PE} table | 18 cells with no missing values; any missing cell explained in the report | [ ] |
| V5 | Versions match the knowledge correctly | Spot-check 3 tasks: the launched server version matches the stage label | All spot checks consistent; server version identifier recorded in the logs | [ ] |

## 3. Three change levels

> The paper's 11 mutation operators belong to three levels: Tool (O1 add, O2 replace, O3 delete, O4 merge), Parameter (O5 flexible expansion, O6 constraint change, O7 parameter pruning, O8 interface refactoring), and Description (O9 tool-description update, O10 parameter-description update, O11 joint-description update).

| ID | Requirement | How to verify | Pass criterion | Status |
|---|---|---|---|---|
| C1 | Selected tasks cover **Tool-level** changes | Tally by `change_level` in the task annotation | Tool-level changed-task count ≥ N₀ (N₀ fixed by the group before running; among candidates only 3 tasks have a required tool deleted and N₀≥10 is unreachable — set N₀ to the attainable count and state the shortfall in the report) | [ ] |
| C2 | Cover **Parameter-level** changes | Same | Parameter level ≥ N₀ (per real catalogs, among the 17 core tasks only 9/24/117/416 have a changed required tool, all Description+Parameter jointly — report the sample size honestly) | [ ] |
| C3 | Cover **Description-level** changes | Same | Description level ≥ N₀ | [ ] |
| C4 | Change-type labels are **independently re-checkable** from benchmark data | Diff the early vs middle/late server files and recompute the types | On a 20% sample of tasks, labels match the diff 100% | [x] for the 17 core tasks (reproduced 2026-10-17 from live pilot catalogs; scripts in `verification_evidence/`) |
| C5 | Report metrics separately by change type | Report table contains Tool / Param / Desc rows | All three rows have TF and PE with sample sizes stated | [ ] |

## 4. Metrics that must be reported

| ID | Metric | Definition | How to verify | Pass criterion | Status |
|---|---|---|---|---|---|
| M1 | **TF** (Task Fulfillment) | 1–10 score, higher is better, given by the judge model against the rubric | Use the repository evaluator unchanged; do not modify the scoring prompt | All runs use the same judge model and prompt; raw judge text saved in logs | [~] pipeline ready |
| M2 | **PE** (Planning Effectiveness) | 1–10 score for avoiding redundant/ineffective tool calls | Same | Same | [~] pipeline ready |
| M3 | **ECS** (Evolutionary Competency Score) | For each task, mean of the three stage TF values minus their standard deviation (**population standard deviation per the repo script, divide by N when N=3**; if the paper uses N−1, follow the repo and say so), then average over tasks: `ECS = mean_u( μ_u − σ_u )` | Write an independent recomputation and compare against the repository evaluator output | Unit test: the two differ by < 0.01; sanity cases `{9,9,9}` → 9, and `{9,5,9}` lower than `{8,8,8}` under the repo definition | [~] repo script used (`evolutionary_volatility.py`); independent check pending |
| M4 | Main report table | TF, PE (per stage) and ECS for all three strategies in one table | Manually trace table numbers back to raw logs | 5 randomly sampled numbers traceable to raw logs | [ ] |
| M5 | Repeated runs | Three runs per strategy preferred; current plan is 1 run (5 judge slots per trajectory are scoring slots, not repeated runs; three runs need four workers) | Count run ids in the logs | Three runs: report mean ± SD; one run: state "single run" explicitly on the report's first page | [ ] |

> Reference: with N=3 integer scores in [1,10], the N−1 SD gives an ECS lower bound around −1.20; the population SD (repo convention) gives around −0.24; both have upper bound 10. Use the repo-consistent bound for sanity checks.

## 5. Cost analysis

| ID | Requirement | How to verify | Pass criterion | Status |
|---|---|---|---|---|
| K1 | Count **update-step** tokens (input/output separately) per strategy | Unified counter at the model-call layer reading API `usage` | One row per strategy; No Update is 0 | [~] recorded in `records.json`; confirmed 0 for both baselines in code |
| K2 | Count API calls | Same | Matches the number of call-log entries | [~] |
| K3 | Count wall-clock duration | Record update-step start/end with a fixed concurrency setting | Measured on the same machine with the same parallelism; parallel evaluation wall-time must not be counted as update cost | [~] |
| K4 | Monetary cost | State unit price and pricing date in the report | Cost = tokens × unit price; formula recomputable | [ ] |
| K5 | Separate "update cost" from "evaluation cost" | Logged separately | Report lists the two in separate columns | [~] fields separated in records |

## 6. Performance Recovery and Capability Retention

> The formulas below are proposals; **the group must confirm and freeze them before running**, to avoid any appearance of post-hoc data selection.

| ID | Requirement | Proposed definition | How to verify | Pass criterion | Status |
|---|---|---|---|---|---|
| R1 | **Recovery** on changed tasks | Per stage (Middle/Late): `Recovery = (TF_strategy − TF_NoUpdate) / (TF_Early − TF_NoUpdate)`, plus the absolute difference `ΔTF`; tasks with denominator ≤ 0.5 are excluded from the ratio and compared on ΔTF only | Recompute on the per-task paired table | Report both ratio and absolute difference; state how many tasks were excluded | [ ] freeze formula before the formal run |
| R2 | **Retention** on unchanged tasks | `ΔTF = TF_strategy − TF_NoUpdate`; count tasks dropping by ≥ 2 points | Per-task paired table | Report mean ΔTF and the number of harmed tasks; list every harmed task | [ ] freeze formula before the formal run |
| R3 | Paired comparison | Same task, same stage, three strategies side by side | Check primary key (task_id, stage) for duplicates/missing values | Primary-key sets identical across the three strategies | [ ] |
| R4 | Robustness | If three runs are done, bootstrap confidence intervals or paired tests on the differences | Fixed random seed | Report intervals; with one run, state that intervals cannot be given | [ ] |

## 7. Failure-case analysis

| ID | Requirement | Proposed decision rule | How to verify | Pass criterion | Status |
|---|---|---|---|---|---|
| F1 | **Under-update** ≥ 1 complete case | An entry exists in the ground-truth change set (diff of early/late server files) but the patch does not cover it (missed tool, parameter, description, or usage rule), and the task clearly drops relative to Early | Patch manifest vs diff ground truth; set difference non-empty | Case includes the full trajectory: task, stage, patch diff, step-by-step Action/Observation, judge score, one-sentence root cause | [ ] needs selective_patch runs |
| F2 | **Over-update** ≥ 1 complete case | The patch changes a knowledge entry of an **unchanged** tool, and the task using it drops vs No Update by ≥ threshold (proposed: 2 points) | Patch manifest vs diff ground truth to find extra edits; paired table to find the dropped task | Same as F1, additionally highlighting the wrongly modified entry and its before/after text | [ ] needs selective_patch runs |
| F3 | At least two failure categories, one complete trajectory each | — | Two report subsections mapping to F1, F2 | Both trajectories findable in raw logs by run id | [ ] |
| F4 | Failure statistics | Count all failed tasks by category, automatic classification with manual review | Script + review | Report gives proportions of both categories; "unclassifiable" listed separately | [ ] |

> Paper observation (useful as a hypothesis): tool additions, tool merges, and description updates hurt scores most; deletion/pruning changes have little effect.

## 8. Discussion

| ID | Requirement | How to verify | Pass criterion | Status |
|---|---|---|---|---|
| D1 | Scenarios where selective patching helps significantly | Stratify by change type, server category, number of servers per task | Every conclusion backed by a table or number | [ ] |
| D2 | Scenarios where it fails | Same, cross-referenced with failure cases | At least one failure scenario with a mechanism explanation | [ ] |
| D3 | **Hardest change type** | Compare Recovery and failure rates across the three levels | One type named with supporting data | [ ] |

## 9. Fairness and prohibitions

| ID | Requirement | How to verify | Pass criterion | Status |
|---|---|---|---|---|
| X1 | Same base model | Model identifier in logs | Identical across all runs | [x] glm-4-flash-250414 in config |
| X2 | Same decoding parameters | Config-file hash | Identical across all runs (paper default temperature 0.2; if the repo default differs, follow the repo and state it) | [x] agent 0.2 / judge 0 |
| X3 | Same task subset | Subset-file hash | All runs reference the same hash | [ ] freeze pending |
| X4 | Same judging protocol | Judge model + prompt hash | Identical across all runs | [x] prompt unchanged |
| X5 | **No model fine-tuning** | Code review | No training/fine-tuning code or weight files in the repo | [x] |
| X6 | **No modification of benchmark labels/data** | `sha256sum` of the benchmark directory before and after the experiment | Checksums unchanged | [x] |
| X7 | Performance changes come only from tool-knowledge updates | Diff every other input (prompt templates, tool implementations, random seeds) | Empty difference list | [x] by design; verify at the formal run |
| X8 | Same runtime environment | Record OS and Python/Node versions | All strategies on the same OS type (upstream ran on Linux; the project runs on Windows/macOS — state which) | [ ] decide the formal-run machine |
| X9 | Consistency across parallel workers | Same model/parameters per worker; log key number (never the key itself) | Max 2 workers per key; 4 workers need a second key | [x] config supports two accounts |

## 10. Deliverables

| ID | Requirement | How to verify | Pass criterion | Status |
|---|---|---|---|---|
| P1 | Adaptation pipeline that runs with MCPEvol-Bench | Follow the README in a clean environment | One command runs a minimal subset (≥ 3 tasks) and produces results | [x] |
| P2 | Own selective-patching algorithm | Code review | Independent module and algorithm description; not a wrapper around Full Rewrite | [ ] Role 1 |
| P3 | Two baselines | See S1, S2 | Same entry point as P2 | [x] |
| P4 | Reproduction material: configs, commands, raw logs | Check the repository layout | Raw logs complete; every report number traceable to a log | [~] archived pilots are `dirty_source: True` — rerun from a clean commit |
| P5 | Report with 5 parts: main results, recovery & retention, update cost, failure cases, discussion | Cross-check against sections 4–8 above | All 5 parts present | [ ] |
| P6 | Presentation: 10-minute talk + 5-minute Q&A | Rehearse with timing | ≤ 10 minutes, covering the five required points (method idea, integration, key result comparisons, both failure types, conclusions) | [ ] |
| P7 | Submission via GitHub repo or Google Drive | Link check | Link accessible to reviewers | [ ] |

---

## Appendix A: Task-selection rule (how `task_subset_annotation.csv` is produced)

Goal: an explicit, repeatable rule — a different person with the same data obtains the same subset.

**Data granularity**: one row per (task_id, stage); each task produces three rows (early / middle / late) so the three versions of the same task pair directly.

**Changed vs Unchanged decision** (must be based on real `tools/list` catalogs; mutation records are proven unreliable and must not be used):
- First determine the task's "involved tool set": prefer the target servers/tools the benchmark annotates for the task; if only server-level information exists, use all tools in the task context and note which one was used in `selection_reason`. [field checked: `servers` maps server → tool list]
- For the involved tool set, compare the early server definition with the stage definition (tool names, parameter schemas, description text):
  - Any difference → `Changed`
  - Identical → `Unchanged`
- Early is the original server and is always `Unchanged` (`change_level = None`).
- `change_level` is the highest level occurring on the task's involved tools: Tool > Parameter > Description; if multiple levels occur, mark `Mixed` and list all operator ids in `operator_ids`.

**Selection steps (in order)**:

1. **Runnable (connectivity check)**: every required server is deployable at all three stages, needs no external key, and one no_update trajectory completes on all three versions. Do this before freezing the ID list; tasks failing after the freeze are not replaced — they are excluded and reported.
2. **Has an evaluation path**: the repository provides a usable evaluation entry for the task (judge prompt, reference information, or evaluation script). Otherwise exclude and record the count.
3. **If the assignment specifies a fixed subset**: use it directly, only fill in the annotation columns; do not re-sample.
4. **Otherwise stratified sampling**:
   - Changed tasks: sample N₀ per level (Tool / Parameter / Description), preferring single-level tasks for clean attribution; reserve a few slots for Mixed tasks.
   - Unchanged controls: similar count to changed tasks; match server category and server count, to measure Retention.
   - Fixed random seed (42 recommended); sort ascending by task_id before sampling.
   - **Rule currently adopted (v0.3)**: core = every task runnable under current isolation policies whose servers are all covered by the pilot real catalogs (17 tasks, no sampling): changed 9, 24, 117, 416; 13 controls (267, 271, 273, 274, 278, 386, 389, 390, 394, 403, 410, 411, 425); 8 more are runnable but lack catalog data (107, 114, 29, 358, 102, 157, 320, 356). Only 25 of the 201 candidates are runnable under current policies.
5. **Freeze**: after generation, compute the file SHA-256, record it in section 0 and every run log; all three strategies only read this file.

**Reuse**: the rule is data-agnostic; it can be rerun with new server versions or a new N₀. The script lives at `scripts/select_tasks.py` (planned), takes the benchmark directory as input and outputs `task_selection.csv`.

## Appendix B: items to check after cloning the repository

| # | Item to check | Result |
|---|---|---|
| 1 | Location and fields of task files (task_id, involved servers/tools) | `src/custom/data/test_cases/test_cases.json` (393 entries); fields `idx`, `question`, `servers` (server → tool list), `tool_calls`, `answer`; candidate ids in `chosen_idx.json` (201) |
| 2 | How the three stage versions are stored (directories, NPM versions, or configs) | **Checked 2026-10-17.** `servers/1mcp_config/{original,iter3,iter5}/mcp.json`, 167 servers each; launchers: original 154 npx / 12 uvx / 1 uv; iter3 69 local node + 85 npx / 12 uvx / 1 uv; iter5 87 local node + 67 npx / 12 uvx / 1 uv. Local packages come from the three zips in HF dataset `anonymous2233/evol-servers` (3,395,494,138 bytes total). `scripts/prepare_local_config.py` replaces `/path/to/iter3-servers`, `/path/to/iter5-servers`, `/path/to/workspace/` placeholders and freezes each stage's npx packages into its extracted archive (with iter3 as fallback for original); all three zips are required. No official checksums — record SHA-256 locally [Role 2]. |
| 3 | Existing change list / per-round operator records (for `operator_ids`) | **Checked 2026-10-17.** Four nested `mutation/HYBRID/evolution.json` files (89/86/85/87 servers; 270/332/295/284 tool records; no fifth level) serve only the upstream `--step 4` overlay path and do not define experiment stages; the live experiment does not read them, and they disagree with the real catalogs (shrimp/mcp-tasks recorded changed but actually unchanged). Operator ids O1–O11 do not appear in the records; **the only valid change list comes from diffing the three stages' real `tools/list` catalogs** — done for the five pilot servers (server-level table in `benchmark_task_list.md` v0.3); `catalog-diff` remains for the other servers. |
| 4 | Evaluator entry point, environment variables, default judge model and temperature | `src/custom/analysis/answer/evaluation.py`; ECS script `evolutionary_volatility.py` (population SD); upstream evaluator default temperature 0.0; this project uses glm-4-flash-250414, agent temperature 0.2 |
| 5 | Whether a "fixed subset" file exists | The assignment gives no fixed subset; self-selection with documentation is allowed; group pilot subset is `config/subsets/selected_tasks.json` (5 tasks, to be replaced) |
| 6 | What exactly constitutes tool knowledge (descriptions, schemas, usage rules, routing) in the harness | Not a set of files but an in-memory dictionary keyed by `server::tool`, holding name, description and parameter schema, built by `semantic()` in `src/custom/experiment/adapters.py` from each stage's `tools/list`; `update(strategy, knowledge, old_tools, new_tools, context)` performs the update (No Update keeps Early knowledge; Full Rewrite rebuilds everything from the current catalog with zero model calls; Selective Patch is registered by Role 1). Transport-routing fields (`remote_name`, `meta`) are excluded from knowledge; Early freezing and ordered updates live in `core.py`; each update result is recorded in `results/<id>/records.json`. |
| 7 | License and citation | No LICENSE file in the upstream snapshot; cite arXiv:2607.14642 |
