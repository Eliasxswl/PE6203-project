# Experimental Protocol (v0.5, Updated 2026-10-29) — Group Project 4, Role 3

Status legend: **[FIXED]** frozen in the repo or verified against primary sources; **[PROPOSED]** recommendation needing group sign-off; **[TBD]** needs verification or another role's action. Task subset frozen at commit 60013b9 (17 tasks, SHA-256 `fb5887bc21829ab3a8c7b4da553cde1d75a2b79b016a23278106051b23368a07`); candidate pool hash `de89ef288f16677bc946851ee92739279ab38d94de900045685cdde011c474fe`. Formal run: `results/20261026T084527.010290Z_Kevin`. Remaining open items: clean-source rerun (`dirty_source: True`), bundle archive checksums, update-cost pricing date.

Changes from v0.4: §3 records that `selective_patch` is registered and that the strategy distinction now lives in the experience layer, not in the catalog; §4 repeats set to 3; §6 replaced projections with measured cost; §7 and §8 closed with the formal run and the Task 9 case; §9 adds the failure taxonomy and its controlled test; §10 and §12 updated to the residual gaps. §1, §2 and §5 are unchanged: their evidence chain and frozen subset still hold.

## 1. Purpose
Test whether a *selective patch* of tool-related harness knowledge recovers performance on changed tools while preserving tasks that should stay solvable, versus *no update* and *full rewrite*. Only the harness update may vary between strategies.

## 2. Benchmark and versions

### 2.1 Verified stage mapping [FIXED 2026-10-17]
Early = `original`, Middle = `iter3`, Late = `iter5`. Evidence chain:
1. **Paper, §5.2 "Benchmark Configurations"** (arXiv:2607.14642v1, NeurIPS 2026): *"MCPEvol-Bench pairs each task with three MCP server configurations representing different evolution stages: Early Stage (original, non-evolved server), Middle Stage (evolved for 3 rounds), and Late Stage (evolved for 5 rounds)."* The same section states **one mutation operator is applied per round**, so "iter3/iter5" are evolution-round counts on the server code, not record-folder counts.
2. **Paper Table 3 caption**: *"three evolution stages … the early stage with the original servers, the middle stage after three evolution iterations, and the late stage after five evolution iterations."*
3. **Upstream README at the fork base commit** `888c779`: the only stage configs shipped are `servers/1mcp_config/{original,iter3,iter5}/mcp.json` (167 servers each, verified by counting), and the ECS script takes exactly three evaluation directories ("baseline vs. two evolution stages").
4. **Fork**: `config/experiment.json` → `stages: ["original","iter3","iter5"]`; `docs/fixed-plan.md` states `original` (Early), `iter3` (Middle), `iter5` (Late).

### 2.2 What "iter5" means; why four mutation-record levels are not a missing layer [FIXED]
- `iter5` is the **server-code snapshot after five evolution rounds**, distributed as `iter5_servers.zip` and referenced by `iter5/mcp.json` (87 of 167 entries launch local `node` bundles via the `/path/to/iter5-servers/...` placeholder). Reproducing Late requires that archive — **not** a fifth nested mutation record.
- The public repo contains exactly **four** nested provenance-record files, `src/custom/data/mutation/HYBRID/evolution.json` then `/HYBRID/HYBRID/`, `/HYBRID/HYBRID/HYBRID/`, `/HYBRID/HYBRID/HYBRID/HYBRID/` (89/86/85/87 servers and 270/332/295/284 tool records respectively). In the upstream runner these are consumed **only by `--step 4`**, which overlays recorded description/schema edits onto the tool view; `get_all_evolution_status()` walks however many nested `HYBRID` directories the operator points to. `--step 3` instead runs against the live server on the configured port. Record depth and the launched snapshot are independent axes.
- This experiment uses native frozen-stage `tools/list` catalogs: `mode: "live"`, `runtime.catalog_source: "live"`, `runtime.evolution_files` empty for all three stages, `metadata_verified: false`. Overlays are not applied. This matters because the records do not match the snapshots (pilot-verified): shrimp-task-manager and mcp-tasks are recorded as Description-changed but show **zero** live change; `parallel-thinking` exists in the iter3 snapshot without a tracked addition; `duplicate_diagram` is recorded earlier than its observed iter5 appearance.
- Consequence for the report: this is a **comparison on the three supplied snapshots**, not an exact replay of every paper overlay; say so explicitly (already reflected in `fixed-plan.md`, Environment boundary).

### 2.3 Bundle availability and reproducibility limits
- The upstream HuggingFace dataset `anonymous2233/evol-servers` (public, last modified 2026-05-10) contains exactly `original_servers.zip`, `iter3_servers.zip`, `iter5_servers.zip` (+ README/.gitattributes); reported used storage **3,395,494,138 bytes ≈ 3.16 GiB** compressed, matching the team's ~3 GB / ~11 GB unzipped observation. **All three stages are publicly reproducible; nothing required for Early/Middle/Late is missing.**
- Launcher counts in the shipped configs (167 servers per stage): original 154 npx / 12 uvx / 1 uv; iter3 69 local node + 85 npx / 12 uvx / 1 uv; iter5 87 local node + 67 npx / 12 uvx / 1 uv. `scripts/prepare_local_config.py` rewrites placeholders to each extracted archive and **freezes `npx` packages against the stage archive** (using iter3 as a fallback for original), so **all three archives must be downloaded**, including `original_servers.zip`.
- Limits to record: (a) the dataset publishes **no official archive checksums** — Role 2 to record SHA-256 of the three downloaded zips plus an extracted-tree manifest into the run manifest; (b) the 12 uvx / 1 uv entries still launch via uv tooling, but none of the 25 gate-passing tasks depends on them; (c) snapshot fidelity is asserted only for the servers actually captured live; (d) fork experiments run on Windows (native checks done); real macOS/Linux runs remain pending, and web-dependent servers (12306, driflyte) need per-machine preflight.

### 2.4 Other fixed benchmark facts
Fork starts at upstream commit `888c779a0fe735f612ca62bdd1fdd7c9e6bf8701`; a separate upstream snapshot was byte-identical for `test_cases.json` and the four record files. Pool: 201 candidate tasks (`chosen_idx.json`) from 393 entries; task content, tools, fixtures and rubric unmodified.

## 3. Strategies [FIXED 2026-10-29]
`no_update`, `full_rewrite`, `selective_patch`, set through `strategies` in `config/experiment.json`; `strategy_plugins` lists `custom.experiment.selective_patch`. Tool knowledge is an in-memory dictionary keyed `server::tool` (name, description, schema) built from the stage catalog (`adapters.py`); transport routing is excluded. All strategies start from independent copies of the same Early catalog and evolve Early → Middle → Late. [FIXED 2026-10-29]

Two properties of the implemented strategies must be stated in the report, because they bound every score difference:

1. **Catalog knowledge is identical between Full Rewrite and Selective Patch.** Full Rewrite rebuilds through `semantic(new_tools)`; Selective Patch patches only differing fields. Since the knowledge record is built from the same catalog, both produce byte-identical catalog knowledge — verified by `knowledge_sha256` on 153 of 153 strategy pairs. Selective Patch instead exceeds Full Rewrite only where an unchanged tool is untouched; where a tool changed, both write the same value.
2. **The strategies diverge in the experience layer, not the catalog.** The adapters' deterministic rebuild has no model cost. The differentiating update is the experience/knowledge layer maintained by the strategy owner (`experience_state.py`, seeded from `config/practice/shrimp-k0.json`): Full Rewrite asks the updater to rewrite every entry, Selective Patch rewrites only entries whose source tool changed. This is what the update-cost figures in §7 measure, and it is verified by `experience_state_sha256` differing on 102 of 153 pairs while `knowledge_sha256` stays equal.

Consequence: a score difference between the two strategies is attributable to which experience entries were rewritten, never to catalog content. The Task 9 case in §9 tests exactly that mechanism.

## 4. Controlled variables [FIXED]
Same model (`glm-4-flash-250414`) for Agent and judge — `judge_model: ""` resolves to `agent_model` in code (`core.py`, `checks.py`); Agent temperature 0.2, judge temperature 0; 8192 max tokens; `agent_repeats: 3` in the formal run; 5 judge attempts per trajectory (judge slots, **not** repeated runs); same task list for every strategy and version; request cap `max(10, 2 × Early tool count) + 1`; fresh fixtures, backend state and conversation per task; no retries, no judge top-up. Admission: at most 2 concurrent in-flight requests per account/model group, 0.2 s dispatch interval; the formal profile ran one worker per account. No fine-tuning, no label changes.

Formal run composition: 3 strategies × 3 stages × 17 tasks × 3 repeats = 459 logical conditions, of which Early is executed once and shared (102 references), leaving 357 actual Agent executions and 1,785 judge slots. Two conditions failed execution (`full_rewrite/iter5/9/0`, `selective_patch/iter5/278/0`) and are excluded with cause; 457 conditions carry valid scores.

## 5. Task selection
### 5.1 Gate: which tasks can run [FIXED by code]
A task runs only if every required server has a reviewed backend-isolation policy (4 built-in + 11 in `runtime.policies`) and a frozen local executable. **25 of 201 candidates pass**: 17 core (catalog-covered) + 8 extension. Any other task needs Role 2 source review and a new policy.

### 5.2 Definitions [PROPOSED]
*Required tools* = tools listed under the task's `servers` field in `test_cases.json`. A task is **affected at a stage** if a required tool's description or schema differs from Early or the tool is removed; **new tools** added to its servers are recorded separately (Tool-level additions). A **retention control** has no required-tool difference at any stage. Aliases in `runtime.py` (e.g. `server-sequential-thinking`) resolve before comparison.

### 5.3 Current labels and subset proposal [PROPOSED]
All labels re-verified 2026-10-17 from live pilot catalogs; full table in `benchmark_task_list.md`.
- **Changed (4)**: 9, 24, 117, 416 — Description+Parameter on required tools (117 Description-only at Middle); 24 and 117 also see added tools.
- **Controls (13)**: 267, 271, 273, 274, 278, 386, 389, 390, 394, 403, 410, 411, 425.
- **Extension (8)**: 29 and 114 are already provably changed on catalog-covered servers (sequentialthinking; request_planning); 102/107 hinge on the 12306 catalog (paper Table 2 shows `get-tickets` gaining price parameters — external PARAM evidence pending live confirmation); 157/320/356/358 need catalogs for time/tina/driflyte/bazi/commands. **All their servers already have reviewed policies**; Role 2 action is catalog capture + preflight only.
- Frozen as one ID list in `config/subsets/selected_tasks.json` (replace current pilot IDs) with SHA-256; `task_count` must match; no replacement after freeze; failures excluded with reasons and coverage counts.

### 5.4 Coverage and gaps
Parameter and Description changes are present but co-occur on the same 4 tasks; no Parameter-only or Description-only case at Late (117 is DESC-only at Middle). Tool-level exists only as additions (24, 117); required-tool removal is unreachable inside the gate (candidates 72/90/430 need unreviewed external services). Imbalance 13 controls vs 4 changed; server family confounded with change status. Plan: prioritize 12306/commands/time catalog capture and preflight to enlarge the changed set, keep all 13 controls, and report remaining gaps explicitly with per-task values.

## 6. Repeats and compute budget [FIXED 2026-10-29]
- Executed: **3 repeats per strategy/stage/task** (`agent_repeats: 3`), 5 judge slots per trajectory. The assignment's "three runs preferred" is therefore satisfied, and the report reports repeat means rather than a single run.
- Updates are counted once per episode transition, so the strategy cost is 2 transitions per strategy/task (Early→Middle, Middle→Late), not one per repeat. Recorded cost is thus per-episode and must be described that way.
- Max 2 concurrent workers per API key (official limit for this model); the formal run used one worker per account. Key identities appear only as environment-variable names and quota groups, never in records, documents or Git.
- Wall-clock: the run manifest retains per-trajectory timings; use them rather than the pilot projections in v0.4, which assumed 153 trajectories and one repeat.

## 7. Metrics and reported results [FIXED 2026-10-29]
TF, PE (1–10) and ECS from the benchmark. **ECS follows the repo script (population standard deviation, divide by N=3)** over matched valid records across stages. Strategy comparison uses matched identities only (`paired_ecs`), never independent group means.

Reported values from the formal run:

| Quantity | Value |
|---|---|
| Paired ECS, 49 matched triples | Selective Patch 8.547 > No Update 8.371 > Full Rewrite 7.939 |
| Update cost, No Update | 0 calls, 0 tokens, $0.00 |
| Update cost, Selective Patch | 12 calls, ≈52K tokens, $0.0042 |
| Update cost, Full Rewrite | 42 calls, ≈212K tokens, $0.0182 |
| Stratified TF/PE | `compliance_checklist.md` §24 (Description+Parameter, Tool-addition, Retention rows) |

Three reporting rules follow from the data:
1. Report means **per cohort**, not pooled. Retention controls sit near 9.4/10, so pooling dilutes any adaptation effect toward zero.
2. Report the **paired** delta next to every mean. The over-update cases are invisible in group means and only appear in trajectory-level pairing.
3. State update cost as per-episode, not per-trajectory (see §6).

## 8. Preflight [EXECUTED before the formal run]
1. `validate` and `check` executed on the run machine; the manifest records Windows 11, Python 3.12.14, Node v24.21.0, and a hash for every local MCP config and tool entry (`fingerprints.local_config:*`, `fingerprints.tool_entry:*`).
2. Catalog evidence for the 17 core tasks captured from live `tools/list` diffs; the eight extension servers were never captured and were excluded from the freeze rather than labelled from secondary evidence.
3. Selection frozen with SHA-256 `fb5887bc…` **before** the formal run; the hash is recorded in the same manifest that carries the scores, so subset identity is bound to the results.
4. **Not done:** the three bundle archive SHA-256 values are absent (`tool_bundles: missing` in the manifest). This is the one open preflight item and is tracked as gap #22 in the compliance checklist.

## 9. Failure handling and taxonomy [FIXED 2026-10-29]
Execution/provider failures are excluded with cause and coverage counts; Agent operational mistakes stay scored; timeouts are never replayed; judge failures consume slots; means use valid scores with missing coverage stated explicitly.

Two failure classes are defined with numeric thresholds, so a case can be checked rather than argued:

- **F1 under-update** — a changed required tool's knowledge is not updated and the task fails. Example: `no_update/iter5/416/0`, TF 1.0, with `splitDetails`, `priority` and `tags` absent from the knowledge the Agent reads.
- **F2 over-update** — an unchanged tool's knowledge *is* modified and the paired No Update trajectory drops by at least 2.0 TF. Confirmed within the formal run: `iter5/389/0`, `iter5/403/0`, `iter5/410/1`, `iter5/278/2` (each 10.0 → 1.0), `iter5/274/2` (6.4 → 1.5), `iter3/394/2` (10.0 → 7.0), `iter5/394/2` (10.0 → 7.6).

**Task 9 confirmation case** (`results/20261029T113248.805747Z_Kevin`). Ten groups × three conditions, 30 executions, zero Judge calls, zero updater calls, zero infrastructure failures. Restoring only the five rewritten-but-unchanged records for tools Task 9 cannot call moved workflow success from 3/10 to 10/10; an equal-length key-order control scored 0/10; the paired comparison produced seven discordant pairs with an exact two-sided p of 0.0156.

Scope of that result must be stated exactly: it establishes that the **class** of over-update damage is real and causally tied to rebuilding records for tools the task never touches. It does **not** identify any individual harmful fact or phrase — the five restored records differ in wording, length and presentation together. Report the finding as "failure class confirmed, damaging unit not localised".

## 10. Assumptions and limitations [UPDATED 2026-10-29]
Design limits (cannot be removed without new benchmark content):
- Subset is gate-limited, not random; results do not generalize to the benchmark, and the core exercises task-management-style tools.
- The changed cohort is 4 tasks and its changes are Description+Parameter **jointly**; there is no Parameter-only, Description-only or Tool-only task. Tool-level change exists only as added tools (24, 117), and required-tool removal is unreachable inside the gate. Report this as a coverage limit, never as a measured ranking of change types.
- Snapshot comparison, not paper-overlay replication (§2.2).
- Same model serves as Agent and judge; the task-117 audit showed judge-validity limits that repeated slots do not remove.

Measurement limits discovered during analysis:
- **Ceiling effect.** Retention controls score near 9.4/10, so an over-update effect of roughly one point is swamped in cohort means. Only paired, per-trajectory screening surfaces the 10.0 → 1.0 cases. Any claim of "no damage" at mean level is unsupported.
- **Localisation gap.** Task 9 confirms the failure class but not a damaging unit; no individual harmful fact or phrase has been identified.
- **Tool-addition signal is small.** In the two Task-addition tasks, Selective Patch falls from 9.93 to 8.50 at Late while Full Rewrite stays at 9.80 — a 6-trajectory cell. Flag it as a lead to check, not a finding.

Provenance limits (open items):
- The formal run is `dirty_source: True` at revision `d7ddd29`; it cannot be rebuilt from a commit.
- The three bundle archive SHA-256 values are absent from the manifest.
- Update cost has no pricing date, so figures cannot be re-priced.
- Provider overload caused many excluded `execution_failed` records in early archived runs; upstream ran on Linux while this project ran Windows 11; web-dependent tasks may see changing content.

## 11. Reproducibility requirements
Python 3.11+ and Node.js 24; record OS, versions and model version; same environment type for all strategies. Commit code and config before any reported run (`dirty_source: False`); no edits to code, config, selection, inputs or generated local configs during a run; changed any of those → new experiment, never resume across them. Publish `config/experiment.json`, `selected_tasks.json` with SHA-256, run commands, raw `results/<id>/{experiment.json,records.json}`, and the three bundle archive names + SHA-256. Keep code and result commits separate; credentials and local configs stay out of Git.

## 12. Status and residual items
Closed: `selective_patch` registration; subset freeze with SHA-256; three-strategy × three-stage run at 3 repeats; TF/PE/ECS tables; recovery/retention aggregates; update cost; F1 and F2 failure cases; Task 9 confirmation case.

| Item | Owner | Blocks |
|---|---|---|
| Clean-commit rerun with identical settings, or first-page disclosure of revision `d7ddd29` and the uncommitted delta | Group (run owner) | Requirement #14 |
| SHA-256 of the three stage archives plus an extracted-tree manifest into the run manifest | Role 2 | Requirement #22 |
| Pricing date and model/price-version for the update cost | Role 2 / run owner | Requirement #26 |
| Discussion sections D1–D3 using the stratified table and the Task 9 case | Role 5 | Requirement #12 |
| Judge-validity limitation restated on the report | Role 5 | Requirement #16 |

Not closable within this project: Tool-level coverage (#6) and the eight extension tasks (#23). They require catalog capture for servers outside the reviewed gate. Document as scope, not as outcome.
