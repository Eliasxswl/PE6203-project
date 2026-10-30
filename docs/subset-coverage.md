# Frozen subset coverage by change level

Frozen set: `config/subsets/selected_tasks.json`, 17 tasks, SHA-256 `fb5887bc21829ab3a8c7b4da553cde1d75a2b79b016a23278106051b23368a07`.
Labels derive from live `tools/list` diffs only — upstream mutation records are not a labelling source (see `experimental_protocol.md` §2.2).

## Selection rule (quotable)

> From the 201 candidate tasks, a task enters the frozen subset only if it completes on all three stages in live mode without environment or network failure, and its required tools show a verifiable `tools/list` difference at at least one stage or, for controls, no difference at any stage. Labels come from those diffs alone. No task is replaced after the freeze.

25 of 201 candidates were runnable under this gate. All 4 runnable tasks with a changed required tool were taken, and 13 runnable tasks with no change at any stage were taken as retention controls, giving 17.

| Change level | Count | Task IDs | Notes |
|---|---|---|---|
| Description | 4 | 9, 24, 117, 416 | Always co-occurs with Parameter; task 117 is Description-only at Middle |
| Parameter | 4 | 9, 24, 117, 416 | Always co-occurs with Description |
| Tool, added | 2 | 24, 117 | New tools appear on the task's servers; no required tool is replaced |
| Tool, renamed | 0 | — | **Not assessed** |
| Tool, removed (catalog) | 1 | 9, 24 | `@modelcontextprotocol/server-filesystem::read_file` disappears at Late on these two tasks; no task calls it, task 9 uses `read_text_file`, so this is not a required-tool removal |
| Tool, removed (required) | 0 | — | **Not assessed** — no selected task loses a tool it must call |
| Parameter-only | 0 | — | **Not assessed** |
| Description-only | 1 partial | 117 | Description-only at Middle only, Parameter changes at Late |
| Retention control | 13 | 267, 271, 273, 274, 278, 386, 389, 390, 394, 403, 410, 411, 425 | No required-tool difference at any stage |

## What this coverage does and does not support

Supports: a comparison of Description+Parameter change against unchanged tasks, and a check that updating supplies arguments a task actually needs (task 416 case).

Does **not** support: a ranking of change levels. There is no Task-only, Parameter-only or Description-only task in the frozen set, so statements such as "description changes are the hardest" cannot be derived from these 17 tasks. Any such claim in the report must be marked as untested.

## Not assessed, and why

| Missing level | Candidate tasks that would supply it | Why it stays out |
|---|---|---|
| Tool rename | none identified in the runnable set | no runnable candidate exhibits a rename on a required tool |
| Tool removal on a *required* tool | 72, 90, 430 | depend on external services without a reviewed isolation policy; the gate rejects them. Catalogue-level removal does occur (`read_file` on tasks 9 and 24) but no task calls it, so it exercises neither recovery nor failure |
| Extension-hosted changes | 29, 102, 107, 114, 157, 320, 356, 358 | catalogs never captured, so no label can be derived from a real diff |

Neither gap can be closed by relabelling, and both are reported as scope limits rather than results.

## Confounding to state alongside the coverage

- Imbalance: 4 changed tasks versus 13 controls.
- Server family is confounded with change status — the changed tasks lean on the task-manager servers, so effect and tool family cannot be separated with this subset.
