# Pipeline protocol and change record

Fork: [Octobrist/MCPEvol-Bench](https://github.com/Octobrist/MCPEvol-Bench), starting at `888c779a0fe735f612ca62bdd1fdd7c9e6bf8701`. Group repository: [Eliasxswl/PE6203-project](https://github.com/Eliasxswl/PE6203-project).

The runnable pipeline and the two baselines are implemented. Role 1 still supplies Selective Patch. Completed model-backed pilots are archived under `results/`, including provider-failure runs. Code and result publication remain separate. See [setup.md](setup.md) for installation and execution commands.

## Current pilot

- The authority is `config/experiment.json`, with one ID list in `config/subsets/selected_tasks.json`.
- Selected IDs: 9, 24, 117, 273, 403. These were screened for local dependencies, not sampled as a representative benchmark subset. Original task content, tool implementations, templates, fixtures, prompts, and rubric remain unchanged.
- Strategies: `no_update`, `full_rewrite`. Versions: `original` (Early), `iter3` (Middle), `iter5` (Late). One Agent repeat and five judge slots per trajectory give **30 trajectories / 150 planned slots**.
- Task count and Agent repeats are configurable. The earlier two-baseline, 10-task, three-repeat design gives 180 trajectories / 900 slots; this is not the active pilot. Adding Selective Patch requires registration and a separately frozen experiment.
- Agent and judge currently use `glm-4-flash-250414`, with the thinking-mode option omitted. Agent temperature is 0.2, judge temperature is 0, and both output budgets are 8192 tokens. GLM-4.7-Flash was tried in separate pilots and encountered persistent provider overload.
- All strategies start from independent copies of the same frozen Early catalog. Knowledge evolves in version order. Each task gets fresh fixtures, backend state, services, and Agent conversation.
- The request cap preserves the upstream Early effective budget, `max(10, 2 * required Early tool count) + 1`, across versions. Operational mistakes and budget exhaustion remain scored behavior.

Completed-pilot scores are preliminary: an audit of task 117 found high TF scores on trajectories missing required splitting/archive-search steps. This exposes judge-validity limitations; repeated ratings do not remove systematic grading bias. Raw results and the upstream rubric are preserved.

## Entry points and member interfaces

Use `python -m custom.experiment` from the repository root. Its commands are `select`, `validate`, `check`, `run`, and `summarize`. `run` owns task execution, private server lifetimes, and scoring; no separate server/scoring runner is required. Legacy wrappers delegate to it. `check` is independent diagnostic evidence, not a strategy or benchmark trajectory.

Role 1 registers `update(knowledge, old_tools, new_tools, context) -> UpdateResult` through `custom.experiment.adapters.register` and lists its module in `strategy_plugins`. Knowledge is keyed by `server::tool`; descriptions and schemas are separate from transport routes. Inputs are defensive copies. Updates record changed entries, explanation, and elapsed time. Missing strategies fail before model calls.

Role 3 edits the single frozen ID list before an experiment and sets matching `task_count`. Selection validates distinct IDs and membership in the 201 upstream candidates. The same list is used for every strategy/version; failures never trigger replacement tasks. Reference answers and trajectories are excluded from Agent input.

Roles 4 and 5 consume `results/<UTC-microseconds>_<git-user-name>/{experiment.json,records.json}`. The manifest preserves settings, selected IDs, source/code fingerprints, revision, and dirty-source status at launch. Records contain trajectories, tool/model attempts, knowledge snapshots, fixed judge slots, timings, errors, and aggregates. Later Git commits do not rewrite launch provenance.

## Execution, overload, and recovery

Serial remains the default. Optional spawn workers now execute independent tasks within a version and queue separate scoring jobs in the same bounded pool. A stage barrier precedes each ordered knowledge update. Agent turns and tool calls remain sequential within each private trajectory. One parent writer durably checkpoints events; crash recovery affects only the failed trajectory.

`request_policy` shares admission per endpoint/account group/model. The current GLM-4-Flash-250414 profile allows two in-flight requests, including long-context requests, and 0.2 seconds between dispatches, with no post-success sleep. HTTP 429 reduces capacity and adds shared exponential cooldown with jitter and Retry-After. Success gradually restores capacity. Balance/quota exhaustion blocks subsequent dispatch for the credential. Gates never retry or top up judge slots. The current profile assigns tasks stably across two account keys for both Agent and judge, with up to two requests per account; use `--parallel --workers 4` for four workers. Separate Agent/judge credentials and endpoints remain supported; same-account keys must share a quota group. Queue time and API time are distinct events. This changes scheduling and timing, not tasks, prompts, tool knowledge, or score rubrics. Private state and declared resource locks protect task concurrency; mutable external services still require a concrete reset/namespace implementation.

Execution failures (startup, provider, transport, or worker failures) are excluded with causes, traces, and coverage counts. Agent mistakes in an operational environment remain scored. A timeout may have an unknown outcome and is never replayed. Judge failures consume their slots; means use valid scores, with missing coverage explicit. ECS uses matched valid task/repeat records across all stages and the upstream population standard deviation. Paired strategy comparisons use matched identities.

Resume preserves completed, failed, and ambiguous attempts and continues unstarted work. Changed code, config, local server configs, selection, or inputs require a new experiment. Source drift during execution invalidates scores. Keep those files unchanged while a run is active.

## Environment boundary

The active experiment uses native frozen-stage `tools/list` catalogs. Public mutation records do not uniquely match archived additions: `parallel-thinking` is present in iter3 without a matching tracked addition, while `duplicate_diagram` is recorded earlier than its observed appearance in iter5. Unverified overlays are not asserted to be active. The optional overlay mode still requires an explicit verified mapping. This is a comparison on the supplied snapshots, not an exact replication of every paper overlay.

The selected local backends have isolation policies. Task and graph state is redirected into private workspaces; child services do not inherit model credentials. Frozen npm binaries are resolved within their own stages; selected downloading launchers are rejected. The Windows import hook normalizes absolute Node module paths without editing archive contents. Unsupported browser, external mutable services, and unbundled Python backends remain outside this local pilot. Native Windows checks have run; a real macOS run remains pending.

The [paper, Appendix D.3](https://arxiv.org/html/2607.14642v1#A4.SS3) reports CentOS 7.9, Python 3.12.12, Node 24.13.0 and npm 11.6.2. Those details do not require the course project to use that exact environment and do not certify current public endpoints.

## Implementation record

| Files / scope | Change and purpose | Verification |
| --- | --- | --- |
| `custom/__init__.py`, CLI, selection, config | One root entry point; configurable task/repeat counts; one validated ID list; no copied task dataset or reference leakage. | Selection, 30/150 pilot and 180/900 larger-plan checks, CLI validation. |
| `adapters.py`, `core.py`, Agent | Independent Early knowledge, ordered updates, semantic/route separation, stable aliases, accurate request caps, complete raw traces alongside upstream visible truncation. | Copy isolation, Role 1 contract fixture, rename/overlay handling, alias identity, stop/budget boundaries. |
| `runtime.py`, local-config preparation, Windows loader | Fresh verified fixtures and owned processes; private backend state; frozen stage-specific launchers; credential filtering and import-path compatibility. | Fixture bytes, within-task persistence, reset, launcher selection, Windows process ownership and archived imports. |
| `results.py`, `parallel.py`, core | Atomic single-writer checkpoints; task-level spawn pool, separate scoring jobs, version barriers, trajectory-local crash recovery. | One-episode worker utilization, parent/worker crash recovery, serial/spawn equivalence, exact slot counts and no replay. |
| `rate_limit.py`, `isolation.py`, provider settings | Short-lock account/model admission, conservative long-context cap, adaptive cooldown, declared resource ownership, independent credentials and stable account pools. | Spawn concurrency caps, named-resource exclusion, no success delay, quota blocking, recovery/Retry-After, exact calls, role credentials and account assignment. |
| README, setup, environment example, tests | Current model/profile and startup commands; explicit diagnostic/formal separation; code and result publication kept separate. | Offline tests, command/path/link checks, live launch fingerprints, staged-file review. |

Offline acceptance on 2026-10-15 passed all 65 tests after the concurrency changes. Coverage includes one-episode task parallelism, serial/parallel score equivalence, durable worker/parent crash recovery, exact judge slots, long-context subcaps, cross-process admission and named-resource exclusion, separate judge credentials, and stable account-pool assignment. Live configuration validation and whitespace checks passed. Two concurrent tiny GLM-4-Flash-250414 calls succeeded with the updated key. Two real local filesystem MCP runtimes used distinct ports and private directories, wrote the same filename independently, and left official fixtures unchanged. A separate GLM-4.7-Flash probe still returned provider error 1305. A subsequent diagnostic overlapped two successful GLM-4-Flash-250414 requests with 21,026 input tokens each; the pilot long-context cap was raised from 1 to the account-reported cap of 2. The generic console 8K/1% note names GLM-4-Flash and does not establish its applicability or rounding for the 250414 variant. Four-worker follow-up checks passed: four overlapping free-model requests (21,024 input tokens each, two per account), four independent live filesystem runtimes, and the common offline pipeline with four Agent worker PIDs and 30/150 completions. The 19 admission tests also passed after removing their dependence on the live provider profile. These are diagnostics, not new formal experiment results. Native Windows was tested; real macOS/Linux execution and unreviewed external backends remain unverified.

Validation logs are local diagnostics, not benchmark results. Startup and model checks do not replace per-trajectory execution evidence. Results are uploaded separately after execution finishes; credentials, runtime logs/state, local configs, downloads, and extracted bundles stay ignored. Stage explicit paths to avoid mixing results with code. Do not create additional documents, commits, pushes, PRs, or model-backed checks without user authorization.
