# Assignment Compliance Checklist (Draft v0.4)

Status: **Met** / **Partial** / **Not met** / **Pending** (owned by another role). Evidence paths refer to the team fork `Eliasxswl/PE6203-project`. v0.4: stage mapping verified (#5, #21); bundle availability verified, local checksums still due (#22); extension blockers reduced to catalog capture + preflight (#6, #20, #23); judge fallback confirmed in code (#2).

| # | Requirement (assignment) | Status | Evidence / action |
|---|---|---|---|
| 1 | Three strategies compared: no update, full rewrite, selective patch | Partial | Baselines run; `selective_patch` not registered (`strategy_plugins` empty). Role 1; adding it starts a new frozen experiment. |
| 2 | Base model, decoding and judge fixed across strategies | Met | `config/experiment.json`: one model glm-4-flash-250414; `judge_model: ""` falls back to agent model in `core.py`/`checks.py`; temps 0.2/0, 8192 tokens, 5 judge slots; same model on both API keys. |
| 3 | No fine-tuning; no benchmark label changes | Met | Tasks/rubric unmodified; upstream data byte-identical to the fork; reference answers excluded from Agent input. |
| 4 | MCPEvol-Bench; fixed documented subset, same for all strategies | Partial | Rule, gate and 17-task core written (protocol §5; task list v0.3); 25/201 candidates runnable; freeze one `selected_tasks.json` + SHA-256 after preflight, set matching `task_count`. |
| 5 | Early, Middle, Late evaluated | Met (mapping); Partial (run coverage) | Mapping verified: paper §5.2 and Table 3 (original / 3 rounds / 5 rounds), upstream README, fork config — see #21. Baselines have run all three stages; selective_patch has not. |
| 6 | Tool-, Parameter-, Description-level changes in selected tasks | Partial | Live catalogs: DESC+PARAM on required tools in 9/24/117/416 (117 DESC-only at Middle); Tool-level only as added tools for 24/117; no required-tool removal inside the runnable gate. Tasks 29/114 provably changed now; 102/107/114 may add PARAM-centric, non-taskmanager cases after 12306 catalog capture. Document any residual gap. |
| 7 | Three runs preferred; single run must be stated | Partial | Plan: 1 run (5 judge slots are not repeats), stated on the report's first page. Three runs ≈ 13 h serial / ≈ 2.5–3 h with 4 workers; decide at freeze. |
| 8 | Report TF, PE, ECS for method and both baselines | Pending | Pipeline computes them incl. `paired_ecs`; ECS uses repo definition (population SD). Needs the final run with all three strategies. |
| 9 | Recovery and retention analysis | Partial | 13 verified control tasks + unchanged tools inside changed tasks; formulas R1/R2 drafted, must be frozen before running; imbalance 13 vs 4 and server confound to be reported; extension tasks may reduce the confound. |
| 10 | Update cost per strategy | Partial | Pipeline records update usage/timings/calls; measure update step under fixed worker count, separate from evaluation; confirm full_rewrite token cost (protocol §3). |
| 11 | Failure analysis: ≥2 types, ≥1 trajectory each | Pending | Definitions ready (F1/F2); needs selective_patch runs. |
| 12 | Discussion: when patching helps/fails, hardest change type | Pending | Report authors (Role 5); stratified analysis plan in checklist §8. |
| 13 | Codebase: pipeline, own selective method, two baselines | Partial | Pipeline + two baselines done (65 offline tests passing at 2026-10-15); own method pending. |
| 14 | Reproduction material: configs, commands, raw logs | Partial | Present; archived runs have `dirty_source: True` — rerun from a clean commit; publish configs, frozen subset hash, bundle checksums, OS/version records. |
| 15 | 10-min presentation + 5-min Q&A | Pending | Whole group. |
| 16 | Judge validity concern documented | Partial | Task-117 audit (high TF with missing steps); same model as Agent and judge; state in limitations. |
| 17 | Preflight before subset freeze | Pending | `validate`/`check` on each machine; `catalog-diff` on extension servers; one trajectory per candidate on all stages; failures/causes recorded; no post-freeze replacement. Probes 135/109/161/401/54/90/430/72 remain non-runnable. |
| 18 | Same OS/environment type for all strategies | Pending | Upstream: Linux (CentOS 7.9); project: Windows tested, macOS/Linux pending; state the environment; run all strategies in one environment type. |
| 19 | Compute plan and key usage | Partial | Max 2 workers/key; second key for 4 workers (already configured, stable account assignment); keys logged by number only; observed ≈50 min (serial) / ≈10 min (4 workers) for the 2-strategy 5-task pilot. |
| 20 | Change types verified against real catalogs | Partial | Done independently for the 17 core tasks (server-level diff reproduced from pilot `judge_catalog`, 2026-10-17). Extension: 29/114 partly labeled from covered servers; remaining servers need `catalog-diff` (Role 2). |
| 21 | (new) Early/Middle/Late mapping verified against primary sources | Met | Paper arXiv:2607.14642v1 §5.2 + Table 3 caption; upstream README at commit `888c779`; `stages` in `config/experiment.json`; protocol §2.1. iter5 = five-round server snapshot, not a fifth mutation layer; four HYBRID record levels feed only upstream `--step 4` overlays and are not applied (`mode: live`). |
| 22 | (new) Stage bundles available and pinned | Met (public) / Partial (local) | HF dataset `anonymous2233/evol-servers` holds exactly original/iter3/iter5 zips (3,395,494,138 B); 167 servers per stage config; all three archives required. Role 2: record zip SHA-256 + extracted-tree manifest; official checksums are not published. |
| 23 | (new) Extension tasks unblocked for labeling | Partial | Every server behind the 8 extension tasks already has a reviewed policy (4 built-in + 11 policies); no new source review needed. Remaining: catalog capture and network preflight (12306, driflyte). |

**Open items for Role 3:** group decision on controls vs changed balance, extension inclusion and repeats (#4, #6, #7, #9); receive Role 2 catalog/preflight evidence and bundle checksums (#17, #22, #23); freeze the ID list and R1/R2 formulas; keep this table current through the formal run.
