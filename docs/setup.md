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
BIGMODEL_MODEL=glm-4-flash-250414
BIGMODEL_JUDGE_MODEL=
BENCH_JUDGE_RUNS=5
PYTHONUTF8=1
```

The Python entry points load `.env` automatically. Existing environment variables override file values. Quotes around these values are optional. A blank judge model uses the agent model. Keep agent and judge settings fixed across compared strategies. `.env` is ignored by Git.

The base URL above is BigModel's ordinary OpenAI-compatible API endpoint. See the [official interface documentation](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction).

Optional API checks:

```text
python scripts/check_model.py
python scripts/check_model.py --tool-call
```

Each command sends one model request and may incur API cost. The first checks text output; the second checks function calling. Both passed with `glm-4-flash-250414` during the local pilot (159 tokens combined).

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

The smoke configurations contain only sequential-thinking. Windows checks discovered 1 tool in Early, 2 in Middle, and 3 in Late, and a real Early tool call succeeded. These checks do not call a model and do not validate a complete benchmark task. macOS has not been tested on a real Mac yet.

## 5. Run one baseline task

Task 9 is a small official task requiring filesystem search/read and task-manager planning. Its unchanged task record and selection IDs are in `config/subsets/baseline-smoke.json` and `baseline-smoke-selection.json`. This development subset does not establish coverage of the final assignment.

Prepare a fresh run at the repository root after generating local configs:

```text
python scripts/prepare_baseline_smoke.py --run-id run-1
python scripts/start_mcp.py --config config/local/baseline-run-1/mcp.json --port 3050
```

Keep that service running in terminal 1. The helper copies the official log into an isolated workspace, restricts filesystem access to that workspace, and sets a separate task-manager data file. Existing results are preserved. Use a new run ID for another independent trajectory.

Set the matching workspace in terminal 2 before running the Agent. On Windows PowerShell, from the repository root:

```powershell
$env:BENCH_WORKSPACE = (Resolve-Path results/baseline/original/run-1/workspace).Path
```

On macOS, from the repository root:

```bash
export BENCH_WORKSPACE="$PWD/results/baseline/original/run-1/workspace"
```

Then use the same command on both systems:

```text
cd src
python -m custom.real_mcp.tool_level_test --step 3 --stage original --run_id run-1 --test_case_file ../config/subsets/baseline-smoke.json --mcp_server_url http://127.0.0.1:3050/mcp
```

The model comes from `.env`. Existing answer files are skipped on resume. Use `run-2` and `run-3`, their respective prepared configs and workspaces, and fresh services for independent repeats. Resetting arbitrary benchmark servers still requires task-specific work.

Other subsets must retain official task IDs and metadata and have their required servers verified. Middle/Late use `--step 4 --stage iter3` or `iter5`, plus `--mutation_path` pointing to verified evolution metadata. The mutation path is an input only; it no longer controls the result directory. The current runner exposes selected live tool metadata and does not yet implement the three adaptation strategies.

## 6. Score and locate results

All baseline stages now use the same layout, relative to the repository root:

```text
results/baseline/original/run-1/answers/9.json
results/baseline/original/run-1/scores/9.json
results/baseline/original/run-1/workspace/
```

Replace `original` and `run-1` with the selected stage and run ID. Optional `--output_path` sets the run directory directly (relative paths resolve from the command's working directory); `answers/` and `scores/` remain sibling directories. This replaces the upstream layout that nested results under model names or mutation metadata. Legacy `ANSWER` directories can still be scored explicitly.

From `src/`, with the matching tool service running:

```text
python -m custom.analysis.answer.evaluation --answer_path ../results/baseline/original/run-1/answers --task_selection ../config/subsets/baseline-smoke-selection.json --num_runs 5 --max-workers 1 --mcp_server_url http://127.0.0.1:3050/mcp
```

A blank `BIGMODEL_JUDGE_MODEL` defaults to the Agent model. Scoring uses temperature 0 and five independent judge attempts. Each score file includes `eval_result.runs`, `eval_result.aggregate` with exact means and attempt counts, and the scoring policy. Some legacy summary fields are rounded; use aggregate means for analysis. Failed attempts are recorded without top-up, API requests do not automatically retry, and resume reuses completed five-attempt files. Agent answer files include model token usage and elapsed time; judge token/currency accounting remains pending.

The Windows development pilot produced three Agent trajectories and 15 successful judge responses for task 9. Run 1 failed due to a routing metadata bug that was then fixed. Runs 2 and 3 reached the search tool but used nonrecursive glob patterns and failed to find the nested log. Separate direct checks confirmed search with `**/*yesterday*`, log reading, and planning all work. The pilot must not be averaged into a formal three-repeat comparison because code changed between runs and tasks were not fulfilled. No additional model runs were added.

The small judge also miscounted calls in some explanations. Repetition reduces random variation but cannot remove systematic scoring errors or self-evaluation bias. Keep the judge settings and rubric identical across strategies and inspect explanations against saved trajectories. These pilot scores require that manual audit before reporting.

Local pilot outputs are under `results/baseline/original/run-{1,2,3}/`; `summary.json` records their debug status. Results and workspaces are ignored by Git by default. Publish selected sanitized experiment results explicitly when the group is ready.

For ECS, supply three matching stage score directories to `custom/analysis/answer/evolutionary_volatility.py`. Cross-repeat aggregation and plotting remain to be integrated.

## 7. Integration and current limits

- `src/custom/agents/SimpleOpenAIAgent.py`: model/tool execution loop.
- `src/custom/real_mcp/tool_level_test.py`: task loading and tool metadata.
- `src/custom/analysis/answer/evaluation.py`: judge calls and result storage.
- `src/custom/utils/model_config.py`: `.env` settings.

The planned adaptation hook updates persistent tool knowledge before the Agent executes a task. The knowledge format, three strategies, and their common interface are not implemented. Automatic three-run scheduling, clean-state reset, update/model cost accounting, and final result aggregation are also pending.

Protocol: three independent Agent runs per task/stage/strategy and five judge attempts per trajectory. That is 45 judge attempts per task/stage across three strategies, or 135 across all three stages, excluding the Agent's own model calls.

Offline checks, from the repository root:

```text
python -m unittest discover -s tests -v
```

Commit source, tests, configuration templates, and appropriate experiment outputs for reproducibility. Keep credentials, virtual environments, downloaded bundles, and generated node_modules out of Git. No additional generated documentation is maintained beyond the root README and this guide.
