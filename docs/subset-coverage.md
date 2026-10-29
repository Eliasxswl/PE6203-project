# Frozen subset coverage by change level

Frozen set: `config/subsets/selected_tasks.json`, 17 tasks, SHA-256 `fb5887bc21829ab3a8c7b4da553cde1d75a2b79b016a23278106051b23368a07`.
Labels derive from live `tools/list` diffs only — upstream mutation records are not a labelling source (see `experimental_protocol.md` §2.2).

| Change level | Count | Task IDs | Notes |
|---|---|---|---|
| Description | 4 | 9, 24, 117, 416 | Always co-occurs with Parameter; task 117 is Description-only at Middle |
| Parameter | 4 | 9, 24, 117, 416 | Always co-occurs with Description |
| Tool, added | 2 | 24, 117 | New tools appear on the task's servers; no required tool is replaced |
| Tool, removed | 0 | — | Unreachable inside the runnable gate |
| Retention control | 13 | 267, 271, 273, 274, 278, 386, 389, 390, 394, 403, 410, 411, 425 | No required-tool difference at any stage |

## What this coverage does and does not support

Supports: a comparison of Description+Parameter change against unchanged tasks, and a check that updating supplies arguments a task actually needs (task 416 case).

Does **not** support: a ranking of change levels. There is no Task-only, Parameter-only or Description-only task in the frozen set, so statements such as "description changes are the hardest" cannot be derived from these 17 tasks. Any such claim in the report must be marked as untested.

Why the gaps stay open: candidates with required-tool removal (72, 90, 430) depend on external services without a reviewed isolation policy; the 8 extension tasks (29, 102, 107, 114, 157, 320, 356, 358) need catalog capture for servers outside the reviewed gate. Neither can be closed by relabelling.

## Confounding to state alongside the coverage

- Imbalance: 4 changed tasks versus 13 controls.
- Server family is confounded with change status — the changed tasks lean on the task-manager servers, so effect and tool family cannot be separated with this subset.
