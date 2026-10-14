# Fixed Plan: Minimal Upstream Integration

Reference: `Octobrist/MCPEvol-Bench` at `888c779a0fe735f612ca62bdd1fdd7c9e6bf8701` -> `Eliasxswl/PE6203-project`. This plan supersedes the handoff. The common pipeline, baseline, No Update, and Full Rewrite are implemented; Role 1's Selective Patch and live environment verification remain dependencies. No model-backed experiment has been started by this implementation.

## 1. Change policy

- Treat upstream semantics as authoritative. Reuse the Agent, official tools, tasks, fixtures, prompts, and rubric; prefer small extensions over a harness rewrite.
- Change behavior only for a demonstrated defect, required compatibility, or the agreed protocol. Unusual behavior alone is not evidence of a bug.
- Code and documentation default to English. Additional documents, commits, pushes, PRs, and model-backed calls require explicit authorization; development uses offline mocks.
- Record every logical change here, including support code/config/tests/docs: **status; files; before -> after; necessity; benchmark effect; evidence and validation**. Group related files. Distinguish confirmed defects from observations and proposed choices; Git diffs alone are insufficient.

## 2. Fixed experiment protocol

- Freeze 10 distinct IDs from the 201 candidates with a recorded seed and deterministic ordering in `config/subsets/selected_tasks.json`: `{"samples": [{"idx": ...}]}`. Reject duplicates, unknown IDs, and invalid membership; never redraw failed tasks.
- Read untouched `src/custom/data/test_cases/test_cases.json`; exclude reference answers/trajectories/evaluations from Agent input. Preserve `anotation_path/` and official tools; copy fixtures into private workspaces.
- Run the same tasks in `original` (Early), `iter3` (Middle), and `iter5` (Late); verify snapshot/metadata correspondence.
- Current authorized experiment: `no_update` and `full_rewrite`, 10 tasks across 3 versions with 3 repeats and 5 judge slots: **180 trajectories / 900 planned slots**. Connectivity checking is a separate command and does not enter formal results.
- Later, separately authorized: **270 trajectories / 1,350 slots** across three strategies. Identical Early knowledge; `no_update` retains it, `full_rewrite` rebuilds it at transitions, Role 1's `selective_patch` updates affected entries.
- Fix and record models, prompts, temperatures, token/request limits, stop rules, judge policy, and execution mode. Current model: `glm-4.7-flash`; blank judge model uses it. Explicit thinking: Agent enabled, judge disabled; Agent output budget 8192. Temperatures: Agent 0.2, judge 0.

## 3. Existing fork changes: observed baseline

Observed in the diff against upstream; purposes are inferred from code. Listed tests already exist, but were not rerun for this documentation edit. No formal experiment is certified here.

| Scope / files | Before -> after; necessity and effect | Evidence / validation |
| --- | --- | --- |
| `model_config.py`, `.env.example`, Agent, `openai_llm.py`, runner/judge | Embedded settings -> private shared configuration; BigModel/API compatibility (`max_tokens`, deferred local-model imports). Task content unchanged. | Source diff; authorized provider check pending. |
| `requirements-api.txt`, `.gitignore`, setup/diagnostic scripts and launch wrappers | Full environment -> pinned API dependencies, portable local configs and bundled launchers; team setup and reproducibility. Upstream templates preserved. | `test_local_config.py`, `test_platform_setup.py`; real macOS check pending. |
| `mcp_utils.py`, Agent, runner | Assumed names -> stable source identity plus `benchmark_remote_name`; current 1mcp compatibility, without semantic migration. Unused `pty` import removed for Windows. | `test_mcp_routing.py`. |
| Agent, `openai_llm.py`, `evaluation.py` | Retries/top-up -> no automatic retries, fixed 5 judge attempts; protocol change. Added score validation and replaced unavailable parser import. | Source diff; `test_fixed_judge_attempts.py`. |
| `result_paths.py`, runner/judge, smoke script/subsets | Model/mutation output paths -> stage/run paths, task-9 isolation, usage/timing, explicit judge selection, completed-file skipping; development support. General reset/resume pending. | `test_result_paths.py`, `test_fixed_judge_attempts.py`. |
| `README.md`, `docs/setup.md`, `config/experiment.json`, this plan | Upstream instructions -> group setup/protocol. Replace `handoff.md` and update links; no runtime change. | Source comparison and link checks. |

## 4. Decisions for remaining implementation

| Decision | Reason / required boundary | Acceptance evidence |
| --- | --- | --- |
| Preserve visible truncation, prompts, and within-task feedback; save complete raw traces separately. | About 500-character truncation is explicit upstream behavior, not a confirmed bug. Do not expand Agent/judge inputs silently. | Complete saved response; unchanged visible response. |
| Correct round-cap/status inconsistency; declare effective budget. | Offline upstream check: cap 2 allows 3 calls; normal completion at cap 3 still sets `exceeded`. Record any budget change. Tool-count budgets may remain if independent of strategy knowledge. | Boundary checks; completion distinct from exhaustion. |
| Apply the frozen list to every stage and judge. | Upstream filtering is a different evaluation design. Our paired comparison needs unaffected controls; no secondary filtering or reused Early scores. | Same 10 planned IDs; failures explicitly recorded. |
| Add a knowledge adapter before execution. | Evolution-based replacement must not override strategy knowledge. Separate semantics from routing; no automatic migration for `no_update`. | Independent copies, ordered transitions, no strategy substitution/leakage. |
| Restore state before each trajectory. | Fresh upstream Agent conversations do not reset persisted task-manager files or other backends. Keep side effects within a trajectory. | Task/repeat isolation and verified reset after interruption. |
| Add failure handling and durable checkpoints. | Isolate local failures; retain completed work and avoid replaying ambiguous requests. | Inject task/judge/worker/parent failures; verify clean recovery. |

## 5. Failure, scoring, and recovery rules

- **Execution failure:** provider/service unavailable, startup failure, or worker crash. Record phase/type, trace, timing, and exclusion reason; skip without judging, continue unrelated work, and do not retry terminal failures on restart.
- **Agent performance failure:** obsolete calls, bad parameters, unsuccessful planning, or budget exhaustion in an operational environment. Preserve and score it: this measures adaptation, not infrastructure availability.
- A transport timeout is an execution failure with an unknown request outcome; record its cause chain and never replay it. A received MCP invalid-parameter error remains Agent feedback, with the original protocol error saved.
- Judge failures consume slots without top-up. Means use valid scores only, never zeros for missing results. Report planned/valid/failed/interrupted/excluded counts; use matched identities for paired comparisons and matched valid stages for upstream ECS.
- Atomically checkpoint before dispatch and after each model attempt, trajectory, and knowledge transition, with one writer. Resume preserves completed attempts/knowledge and continues unstarted work. Undocumented outcomes of in-flight requests become **outcome unknown**, never automatic replays.
- Record user termination and observed fatal errors. Forced kill/power loss may only be identifiable as an unclean stop from unfinished records; do not invent causes. Distinguish worker loss from global shutdown.
- Restart with private workspaces/endpoints/persistence and verified file/database/external-state reset. Unverifiable reset excludes the affected run; lost shared integrity stops the experiment with a record. Clean only owned resources; `Future.cancel()`/`atexit` cannot guarantee hard-crash cleanup.
- Verify code/config/data fingerprints on resume; changed experimental inputs require a new experiment.

## 6. Minimal implementation path

1. Add `python -m custom.experiment` from repository root: `select`, `validate`, `run`, `summarize`, explicit resume. Default to serial; validate configuration/strategies before calls. Keep wrappers thin.
2. Extend upstream execution with selection, owned runtime/reset, raw traces, failures, checkpoints, and resume; complete baseline first. Separate responsibilities without unnecessary abstractions.
3. Register `update(knowledge, old_tools, new_tools, context) -> UpdateResult`; immutable inputs, common knowledge scope/non-tool context, before/after snapshots, changes, explanation, elapsed time. Role 1 supplies Selective Patch; missing strategies fail validation.
4. Optional spawn parallelism, initially 2 workers: one strategy/repeat episode, fresh knowledge, ordered Early -> Middle -> Late. Create clients inside workers; sequential model calls, explicit timeouts, incremental events to the parent writer, owned cleanup.
5. Save `results/<UTC-microseconds>_<sanitized-git-user-name>/{experiment.json,records.json}` without overwrite. Record revision/dirty-source and data fingerprints, settings, `(strategy, stage, task_id, repeat)`, statuses/traces/knowledge/timings/available usage, judge slots, aggregates. Exclude credentials; ignore transient runtime separately.
6. Offline acceptance: unchanged inputs, fairness/state isolation, serial/parallel equivalence, exact attempt limits, failure isolation, recovery without duplicate calls, credential-safe output. Exercise Windows spawn; macOS remains unverified until a real-machine check. Update this record and review before authorizing baseline execution.

## 7. Implementation change record

Status: implemented and offline acceptance passed on 2026-10-15 (Singapore). New code is under `src/custom/experiment/`; upstream data, tool implementations, prompts, and rubric are unchanged.

| Files / scope | Before -> after; necessity and benchmark effect | Validation |
| --- | --- | --- |
| `custom/__init__.py`, experiment CLI/selection, `config/experiment.json`, frozen selection | Ad hoc runners -> one root entry point and validated ten-ID authority (seed 6203). No copied task dataset or reference leakage. Public settings and inputs are fingerprinted. | Frozen/invalid selection, strategy preflight, fingerprint guards. |
| `adapters.py`, `core.py` | No persistent knowledge -> shared frozen Early catalog, independent copies and ordered updates. Scope is all tools on each task's required servers, allowing discovery without oracle migrations. Preserve upstream DESC overlays through an explicit verified mapping before strategy updates; source inspection found original descriptions still present in Remotion/tasks bundles. Routes remain separate; Role 1 has a validated JSON contract, not a substitute algorithm. | Equal starting knowledge, copy isolation, rename/overlay behavior, Role 1 fixture. |
| Agent, core | Implicit extra round -> explicit cap and accurate stop reason; common runner preserves Early effective `max(10, 2 * original tool count) + 1` across stages. Hooks checkpoint calls and preserve raw traces/visible truncation. API-safe aliases retain server/tool identities; the judge uses qualified semantic names to avoid misreading duplicate names. RPC parameter errors remain scored feedback. | Cap/finish boundaries, raw versus visible trace, semantic/RPC errors, alias identity checks. |
| `runtime.py` | Shared tool state -> verified fixture copies, private services/endpoints/state and owned cleanup. Task-manager state stays inside the private filesystem workspace so tools can interact within one trajectory. Short paths preserve long Windows PDF names. Unknown/reset-unverified backends fail; official files remain unchanged. | Fresh task state, within-task persistence/access, fixture bytes, unknown-backend rejection, Windows owned-process check. |
| `results.py`, core | Completed-file skipping -> atomic checkpoints, fixed judge slots, causal errors, truthful interruption/timeout outcomes, coverage and matched ECS. Windows sharing violations retry only the same file replacement within a bounded interval, never requests. Engine and external plugin/helper code enter resume fingerprints. | Parent/worker crash and partial-judge recovery, timeouts, no duplicate calls, single writer, redaction, population ECS, plugin changes. |
| `parallel.py` | Serial-only orchestration -> optional supervised spawn episodes, bounded concurrency, durable parent acknowledgement before dispatch, cancellation and isolated worker-crash records. No nested judge pool. | Windows spawn equivalence and worker-crash continuation/restart. |
| `.gitignore`, wrappers, README/setup, this record, tests | Ignored formal outputs and alternate smoke path -> two-file formal output, ignored offline diagnostics, thin compatibility wrappers and current instructions. Source drift invalidates scores; tests never call real models. | CLI/link checks, offline acceptance suite, unchanged upstream input diff. |

Remaining verification: selected servers' launchers/state policies and stage/metadata correspondence, Role 1 Selective Patch registration, and a real macOS runtime check. These are not silently treated as completed.

Test environment note: the restricted Windows execution environment blocked asyncio's local socket-pair initialization. The RPC mock test passed with localhost permission; no external model/MCP request was made. This does not certify real tool connectivity.

Final evidence: `python -m unittest discover -s tests -v` passed all **39 tests**, including Windows spawn, parent/worker crash recovery, unknown timeouts, intra-task state, and alias/RPC handling. `git diff --check` passed; diff against the pinned upstream is empty for `anotation_path/`, `src/custom/data/`, and `servers/1mcp_config/`. Offline CLI validation and the compatibility wrapper passed; live validation rejects the unverified metadata mapping before constructing clients. Earlier evolving-code checks remain ignored diagnostics with invalidated scores.

Common development command: `python -m custom.experiment run --config config/experiment.json --offline`. Add `--parallel --workers 2` for spawn scheduling or `--resume <experiment-directory>` to continue. Formal execution requires the remaining verification and explicit authorization; no commits, pushes, PRs, or real model experiments were performed.

## 8. Acceptance review changes

- Removed the redundant third baseline from the strategy registry and formal configuration. Separate `check` command stores catalog/model preflight evidence only under ignored runtime state. It does not fabricate benchmark trajectories.
- Confirmed the retained three-repeat protocol produces 180 identities and 900 judge slots for the two baselines; regression coverage asserts these counts and rejects the removed strategy.
- Made GLM-4.7 thinking settings explicit and preserved SDK response fields across tool turns. Judge thinking is disabled to isolate final scoring JSON; no retries or top-up were added.
- Frozen npm launchers now resolve archive binaries for their own stages, preventing npx from running one current package version in all environments. Unbundled Python services are still reported as unavailable rather than silently replaced with an arbitrary release.
- Added reviewed state policies for source-inspected local/process/read-only servers; task and graph registries are redirected to private state. Child services no longer inherit model credentials from the parent environment. Unknown or mutable external services remain unresolved.
- Catalog source is explicitly live frozen-stage discovery. The public mutation records do not uniquely match the archived addition order: `parallel-thinking` is present in iter3 but absent from the tracked additions; `duplicate_diagram` is recorded in the second file but present only in iter5. Unverified metadata overlays are therefore not asserted to be part of the live environment. This experiment is a comparison on the supplied snapshots, not an exact replication of every paper mutation overlay.
- Original dataset, official server templates, and fixtures remain unchanged. Live dependencies are not certified by offline tests alone; formal execution awaits resolution of the frozen subset's runtime limitations.

Acceptance evidence: the revised 41-test offline suite passed; the added Windows loader regression and affected fixture/reset regression also passed. All three archived mcp-tasks backends now expose five tools through the compatibility loader, without changing archive bytes. GLM-4.7-Flash passed the separate three-request tool/feedback/scoring-JSON check.

The [original paper, Appendix D.3](https://arxiv.org/html/2607.14642v1#A4.SS3) reports CentOS 7.9, Python 3.12.12, Node 24.13.0 and npm 11.6.2. Its safeguards exclude servers requiring proprietary API keys. These statements do not prove that the current public bundles and external endpoints are all operational. The observed mcp-tasks failure was a Windows absolute-import error; the loader only normalizes paths. The 12306 startup currently fails when its expected website marker is absent. Mutable external services, an unbundled Python backend and unsupported browser state remain unresolved; the frozen task list has not been replaced and formal execution has not started.
