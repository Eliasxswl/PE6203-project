# Assignment Compliance Checklist (Draft v0.1)

Status: **Met** / **Partial** / **Not met** / **Pending** (owned by another role).

| # | Requirement (assignment) | Status | Evidence / action |
|---|---|---|---|
| 1 | Three strategies compared: no update, full rewrite, selective patch | Partial | Baselines run; `selective_patch` not registered (`strategy_plugins` empty). Role 1. |
| 2 | Base model, decoding and judge fixed across strategies | Met | `config/experiment.json` (one model, temps 0.2/0, 5 judge slots). |
| 3 | No fine-tuning; no benchmark label changes | Met | Tasks/rubric unmodified; reference answers kept from Agent input. |
| 4 | Use MCPEvol-Bench; fixed documented subset, same for all strategies | Met | Fork commit `888c779`; one ID list `selected_tasks.json`. Document the selection criteria (protocol §5). |
| 5 | Early, Middle, Late versions evaluated | Partial | `original/iter3/iter5` configured; record-file ↔ stage mapping unverified. Role 3 to verify. |
| 6 | Tool-, Parameter-, Description-level changes in selected tasks | Not met | Current 5 tasks lack Tool-level (and explicit Parameter-level coverage). Reselect (protocol §5). |
| 7 | Three runs per strategy preferred; single run must be stated | Partial | Pilot uses 1 repeat; decide 1 vs 3 and state it. |
| 8 | Report TF, PE, ECS for method and both baselines | Pending | Pipeline computes them; needs final run with all three strategies. |
| 9 | Recovery and retention analysis | Not met | No retention control set defined yet (protocol §5.4). |
| 10 | Update cost (tokens/time/API cost) per strategy | Partial | Pipeline logs elapsed time and usage; verify token counts for each strategy. |
| 11 | Failure analysis: ≥2 types, ≥1 example trajectory each | Pending | Trajectories are in `records.json`; needs selective_patch runs. |
| 12 | Discussion: when patching helps/fails, hardest changes | Pending | Report authors. |
| 13 | Codebase: pipeline, own selective method, two baselines | Partial | Pipeline + baselines done; own method pending. |
| 14 | Reproduction material: configs, run commands, raw logs | Partial | Present, but archived runs have `dirty_source: True`; rerun from a clean commit. |
| 15 | 10-min presentation + 5-min Q&A | Pending | Whole group. |
| 16 | Judge validity concern documented | Partial | Known (task 117 audit); state in limitations. |

**Open items for Role 3:** verify stage mapping (#5), propose new subset meeting #6 and #9, decide repeats (#7), finalize protocol and keep this table updated.
