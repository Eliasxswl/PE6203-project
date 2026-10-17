# Benchmark Task List (v0.3) — Group Project 4, Role 3

**Status: provisional, not frozen.** Labels are independently re-verified on 2026-10-17 from two primary sources: (a) required tools per task in `test_cases.json` (393 entries; candidate pool 201) and (b) the **live `tools/list` catalogs** recorded in the pilot run `results/20261015T045814.065101Z_Kevin/records.json` (`judge_catalog`, 30 trajectories, 2 strategies × 3 stages × 5 tasks). Within-stage catalogs are identical across the five pilot tasks (no inconsistency). Mutation records are not used for labeling. Machine-readable companion: `task_subset_annotation.csv`; all 201 candidates: `candidate_task_list.csv`.

## What was verified in v0.3
1. **Stage mapping is now confirmed** (was open in v0.2): Early = `original`, Middle = `iter3`, Late = `iter5`. Evidence and reproducibility limits are in `experimental_protocol.md` §2.
2. **Independent server-level catalog diff** across the three stages (see table below); the v0.2 labels for all 17 core tasks reproduce exactly from raw data.
3. **Required-tool counts for all 25 gate-passing tasks** were recomputed from `test_cases.json`; they match `task_subset_annotation.csv`.
4. **Extension blockers clarified**: every server used by the 8 extension tasks already has a reviewed isolation policy — no new Role 2 source review is needed. Only catalog capture and network preflight remain (details below).
5. Malformed extension table in v0.2 fixed.

## Runnable gate (unchanged, verified in config)
A task runs only if every required server has a reviewed backend-isolation policy — **4 built-in** (`runtime.py` BUILTIN_POLICIES: filesystem, kazuph taskmanager, sequential-thinking, guanxiong time) **plus 11 in `config/experiment.json` `runtime.policies`** (12306-mcp, original_from_tina, @remotion, @opentofu, @driflyte, bazi-mcp, mcp-trends-hub, mcp-server-commands, mcp-shrimp-task-manager, mcp-tasks, @aiuluna/knowledge-graph-mcp) — and uses frozen local executables (`npx`/`uvx` launchers are rewritten/rejected). **25 of 201 candidates pass** (17 core + 8 extension; 176 fail). Adding any other task needs Role 2 to review that server's source and add a policy.

Server aliases exist in `runtime.py` ALIASES (e.g. `server-sequential-thinking` → `@modelcontextprotocol/server-sequential-thinking`); labels below use the canonical names.

## Rule
Core = every gate-passing candidate whose servers are all covered by pilot catalogs (17 tasks; deterministic, no sampling). Extension = gate-passing with at least one server lacking captured catalogs (8 tasks). A task is **affected at a stage** if a *required* tool's description or schema differs from Early, or the required tool is removed. Tools newly added to a required server are recorded separately (Tool-level additions). Early is always the unchanged baseline.

## Verified server-level changes (the complete diff, 5 covered servers)

| Server | Tool | vs Early at Middle (`iter3`) | vs Early at Late (`iter5`) |
|---|---|---|---|
| @kazuph/mcp-taskmanager | request_planning | DESC + PARAM | DESC + PARAM |
| @modelcontextprotocol/server-filesystem | read_text_file | DESC + PARAM | DESC + PARAM |
| @modelcontextprotocol/server-filesystem | search_files | unchanged | PARAM |
| @modelcontextprotocol/server-filesystem | read_file | unchanged | **REMOVED** (not required by any gate-passing task) |
| @modelcontextprotocol/server-sequential-thinking | sequentialthinking | DESC | DESC + PARAM |
| @modelcontextprotocol/server-sequential-thinking | parallel-thinking | **ADDED** | present (added Middle) |
| @modelcontextprotocol/server-sequential-thinking | convergent-synthesis | absent | **ADDED** |
| mcp-shrimp-task-manager | (all tools) | no change | no change |
| mcp-tasks | (all tools) | no change | no change |

Catalog sizes recorded: 45 tools (original) → 46 (iter3, +parallel-thinking) → 46 (iter5, +parallel-thinking +convergent-synthesis −read_file).

## Changed core tasks (4) — re-verified
| ID | Servers (required tool count) | Middle, on required tools | Late, on required tools | Required-tool change detail (Late) |
|---|---|---|---|---|
| 9 | filesystem, kazuph taskmanager (3) | DESC+PARAM | DESC+PARAM | search_files: PARAM; read_text_file: DESC+PARAM; request_planning: DESC+PARAM |
| 24 | filesystem, sequential-thinking, mcp-tasks (4) | DESC+PARAM; new tool visible: parallel-thinking | DESC+PARAM; new tools visible: parallel-thinking, convergent-synthesis | read_text_file: DESC+PARAM; sequentialthinking: DESC+PARAM. Unchanged required: tasks_add, tasks_setup |
| 117 | shrimp, mcp-tasks, sequential-thinking (6) | DESC only; new tool visible: parallel-thinking | DESC+PARAM; new tools visible: parallel-thinking, convergent-synthesis | sequentialthinking: DESC+PARAM. Five shrimp/mcp-tasks tools unchanged |
| 416 | shrimp, kazuph taskmanager (7) | DESC+PARAM | DESC+PARAM | request_planning: DESC+PARAM; six shrimp/taskmanager tools unchanged |

Note: task 117 is **Description-only at Middle and Description+Parameter at Late** — the only covered case with a single level active at one stage.

## Unaffected core tasks = retention controls (13) — re-verified
| ID | Required tool count | | ID | Required tool count |
|---|---|---|---|---|
| 267 | 5 | | 390 | 7 |
| 271 | 6 | | 394 | 7 |
| 273 | 4 | | 403 | 4 |
| 274 | 5 | | 410 | 5 |
| 278 | 6 | | 411 | 4 |
| 386 | 4 | | 425 | 4 |
| 389 | 4 | | | |

Every required tool (all on mcp-shrimp-task-manager / mcp-tasks) is identical in all three stages.

## Extension tasks (8) — status updated; all their servers are already policy-reviewed
Blocking items are **catalog capture** (`catalog-diff`/`check`, Role 2 — no code or policy change expected) and, for two servers, a **network reachability preflight**.

| ID | Servers (required tools) | What is already provable | Remaining for labeling |
|---|---|---|---|
| 29 | sequential-thinking, mcp-server-commands (2) | **Already provably changed**: sequentialthinking DESC (Middle) / DESC+PARAM (Late) | mcp-server-commands catalog; one preflight trajectory |
| 114 | 12306-mcp, kazuph taskmanager (8) | **Already provably changed**: request_planning DESC+PARAM at both stages | 12306 catalog + network preflight (may add more changed tools) |
| 102 | 12306-mcp, mcp-tasks (6) | mcp-tasks verified unchanged; label hinges entirely on 12306. Paper Table 2 documents 12306 `get-tickets` gaining `minPrice`/`maxPrice` parameters — external PARAM-level evidence | 12306 live catalog + network preflight |
| 107 | 12306-mcp, mcp-tasks (5) | same as 102 | same as 102 |
| 157 | @guanxiong/mcp-server-time, original_from_tina (3) | time server is a **built-in** policy server; tina is reviewed | catalogs for both servers; preflight |
| 320 | @driflyte, bazi-mcp, mcp-server-commands (4) | all three servers reviewed (driflyte is read-only remote) | catalogs; driflyte network preflight |
| 356 | @driflyte, original_from_tina (4) | both reviewed | catalogs; driflyte network preflight |
| 358 | bazi-mcp, @driflyte, mcp-server-commands (4) | all reviewed | catalogs; driflyte network preflight |

## Coverage and gaps (after verification)
- **Parameter-level changes on required tools**: tasks 9, 24, 416 (both stages), 117 (Late only), plus search_files-only PARAM for 9 at Late. All Parameter changes co-occur with Description changes — there is **no Parameter-only task at Late** in the core. Candidates 102/107/114 are the realistic route to PARAM-centric cases (12306) if the live catalog confirms the paper's example.
- **Description-level**: same four tasks (117 is DESC-only at Middle).
- **Tool-level**: only **additions** visible to 24 and 117 (parallel-thinking at Middle; convergent-synthesis at Late). **No required tool is removed in any of the 25 gate-passing tasks.** The three candidates with a required-tool deletion (72, 90, 430; servers include swiftipedia/wikipedia/leetcode/ygocdb) fail the runnable gate (no isolation policy; external mutable services). Recommendation: do not substitute unrelated tasks; set the Tool-level quota to what is attainable and report this as a benchmark/gate limitation.
- **Sample imbalance and confounding**: 4 changed vs 13 controls; every control uses only shrimp/mcp-tasks, and changed tasks use filesystem/taskmanager/sequential-thinking — server family is confounded with change status. Adding 102/107/114 (12306) would both enlarge the changed set and break the confound; this is the highest-value preflight target. Conclusions from the core alone are limited to task-management-style tools.
- Earlier probes (135, 109, 161, 401, 54, 90, 430, 72) are not runnable under current policies.

## Recommendation to the group (decision needed before freeze)
1. Keep all 13 controls (retention is a primary claim; report per-task ΔTF with n=4 changed rather than trimming evidence). If the group insists on balance, trim controls by matching required-tool-count distribution, never ad hoc.
2. Ask Role 2, before freeze, for: catalog capture on the eight extension servers and one no_update preflight trajectory per extension task on all three stages; record pass/fail causes (especially 12306 and driflyte network).
3. Add every extension task that (a) shows a required-tool change in its live catalog and (b) passes preflight; expected priority 114/102/107, then 29, then 320/356/358/157.
4. Freeze one ID list (`config/subsets/selected_tasks.json`, replace the current five pilot IDs 9/24/117/273/403, set matching `task_count`) with SHA-256; no replacement after freeze — post-freeze failures are excluded with reasons and coverage counts.

## Needed to freeze
Group sign-off on items 1–3 above; preflight results for all selected tasks; the frozen ID list with SHA-256; archive SHA-256 for the three server bundles (protocol §2.3).
