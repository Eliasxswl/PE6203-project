# Role 4 three-strategy handoff

The designated result is `results/20261026T084527.010290Z_Kevin/`. This analysis supersedes the old two-strategy pilot interpretation for this run, not the original records. See [detailed results](RESULTS.md), [failure evidence](CASES.md), and [Chinese explanation / bilingual team update](SUMMARY.md).

Reproduce from the repository root, without network, model calls or MCP execution:

```text
python scripts/role4/analyze_three_strategy.py
python -m unittest discover -s tests -p test_role4_three_strategy.py -v
```

Derived data are stored under ignored `.runtime/role4-three-strategy/`: `analysis.json` includes per-task paired deltas, hashes, repeat-level means, costs, physical inference usage, dependency audit and validation; `case_evidence.json` preserves the focused raw traces. Use `--plot` with an analysis environment containing Matplotlib to regenerate the two checked-in figures. Standard-library analysis needs no plotting dependency. Report artifacts here are intentionally small; do not commit duplicates of the 53 MB records, source zip, cache or private environment.

## Correct interpretation

- 459 logical rows include 102 reused Early aliases, so there are 357 unique executions, not 459 independent trials. Three Agent repeats and five judge slots are different units.
- Use common task/repeat sets across strategies: Early/Middle N=51, Late N=49; paired all-stage ECS N=49. Two recorded execution failures are retained as exclusions with causes.
- This run uses `experience_evolution_v1`: learned experience records are rewritten by `openai/gpt-6-luna` for Full Rewrite/Selective Patch, while the Agent and judge use the configured GLM model. This changes the old pilot's zero-model-cost Full Rewrite interpretation.
- Archive SHA-256 matches the manifest. `dirty_source=true` remains an explicit protocol deviation; a source archive establishes traceability but does not make the run clean-source compliant. The report cannot certify course acceptance.
- Selective Patch has the highest paired ECS and much lower update spend than Full Rewrite, but Full Rewrite recovers more TF on the four changed tasks. The cost/retention tradeoff is more supportable than a claim of universal superiority.
- The audit found no Selective Patch dependency-selection omissions or unrelated entry edits; not all semantic or behavioral correctness follows from that. The over-update case remains a candidate, with causal evidence explicitly missing.

## Ready for Role 5

Use RESULTS.md for reported numbers, SUMMARY.md for the narrative, and CASES.md for the actual call/error sequence and evidence levels. `metrics.png` and `tradeoffs.png` can be reused in slides. Preserve denominators, the shared-Early qualification and the distinction between update cost and total inference cost.

## Remaining evidence requests

1. Team confirmation that this is the intended final run despite the older protocol wording and dirty-source flag; update the protocol to describe experience-memory updates, shared Early and three repeats.
2. If a causally confirmed over-update example is required, obtain an existing frozen-memory counterfactual or coordinate a targeted follow-up with Role 2. No extra paid run was launched by this analysis.
3. Role 3 should confirm how Tool-level additions visible to tasks 24/117 satisfy the coverage requirement: no selected task requires a deleted tool, and new tools are not required tools in those tasks. Do not claim pure Tool-change or representative benchmark coverage.
