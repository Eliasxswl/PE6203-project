# Minimal harness repair

Branch: `harness-repair`. Base: `bd660f5`. Main and archived results remain unchanged. No commit, push, live model calls, or new benchmark run is part of this change.

## Scope and rationale

Keep the benchmark tasks, fixtures, tool implementations, strategy adapters, model settings, request caps, repeat counts, five judge slots, and aggregation unchanged. Repair shared execution and grading defects, rather than build another agent framework. Apply one protocol, `minimal_repair_v1`, to every strategy and version. Its scores must not be pooled with earlier pilots.

1. **Termination:** explain final-text termination in the system instruction; end on a nonempty text response without tool calls; execute requested tools even if accompanying text contains `[FINISH]`. Record empty, refused, length-limited, and budget-exhausted exits separately. Preserve the final text without injecting synthetic user demands or making an extra model request. Runtime/provider failures remain execution failures; unsuccessful task behavior remains eligible for grading.
2. **Tool evidence:** serialize MCP text, structured content, and error status as JSON instead of Python object representations. Remove the fixed 500-character cut. Bound oversized model-visible output explicitly, preserving its error flag and disclosing truncation. Retain complete raw results. Reject a provider response that declares tool calls without structured calls, rather than treating serialized calls as a final answer. Do not retry, repair tool arguments, or infer task success.
3. **Grading:** preserve assistant statements and use complete recorded tool results where available. Keep the upstream rubric available as the legacy default; the formal runner explicitly selects a repaired profile that separates completion from efficiency, makes percentage boundaries unambiguous, treats tool instructions as evidence rather than the user's task, and defines zero-opportunity cases on the existing 1–10 scale. Empty output is not proof of failure or success. Retain strict score validation and five attempts without top-up.
4. **Outcome evidence:** capture bounded, deterministic before/after evidence for regular files in the private workspace (created, modified, deleted; hashes and readable text). Persist it before runtime cleanup and before judging, so serial, parallel, and resumed grading use the same evidence. Disclose skipped/oversized/unreadable files and directory/root observation errors; never open special files such as FIFOs, follow symlinks, or read outside the workspace. Evidence collection must not block on special files or turn observation errors into task-execution failures. This is supplementary evidence, not a universal task validator or a new metric. External state and semantic outcome validation still require domain-specific checks and human judge calibration.
5. **Provenance and documentation:** label new manifests/rows with the protocol and update the existing setup/protocol descriptions. Existing fingerprints prevent resuming an old experiment under changed source. Do not rewrite old results or other members' documents.

## File allowlist

- `src/custom/agents/SimpleOpenAIAgent.py`
- `src/custom/agents/tool_results.py` (new, serialization only)
- `src/custom/prompt/eval_error_prompt.py`
- `src/custom/experiment/core.py`
- `src/custom/experiment/evidence.py` (new, workspace evidence and protocol label)
- `src/custom/experiment/results.py`
- `tests/test_harness.py` (new, regression cases)
- `tests/test_experiment.py` (adjust affected expectations and verify integration)
- `docs/harness-repair-plan.md`, `docs/fixed-plan.md`, `docs/setup.md`

## Acceptance and review

Use offline scripted model/tool responses, temporary workspaces, and the existing serial/spawn acceptance suite. Cover task-24-style completion without repeated writes, tool calls containing a finish marker, errors and long MCP outputs, empty/length/refusal/budget exits, retained judge evidence, legacy/repaired rubric separation, artifact deletion/truncation/symlink boundaries, and persisted evidence in the shared runner. Verify no task, tool, selection, configuration, strategy, repeat, or aggregation changes. Review the final diff against this allowlist; record checks and remaining limitations here. Live judge accuracy is not established by mocked tests.

References: [agent loop](https://openai.github.io/openai-agents-python/running_agents/#the-agent-loop), [MCP tool results](https://modelcontextprotocol.io/specification/2025-06-18/server/tools), [agent evaluation design](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents).

## Completion record

Implemented within the 11-file allowlist. Self-review confirmed unchanged tasks, fixtures, tools, selection, configuration, adapters, isolation, scheduling, rate limits, and aggregation. Main remains at `bd660f5`; no commit or push was made.

Validation:

- Final acceptance on 2026-10-15: one fresh full run of **85 tests**, **84 passed and one skipped**, in 481.370 seconds. This covers serial/spawn equivalence, fault recovery, private state, quota controls, fixed judge slots, and evidence persistence. The skipped test requires real symlink creation, which this Windows host denies; deterministic link/root guards pass. Diagnostic log: `.runtime/harness-repair-final-acceptance.log` (ignored; not benchmark results).
- Acceptance reproduced and repaired two evidence-collector defects: root/directory observation errors could abort the task, and special files such as FIFOs could be opened and block. Three added regressions pass in the full run. These repairs only disclose unavailable evidence and skip non-regular files; they do not determine task success or alter scores. The source fingerprint remained unchanged during final acceptance.
- Final grading-boundary clarification is covered by the focused harness/rubric tests. The legacy rubric is byte-identical to main for all six dimension orders.
- Read-only replay of all six archived task-24 traces stops after four model replies and three tool calls, instead of eleven replies and repeated writes. No real model/tool request was made. Judge inputs rendered successfully for all 30 archived trajectories without changing results.
- `git diff --check` and the file-allowlist check pass. No implementation changes remain outside this plan.

Limits: this is not a general task-verification framework. Workspace evidence is supplementary, bounded, and excludes remote state; skipped data is explicitly identified. Model-visible tool results are capped at 32,000 characters, judge tool evidence shares a 96,000-character allowance, and local changed-file text is capped at 16,000 characters. Zero-claim Grounding and zero-call Planning Efficiency use 10 by convention, explicitly without implying task completion. Fresh live judge calibration, including false-success cases such as task 117, remains necessary. No live experiment was started.

## Structured judge input follow-up (2026-10-16)

Authorized scope: change only how the formal runner presents evidence to the Judge. Keep the current rubric, score JSON fields, model settings, five judge slots, shuffle, aggregation, Agent execution, tools, and fixtures unchanged. Do not add task-success validators, human review, reference answers, model requests, dependencies, or an alternate runner.

- Put evaluator rules in a real system message and serialize the original task, tool definitions, numbered trajectory, existing outcome evidence, and final answer in a separate JSON user message. Historical roles and tool instructions are untrusted data, not live evaluator messages. Preserve call IDs, semantic names, arguments, error flags, and existing explicit size limits. Represent a duplicate terminal answer by reference without dropping its evidence.
- Require requirement-by-requirement evidence references inside existing reasoning fields, without changing scores or the output schema. Keep the legacy prompt available unchanged.
- Label the new protocol `minimal_repair_v2`; never overwrite archived results or resume an earlier protocol. Adapt the offline client and focused/integration tests to the message list.
- Source allowlist: `src/custom/prompt/eval_error_prompt.py`, `src/custom/experiment/core.py`, `src/custom/experiment/evidence.py`, `src/custom/experiment/testing.py`, `tests/test_harness.py`, `tests/test_experiment.py`. Update this plan, `docs/fixed-plan.md`, and `docs/setup.md` in place.
- Separately authorized experiment expansion: preserve IDs 9, 24, 117, 273, 403, choose five additional dependency-screened official tasks, and freeze their IDs in `config/subsets/selected_tasks.json`. Change only `task_count` in `config/experiment.json`. Document the screening and final list here and in the existing protocol/setup descriptions. This is a convenience pilot, not a representative random sample.
- Validate message/data boundaries, evidence preservation, terminal-answer references, legacy compatibility, and shared serial/spawn execution offline. Render archived inputs without model calls. Then preflight tools and run the ten-task pilot through `python -m custom.experiment`, four optional workers, one repeat, two baselines, three versions: 60 trajectories and 300 planned ratings. Do not commit or push.

Frozen expansion: keep 9, 24, 117, 273, 403 in their existing order; append 267, 157, 278, 389, 425. This preserves the original tasks' account assignment. Added tasks exercise prioritized log-aggregation planning, time/static simulated cafe, dependency planning, Chinese planning, and project task lists. No new backend isolation policy is required: only existing private task managers, sequential thinking, time, and source-reviewed simulated cafe are used. Local fixture code/log inputs already exist. No official task or fixture is edited. The only configuration changes are the frozen selection and `task_count: 10`.

Acceptance environment: the first sandboxed attempt stalled during Windows asyncio local socket-pair creation; a focused stack dump reproduced the sandbox restriction before tool logic. Stop only those owned test processes and rerun with local socket access. No runtime compatibility patch is added. The JSON document keeps the original task first and final answer last in deterministic insertion order.

Follow-up acceptance: the final full suite covered 87 tests in 386.677 seconds: 85 passed, one host-permission symlink skip, and one error in the unchanged named-resource concurrency test. That test exposed a first-use Windows lock-file initialization race (`stream.flush()` before locking). The complete 19-test admission/resource suite passed on a separate rerun in 6.708 seconds. No concurrency source or test was changed to hide the failure. Both actual account/model quota locks and the MCP startup lock are already initialized, and this pilot declares no exclusive backend resources. Record this existing limitation for a separate repair rather than expanding this input-only patch. All structured-input tests passed; all 30 archived inputs preserved the task, answer, and both tool schemas; legacy output remained identical in six orders. Source fingerprint stayed frozen. Preflight passed all 21 server/version combinations. Proceed with the authorized 60-trajectory/300-slot experiment; do not claim live judge accuracy from these offline checks.

Experiment record: `results/20261015T200405.239100Z_Kevin` ran from 2026-10-15 20:04:05 UTC to 20:27:48 UTC (23 minutes 43.502 seconds). All 60 Agent trajectories ended normally. All 300 fixed judge slots were attempted: 273 valid and 27 invalid (26 unparseable objects, one out-of-range score). Full Rewrite / Middle / task 117 had five invalid judge returns and is excluded for `no_valid_judge_attempts`, leaving 59 scored trajectories. No top-up, score repair, rerun, model change, task validator, or human grading was performed. All 456 model API requests completed successfully; peak concurrency was four, with two per account and no overload/cooldown. All 95 prepared/started runtimes stopped; no request remained active. Source/config/data fingerprints matched at completion. The status is `completed_with_failures` because of invalid judging, not an Agent/API execution failure. Structured input delivery is verified; Judge accuracy or improvement is not established. Main remains at `bd660f5`; no commit or push was made.

## Local branch separation (2026-10-16)

The execution-only repair was accepted by all 75 offline tests in 461.501 seconds and six archived task-24 replays, then committed as `1990f3ac819cb69ebbf35b58f99b0d7f14511428` (`Fix harness execution`) and fast-forwarded into local `main`. Main retains the original Judge implementation, scoring rules, model settings, and five-task selection; it uses `execution_repair_v1`. The structured Judge, clarified rubric, bounded workspace evidence, and ten-task selection remain experimental on `harness-repair` under `minimal_repair_v2`. Their source was restored from a hash-verified local backup. Preserve the newly added protocol regression when restoring the broader tests. Experimental results remain unchanged and uncommitted; no push occurred. The README on this experimental branch matches its ten-task configuration.
