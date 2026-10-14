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

Each command sends one model request and may incur API cost. The first checks text output; the second checks function calling. They have not been run with a real key in our setup work.

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
node .runtime/node_modules/@1mcp/agent/build/index.js serve --host 127.0.0.1 --port 3050 --config config/local/smoke.json --config-dir config/local
```

In terminal 2, also at the repository root with the environment active:

```text
python scripts/probe_mcp.py --url http://127.0.0.1:3050/mcp
```

For other stages, replace `smoke.json` with `smoke-iter3.json` and port `3053`, or `smoke-iter5.json` and port `3055`. Match the probe URL to the port. Run stages sequentially when sharing the same config directory. Stop the server with Ctrl+C.

The smoke configurations contain only sequential-thinking. Windows checks discovered 1 tool in Early, 2 in Middle, and 3 in Late, and a real Early tool call succeeded. These checks do not call a model and do not validate a complete benchmark task. macOS has not been tested on a real Mac yet.

## 5. Run one baseline task

Create `src/custom/data/test_cases/dev-subset.json` by selecting records from `test_cases.json`, retaining their IDs and server/tool metadata. Create `dev-selection.json` with the matching IDs for scoring:

```json
{"samples": [{"idx": 42}]}
```

The ID above is a format example; choose a task whose required servers have been verified. Keep only those servers in `config/local/original.json`. Stop the smoke service and restart terminal 1 using `--config config/local/original.json`.

In terminal 2:

```text
cd src
python -m custom.real_mcp.tool_level_test --step 3 --test_case_file custom/data/test_cases/dev-subset.json --output_path custom/data/local_output --mcp_server_url http://127.0.0.1:3050/mcp
```

The runner reads the model from `.env`; this command calls the model. Middle/Late use `--step 4` plus `--mutation_path` pointing to verified evolution metadata. Task IDs, metadata, and the running server stage must match. Do not infer the mutation path from the stage name alone.

## 6. Score and locate results

For an Early run using the output path above, answers and trajectories are written to:

```text
src/custom/data/local_output/glm-4-flash-250414/ANSWER/<task-id>.json
```

From `src/`, with the matching tool server still running:

```text
python -m custom.analysis.answer.evaluation --answer_path custom/data/local_output/glm-4-flash-250414/ANSWER --task_selection custom/data/test_cases/dev-selection.json --num_runs 5 --max-workers 1 --mcp_server_url http://127.0.0.1:3050/mcp
```

This calls the judge model. The scorer derives its output directory by replacing `ANSWER` with `EVAL`:

```text
src/custom/data/local_output/glm-4-flash-250414/EVAL/<task-id>.json
```

Each file contains the saved task/trajectory plus `eval_result.runs` (five judge attempts), `eval_result.aggregate` (mean scores and success/attempt counts), and the scoring policy. Attempts that fail are recorded without extra top-up. The API-mode clients do not automatically retry requests. Resume reuses completed five-attempt files.

The upstream Middle/Late runner currently ignores `--output_path` for answers and writes under the supplied mutation directory:

```text
<mutation-path>/ANSWER-glm-4-flash-250414/<task-id>.json
<mutation-path>/EVAL-glm-4-flash-250414/<task-id>.json
```

The second directory appears after scoring the first. Changing the model changes its directory name. Use separate output locations for independent experiments; strategy/stage/repeat isolation has not been implemented yet. No real model-backed task or score files have been produced in the current setup.

For ECS, supply three matching stage evaluation directories to `custom/analysis/answer/evolutionary_volatility.py`. Cross-repeat aggregation and plotting remain to be integrated.

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
