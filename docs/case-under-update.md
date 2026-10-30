# Under-update failure case: Task 416 (No Update, Late stage)

Source run: `results/20261026T084527.010290Z_Kevin`, trajectory `no_update/iter5/416/0`.
Comparison trajectories: `full_rewrite/iter5/416/0`, `selective_patch/iter5/416/0`.

## What changed in the environment

At the Late stage the required tool `@kazuph/mcp-taskmanager::request_planning` demands five named arguments. The stage catalog recorded for this trajectory states it directly:

> "Register a new user request and plan its associated tasks with priority levels and optional deadline tracking. You must provide 'originalRequest', 'splitDetails', 'tasks', 'priority', and 'tags'."

The Early-stage version of the same tool does not carry `splitDetails`, `priority` or `tags`.

## What the No Update strategy did

No Update retains the Early catalog for the whole episode, so the Agent is shown an out-of-date description. Counting the occurrence of each required argument name in the Agent-visible system prompt of `no_update/iter5/416/0` (21,340 characters):

| Argument | No Update | Full Rewrite | Selective Patch |
|---|---|---|---|
| `splitDetails` | 0 | 3 | 3 |
| `priority` | 0 | 4 | 5 |
| `tags` | 0 | 4 | 5 |
| `originalRequest` | 1 | 2 | 2 |

The same pattern repeats in `no_update/iter5/416/1` (0 / 0 / 0), so this is the strategy's behaviour and not a single sample.

## Trajectory

The Agent made two tool calls and stopped. The Judge recorded **0 of 6 requirements met** and a defect rate of 100%:

```text
task_fulfillment_reasoning: "Total requirements: 6. Met requirements: 0. Defect rate: 100%. Score: 1."
```

| Trajectory | TF | PE (5-slot mean) |
|---|---|---|
| `no_update/iter5/416/0` | 1.0 | 4.6 |
| `full_rewrite/iter5/416/0` | 10.0 | — |
| `selective_patch/iter5/416/0` | 5.8 | — |

Because the Agent was never told that `splitDetails`, `priority` and `tags` were required, it could not construct a valid planning call. The task is unrecoverable from that starting knowledge, which is the definition of under-update used in this project: a changed required tool's knowledge is not updated and the task fails.

## Root cause

No Update is defined as discarding every environment change on both knowledge layers, so it under-updates by construction on every changed task. It is not a detector failure; it is the intended baseline.

This matters for how the two failure classes are represented. **Selective Patch cannot produce a catalog under-update**: its patch compares the full previous and current catalogs field by field and writes every differing value, so any required argument added or renamed at a stage is copied into the Agent knowledge. An under-update case therefore has to come from the No Update baseline. Claiming a "selective patch missed a change" case would misrepresent the implementation.

## Selective Patch on the same task: patched but only partly recovered

Selective Patch cannot reproduce this failure — its field-level diff writes every differing catalog value — but it does not fully repair the task either. All 18 scored trajectories for task 416:

| Strategy | Middle (3 repeats) | Late (3 repeats) |
|---|---|---|
| No Update | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 |
| Full Rewrite | 7.6 / 8.8 / 1.6 | 10.0 / 10.0 / 1.0 |
| Selective Patch | 2.0 / 4.6 / 3.6 | 5.8 / 4.6 / 5.8 |

Full Rewrite and Selective Patch hold byte-identical catalog knowledge for this task, so the recovery gap between them can only come from the experience layer: Full Rewrite rewrites every entry, Selective Patch rewrites only entries tied to changed tools. Whether the missing context is the untouched entries themselves or per-repeat variance, this sample cannot separate — Full Rewrite's own repeats span 1.6 to 8.8 at Middle and 1.0 to 10.0 at Late. What the table establishes is that even with the catalog fully updated, recovery is partial and high-variance for both strategies, while No Update stays at 1.0 throughout.

This case is also load-bearing for the comparison: excluding task 416 from the paired bootstrap moves Selective Patch − No Update from +0.18 to +0.03 (README, Statistical evidence). One task carries most of the selective-patching advantage over No Update.

## Limitation

Single task, single repeat family, one snapshot pair. It establishes the mechanism (required argument absent from Agent knowledge → task failure) and ties it to a concrete score drop, but it does not estimate how often under-update costs points across the benchmark. The 13 retention controls exist precisely to show that a strategy can also fail in the opposite direction; see the over-update case for that side.
