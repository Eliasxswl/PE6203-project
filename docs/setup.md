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

Use a Node.js version supported by 1mcp; Node.js 24 was used locally. Install only `requirements-api.txt` for our workflow. The upstream `requirements.txt` describes a much larger environment, including local-model/GPU packages, and is retained as a reference. Windows-only packages in our list have platform markers.

## 2. Local model configuration

Copy `.env.example` to `.env` once and fill in:

```ini
BIGMODEL_API_KEY=your-key
BIGMODEL_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
BIGMODEL_MODEL=glm-4.7-flash
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

Each command sends one model request. The first checks text output; the second checks function calling. Historical execution outputs have been cleared; run these checks only when a model-backed check is authorized.

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

The generator resolves Windows `.cmd`/`.exe` launchers and macOS `bin` launchers, and replaces template workspace paths. Some remaining npx entries may download packages on first use; verify their versions before formal experiments. Some tools require additional browser, database, network, or OS dependencies.

## 4. Verify MCP before running a task

With the virtual environment active, keep terminal 1 running:

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

The common entry point runs from the repository root without changing directories or setting PYTHONPATH. The current seed is 6203 and the ten IDs are already frozen in `config/subsets/selected_tasks.json`. The source remains the untouched official task dataset; reference answers and trajectories are excluded from Agent input.

```text
python -m custom.experiment validate --config config/experiment.json --offline
```

Use `select --config config/experiment.json` only when the selection file does not exist. To intentionally adjust the subset before a new experiment, edit this same ID list; validation rejects duplicate, unknown, and noncandidate IDs. Selection never replaces failed tasks.

`config/experiment.json` fixes three stages, three Agent repeats, five judge slots, models, temperatures, token limits, and timeout policy. GLM-4.7-Flash uses explicit thinking settings: Agent enabled, judge disabled; Agent output budget is 8192 tokens. These settings are identical across the two strategies. The two baseline strategies are `no_update` and `full_rewrite`; together they plan 180 trajectories and 900 judge attempts. The effective request cap is the upstream Early tool-count budget plus the historical extra request, frozen per task across stages. Completion and exhaustion are recorded separately.

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

Offline output is under `.runtime/experiments/offline-results/`, separate from formal model-backed results. The launcher prints the exact experiment directory. Serial execution is the default; optional spawn workers execute ordered strategy/repeat episodes with one model request per worker at a time. Resume preserves the original mode and worker count.

After review and explicit authorization, omit `--offline` for live execution. First use `check --config config/experiment.json` to discover stage catalogs and test model tool calling and scoring JSON separately. If selecting `catalog_source: evolution_overlay`, supply ordered evolution files and verify their correspondence before setting `runtime.metadata_verified`; live catalogs do not pretend this mapping has been verified. Configure private MCP launchers in `config/local/`; downloading launchers are rejected until replaced by verified frozen entry points.

Filesystem, task-manager, sequential-thinking, and time backends have explicit built-in isolation. Other backends require a source review and a recorded policy in `runtime.policies`. A reviewed workspace policy may declare `env_paths`, mapping state environment variables to paths relative to the private runtime. Read-only external services may use a reviewed stateless policy. Mutable remote services need a concrete isolation/reset implementation, not merely a reviewed flag. Unsupported backends produce recorded execution failures; no task is silently replaced.

Formal output is shallow:

```text
results/<UTC-microseconds>_<sanitized-git-user-name>/
    experiment.json
    records.json
```

The manifest records public settings, source/code fingerprints, selected IDs, and planned identities. Records contain complete traces, knowledge snapshots/updates, model attempt statuses/available usage, exactly five judge slots per trajectory, failures, timings, and aggregates. Credentials and temporary runtime state are excluded from formal output.

Execution failures skip scoring and do not stop unrelated runs. Agent mistakes in an operational environment remain scored. Judge failures consume slots without top-up; means use valid scores and include explicit coverage counts. ECS uses valid matched task/repeat records across the three stages and the upstream population standard deviation.

Checkpoints are saved before requests and after completions. Completed/failed attempts are retained; an interrupted in-flight request becomes outcome unknown and is never automatically replayed. Remaining judge slots can resume from a completed Agent trajectory without rerunning tools. Code/config/data changes require a new experiment; detected changes during execution invalidate its scores. Restart creates fresh fixture copies and owned services while restoring the committed knowledge snapshot.

Transport timeouts also have unknown request outcomes, with recorded causal errors. MCP parameter-validation errors remain normal Agent feedback. The offline RPC mock test still needs Windows localhost socket-pair access for asyncio; the restricted execution sandbox may need that permission even though no model/MCP endpoint is contacted.

The old `run_agent.ps1` delegates to this entry point; `prepare_baseline_smoke.py` now delegates to validation. Legacy per-task outputs remain readable through existing analysis utilities but are not the formal experiment path.

## 7. Strategy integration and change record

The adapter interface is `update(knowledge, old_tools, new_tools, context) -> UpdateResult`. Knowledge is keyed by `server::tool` and contains description/schema information; transport routes are excluded. Role 1 registers Selective Patch with `custom.experiment.adapters.register`, and lists its importable module in `strategy_plugins`. Inputs are defensive copies; results include knowledge, changed entries, explanation, and elapsed time. Unavailable strategies fail before model calls.

Keep [fixed-plan.md](fixed-plan.md) as the change reference: record files, before/after behavior, necessity, benchmark effect, and verification for each logical change. Code and documentation default to English; additional documents, commits, pushes, PRs, and model-backed checks require explicit instructions.

Windows spawn, interruption, worker failure, and state isolation have offline acceptance checks. macOS launcher resolution is covered, but a real macOS runtime check remains pending.
