# Pipeline protocol and change record

Fork: [Octobrist/MCPEvol-Bench](https://github.com/Octobrist/MCPEvol-Bench), starting at `888c779a0fe735f612ca62bdd1fdd7c9e6bf8701`. Group repository: [Eliasxswl/PE6203-project](https://github.com/Eliasxswl/PE6203-project).

The runnable pipeline and the two baselines are implemented. Role 1 still supplies Selective Patch. Model-backed pilots have started; their outputs remain local until a separate result upload is authorized. See [setup.md](setup.md) for installation and execution commands.

## Current pilot

- The authority is `config/experiment.json`, with one ID list in `config/subsets/selected_tasks.json`.
- Selected IDs: 9, 24, 117, 273, 403. These were screened for local dependencies, not sampled as a representative benchmark subset. Original task content, tool implementations, templates, fixtures, prompts, and rubric remain unchanged.
- Strategies: `no_update`, `full_rewrite`. Versions: `original` (Early), `iter3` (Middle), `iter5` (Late). One Agent repeat and five judge slots per trajectory give **30 trajectories / 150 planned slots**.
- Task count and Agent repeats are configurable. The earlier two-baseline, 10-task, three-repeat design gives 180 trajectories / 900 slots; this is not the active pilot. Adding Selective Patch requires registration and a separately frozen experiment.
- Agent and judge currently use `glm-4-flash-250414`, with the thinking-mode option omitted. Agent temperature is 0.2, judge temperature is 0, and both output budgets are 8192 tokens. GLM-4.7-Flash was tried in separate pilots and encountered persistent provider overload.
- All strategies start from independent copies of the same frozen Early catalog. Knowledge evolves in version order. Each task gets fresh fixtures, backend state, services, and Agent conversation.
- The request cap preserves the upstream Early effective budget, `max(10, 2 * required Early tool count) + 1`, across versions. Operational mistakes and budget exhaustion remain scored behavior.

## Entry points and member interfaces

Use `python -m custom.experiment` from the repository root. Its commands are `select`, `validate`, `check`, `run`, and `summarize`. `run` owns task execution, private server lifetimes, and scoring; no separate server/scoring runner is required. Legacy wrappers delegate to it. `check` is independent diagnostic evidence, not a strategy or benchmark trajectory.

Role 1 registers `update(knowledge, old_tools, new_tools, context) -> UpdateResult` through `custom.experiment.adapters.register` and lists its module in `strategy_plugins`. Knowledge is keyed by `server::tool`; descriptions and schemas are separate from transport routes. Inputs are defensive copies. Updates record changed entries, explanation, and elapsed time. Missing strategies fail before model calls.

Role 3 edits the single frozen ID list before an experiment and sets matching `task_count`. Selection validates distinct IDs and membership in the 201 upstream candidates. The same list is used for every strategy/version; failures never trigger replacement tasks. Reference answers and trajectories are excluded from Agent input.

Roles 4 and 5 consume `results/<UTC-microseconds>_<git-user-name>/{experiment.json,records.json}`. The manifest preserves settings, selected IDs, source/code fingerprints, revision, and dirty-source status at launch. Records contain trajectories, tool/model attempts, knowledge snapshots, fixed judge slots, timings, errors, and aggregates. Later Git commits do not rewrite launch provenance.

## Execution, overload, and recovery

Serial execution is the default. Optional spawn workers supervise independent strategy/repeat episodes and preserve version order. One parent writer durably checkpoints events. Workers own their services and can be stopped without killing unrelated processes.

`request_policy` shares one model gate across Agent, judge, and workers using the same endpoint, credential, and policy in this checkout. The current minimum response-to-next-request interval is 10 seconds. HTTP 429 adds cooldowns of 60/120/240/300 seconds; successes retain half the current cooldown until five clean responses reduce its level. Provider `Retry-After` is honored. The gate never retries a failed call or adds judge slots. It records waits/dispatches and keeps local state under ignored runtime storage. A crashed owner leaves a conservative in-flight lease. This mitigates overload; it cannot guarantee provider availability.

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
| `results.py`, `parallel.py` | Atomic single-writer checkpoints; truthful failure/unknown outcomes; conservative recovery; matched scoring; optional supervised spawn scheduling. | Parent/worker crash recovery, timeout and partial-judge recovery, serial/spawn equivalence, exact slot counts and no replay. |
| `rate_limit.py`, core, policy validation | Shared model admission and persistent cooldown across clients/workers, without network retries. | Virtual-clock spacing/cooldown/recovery, spawn ownership, cancellation, crash lease, Retry-After, exact call counts, factory integration. |
| README, setup, environment example, tests | Current model/profile and startup commands; explicit diagnostic/formal separation; code and result publication kept separate. | Offline tests, command/path/link checks, live launch fingerprints, staged-file review. |

Offline acceptance on 2026-10-15 passed all 55 tests. Root CLI help, live configuration validation without model calls, documentation links, staged whitespace checks, and running-experiment fingerprint checks passed. These checks do not certify a real macOS installation or every external backend.

Validation logs are local diagnostics, not benchmark results. Startup and model checks do not replace per-trajectory execution evidence. Results are uploaded separately after execution finishes; credentials, runtime logs/state, local configs, downloads, and extracted bundles stay ignored. Stage explicit paths to avoid mixing results with code. Do not create additional documents, commits, pushes, PRs, or model-backed checks without user authorization.
