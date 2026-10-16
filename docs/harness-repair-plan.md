# Execution-only harness repair

Base: `bd660f5`. Keep the benchmark tasks, tools, fixtures, strategies, selection, model settings, request caps, repeat counts, concurrency, and Judge implementation unchanged.

## Included

- End on a nonempty final response without tool calls; execute structured tool calls even when accompanying text contains a finish marker. Keep empty, refused, output-length, request-budget, and execution-failure exits distinct. Do not inject synthetic user demands or make another model request.
- Replace the fixed 500-character Python-object preview with MCP JSON content/structured data/error flags. Retain raw results. Disclose truncation beyond the existing 32,000-character Agent-visible budget.
- Record provider/runtime failures as execution failures, and keep operational Agent mistakes as tool feedback. Reject declared tool calls without structured calls.
- Label manifests and trajectories `execution_repair_v1`; keep old results immutable and retain source-fingerprint resume protection.

## Excluded

Judge input restructuring, rubric/score changes, local outcome collection, task-success validators, ten-task configuration, experimental result uploads, and the existing Windows first-use lock initialization race are outside this merge. Keep experimental work on `harness-repair`. No network/model experiment or push is part of this merge.

## Acceptance

Use offline Agent/tool responses and the shared serial/spawn suite. Verify termination, finish-marker/tool precedence, long/error results, refusal/length/budget distinction, transport classification, protocol persistence, and immutable legacy Judge code. Compare the staged diff to this scope before committing. The previously observed first-use Windows lock race remains a separately recorded limitation; do not hide or repair it in this patch.

Acceptance on 2026-10-16: all 75 offline tests passed in 461.501 seconds, including serial/spawn equivalence, recovery, quota/resource exclusion, execution errors, tool-result transport, and protocol metadata. All six archived task-24 traces ended after four model replies and three tool calls in an offline replay. No model or real tool call was made. The legacy Judge implementation, prompt, model configuration, and five-task selection match `bd660f5`; archived experimental results are unchanged. `git diff --check` passed and the source fingerprint stayed fixed during acceptance.
