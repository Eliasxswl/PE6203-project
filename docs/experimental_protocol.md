# Experimental Protocol (v0.4, Frozen 2026-10-17) — Group Project 4, Role 3

Status legend: **[FIXED]** frozen in the repo or verified against primary sources; **[PROPOSED]** recommendation needing group sign-off; **[TBD]** needs verification or another role's action. Task subset frozen at commit 60013b9 (17 tasks, SHA-256 `fb5887bc21829ab3a8c7b4da553cde1d75a2b79b016a23278106051b23368a07`); candidate pool hash `de89ef288f16677bc946851ee92739279ab38d94de900045685cdde011c474fe`. Remaining open items: 1-run vs 3-run decision, Role 2 merge of `codex/selective-patch` + clean rerun.

Changes from v0.3: §2 stage mapping verified against the paper and upstream artifacts (was [TBD]); iter5 resolved as a five-round server snapshot, not a fifth mutation layer; bundle inventory and reproducibility limits documented; §5 extension status updated (all eight extension servers already have isolation policies; tasks 29 and 114 provably changed today); §6 timing refreshed from the 2026-10-17 pilot observations; §8 preflight made concrete; judge fallback confirmed in code.

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

## 3. Strategies [FIXED, except selective_patch]
`no_update`, `full_rewrite`, `selective_patch`, set through `strategies` in `config/experiment.json`. Knowledge is an in-memory dictionary keyed `server::tool` (name, description, schema) built from the stage catalog (`adapters.py`); transport routing is excluded. All strategies start from independent copies of the same Early catalog and evolve Early → Middle → Late. `selective_patch` is not yet registered (`strategy_plugins` empty, Role 1); adding it requires a new, separately frozen experiment. [TBD] Confirm whether `full_rewrite` calls the model during rebuild (needed for the update-cost comparison; currently its token cost cannot be assumed zero).

## 4. Controlled variables [FIXED]
Same model (`glm-4-flash-250414`) for Agent and judge — `judge_model: ""` resolves to `agent_model` in code (`core.py`, `checks.py`); Agent temperature 0.2, judge temperature 0; 8192 max tokens; `agent_repeats: 1`; 5 judge attempts per trajectory (judge slots, **not** repeated runs); same task list for every strategy and version; request cap `max(10, 2 × Early tool count) + 1`; fresh fixtures, backend state and conversation per task; no retries, no judge top-up. Admission: at most 2 concurrent in-flight requests per account/model group, 0.2 s dispatch interval. No fine-tuning, no label changes.

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

## 6. Repeats and compute budget [PROPOSED]
- Primary plan: **1 run per strategy** (`agent_repeats: 1`), 5 judge slots per trajectory; state "single run" on the report's first page. Three runs preferred by the assignment.
- Observed (current two-strategy pilot, 5 tasks, 3 stages, 1 repeat): ≈ 50 min serial with 1 worker (≈100 s per trajectory incl. judging), ≈ 10 min with 4 workers (two API keys).
- Formal projections (3 strategies, 17 tasks = 153 trajectories): ≈ 4.3 h serial; ≈ 50–70 min with 4 workers. Three repeats: ≈ 13 h serial / ≈ 2.5–3 h with 4 workers. Linear/constant-overhead estimates; re-estimate after the first formal block.
- Max 2 concurrent workers per API key (official limit for this model); 4 workers need the second account key with the identical model/settings; key identities logged by number only, never written into documents or Git.

## 7. Metrics
TF, PE (1–10) and ECS from the benchmark. **ECS follows the repo script (population standard deviation, divide by N=3)** and matched valid records across stages; paired strategy comparisons use matched identities (`paired_ecs`). Recovery/retention formulas: `benchmark_checklist.md` R1/R2 — freeze before any reported run; with 4 changed tasks, report per-task values, not only means. Update cost (tokens in/out, calls, wall-clock for the update step only, fixed worker count) comes from `records.json`, separated from evaluation cost; confirm full_rewrite update token usage (§3).

## 8. Preflight (do before freeze, not after) [PROPOSED]
1. `python -m custom.experiment validate --config config/experiment.json` then `check` on every teammate machine (`check --skip-models` for tool-only); record OS/Python/Node versions.
2. `catalog-diff` for the eight extension servers (12306, mcp-server-commands, @guanxiong/mcp-server-time, original_from_tina, @driflyte, bazi-mcp; the other required servers are already covered); save the catalog evidence with the run.
3. One no_update trajectory per candidate task on all three stages; a task passes only if it completes without environment/network errors. Explicit traffic-light row per task (12306 and driflyte are the expected network risks; uv/uvx entries and website-dependent content are known hazards).
4. Freeze the ID list + SHA-256 only after step 3; record the three bundle archive checksums.

## 9. Failure handling [FIXED]
Execution/provider failures are excluded with cause and coverage counts; Agent operational mistakes stay scored; timeouts are never replayed; judge failures consume slots, means use valid scores with missing coverage explicit. Failures are classified under-update or over-update, each with one example trajectory from the selective_patch runs.

## 10. Assumptions and limitations
- Subset is gate-limited, not random; does not generalize to the benchmark; conclusions from the core are limited to task-management-style tools.
- Only 5 servers have live-catalog evidence today; extension labels pending §8 step 2.
- Snapshot comparison, not paper-overlay replication (§2.2); same model is Agent and judge, and the task-117 audit showed judge-validity limits that repeated slots do not remove.
- Provider overload caused many excluded `execution_failed` records in early archived runs; upstream ran on Linux; web-dependent tasks may see changing content.

## 11. Reproducibility requirements
Python 3.11+ and Node.js 24; record OS, versions and model version; same environment type for all strategies. Commit code and config before any reported run (`dirty_source: False`); no edits to code, config, selection, inputs or generated local configs during a run; changed any of those → new experiment, never resume across them. Publish `config/experiment.json`, `selected_tasks.json` with SHA-256, run commands, raw `results/<id>/{experiment.json,records.json}`, and the three bundle archive names + SHA-256. Keep code and result commits separate; credentials and local configs stay out of Git.

## 12. Pending items and owners
| Item | Owner | Needed by |
|---|---|---|
| Register `selective_patch` via `adapters.register` + `strategy_plugins` | Role 1 | formal 3-strategy run |
| Catalog capture for 8 extension servers; bundle SHA-256; preflight trajectories; clean-commit rerun (archived pilots are `dirty_source: True`) | Role 2 | subset freeze |
| Freeze decision (controls, extensions, 1 vs 3 repeats), R1/R2 formula freeze | Role 3 + group | before formal run |
| Final TF/PE/ECS tables, recovery/retention, costs, two failure cases | Role 4 | after formal run |
