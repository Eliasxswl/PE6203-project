# Selective Patch over-update cases

Three literal F2 trajectories from the Selective Patch strategy in the formal run `results/20261026T084527.010290Z_Kevin` — unchanged tools' knowledge modified with a paired No Update drop of at least 2.0 TF. Full Rewrite has seven such trajectories; Selective Patch's surface is smaller but not zero. The mechanism is identified from run records and code in each case below; none is counterfactually confirmed.

## Why Selective Patch can over-update at all

Selective Patch selects experience **entries**, not tools. An entry references several tools (`tool_ids`), and `affected()` in `src/custom/experiment/experience_state.py` selects an entry when **any** of its tools differs between stages. One changed tool therefore rewrites the guidance of its unchanged siblings inside the same entry. Selectivity bounds how much is rewritten; it does not bound what a rewritten entry covers.

## Case 1 — Task 389, Late, repeat 0 (10.0 → 1.0)

Task 389 is a retention control: no required tool changes at any stage.

| Trajectory | TF |
|---|---|
| `no_update/iter5/389/0` | 10.0 |
| `full_rewrite/iter5/389/0` | 1.0 |
| `selective_patch/iter5/389/0` | 1.0 |

The Agent-visible guidance blocks differ between No Update and Selective Patch even though the tools did not change. No Update's guidance for the task flow reads "To retrieve the next task, use 'get_next_task' with the correct 'requestId'. Always verify the 'requestId' before making…"; Selective Patch's rewritten guidance reads "Register a request with a valid priority-aware task plan and required tags, then retrieve its first task using the actual…". The run ends with a schema rejection:

```text
schema_input_invalid — argument_path: /initialConcept, constraint: minLength,
expected: 50, message: "'分析当前log_analysis.py脚本，制定改进计划，列出具体的开发任务以跟踪进度' is too short"
```

The Judge records 0 of 4 requirements met ("did not provide a detailed task description"). The chain — rewritten guidance steers the Agent toward registering a new request, the failing call then carries an `initialConcept` under the 50-character minimum — is consistent with the guidance rewrite but is not proven to be caused by it; the two system prompts differ in other guidance entries as well. Full Rewrite shows the same signature on this trajectory, and its Task 9 controlled test already demonstrates the damage class for that strategy.

## Case 2 — Task 274, Late, repeat 0 (10.0 → 7.0) and Middle, repeat 2 (10.0 → 7.6)

Two milder Selective Patch hits on the same retention task. Unlike case 1, no single schema error is identifiable; the paired drop of about 3 points is consistent with guidance-level damage but could also be repeat variance. Recorded for completeness of the F2 count, not offered as mechanism evidence.

## Case 3 — Task 117, Late, repeat 1 (2.0)

Task 117's required tool changes at Late, so this is not an F2 case; it is included because it shows the same damage direction from the Selective Patch side on a changed tool. Selective Patch's Agent knowledge contains the updated interface (`tags` appears 4 times, `priority` 5 times), yet the run scores 2.0 while its sibling repeats score 10.0 and 9.0. The Judge attributes the failure directly:

```text
"The agent attempted to plan the tasks but encountered a schema error due to
the inclusion of 'tags' in the input."
```

The updated knowledge supplied the new argument; the Agent then passed `tags` to a call whose schema rejects it. Updated knowledge changing Agent behaviour into an invalid call is the failure direction of the over-update class, here triggered on a tool the patch was supposed to fix.

## Status and use

- Cases 1 and 2 rest on single trajectories; case 3 likewise. None has a controlled test comparable to Task 9's ten-group comparison. A restore-the-guidance counterfactual for Task 389 would be the natural next experiment.
- Literal F2 count in the formal run: Full Rewrite 7, Selective Patch 3 (one catastrophic, two mild). Both strategies' counts come from the same paired screen against No Update.
- Honest summary for the report: Selective Patch's over-update surface is smaller than Full Rewrite's, but it is not zero, and entry bundling (above) explains why a selective policy still damages unchanged tools.
