# Setup and execution

This guide covers the API-based group workflow on Windows and macOS. Commands start from the repository root unless stated otherwise. Python 3.12 was used for the Windows smoke checks; it is not a course requirement. The currently pinned dependencies require Python 3.11 or newer. Check the interpreter version before installing.

## 1. Environment

Windows PowerShell:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If your Windows installation exposes `py` instead of `python`, use `py --version` and `py -m venv .venv`. Once the environment is active, use `python` for the remaining commands.

macOS:

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
```

Skip environment creation if `.venv` already exists, but activate it in each terminal. If the selected interpreter is older than 3.11, choose a newer installed interpreter. Python 3.11+ is the dependency floor, not a guarantee that every external tool supports your machine.

Common commands after activation:

```text
python -m pip install -r requirements-api.txt
npm install --prefix .runtime @1mcp/agent@0.39.1
python -m pip check
```

Use Node.js 24 for the tested setup, including the Windows archived-import hook. Older Node versions have not been verified for this pipeline. Install only `requirements-api.txt` for our workflow. The upstream `requirements.txt` describes a much larger environment, including local-model/GPU packages, and is retained as a reference. Windows-only packages in our list have platform markers.

## 2. Local model configuration

Copy `.env.example` to `.env` once and fill in:

```ini
BIGMODEL_API_KEY=your-key
BIGMODEL_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
BIGMODEL_MODEL=glm-4-flash-250414
BIGMODEL_JUDGE_MODEL=
BENCH_JUDGE_RUNS=5
PYTHONUTF8=1
```

The Python entry points load `.env` automatically. Existing environment variables override file values. Quotes around these values are optional. A blank judge model uses the agent model. Keep agent and judge settings fixed across compared strategies. `.env` is ignored by Git.

The common experiment entry point takes models, temperatures, and limits from `config/experiment.json`; `.env` supplies credentials and the provider endpoint. The model environment variables above remain available to standalone diagnostics. Keep `BENCH_JUDGE_RUNS=5` for the reused judge formatter.

The base URL above is BigModel's ordinary OpenAI-compatible API endpoint. See the [official interface documentation](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction).

Optional API checks:

```text
python scripts/check_model.py
python scripts/check_model.py --tool-call
```

Each command sends one model request. The first checks text output; the second checks function calling. These standalone helpers use `.env` and do not exercise the experiment's shared request gate; prefer the common `check` command below when checking experiment settings.

## 3. Tasks and tool bundles

| Path | Purpose |
| --- | --- |
| `src/custom/data/test_cases/test_cases.json` | Full task records |
| `src/custom/data/test_cases/chosen_idx.json` | 201 candidate IDs; confirm the final subset |
| `anotation_path/` | Input files and task workspace |
| `servers/1mcp_config/{original,iter3,iter5}/mcp.json` | Upstream server templates |
| `config/local/` | Generated machine-specific configurations |
| `config/experiment.json` | Intended experiment protocol |

Download `original_servers.zip`, `iter3_servers.zip`, and `iter5_servers.zip` from [the upstream bundles](https://huggingface.co/datasets/anonymous2233/evol-servers/tree/main) into `servers/downloads/`. Each archive is about 1 GB and contains many small files. Then run:

```text
python scripts/extract_servers.py original
python scripts/extract_servers.py iter3
python scripts/extract_servers.py iter5
python scripts/prepare_local_config.py
```

Extraction creates `servers/original_servers/`, `servers/iter3_servers/`, and `servers/iter5_servers/`. `original` is Early, `iter3` is Middle, and `iter5` is Late. Downloads and generated configs are local-only files. Every teammate must generate configs for their own machine.

The generator resolves Windows `.cmd`/`.exe` launchers and macOS `bin` launchers, replaces template workspace paths, and resolves available npm binaries from each frozen archive. The formal runtime rejects any selected backend still using a downloading launcher such as npx or uvx; inspect its local configuration before running. Other tools may require additional browser, database, network, or OS dependencies. Do not regenerate local configs while an experiment is running: they are fingerprinted inputs.

## 4. Verify MCP before running a task

The common check starts and closes its own private servers. It discovers the selected tools across all three versions, then checks model tool calling, tool feedback, and scoring JSON (three model requests if all succeed):

```text
python -m custom.experiment check --config config/experiment.json
```

Use `--skip-models` for tool-only checking. To narrow a diagnostic check, add `--server <selected-server-name>` and/or `--stage original`. Reports go under ignored `.runtime/experiments/checks/`; they never become benchmark trajectories. Live `run` also owns its servers and performs scoring automatically, so no manual server or separate scoring command is required.

For optional manual smoke diagnostics, with the virtual environment active, keep terminal 1 running:

```text
python scripts/start_mcp.py --stage smoke
```

In terminal 2, also at the repository root with the environment active:

```text
python scripts/probe_mcp.py --url http://127.0.0.1:3050/mcp
```

For other stages, use `--stage smoke-iter3 --port 3053` or `--stage smoke-iter5 --port 3055`. Match the probe URL to the port. Run stages sequentially when sharing the same config directory. Stop the server with Ctrl+C. The launcher passes absolute paths; relative 1mcp config paths caused an empty server configuration locally.

The smoke configurations contain only sequential-thinking. Tool discovery does not call a model and does not validate a complete benchmark task. A real macOS runtime check is still required.

## 5. Freeze and validate the experiment

The common entry point runs from the repository root without changing directories or setting PYTHONPATH. The current seed is 6203 and the five pilot IDs are frozen in `config/subsets/selected_tasks.json`. The source remains the untouched official task dataset; reference answers and trajectories are excluded from Agent input.

```text
python -m custom.experiment validate --config config/experiment.json --offline
```

Use `select --config config/experiment.json` only when the selection file does not exist. To intentionally adjust the subset before a new experiment, edit this same ID list; set `task_count` to the list length; validation rejects count mismatches, duplicate, unknown, and noncandidate IDs. Selection never replaces failed tasks.

`config/experiment.json` sets models, temperatures, token limits, and timeouts. The current pilot uses GLM-4-Flash-250414 for Agent and judge, omitting the newer thinking-mode option; output budgets are 8192 tokens. Settings are identical across strategies. GLM-4.7-Flash was tried earlier but encountered persistent provider overload; its results belong to separate experiments.

The baseline strategies are `no_update` and `full_rewrite`. The current pilot uses 5 tasks, 3 versions, 1 Agent repeat, and 5 judge slots per trajectory: 30 trajectories and 150 planned slots. Set `task_count` and `agent_repeats` together with the frozen ID list for another protocol. IDs 9, 24, 117, 273, and 403 were selected for local dependencies, not as a representative random sample. The earlier 10-task, three-repeat design would produce 180 trajectories / 900 slots with two strategies.

`request_policy` shares one admission gate per model across Agent, judge, and spawn workers using the same endpoint, credential, and policy in this checkout. It waits at least 10 seconds after each response. HTTP 429 triggers a 60/120/240/300-second cooldown; subsequent successes retain half that delay until five clean responses lower the cooldown level. Server `Retry-After` is honored. A crashed owner leaves a conservative request lease. Waits and dispatches are logged; failed requests are never replayed, and judge slots remain exactly five. Gate state stays under ignored `.runtime/experiments/rate-limits/`. These timing values do not guarantee provider availability.

The effective request cap is the upstream Early tool-count budget plus its historical extra request, frozen per task across stages. Completion and exhaustion are recorded separately.

All tools belonging to each task's required servers form the knowledge scope. One Early catalog is frozen for all strategies/repeats; each episode receives a copy. Current semantic descriptions and schemas are separate from changing callable routes. The Agent prompt, stop feedback, visible response truncation, and upstream judge rubric remain in use; complete raw responses are additionally saved.

The experiment uses actual frozen-stage `tools/list` catalogs (`runtime.catalog_source: live`) as the common environment. Each strategy decides whether to update its knowledge. Evolution overlays remain an explicit alternative requiring a verified mapping; they are not applied in this experiment because the available records do not align cleanly with the archived tool-addition order. No tool migration answer is supplied. The judge represents calls and catalog entries with server/tool identities so API aliases cannot confuse duplicate names.

## 6. Offline checks, execution, and recovery

Development runs use only fake models and tools:

```text
python -m custom.experiment run --config config/experiment.json --offline
python -m custom.experiment run --config config/experiment.json --offline --parallel --workers 2
python -m custom.experiment run --config config/experiment.json --offline --resume <offline-experiment-directory>
python -m custom.experiment summarize --experiment <experiment-directory>
python -m unittest discover -s tests -v
```

Offline output is under `.runtime/experiments/offline-results/`, separate from model-backed results. The launcher prints the exact experiment directory. Serial execution is the default; optional spawn workers execute ordered strategy/repeat episodes. Live model calls also share the request gate, so parallel workers do not bypass its serialization/cooldown. Resume preserves the original mode and worker count.

For live execution after setup and checking:

```text
python -m custom.experiment validate --config config/experiment.json
python -m custom.experiment run --config config/experiment.json
```

Both task execution and scoring run through this entry point. `validate` sends no model requests but requires local configs and credentials in live mode. If selecting `catalog_source: evolution_overlay`, supply ordered evolution files and verify their correspondence before setting `runtime.metadata_verified`; live catalogs do not pretend this mapping has been verified. Configure private MCP launchers in `config/local/`; downloading launchers are rejected until replaced by verified frozen entry points.

Filesystem, task-manager, sequential-thinking, and time backends have explicit built-in isolation. Other backends require a source review and a recorded policy in `runtime.policies`. A reviewed workspace policy may declare `env_paths`, mapping state environment variables to paths relative to the private runtime. Read-only external services may use a reviewed stateless policy. Mutable remote services need a concrete isolation/reset implementation, not merely a reviewed flag. Unsupported backends produce recorded execution failures; no task is silently replaced.

Formal output is shallow:

```text
results/<UTC-microseconds>_<sanitized-git-user-name>/
    experiment.json
    records.json
```

The manifest records public settings, source/code fingerprints, selected IDs, and planned identities. Records contain complete traces, knowledge snapshots/updates, model attempt statuses/available usage, exactly five judge slots per trajectory, failures, timings, and aggregates. Credentials and temporary runtime state are excluded from formal output.

Results are not included in the current code push. Once execution finishes, upload only the selected complete experiment directory in a separate commit; retain its manifest and records together. The experiment ID combines a UTC timestamp with microseconds and the Git user name, so different runs use separate directories. Avoid editing or committing the same run's `records.json` from two machines. Stage explicit code/doc paths for code commits and explicit experiment directories for result commits. `.env`, local configs, logs, downloads, and runtime state remain ignored; do not force-add them.

Execution failures skip scoring and do not stop unrelated runs. Agent mistakes in an operational environment remain scored. Judge failures consume slots without top-up; means use valid scores and include explicit coverage counts. ECS uses valid matched task/repeat records across the three stages and the upstream population standard deviation.

Checkpoints are saved before requests and after completions. Completed/failed attempts are retained; an interrupted in-flight request becomes outcome unknown and is never automatically replayed. Remaining judge slots can resume from a completed Agent trajectory without rerunning tools. Code/config/data changes require a new experiment; detected changes during execution invalidate its scores. Restart creates fresh fixture copies and owned services while restoring the committed knowledge snapshot.

Transport timeouts also have unknown request outcomes, with recorded causal errors. MCP parameter-validation errors remain normal Agent feedback. The offline RPC mock test still needs Windows localhost socket-pair access for asyncio; the restricted execution sandbox may need that permission even though no model/MCP endpoint is contacted.

The old `run_agent.ps1` delegates to this entry point; `prepare_baseline_smoke.py` now delegates to validation. Legacy per-task outputs remain readable through existing analysis utilities but are not the formal experiment path.

## 7. Strategy integration and change record

The adapter interface is `update(knowledge, old_tools, new_tools, context) -> UpdateResult`. Knowledge is keyed by `server::tool` and contains description/schema information; transport routes are excluded. Role 1 registers Selective Patch with `custom.experiment.adapters.register`, and lists its importable module in `strategy_plugins`. Inputs are defensive copies; results include knowledge, changed entries, explanation, and elapsed time. Unavailable strategies fail before model calls.

Keep [fixed-plan.md](fixed-plan.md) as the change reference: record files, before/after behavior, necessity, benchmark effect, and verification for each logical change. Code and documentation default to English; additional documents, commits, pushes, PRs, and model-backed checks require explicit instructions.

Windows spawn, interruption, worker failure, and state isolation have offline acceptance checks. macOS launcher resolution is covered, but a real macOS runtime check remains pending.
