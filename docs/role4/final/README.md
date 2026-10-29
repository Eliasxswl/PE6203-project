# Final indexed Role 4 handoff

This is the current report entry point. It follows `results/index.json`, reports both formal rounds separately, and replaces the provisional task-403 over-update candidate with the actual task-9 ten-group confirmation. It does not rewrite formal scores, merge two different protocols, or present Task 9 as another benchmark average.

Read [RESULTS.md](RESULTS.md) for tables and figures, [CASES.md](CASES.md) for under-/over-update evidence and limits, and [SUMMARY.md](SUMMARY.md) for Chinese interpretation and a bilingual group update. The small `analysis.json` file retains recomputed metrics, denominators, exclusions, hashes and all thirty behavioral outcomes. Large raw logs are not duplicated.

## Reproduce offline

```text
python scripts/role4/analyze_final_index.py
python -m unittest discover -s tests -p test_role4_final_index.py -v
```

Outputs default to ignored `.runtime/role4-final/`. `--plot` additionally requires Matplotlib; tables and validation use the standard library. Preparation and analysis make no model calls and start no MCP servers.

The analyzer recomputes TF/PE means from individual judge slots, paired all-stage ECS, matched stage/cohort effects, version-update costs, and Task 9 outcomes from raw tool returns. It independently checks shared-baseline copies, source JSON semantic checksum, source archive hashes, ten groups' equal model/tools/non-memory inputs and initial workspace states, preservation of affected memories, restoration from original K0, and order-only JSON semantic equivalence. Source bytes may differ by Git newline normalization; semantic equality is explicitly verified against the published handoff.

## What changed since the earlier Role 4 PRs

- PR #1 remains historical pilot work; the authoritative two rounds are the active entries in `results/index.json`.
- PR #2's October-26 numbers are retained, with a new separate catalog-baseline round and the task-9 evidence added.
- PR #3 is task-403 preparation, not successful live evidence. The final index explicitly selects task 9 after exploratory screening. No additional task-403 execution is needed for this handoff.
- The old statement "there is no intervention evidence" is superseded by task 9. The appropriate claim is a local context-intervention effect, not sentence-level fault localization or universal superiority.

## Figures and metric definitions for Role 5

`formal_rounds.png` compares paired ECS separately for the two system protocols. `task9.png` reports actual requested-log read rate with Wilson 95% intervals. Do not label the second figure TF, overall completion, or an additional full-benchmark experiment.

Formal rounds: 17 original tasks, three stages, three Agent execution repeats, five judge slots; temperatures 0.2/0. The catalog-only round uses deterministic local updates and the legacy Agent; the learned-knowledge round uses LangChain and a shared update model/validation policy. Shared Early results are counted once for physical execution and costs.

Task 9: 10 private workspace groups × 3 prompt conditions, fixed original Task 9 and FR repeat-2 snapshot, temperature 0.2, no Judge or paid update calls. Initial files are reset between conditions. Five restored records refer to tools unavailable in Task 9; the callable tools and two affected records stay fixed. The condition label `fr_changed_only` does **not** mean changed-only injection: all seven records remain injected, and five use original-K0 text.

The exploratory choice of task/snapshot must remain disclosed. Ten new confirmation groups are evidence for this fixed case, not ten tasks or evidence that all model/knowledge systems improve. The JSON-key-order control modifies formatting of affected as well as unaffected records. Restoration also changes length and wording, so no specific harmful sentence or unique semantic mechanism is isolated.
